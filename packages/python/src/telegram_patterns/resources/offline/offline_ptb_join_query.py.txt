"""Actual python-telegram-bot Application for join request queries with a Mini App check; HTTP is disabled."""
import asyncio
import hmac
import json
from urllib.parse import urlencode

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns.ptb import offline_application
from ptb_join_query_bot import JoinVerification

TOKEN = '100:PTB_JOIN_QUERY_FIXTURE'
GROUP = {'id': -1005, 'type': 'supergroup', 'title': 'Клуб'}
T0 = 1_790_000_000


def init_data(user_id, *, token=TOKEN):
    fields = {'auth_date': str(T0), 'user': json.dumps({'id': user_id, 'first_name': 'U'}, separators=(',', ':'))}
    secret = hmac.digest(b'WebAppData', token.encode(), 'sha256')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
    return urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})


def user(user_id):
    return {'id': user_id, 'is_bot': False, 'first_name': f'U{user_id}'}


async def main():
    application, stub = offline_application(TOKEN)
    helped, now, failing = [], [float(T0)], []

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))
    verification = JoinVerification(web_app_url='https://example.com/check', bot_token=TOKEN, clock=lambda: now[0])
    verification.attach(application)

    def shown(parameters):
        if failing:
            raise TimeoutError('fixture: the Mini App could not be shown')
        return True
    stub.respond('sendChatJoinRequestWebApp', shown)
    stub.respond('answerChatJoinRequestQuery', True)

    async def request(index, user_id, *, query='q', age=1):
        event = {'chat': GROUP, 'from': user(user_id), 'user_chat_id': user_id, 'date': int(now[0] - age)}
        if query:
            event['query_id'] = f'{query}{index}'
        await application.process_update(Update.de_json({'update_id': index, 'chat_join_request': event}, application.bot))

    def calls(name):
        return [p for m, p in stub.calls if m == name]
    await application.initialize()
    try:
        await request(1, 7)
        assert calls('sendChatJoinRequestWebApp') == [{'chat_join_request_query_id': 'q1', 'web_app_url': 'https://example.com/check?chat_id=-1005'}]
        assert await verification.complete(application.bot, init_data=init_data(7), chat_id=-1005, passed=True) == 'approve'
        assert calls('answerChatJoinRequestQuery') == [{'chat_join_request_query_id': 'q1', 'result': 'approve'}]
        assert await verification.complete(application.bot, init_data=init_data(7), chat_id=-1005, passed=True) == 'unknown'
        assert await verification.complete(application.bot, init_data=init_data(7, token='100:OTHER'), chat_id=-1005, passed=True) == 'invalid'
        await request(2, 8)
        assert await verification.complete(application.bot, init_data=init_data(8), chat_id=-1005, passed=False) == 'decline'
        await request(3, 9, age=9)
        assert len(calls('sendChatJoinRequestWebApp')) == 2 and verification.outcomes[-1] == (-1005, 9, 'expired')
        await request(4, 10, query=None)
        assert len(calls('sendChatJoinRequestWebApp')) == 2 and len(calls('answerChatJoinRequestQuery')) == 2
        failing.append(True)
        await request(5, 11)
        assert calls('answerChatJoinRequestQuery')[-1] == {'chat_join_request_query_id': 'q5', 'result': 'queue'}
        await application.process_update(Update.de_json({'update_id': 6, 'message': {
            'message_id': 6, 'date': T0, 'chat': {'id': 7, 'type': 'private'}, 'from': user(7), 'text': '/help',
            'entities': [{'type': 'bot_command', 'offset': 0, 'length': 5}]}}, application.bot))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'new_methods_via_do_api_request': True, 'signed_user_only': True, 'approve_once': True, 'stale_query_untouched': True,
                      'queue_when_mini_app_fails': True, 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
