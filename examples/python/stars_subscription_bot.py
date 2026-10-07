"""Monthly Stars subscription: invoice link, charges, BotSubscriptionUpdated and refunds decide access; no polling on import."""
from datetime import datetime, timezone
import time
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.methods import AnswerPreCheckoutQuery, SendMessage
from aiogram.types import BotSubscriptionUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery
from telegram_patterns import StarsSubscription, SubscriptionEventRejected
from telegram_patterns.aiogram import stars_invoice

Load = Callable[[int, str], Awaitable[StarsSubscription | None]]
Save = Callable[[StarsSubscription], Awaitable[None]]


def plan_payload(user_id: int) -> str:
    # One payload per user and plan: BotSubscriptionUpdated names the subscription by user and payload only.
    return f'pro:{user_id}'


def attach_stars_subscription(dispatcher: Dispatcher, *, load: Load, save: Save, price: int = 250,
                              clock: Callable[[], float] = time.time) -> Router:
    """load/save keep StarsSubscription.as_dict() in the host storage; every event is applied there first."""
    router = Router(name='stars-subscription')

    async def state(user_id: int) -> StarsSubscription:
        return await load(user_id, plan_payload(user_id)) or StarsSubscription(user_id, plan_payload(user_id))

    def until(moment: int | None) -> str:
        return datetime.fromtimestamp(moment or 0, timezone.utc).strftime('%d.%m.%Y %H:%M UTC')

    @router.message(Command('subscribe'), F.chat.type == 'private')
    async def subscribe(message: Message, bot: Bot) -> None:
        if message.from_user is None:
            return
        link = await bot(stars_invoice('Pro на месяц', 'Доступ к разделу Pro, продление каждые 30 дней',
                                       plan_payload(message.from_user.id), price, monthly_subscription=True))
        button = InlineKeyboardButton(text=f'Оплатить {price} ⭐', url=link)
        await bot(SendMessage(chat_id=message.chat.id, text='Подписка продлевается каждые 30 дней, отменить можно в Telegram.',
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]])))

    @router.pre_checkout_query()
    async def checkout(query: PreCheckoutQuery, bot: Bot) -> None:
        # Telegram waits about 10 seconds: only check that the payload belongs to this payer and plan.
        ok = query.currency == 'XTR' and query.invoice_payload == plan_payload(query.from_user.id) and query.total_amount == price
        await bot(AnswerPreCheckoutQuery(pre_checkout_query_id=query.id, ok=ok,
                                         error_message=None if ok else 'Счет устарел, запросите новый: /subscribe'))

    @router.message(F.successful_payment)
    async def paid(message: Message, bot: Bot) -> None:
        payment = message.successful_payment
        if payment is None or message.from_user is None:
            return
        try:
            sub = (await state(message.from_user.id)).record_payment(
                payment.model_dump(), user_id=message.from_user.id, paid_at=int(message.date.timestamp()))
        except SubscriptionEventRejected:
            return  # another product's payment or a conflicting duplicate: log and reconcile, grant nothing
        await save(sub)
        await bot(SendMessage(chat_id=message.chat.id, text=f'Pro доступен до {until(sub.access_until(clock()))}.'))

    @router.subscription()
    async def renewal(event: BotSubscriptionUpdated, bot: Bot) -> None:
        try:
            sub = (await state(event.user.id)).record_update(event.model_dump())
        except SubscriptionEventRejected:
            return
        await save(sub)
        if event.state == 'failed' and sub.has_access(clock()):
            await bot(SendMessage(chat_id=event.user.id, text=f'Продление не прошло. Pro работает до {until(sub.access_until(clock()))}.'))

    @router.message(F.refunded_payment, F.chat.type == 'private')
    async def refunded(message: Message) -> None:
        # In a private chat the chat id is the payer's user id.
        refund = message.refunded_payment
        if refund is None:
            return
        try:
            await save((await state(message.chat.id)).record_refund(refund.model_dump(), user_id=message.chat.id))
        except SubscriptionEventRejected:
            return

    @router.message(Command('pro'))
    async def pro(message: Message, bot: Bot) -> None:
        # Every protected action asks the stored charges with the current time; no cached flag.
        if message.from_user is None:
            return
        sub = await state(message.from_user.id)
        text = 'Раздел Pro открыт.' if sub.has_access(clock()) else 'Нужна подписка: /subscribe'
        await bot(SendMessage(chat_id=message.chat.id, text=text))

    dispatcher.include_router(router)
    return router
