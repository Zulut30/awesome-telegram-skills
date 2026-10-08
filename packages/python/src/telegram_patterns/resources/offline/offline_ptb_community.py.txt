"""Actual python-telegram-bot Application for community service messages in a group and a channel; HTTP is disabled."""
import asyncio
import json

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns.ptb import offline_application
from ptb_community_bot import attach_community_events

GROUP = {'id': -1001, 'type': 'supergroup', 'title': 'Клуб'}
CHANNEL = {'id': -1002, 'type': 'channel', 'title': 'Новости клуба'}
ANNA = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}
HELPER = {'id': 8, 'is_bot': True, 'first_name': 'Помощник'}
BIG = 2**51 + 7


async def main():
    application, stub = offline_application()
    helped, links, arrivals, server = [], {}, [], {'community': None}

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))

    async def save(chat_id, community):
        links[chat_id] = None if community is None else (community['id'], community['name'])

    async def joined(chat_id, user_id, community):
        arrivals.append((chat_id, user_id, community['id']))
    attach_community_events(application, save=save, joined=joined)
    gifts = dict.fromkeys(('unlimited_gifts', 'limited_gifts', 'unique_gifts', 'premium_subscription', 'gifts_from_channels'), False)
    stub.respond('getChat', lambda p: {'id': p['chat_id'], 'type': 'supergroup', 'title': 'Клуб', 'accent_color_id': 0, 'max_reaction_count': 11,
                                       'accepted_gift_types': gifts, **({'community': server['community']} if server['community'] else {})})
    stub.respond('sendMessage', lambda p: {'message_id': 900, 'date': 1, 'chat': GROUP, 'text': p['text']})
    community = {'id': BIG, 'name': 'Город'}

    def service(index, chat, **fields):
        key = 'channel_post' if chat['type'] == 'channel' else 'message'
        return Update.de_json({'update_id': index, key: {'message_id': index, 'date': 1, 'chat': chat, **fields}}, application.bot)

    def command(index, text):
        return service(index, GROUP, **{'from': ANNA, 'text': text, 'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]})
    await application.initialize()
    try:
        await application.process_update(service(1, GROUP, **{'from': ANNA, 'community_chat_added': {'community': community}}))
        await application.process_update(service(2, CHANNEL, community_chat_added={'community': community}))
        assert links == {-1001: (BIG, 'Город'), -1002: (BIG, 'Город')}
        await application.process_update(service(3, GROUP, **{'from': ANNA, 'community_chat_joined': {'community': community}}))
        await application.process_update(service(4, GROUP, **{'from': HELPER, 'community_chat_joined': {'community': community}}))
        assert arrivals == [(-1001, 7, BIG)]
        await application.process_update(service(5, CHANNEL, community_chat_removed={}))
        assert links[-1002] is None and links[-1001] == (BIG, 'Город')
        links.pop(-1001)
        server['community'] = community
        await application.process_update(command(6, '/community'))
        assert links[-1001] == (BIG, 'Город') and stub.calls[-1][1]['text'] == 'Группа входит в сообщество «Город».'
        server['community'] = None
        await application.process_update(command(7, '/community'))
        assert links[-1001] is None and stub.calls[-1][1]['text'] == 'Группа не входит в сообщество.'
        await application.process_update(command(8, '/help'))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'unknown_fields_via_api_kwargs': True, 'added_group': True, 'added_channel': True, 'bot_arrival_ignored': True,
                      'reconciled_from_get_chat': True, 'community_id_bits': BIG.bit_length(), 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
