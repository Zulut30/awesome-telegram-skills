"""Exercise the same cookbook Dispatcher with native SDK transport, no network."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import json
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup, SendMessage, SetMyCommands
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User, UsersShared, SharedUser
from telegram_patterns.testing import StubSession
from keyboards_bot import create_app

DATE = datetime(2026, 10, 4, tzinfo=timezone.utc)


async def scenario() -> dict:
    responses, traces = [], []
    async def record(trace): traces.append(trace)
    def send(method):
        response = Message(message_id=100 + len(responses), date=DATE, chat=Chat(id=method.chat_id, type="private"),
                           text=method.text, reply_markup=method.reply_markup if getattr(method.reply_markup, 'inline_keyboard', None) else None)
        responses.append(response)
        return response
    def edit(method):
        return Message(message_id=method.message_id, date=DATE, chat=Chat(id=method.chat_id, type="private"), reply_markup=method.reply_markup)
    session = StubSession().respond(SendMessage, send).respond(AnswerCallbackQuery, True).respond(EditMessageReplyMarkup, edit).respond(SetMyCommands, True)
    dispatcher, commands = create_app(record)
    actor = User(id=42, first_name="Fixture", is_bot=False)
    chat, update_id = Chat(id=42, type="private"), 0
    async with Bot("100:OFFLINE_FIXTURE", session=session) as bot:
        async def receive(**fields):
            nonlocal update_id
            update_id += 1
            await dispatcher.feed_update(bot, Update(update_id=update_id, **fields))
        async def message(text=None, **fields):
            await receive(message=Message(message_id=update_id + 1, date=DATE, chat=chat, from_user=actor, text=text, **fields))
        await bot.set_my_commands(commands)
        await message("/two")
        menu = responses[-1]
        assert [len(row) for row in menu.reply_markup.inline_keyboard] == [2, 2, 3]
        before = len(session.calls)
        await receive(callback_query=CallbackQuery(id="layout", from_user=actor, chat_instance="fixture", message=menu, data="demo:layout:three"))
        assert [type(call).__name__ for call in session.calls[before:]] == ['AnswerCallbackQuery', 'EditMessageReplyMarkup']
        assert [len(row) for row in session.calls[-1].reply_markup.inline_keyboard] == [3, 3, 3]
        before = len(session.calls)
        await receive(callback_query=CallbackQuery(id="duplicate", from_user=actor, chat_instance="fixture", message=menu, data="demo:layout:three"))
        assert [type(call).__name__ for call in session.calls[before:]] == ['AnswerCallbackQuery']
        foreign = User(id=43, first_name="Foreign fixture", is_bot=False)
        await receive(callback_query=CallbackQuery(id="foreign", from_user=foreign, chat_instance="fixture", message=menu, data="demo:layout:two"))
        assert isinstance(session.calls[-1], AnswerCallbackQuery) and session.calls[-1].text
        await message("/colors")
        assert [button.style for button in responses[-1].reply_markup.inline_keyboard[0]] == ['primary', 'success', 'danger']
        await message("/mixed")
        assert [len(row) for row in responses[-1].reply_markup.inline_keyboard] == [1, 2, 3, 3]
        await message("/reply")
        assert session.calls[-1].reply_markup.input_field_placeholder == "Выберите действие"
        await message("Каталог")
        assert session.calls[-1].text == "Текстовое действие: Каталог"
        await message("/requests")
        markup = session.calls[-1].reply_markup
        assert markup.keyboard[0][0].request_contact and markup.keyboard[0][1].request_location
        assert markup.keyboard[2][0].request_users.request_id == 1
        await message(contact=Contact(phone_number="FIXTURE", first_name="Fixture", user_id=42))
        assert session.calls[-1].text == "Получено событие: contact"
        await message(users_shared=UsersShared(request_id=1, users=[SharedUser(user_id=43)]))
        assert session.calls[-1].text == "Получено событие: users_shared"
        await message("/input")
        prompt = responses[-1]
        assert session.calls[-1].reply_markup.force_reply
        before = len(session.calls)
        await message("This is not a reply")
        assert len(session.calls) == before
        await message("Fixture name", reply_to_message=prompt)
        assert session.calls[-1].text.startswith("Ответ принят") and session.calls[-1].reply_markup.remove_keyboard
        await message("/actions")
        assert session.calls[-1].reply_markup.inline_keyboard[1][0].disabled is not None
        await message("/hide")
        assert session.calls[-1].reply_markup.remove_keyboard
    assert session.closed
    assert len(traces) == update_id * 2 and all(trace.actor_id is None and trace.chat_id is None for trace in traces)
    assert any(trace.detail == 'contact' for trace in traces)
    return {'passed': True, 'network': False, 'updates': update_id, 'traces': len(traces),
            'methods': sorted({type(call).__name__ for call in session.calls}),
            'checks': ['rows_2_3_mixed', 'styles', 'ack_before_edit', 'duplicate_noop', 'foreign_denied',
                       'reply_text', 'request_contact_users', 'bound_force_reply', 'copy_disabled', 'remove_keyboard'],
            'session_closed': session.closed}


if __name__ == '__main__': print(json.dumps(asyncio.run(scenario())))
