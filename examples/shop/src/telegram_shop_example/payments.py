"""Trusted Bot SDK updates are the only receipt ingress, not browser claims."""
from __future__ import annotations
import asyncio
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery, WebAppInfo
from telegram_patterns import PaymentConflict, PermissionDenied, ValidationFailure
from .launch import launch_url, screen_hint
from .storage import io_call
from .store import Store
from .refunds import ShopRefunds


def payment_router(store: Store, *, shop_url: str, terms: str, support: str) -> Router:
    router=Router(name='shop-payments')
    async def recovery_guard(handler, event, data):
        await io_call(store.require_operational)
        return await handler(event,data)
    router.message.outer_middleware.register(recovery_guard)
    router.pre_checkout_query.outer_middleware.register(recovery_guard)
    @router.pre_checkout_query()
    async def precheckout(query: PreCheckoutQuery):
        try:
            if query.bot is None or query.from_user.is_bot:raise PermissionDenied()
            async with asyncio.timeout(3):
                await io_call(store.precheckout,query.bot.id,query.from_user.id,query.id,query.invoice_payload,query.currency,query.total_amount)
        except Exception:
            async with asyncio.timeout(3):await query.answer(ok=False,error_message='Заказ недоступен или требует сверки. Откройте магазин или /paysupport.')
        else:
            async with asyncio.timeout(3):await query.answer(ok=True)

    private=(F.chat.type=='private') & (F.from_user.is_bot==False) & (F.business_connection_id==None)
    @router.message(private,F.successful_payment)
    async def paid(message: Message):
        receipt=message.successful_payment
        if receipt is None or message.from_user is None or message.bot is None or message.chat.id!=message.from_user.id:raise PermissionDenied()
        try:
            result=await ShopRefunds(store,message.bot).paid(message)
        except (PermissionDenied,PaymentConflict):
            await message.answer('Платёж требует сверки. Обратитесь в /paysupport.',parse_mode=None);return
        # A failed notification never rolls back paid/access and never starts a refund.
        if not result['replayed']:
            await message.answer('Платёж требует сверки: /paysupport.' if result['review'] else 'Покупка доступна в магазине → «Мои покупки».',parse_mode=None)

    @router.message(private,F.refunded_payment)
    async def refunded(message: Message):
        if message.bot is None:raise PermissionDenied()
        try:result=await ShopRefunds(store,message.bot).refunded(message)
        except (PermissionDenied,PaymentConflict):
            await message.answer('Возврат требует сверки. Обратитесь в /paysupport.',parse_mode=None);return
        if not result['replayed']:await message.answer('Возврат учтён. Доступ к возвращённой покупке закрыт.',parse_mode=None)

    @router.message(private,Command('start'))
    async def start(message: Message, command: CommandObject):
        try:hint=screen_hint(command.args)
        except ValidationFailure:hint='catalog'
        await message.answer('Каталог учебных материалов. Цена и доступ определяются сервером. Условия: /terms. Поддержка платежей: /paysupport.',parse_mode=None,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Открыть магазин',web_app=WebAppInfo(url=launch_url(shop_url,hint)))]]))
    @router.message(private,Command('terms'))
    async def conditions(message: Message):await message.answer(terms,parse_mode=None)
    @router.message(private,Command('support','paysupport'))
    async def help_(message: Message):await message.answer(support,parse_mode=None)
    return router
