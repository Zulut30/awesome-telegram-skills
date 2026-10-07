"""Actual host Dispatcher for bot-to-bot replies under an instantly answering peer bot; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User
from telegram_patterns.testing import StubSession
from bot_relay_bot import LoopGuard, attach_bot_relay

GROUP = Chat(id=-1004, type='supergroup', title='Ревью')
WHEN = datetime(2026, 10, 7, tzinfo=timezone.utc)
REVIEWER = User(id=200, is_bot=True, first_name='Reviewer', username='reviewer_bot')
ANNA = User(id=7, is_bot=False, first_name='Анна')
ME = User(id=100, is_bot=True, first_name='Contributor', username='contributor_bot')


async def main():
    session = StubSession()
    bot = Bot('100:RELAY_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    now = [0.0]
    guard = LoopGuard(max_depth=3, pause=5.0, clock=lambda: now[0])

    async def respond(text):
        return f'Исправлено: {text}'

    attach_bot_relay(dispatcher, respond=respond, guard=guard)
    sent = []
    session.respond(SendMessage, lambda method: sent.append((method.text, method.reply_parameters.message_id)) or
                    {'message_id': 900 + len(sent), 'date': 1, 'chat': {'id': method.chat_id, 'type': 'supergroup'}, 'text': method.text})
    index = [0]

    async def say(user, text, at):
        index[0] += 1
        now[0] = at
        message = Message(message_id=index[0], date=WHEN, chat=GROUP, from_user=user, text=text)
        await dispatcher.feed_update(bot, Update(update_id=index[0], message=message))
    try:
        await say(REVIEWER, 'Замечание 1', 0)
        assert sent == [('Исправлено: Замечание 1', 1)]
        await say(REVIEWER, 'Замечание 1', 2)
        assert len(sent) == 1, 'a repeated message is answered once'
        await say(REVIEWER, 'Замечание 2', 3)
        assert len(sent) == 1, 'at most one answer per peer every 5 seconds'
        # The peer answers instantly and forever: the depth limit ends the exchange.
        for step in range(20):
            await say(REVIEWER, f'Ответ {step}', 20 + step * 6)
        assert len(sent) == 3, sent
        await say(ME, 'моё сообщение', 200)
        assert len(sent) == 3, 'the bot never answers itself'
        await say(ANNA, '/help', 300)
        await say(REVIEWER, 'Новое замечание', 301)
        assert len(sent) == 4 and helped == ['/help'], 'a person resets the depth, existing handlers still run'
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'answers': len(sent),
                      'dedup': True, 'pause_per_peer': True, 'depth_limit': True, 'endless_peer_bounded': True,
                      'self_ignored': True, 'person_resets': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
