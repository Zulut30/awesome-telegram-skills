"""Actual host Dispatcher and SDK models for community service messages in a group and a channel; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import GetChat, SendMessage
from aiogram.types import Chat, Message, Update, User
from telegram_patterns.testing import StubSession
from community_bot import attach_community_events

GROUP = Chat(id=-1001, type='supergroup', title='Клуб')
CHANNEL = Chat(id=-1002, type='channel', title='Новости клуба')
WHEN = datetime(2026, 10, 7, tzinfo=timezone.utc)
BIG = 2**51 + 7  # community ids may need more than 32 bits


async def main():
    session = StubSession()
    bot = Bot('100:COMMUNITY_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    links, arrivals = {}, []

    async def save(chat_id, community):
        links[chat_id] = None if community is None else (community.id, community.name)

    async def joined(chat_id, user_id, community):
        arrivals.append((chat_id, user_id, community.id))

    attach_community_events(dispatcher, save=save, joined=joined)
    server = {'community': None}
    sent = []
    gifts = {kind: False for kind in ('unlimited_gifts', 'limited_gifts', 'unique_gifts', 'premium_subscription', 'gifts_from_channels')}
    session.respond(GetChat, lambda method: {'id': method.chat_id, 'type': 'supergroup', 'title': 'Клуб', 'accent_color_id': 0, 'max_reaction_count': 11,
                                              'accepted_gift_types': gifts, **({'community': server['community']} if server['community'] else {})})
    session.respond(SendMessage, lambda method: sent.append(method.text) or {'message_id': 900 + len(sent), 'date': 1, 'chat': {'id': method.chat_id, 'type': 'supergroup'}, 'text': method.text})
    anna = User(id=7, is_bot=False, first_name='Анна')
    helper = User(id=8, is_bot=True, first_name='Помощник')
    community = {'id': BIG, 'name': 'Город'}

    def service(index, chat, **fields):
        message = Message.model_validate({'message_id': index, 'date': WHEN, 'chat': chat, **fields})
        return Update(update_id=index, **({'channel_post': message} if chat.type == 'channel' else {'message': message}))
    try:
        await dispatcher.feed_update(bot, service(1, GROUP, from_user=anna, community_chat_added={'community': community}))
        await dispatcher.feed_update(bot, service(2, CHANNEL, community_chat_added={'community': community}))
        assert links == {-1001: (BIG, 'Город'), -1002: (BIG, 'Город')}, 'the link is stored per chat, the id keeps 52 bits'

        await dispatcher.feed_update(bot, service(3, GROUP, from_user=anna, community_chat_joined={'community': community}))
        await dispatcher.feed_update(bot, service(4, GROUP, from_user=helper, community_chat_joined={'community': community}))
        assert arrivals == [(-1001, 7, BIG)], 'a bot arrival is not counted as a member'

        await dispatcher.feed_update(bot, service(5, CHANNEL, community_chat_removed={}))
        assert links[-1002] is None and links[-1001] == (BIG, 'Город'), 'removal carries no community and touches one chat'

        links.pop(-1001)  # the service message was missed: /community reconciles from getChat
        server['community'] = community
        await dispatcher.feed_update(bot, service(6, GROUP, from_user=anna, text='/community'))
        assert links[-1001] == (BIG, 'Город') and sent[-1] == 'Группа входит в сообщество «Город».'
        server['community'] = None
        await dispatcher.feed_update(bot, service(7, GROUP, from_user=anna, text='/community'))
        assert links[-1001] is None and sent[-1] == 'Группа не входит в сообщество.'

        await dispatcher.feed_update(bot, service(8, GROUP, from_user=anna, text='/help'))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'added_group': True, 'added_channel': True,
                      'joined_counted': len(arrivals), 'bot_arrival_ignored': True, 'removed_without_fields': True,
                      'reconciled_from_get_chat': True, 'community_id_bits': BIG.bit_length(),
                      'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
