"""python-telegram-bot: monthly Stars subscription; charges, renewal updates and refunds decide access; no polling on import."""
import time
from collections.abc import Awaitable, Callable
from typing import Any

from telegram import LabeledPrice, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, PreCheckoutQueryHandler, TypeHandler, filters
from telegram_patterns import STARS_SUBSCRIPTION_PERIOD, StarsSubscription, SubscriptionEventRejected, inline_button, inline_markup
from telegram_patterns.ptb import ptb_markup

Load = Callable[[int, str], Awaitable[StarsSubscription | None]]
Save = Callable[[StarsSubscription], Awaitable[None]]


def plan_payload(user_id: int) -> str:
    return f'pro:{user_id}'  # BotSubscriptionUpdated names the subscription by user and payload only


def attach_stars_subscription(application: Application, *, load: Load, save: Save, price: int = 250,  # type: ignore[type-arg]
                              clock: Callable[[], float] = time.time) -> None:
    """Bot API 10.2 `subscription` updates are unknown to python-telegram-bot 22.8 and arrive in Update.api_kwargs;
    list "subscription" in allowed_updates explicitly when polling or setting the webhook."""

    async def state(user_id: int) -> StarsSubscription:
        return await load(user_id, plan_payload(user_id)) or StarsSubscription(user_id, plan_payload(user_id))

    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        link = await context.bot.create_invoice_link('Pro на месяц', 'Доступ к разделу Pro, продление каждые 30 дней', plan_payload(user.id),
                                                     'XTR', [LabeledPrice('Pro на месяц', price)], subscription_period=STARS_SUBSCRIPTION_PERIOD)
        await message.reply_text('Подписка продлевается каждые 30 дней.', reply_markup=ptb_markup(inline_markup([[inline_button(f'Оплатить {price} ⭐', url=link)]])))

    async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.pre_checkout_query
        if query is None:
            return
        ok = query.currency == 'XTR' and query.invoice_payload == plan_payload(query.from_user.id) and query.total_amount == price
        await query.answer(ok, error_message=None if ok else 'Счет устарел, запросите новый: /subscribe')

    async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.successful_payment is None or message.from_user is None:
            return
        try:
            sub = (await state(message.from_user.id)).record_payment(message.successful_payment.to_dict(), user_id=message.from_user.id,
                                                                      paid_at=int(message.date.timestamp()))
        except SubscriptionEventRejected:
            return  # another product's payment or a conflicting duplicate: reconcile, grant nothing
        await save(sub)

    async def renewal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        event: Any = update.api_kwargs.get('subscription')
        if not isinstance(event, dict) or not isinstance(event.get('user'), dict):
            return
        try:
            sub = (await state(event['user']['id'])).record_update(event)
        except SubscriptionEventRejected:
            return
        await save(sub)
        if event.get('state') == 'failed' and sub.has_access(clock()):
            await context.bot.send_message(event['user']['id'], 'Продление не прошло. Pro работает до конца оплаченного месяца.')

    async def pro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is not None and user is not None:
            # Every protected action asks the stored charges with the current time.
            await message.reply_text('Раздел Pro открыт.' if (await state(user.id)).has_access(clock()) else 'Нужна подписка: /subscribe')

    application.add_handler(CommandHandler('subscribe', subscribe, filters=filters.ChatType.PRIVATE))
    application.add_handler(PreCheckoutQueryHandler(checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, paid))
    application.add_handler(CommandHandler('pro', pro))
    application.add_handler(TypeHandler(Update, renewal), group=1)  # sees updates of every type, including unknown ones
