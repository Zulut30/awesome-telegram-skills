"""Настоящий SDK polling через StubSession; останавливаем его после первого запроса."""
import asyncio
import json
from aiogram import Dispatcher
from aiogram.methods import GetMe, GetUpdates, SetMyCommands
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import run_bot, stars_invoice, start_router
from telegram_patterns.testing import StubSession
from bot_fixture import BOT_USER, TOKEN

async def main() -> None:
    requested = asyncio.Event()
    async def updates(request):
        requested.set()
        await asyncio.sleep(0.01)
        return []
    session = StubSession().respond(GetMe, BOT_USER).respond(GetUpdates, updates).respond(SetMyCommands, True)
    dispatcher = Dispatcher(); dispatcher.include_router(start_router('Fixture'))
    invoice = stars_invoice('Тест', 'Публичный пример', 'server-order-1', 1)
    assert invoice.currency == 'XTR' and invoice.prices[0].amount == 1
    # Конструирование invoice не создает заказ, платеж или доступ.
    running = asyncio.create_task(run_bot(dispatcher, BotSettings(TOKEN), session=session, commands=[], handle_signals=False))
    try:
        await asyncio.wait_for(requested.wait(), timeout=5)
        await dispatcher.stop_polling()
        await asyncio.wait_for(running, timeout=5)
    finally:
        if not running.done(): running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await dispatcher.fsm.close()
    assert session.closed and any(isinstance(c, GetUpdates) for c in session.calls)
    print(json.dumps({'passed': True, 'case': 'bot_runner', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
