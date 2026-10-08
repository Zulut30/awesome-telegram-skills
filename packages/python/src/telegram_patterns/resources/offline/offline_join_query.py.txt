"""Actual host Dispatcher for join request queries with a Mini App check and signed initData; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import hmac
import json
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.methods import AnswerChatJoinRequestQuery, SendChatJoinRequestWebApp
from aiogram.types import Chat, ChatJoinRequest, Message, Update, User
from telegram_patterns.testing import StubSession
from join_query_bot import JoinVerification

TOKEN = '100:JOIN_QUERY_FIXTURE'
GROUP = Chat(id=-1005, type='supergroup', title='Клуб')
T0 = 1_790_000_000
ANNA, BEN = User(id=7, is_bot=False, first_name='Анна'), User(id=8, is_bot=False, first_name='Бен')


def init_data(user_id, *, token=TOKEN):
    fields = {'auth_date': str(T0), 'user': json.dumps({'id': user_id, 'first_name': 'U'}, separators=(',', ':'))}
    secret = hmac.digest(b'WebAppData', token.encode(), 'sha256')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
    return urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})


async def main():
    session = StubSession()
    bot = Bot(TOKEN, session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    now = [float(T0)]
    verification = JoinVerification(web_app_url='https://example.com/check', bot_token=TOKEN, clock=lambda: now[0])
    verification.attach(dispatcher)
    shown, answers, failing = [], [], []

    def show(method):
        if failing:
            raise TelegramBadRequest(method=method, message='Bad Request: fixture')
        return shown.append((method.chat_join_request_query_id, method.web_app_url)) or True
    session.respond(SendChatJoinRequestWebApp, show)
    session.respond(AnswerChatJoinRequestQuery, lambda method: answers.append((method.chat_join_request_query_id, method.result)) or True)

    async def request(index, user, *, query='q', age=1):
        event = ChatJoinRequest(chat=GROUP, from_user=user, user_chat_id=user.id, date=datetime.fromtimestamp(now[0] - age, timezone.utc),
                                query_id=None if query is None else f'{query}{index}')
        await dispatcher.feed_update(bot, Update(update_id=index, chat_join_request=event))
    try:
        await request(1, ANNA)
        assert shown == [('q1', 'https://example.com/check?chat_id=-1005')] and not answers, 'the Mini App is shown first'
        assert await verification.complete(bot, init_data=init_data(7), chat_id=-1005, passed=True) == 'approve'
        assert answers == [('q1', 'approve')]
        assert await verification.complete(bot, init_data=init_data(7), chat_id=-1005, passed=True) == 'unknown', 'answered once'
        assert await verification.complete(bot, init_data=init_data(7, token='100:OTHER'), chat_id=-1005, passed=True) == 'invalid'
        assert await verification.complete(bot, init_data=init_data(8), chat_id=-1005, passed=True) == 'unknown', 'no request of Ben'

        await request(2, BEN)
        assert await verification.complete(bot, init_data=init_data(8), chat_id=-1005, passed=False) == 'decline'
        await request(3, User(id=9, is_bot=False, first_name='C'), age=9)
        assert len(shown) == 2 and verification.outcomes[-1] == (-1005, 9, 'expired'), 'too late: nothing is called'
        await request(4, User(id=10, is_bot=False, first_name='D'), query=None)
        assert len(shown) == 2 and len(answers) == 2, 'an ordinary request is not a query'
        failing.append(True)
        await request(5, User(id=11, is_bot=False, first_name='E'))
        assert answers[-1] == ('q5', 'queue') and verification.outcomes[-1] == (-1005, 11, 'queued')
        await dispatcher.feed_update(bot, Update(update_id=6, message=Message(message_id=6, date=datetime.fromtimestamp(T0, timezone.utc),
                                                                             chat=Chat(id=7, type='private'), from_user=ANNA, text='/help')))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'mini_app_shown': True,
                      'signed_user_only': True, 'approve_once': True, 'decline_on_failed_check': True, 'stale_query_untouched': True,
                      'ordinary_request_ignored': True, 'queue_when_mini_app_fails': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
