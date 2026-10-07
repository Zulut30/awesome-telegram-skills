"""Live polling entrypoint. Never invoked by the offline verifier."""
from __future__ import annotations
import argparse
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
import time
from collections.abc import Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Message
from telegram_patterns import BotSettings, PatternError, PermissionDenied
from telegram_patterns.aiogram import CommandReply, TextField, command_menu, command_router, run_bot, text_form_router
from .service import Actor, Service
from .storage import ProcessLock, SQLiteFSM, io_call


COMMANDS = [CommandReply(c, d, t) for c,d,t in [
    ('start', 'Начать', 'Сервис записи. /slots — свободные слоты · /book — запись · /status — мои записи. Напоминания включаются явно: /reminders_on.'),
    ('help', 'Помощь', '/book — код слота и комментарий · /back — исправить · /cancel — закрыть форму. /cancel_booking N — отменить свою запись. /reminders_off — отключить напоминания. После неизвестного результата повторите подтверждение той же формы или проверьте /status.'),
]]


class Application:
    def __init__(self, database: Path, bot_id: int, *, now: Callable[[], float] = time.time):
        self.lock = ProcessLock(database)
        self.task: asyncio.Task | None = None
        try:
            self.service = Service(database, bot_id, now=now)
            self.recovered_notifications = self.service.recover()
            self.storage = SQLiteFSM(database)
            self.dispatcher = Dispatcher(storage=self.storage, events_isolation=SimpleEventIsolation())
            router = Router(name='service-menu')
            private = (F.chat.type == 'private') & (F.from_user.is_bot == False) & (F.business_connection_id == None)
            def actor(message: Message) -> Actor:
                if message.from_user is None or message.bot is None: raise PermissionDenied()
                identity = Actor(message.bot.id, message.from_user.id, message.chat.id)
                self.service.authorize(identity)
                return identity

            @router.message(private, Command('slots'))
            async def slots(message: Message) -> None:
                actor(message)
                values = await io_call(self.service.slots)
                lines = [f"{r['id']} — {r['label']}, " + datetime.fromtimestamp(r['starts_at'], timezone.utc).strftime('%d.%m %H:%M UTC') for r in values]
                await message.answer('Свободные слоты:\n' + '\n'.join(lines) + '\nНачать: /book.' if lines else 'Свободных слотов сейчас нет.', parse_mode=None)

            @router.message(private, Command('status'))
            async def status(message: Message) -> None:
                values = await io_call(self.service.bookings, actor(message))
                reminders = {'pending':'ожидает срока и разрешения','sent':'отправлено','unknown':'отправка не подтверждена',
                             'sending':'отправляется','blocked':'доставка недоступна','skipped':'отменено или выключено','failed':'доставка отклонена'}
                lines = [f"№{r['id']}: {'подтверждена' if r['status']=='booked' else 'отменена'}, {r['label']} — /cancel_booking {r['id']}. "
                         + 'Напоминание: ' + reminders.get(r['reminder_status'],'требует проверки') for r in values]
                await message.answer('\n'.join(lines) if lines else 'У вас пока нет записей. /slots', parse_mode=None)

            @router.message(private, Command('cancel_booking'))
            async def cancel(message: Message, command: CommandObject) -> None:
                identity = actor(message)
                if not command.args or not command.args.isascii() or not command.args.isdecimal() or len(command.args)>12:
                    await message.answer('Укажите номер: /cancel_booking N.', parse_mode=None); return
                try:
                    await io_call(self.service.cancel, identity, int(command.args))
                except PermissionDenied:
                    await message.answer('Запись недоступна. Проверьте /status.', parse_mode=None)
                else:
                    await message.answer('Ваша запись отменена. Не начатое напоминание отменено.', parse_mode=None)

            @router.message(private, Command('reminders_on', 'reminders_off'))
            async def reminders(message: Message, command: CommandObject) -> None:
                enabled = command.command == 'reminders_on'
                await io_call(self.service.reminders, actor(message), enabled)
                await message.answer('Напоминания включены.' if enabled else 'Напоминания отключены. Уже начатую отправку отозвать нельзя.', parse_mode=None)

            self.dispatcher.include_router(router)
            self.dispatcher.include_router(text_form_router([
                TextField('slot', 'Слот', 'Введите код свободного слота из /slots, например slot-1.', max_length=24),
                TextField('note', 'Комментарий', 'Краткий комментарий без контактов, паролей и токенов.', max_length=256),
            ], self.service.submit, name='booking', command='book'))
            # command_router is wrapped by an application filter: no group/Business flow.
            menu = command_router(COMMANDS); menu.message.filter(private)
            self.dispatcher.include_router(menu)

            @self.dispatcher.startup()
            async def startup(bot: Bot) -> None:
                if bot.id != bot_id: raise PermissionDenied()
                self.task = asyncio.create_task(self.notifications(bot), name='service-reminders')

            @self.dispatcher.shutdown()
            async def shutdown() -> None:
                await self.stop_notifications()
        except BaseException:
            self.lock.close()
            raise

    async def notifications(self, bot: Bot) -> None:
        while True:
            await self.service.deliver_one(bot)
            await asyncio.sleep(5)

    async def stop_notifications(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError): await self.task
            self.task = None

    async def close(self) -> None:
        try:
            await self.stop_notifications()
        finally:
            try: await self.dispatcher.fsm.close()
            finally: self.lock.close()


async def live(database: Path) -> None:
    settings = BotSettings.from_env()
    app = Application(database, int(settings.token.split(':', 1)[0]))
    commands = command_menu(COMMANDS)
    from aiogram.types import BotCommand
    commands += [BotCommand(command=c,description=d) for c,d in [
        ('slots','Свободные слоты'),('book','Записаться'),('status','Мои записи'),('back','Назад в форме'),
        ('cancel','Закрыть форму'),('cancel_booking','Отменить свою запись'),('reminders_on','Включить напоминания'),('reminders_off','Отключить напоминания')]]
    try: await run_bot(app.dispatcher, settings, commands=commands)
    finally: await app.close()


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    args=parser.parse_args()
    try: asyncio.run(live(args.database.absolute()))
    except PatternError as exc: parser.exit(2, f'{parser.prog}: error: {exc}\n')


if __name__ == '__main__': main()
