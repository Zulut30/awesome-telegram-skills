"""python-telegram-bot: answer a group button press with an ephemeral message (Bot API 10.2) via api_kwargs; no polling on import."""
import time
from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters
from telegram_patterns import EphemeralMessageRef, EphemeralNotAllowed, EphemeralTrigger, ephemeral_parameters, inline_button, inline_markup
from telegram_patterns.ptb import ptb_markup

PANEL = inline_markup([[inline_button('Мой статус', callback_data='me:status')]])
OWN = inline_markup([[inline_button('Обновить', callback_data='me:refresh'), inline_button('Скрыть', callback_data='me:hide')]])


def attach_ephemeral_status(application: Application, *, status: Callable[[int, int], Awaitable[str]],  # type: ignore[type-arg]
                            clock: Callable[[], float] = time.monotonic) -> None:
    """python-telegram-bot 22.8 implements Bot API 10.0: new fields go in api_kwargs, new methods through do_api_request."""

    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is not None:
            await update.effective_message.reply_text('Нажмите — ответ увидите только вы.', reply_markup=ptb_markup(PANEL))

    async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        received = clock()
        query = update.callback_query
        if query is None or query.message is None:
            return
        chat = query.message.chat
        text = await status(chat.id, query.from_user.id)
        try:
            extra = ephemeral_parameters(chat_type=chat.type, receiver_user_id=query.from_user.id, receiver_is_bot=query.from_user.is_bot,
                                         trigger=EphemeralTrigger.callback(query.id, received), now=clock())
        except EphemeralNotAllowed:
            await query.answer(text[:200], show_alert=True)  # an alert is also seen only by the presser
            return
        await context.bot.send_message(chat.id, text, reply_markup=ptb_markup(OWN), api_kwargs=extra)
        await query.answer()

    async def own(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        ephemeral_id = query.message.api_kwargs.get('ephemeral_message_id')  # message_id of an ephemeral message is 0
        if not isinstance(ephemeral_id, int):
            await query.answer()
            return
        target = EphemeralMessageRef(query.message.chat.id, query.from_user.id, ephemeral_id).target()
        if query.data == 'me:hide':
            await context.bot.do_api_request('deleteEphemeralMessage', api_kwargs=dict(target))
        else:
            text = await status(query.message.chat.id, query.from_user.id)
            await context.bot.do_api_request('editEphemeralMessageText', api_kwargs={**target, 'text': text, 'reply_markup': OWN})
        await query.answer()

    groups = filters.ChatType.GROUPS
    application.add_handler(CommandHandler('panel', panel, filters=groups))
    application.add_handler(CallbackQueryHandler(show, pattern='^me:status$'))
    application.add_handler(CallbackQueryHandler(own, pattern='^me:(refresh|hide)$'))
