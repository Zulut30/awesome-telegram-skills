"""Trusted Bot SDK updates are the only receipt ingress, not browser claims."""
from __future__ import annotations
import asyncio
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery, WebAppInfo
from telegram_patterns import PermissionDenied
from .storage import io_call
from .store import Store


def payment_router(store: Store, *, shop_url: str, terms: str, support: str) -> Router:
    router=Router(name='shop-payments')
    @router.pre_checkout_query()
    async def precheckout(query: PreCheckoutQuery):
        try:
            if query.bot is None or query.from_user.is_bot:raise PermissionDenied()
            async with asyncio.timeout(3):
                await io_call(store.precheckout,query.bot.id,query.from_user.id,query.id,query.invoice_payload,query.currency,query.total_amount)
        except Exception:
            await query.answer(ok=False,error_message='Заказ недоступен или требует сверки. Откройте магазин или /paysupport.')
        else:await query.answer(ok=True)

    private=(F.chat.type=='private') & (F.from_user.is_bot==False) & (F.business_connection_id==None)
    @router.message(private,F.successful_payment)
    async def paid(message: Message):
        receipt=message.successful_payment
        if receipt is None or message.from_user is None or message.bot is None or message.chat.id!=message.from_user.id:raise PermissionDenied()
        try:
            result=await io_call(store.paid,message.bot.id,message.from_user.id,receipt.invoice_payload,receipt.currency,receipt.total_amount,receipt.telegram_payment_charge_id)
        except PermissionDenied:
            await message.answer('Платёж требует сверки. Обратитесь в /paysupport.',parse_mode=None);return
        # A failed notification never rolls back paid/access and never starts a refund.
        if not result['replayed']:
            await message.answer('Платёж требует сверки: /paysupport.' if result['review'] else 'Покупка доступна в магазине → «Мои покупки».',parse_mode=None)

    @router.message(private,Command('start'))
    async def start(message: Message):
        await message.answer('Каталог учебных материалов. Цена и доступ определяются сервером. Условия: /terms. Поддержка платежей: /paysupport.',parse_mode=None,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Открыть магазин',web_app=WebAppInfo(url=shop_url))]]))
    @router.message(private,Command('terms'))
    async def conditions(message: Message):await message.answer(terms,parse_mode=None)
    @router.message(private,Command('support','paysupport'))
    async def help_(message: Message):await message.answer(support,parse_mode=None)
    return router
