"""Actual host Dispatcher plus SDK serialization; HTTP fallback is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User
from telegram_patterns import escape_html, escape_markdown_v2, utf16_length
from telegram_patterns.testing import StubSession
from message_text_bot import attach_reports, compose_report


async def main():
    session = StubSession()
    bot = Bot('100:MESSAGE_TEXT_FIXTURE', session=session, default=DefaultBotProperties(parse_mode='MarkdownV2'))
    dispatcher = Dispatcher()
    help_router = Router(name='existing-help')
    helped = []
    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    attach_reports(dispatcher)
    captured = []
    def response(method):
        serialized = method.model_dump(mode='json', exclude_none=True, include={'text','entities'})
        serialized['parse_mode'] = method.parse_mode
        assert serialized['parse_mode'] is None
        assert session.prepare_value(method.parse_mode, bot=bot, files={}) is None
        assert json.loads(session.prepare_value(method.entities, bot=bot, files={})) == serialized['entities']
        assert 0 < utf16_length(method.text) <= 4096
        captured.append(serialized)
        return {'message_id': 100+len(captured), 'date': 1, 'chat': {'id': method.chat_id,'type':'private'}, 'text':method.text}
    session.respond(SendMessage,response)
    actor = User(id=42,is_bot=False,first_name='<b>Имя_*</b> 😀')
    def incoming(command,index):
        return Update(update_id=index,message=Message(message_id=index,date=datetime(2026,10,5,tzinfo=timezone.utc),
            chat=Chat(id=42,type='private'),from_user=actor,text=command))
    try:
        await dispatcher.feed_update(bot,incoming('/report',1))
        expected=compose_report(actor.full_name,'<b>буквальный текст</b> *_ [] & 😀\n'*160)
        assert len(captured)>1 and ''.join(p['text'] for p in captured)==''.join(c.text for c in expected)
        assert all(p['entities']==c.as_kwargs()['entities'] for p,c in zip(captured,expected))
        sent=len(captured)
        for changes in ({'chat':Chat(id=-42,type='group')}, {'message_thread_id':10,'is_topic_message':True},
                        {'is_topic_message':True}, {'business_connection_id':'unsupported-business'}):
            event=incoming('/report',10).message.model_copy(update=changes)
            await dispatcher.feed_update(bot,Update(update_id=10,message=event))
        assert len(captured)==sent
        await dispatcher.feed_update(bot,incoming('/help',2))
        assert helped==['/help']
        fallback=compose_report('Name','notes',emoji_id='123456789')
        assert not any(e['type']=='custom_emoji' for c in fallback for e in c.as_kwargs()['entities'])
        native=[c.as_kwargs(custom_emoji_entitlement_verified=True) for c in fallback]
        assert any(e['type']=='custom_emoji' for p in native for e in p['entities'])
        for payload in native: SendMessage.model_validate({'chat_id':42,**payload})
        assert escape_html('<b>&')=='&lt;b&gt;&amp;'
        assert escape_markdown_v2('_*')=='\\_\\*'
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'chunks':len(captured),
        'literal_injection':True,'utf16_offsets':True,'split_preserves_entities':True,'explicit_parse_mode_none':True,
        'emoji_capability_fallback':True,'existing_dispatcher_preserved':bool(helped),'private_context_guards':True}))


if __name__=='__main__': asyncio.run(main())
