"""Metadata observer на update; received/handled без содержимого сообщения."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from telegram_patterns.aiogram import UpdatePhase, UpdateTrace, UpdateObserver, update_kinds, event_router
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, message, response

async def main() -> None:
    traces: list[UpdateTrace] = []
    async def record(trace: UpdateTrace) -> None: traces.append(trace)
    async def reply(value) -> None: await value.answer('Публичный ответ', parse_mode=None)
    observer = UpdateObserver(record)
    phase: UpdatePhase = 'received'
    await observer.emit(UpdateTrace(update_id=0, kind='fixture', phase=phase))
    dispatcher = Dispatcher(); dispatcher.update.outer_middleware(observer)
    dispatcher.include_router(event_router({'message': reply}))
    update = message('/observe'); assert update_kinds(update) == ('message',)
    session = StubSession().respond(SendMessage, response)
    async with Bot(TOKEN, session=session) as bot:
        try: await dispatcher.feed_update(bot, update)
        finally: await dispatcher.fsm.close()
    assert [t.phase for t in traces] == ['received', 'received', 'handled']
    assert all(t.actor_id is None and t.chat_id is None for t in traces)
    # best-effort observation, не durable audit или подписка на историю.
    print(json.dumps({'passed': True, 'case': 'bot_events', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
