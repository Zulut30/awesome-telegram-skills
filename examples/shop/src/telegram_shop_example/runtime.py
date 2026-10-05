"""Explicit live entrypoint; HTTPS reverse proxy and owner configuration required."""
from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher
from telegram_patterns import BotSettings
from .api import create_app
from .payments import payment_router
from .storage import ProcessLock
from .store import Store


async def live(args) -> None:
    settings=BotSettings.from_env()
    terms=args.terms.read_text(encoding='utf-8')
    lock=ProcessLock(args.database.absolute())
    bot=Bot(settings.token);dispatcher=Dispatcher();runner=None
    try:
        store=Store(args.database,settings.token,terms_version=args.terms_version);store.recover()
        dispatcher.include_router(payment_router(store,shop_url=args.origin+'/',terms=terms,support=args.support))
        app=create_app(store,bot,args.frontend,origin=args.origin,terms=terms,support=args.support)
        runner=web.AppRunner(app,access_log=None,shutdown_timeout=5);await runner.setup()
        await web.TCPSite(runner,'127.0.0.1',args.port).start()
        await dispatcher.start_polling(bot,close_bot_session=False)
    finally:
        try:
            if runner is not None:await runner.cleanup()
        finally:
            try:await dispatcher.fsm.close();await bot.session.close()
            finally:lock.close()


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--frontend',type=Path,required=True,help='Built frontend dist')
    parser.add_argument('--origin',required=True,help='Exact HTTPS public origin, no trailing slash')
    parser.add_argument('--terms',type=Path,required=True)
    parser.add_argument('--terms-version',required=True)
    parser.add_argument('--support',required=True,help='Configured operator contact/support instructions')
    parser.add_argument('--port',type=int,default=8080)
    asyncio.run(live(parser.parse_args()))
