"""In a group, answer a button press with a message only the presser sees; no polling on import."""
import time
from typing import Awaitable, Callable

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.methods import DeleteEphemeralMessage, EditEphemeralMessageText, SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram_patterns import EphemeralMessageRef, EphemeralNotAllowed, EphemeralTrigger, ephemeral_parameters

GROUPS = ('group', 'supergroup')
PANEL = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Мой статус', callback_data='me:status'),
                                               InlineKeyboardButton(text='Статус вместо панели', callback_data='me:replace')]])
OWN = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Обновить', callback_data='me:refresh'),
                                             InlineKeyboardButton(text='Скрыть', callback_data='me:hide')]])


def attach_ephemeral_status(dispatcher: Dispatcher, *, status: Callable[[int, int], Awaitable[str]],
                            clock: Callable[[], float] = time.monotonic, bot_is_admin: bool = False) -> Router:
    """status(chat_id, user_id) is the service call; it checks the user's access and returns the text."""
    router = Router(name='ephemeral-status')

    @router.message(Command('panel'), F.chat.type.in_(GROUPS))
    async def panel(message: Message) -> None:
        await message.bot(SendMessage(chat_id=message.chat.id, text='Нажмите — ответ увидите только вы.', reply_markup=PANEL))

    @router.callback_query(F.data.in_({'me:status', 'me:replace'}))
    async def show(query: CallbackQuery) -> None:
        received = clock()
        message = query.message
        if not isinstance(message, Message) or message.chat.type not in GROUPS:
            await query.answer('Эта кнопка работает в группе', show_alert=True)
            return
        text = await status(message.chat.id, query.from_user.id)
        try:
            extra = ephemeral_parameters(chat_type=message.chat.type, receiver_user_id=query.from_user.id,
                                         receiver_is_bot=query.from_user.is_bot, bot_is_admin=bot_is_admin,
                                         trigger=EphemeralTrigger.callback(query.id, received), now=clock(),
                                         replace_original=query.data == 'me:replace')
        except EphemeralNotAllowed:
            # The 15-second window passed: an alert is also seen only by the presser.
            await query.answer(text[:200], show_alert=True)
            return
        # The answer names this press by callback_query_id; delivery is not guaranteed, nothing is retried.
        await query.bot(SendMessage.model_validate({'chat_id': message.chat.id, 'text': text, 'reply_markup': OWN, **extra}))
        await query.answer()

    @router.callback_query(F.data.in_({'me:refresh', 'me:hide'}))
    async def own(query: CallbackQuery) -> None:
        message = query.message
        if not isinstance(message, Message) or message.ephemeral_message_id is None:
            await query.answer()
            return
        # Buttons on an ephemeral message are answered by editing or deleting it, never by replacing.
        ref = EphemeralMessageRef(message.chat.id, query.from_user.id, message.ephemeral_message_id)
        if query.data == 'me:hide':
            await query.bot(DeleteEphemeralMessage(**ref.target()))
        else:
            text = await status(message.chat.id, query.from_user.id)
            await query.bot(EditEphemeralMessageText(**ref.target(), text=text, reply_markup=OWN))
        await query.answer()

    dispatcher.include_router(router)
    return router
