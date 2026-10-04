"""Общие synthetic SDK fixtures для примеров; ни одного HTTP fallback."""
from datetime import datetime, timezone
from aiogram.types import CallbackQuery, Chat, Message, Update, User

TOKEN = '100:API_REFERENCE_FIXTURE'
DATE = datetime(2026, 10, 4, tzinfo=timezone.utc)
ACTOR = User(id=42, is_bot=False, first_name='Fixture')
BOT_USER = User(id=100, is_bot=True, first_name='Fixture', username='reference_fixture_bot')

def message(text: str, *, index: int = 1) -> Update:
    return Update(update_id=index, message=Message(message_id=index, date=DATE,
        chat=Chat(id=42, type='private'), from_user=ACTOR, text=text))

def callback(data: str, reply: Message, *, index: int, actor: User = ACTOR) -> Update:
    return Update(update_id=index, callback_query=CallbackQuery(id=str(index), from_user=actor,
        chat_instance='fixture', message=reply, data=data))

def response(request):
    return Message(message_id=100, date=DATE, chat=Chat(id=request.chat_id, type='private'),
                   from_user=BOT_USER, text=request.text)
