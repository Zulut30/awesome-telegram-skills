"""python-telegram-bot: a rich order card through do_api_request, or the same content as text; no polling on import."""
from collections.abc import Callable

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters
from telegram_patterns import RichButton, RichMessage, RichMessageBuilder, RichSpan
from telegram_patterns.ptb import ptb_markup, ptb_text


def order_card(order_id: int) -> RichMessage:
    rows = [['Товар', 'Кол-во', 'Цена'], ['Книга', '1', '500 ₽'], ['Ручка', '2', '100 ₽']]
    return (RichMessageBuilder()
            .heading(f'Заказ №{order_id}', size=1)
            .paragraph(['Статус: ', RichSpan('bold', 'оплачен')])
            .table(rows, compact=True, caption='Итого: 700 ₽')
            .checklist([('Оплата получена', True), ('Передан в доставку', False)])
            .buttons([RichButton('Подтвердить', callback_data=f'order:confirm:{order_id}', style='success')])
            .build())


def attach_order_cards(application: Application, *,  # type: ignore[type-arg]
                       rich_supported: Callable[[Update], bool] = lambda update: True) -> None:
    """python-telegram-bot 22.8 implements Bot API 10.0: sendRichMessage (10.1) goes through do_api_request."""

    async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        card = order_card(42)
        if rich_supported(update):
            await context.bot.do_api_request('sendRichMessage', api_kwargs={'chat_id': message.chat.id, 'rich_message': card.as_input()})
            return
        parts, keyboard = card.fallback().split(), card.fallback_keyboard()
        for index, part in enumerate(parts):
            markup = ptb_markup({'inline_keyboard': keyboard}) if keyboard and index == len(parts) - 1 else None
            await context.bot.send_message(message.chat.id, **ptb_text(part), reply_markup=markup)

    async def act(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.callback_query is not None:
            await update.callback_query.answer('Запрос принят')  # the service checks the user and the order itself

    application.add_handler(CommandHandler('order', show, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(act, pattern='^order:'))
