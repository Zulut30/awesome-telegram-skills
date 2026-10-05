"""Explicit synthetic SDK fixture; no real Telegram transport is permitted."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from aiogram import Bot
from aiogram.methods import (AnswerCallbackQuery, AnswerChatJoinRequestQuery, ApproveChatJoinRequest, CloseForumTopic,
    CreateForumTopic, DeclineChatJoinRequest, GetChatMember, ReopenForumTopic, RestrictChatMember, SendMessage)
from aiogram.methods.base import TelegramMethod
from aiogram.types import (CallbackQuery, Chat, ChatJoinRequest, ChatMember, ChatMemberAdministrator, ChatMemberMember, ChatMemberUpdated,
    ForumTopic, InlineKeyboardMarkup, Message, Update, User)
from telegram_patterns.testing import StubSession

from .bot import Application
from .storage import ProcessLock, connection

BASE = datetime(2026,10,5,12,tzinfo=timezone.utc)
OWNER = User(id=42,is_bot=False,first_name='Admin fixture')
TARGET = User(id=77,is_bot=False,first_name='Member fixture')
BOT_USER = User(id=100,is_bot=True,first_name='Bot fixture',username='group_fixture_bot')
CHAT = -1001234567890
OTHER = -1009876543210
MUTATIONS = (CreateForumTopic,CloseForumTopic,ReopenForumTopic,RestrictChatMember,ApproveChatJoinRequest,DeclineChatJoinRequest)


def administrator(user: User, **rights: Any) -> ChatMemberAdministrator:
    fields = dict(can_be_edited=False,is_anonymous=False,can_manage_chat=True,can_delete_messages=False,
        can_manage_video_chats=False,can_restrict_members=True,can_promote_members=False,can_change_info=False,
        can_invite_users=True,can_post_stories=False,can_edit_stories=False,can_delete_stories=False,
        can_send_welcome_messages=False,can_manage_topics=True)
    fields.update(rights)
    return ChatMemberAdministrator.model_validate({'user':user,**fields})


class Fixture:
    """Native SDK Dispatcher with explicit responses, actual SQLite and no HTTP fallback."""
    def __init__(self, database: Path, *, start: int = 0):
        self.now = BASE.timestamp()
        self.index = start
        self.app = Application(database,100,{CHAT,OTHER},now=lambda:self.now)
        self.session = StubSession()
        self.members: dict[tuple[int,int],ChatMember] = { (chat,user.id):administrator(user) for chat in (CHAT,OTHER) for user in (OWNER,BOT_USER) }
        for chat in (CHAT,OTHER): self.members[(chat,TARGET.id)] = ChatMemberMember(user=TARGET)
        def member_response(method: TelegramMethod[Any]) -> ChatMember:
            assert isinstance(method,GetChatMember) and isinstance(method.chat_id,int)
            return self.members[(method.chat_id,method.user_id)]
        self.session.respond(GetChatMember,member_response)
        self.sent: list[tuple[SendMessage,Message]] = []
        def response(method: TelegramMethod[Any]) -> Message:
            assert isinstance(method,SendMessage)
            assert isinstance(method.chat_id,int) and (method.reply_markup is None or isinstance(method.reply_markup,InlineKeyboardMarkup))
            result = Message(message_id=20000+self.index+len(self.sent),date=BASE,chat=Chat(id=method.chat_id,type='supergroup',is_forum=True),
                from_user=BOT_USER,text=method.text,message_thread_id=method.message_thread_id,is_topic_message=bool(method.message_thread_id),reply_markup=method.reply_markup)
            self.sent.append((method,result)); return result
        self.session.respond(SendMessage,response).respond(AnswerCallbackQuery,True).respond(AnswerChatJoinRequestQuery,True)
        self.session.respond(CreateForumTopic,ForumTopic(message_thread_id=900,name='Fixture topic',icon_color=7322096))
        for method in MUTATIONS[1:]: self.session.respond(method,True)
        self.bot = Bot('100:GROUP_OFFLINE_FIXTURE',session=self.session)

    def next(self) -> int:
        self.index += 1; return self.index

    async def command(self, text: str, *, chat: int = CHAT, thread: int = 10, user: User = OWNER, reply: Message | None = None, sender_chat: Chat | None = None, business: str | None = None, update_id: int | None = None, message_id: int | None = None) -> None:
        index = self.next() if update_id is None else update_id
        message = Message(message_id=index if message_id is None else message_id,date=BASE,chat=Chat(id=chat,type='supergroup',is_forum=True),from_user=user,
            text=text,message_thread_id=thread or None,is_topic_message=bool(thread),reply_to_message=reply,sender_chat=sender_chat,business_connection_id=business)
        await self.app.dispatcher.feed_update(self.bot,Update(update_id=index,message=message))

    def operation(self, action: str, *, chat: int = CHAT) -> dict[str, Any]:
        with connection(self.app.store.database) as db:
            return dict(db.execute('SELECT * FROM group_operations WHERE action=? AND chat=? ORDER BY created DESC,rowid DESC LIMIT 1', (action,chat)).fetchone())

    async def callback(self, operation: dict[str, Any], *, user: User = OWNER, chat: int | None = None, thread: int | None = None, prompt: int | None = None, cancel: bool = False) -> None:
        index = self.next()
        message = Message(message_id=operation['prompt'] if prompt is None else prompt,date=BASE,
            chat=Chat(id=operation['chat'] if chat is None else chat,type='supergroup',is_forum=True),from_user=BOT_USER,
            message_thread_id=operation['thread'] if thread is None else thread,is_topic_message=True)
        query = CallbackQuery(id=str(index),from_user=user,chat_instance='fixture',message=message,data='grp:'+('cancel_' if cancel else 'confirm_')+operation['key'])
        await self.app.dispatcher.feed_update(self.bot,Update(update_id=index,callback_query=query))

    async def join(self, *, query: str | None = None, chat: int = CHAT, stamp: int = 0, update_id: int | None = None) -> None:
        index = self.next() if update_id is None else update_id
        event = ChatJoinRequest(chat=Chat(id=chat,type='supergroup',is_forum=True),from_user=TARGET,user_chat_id=987654,
            date=datetime.fromtimestamp(self.now+stamp,timezone.utc),bio='PRIVATE_FIXTURE_BIO',query_id=query)
        await self.app.dispatcher.feed_update(self.bot,Update(update_id=index,chat_join_request=event))

    async def membership(self, user: User = OWNER, *, chat: int = CHAT, stamp: int = 1) -> None:
        index = self.next()
        event = ChatMemberUpdated(chat=Chat(id=chat,type='supergroup',is_forum=True),from_user=OWNER,
            date=datetime.fromtimestamp(self.now+stamp,timezone.utc),old_chat_member=administrator(user),new_chat_member=ChatMemberMember(user=user))
        self.members[(chat,user.id)] = event.new_chat_member
        update = Update(update_id=index,my_chat_member=event) if user.is_bot else Update(update_id=index,chat_member=event)
        await self.app.dispatcher.feed_update(self.bot,update)

    def effects(self) -> list[TelegramMethod[Any]]:
        return [method for method in self.session.calls if isinstance(method,MUTATIONS)]

    async def close(self) -> None:
        try: await self.bot.session.close()
        finally: await self.app.close()


def guards() -> list[int]:
    attempts = [0]
    def audit(event: str, args: tuple[Any,...]) -> None:
        if event in {'socket.connect','socket.getaddrinfo'}:
            attempts[0] += 1; raise RuntimeError('Network forbidden in group fixture')
    sys.addaudithook(audit)
    from aiogram.client.session.aiohttp import AiohttpSession
    async def deny(*args: Any, **kwargs: Any) -> Any:
        attempts[0] += 1; raise RuntimeError('Real Telegram transport forbidden')
    AiohttpSession.make_request = deny  # type: ignore[method-assign]
    return attempts


async def phase(database: Path, name: str) -> dict[str, Any]:
    attempts = guards()
    fixture = Fixture(database,start={'preview':0,'confirm':100,'crash':200,'recover':300}[name])
    checks: list[str] = []
    try:
        if name == 'preview':
            await fixture.command('/group_help'); await fixture.command('/rights'); await fixture.command('/topic_info')
            await fixture.command('/topic_create Offline created topic')
            operation = fixture.operation('topic_create'); assert operation['status']=='ready' and not fixture.effects()
            checks = ['menu','current-admin-rights','thread-info','bound-persisted-preview','no-mutation-before-confirm']
        elif name == 'confirm':
            operation = fixture.operation('topic_create'); assert operation['status']=='ready'
            await fixture.callback(operation,user=TARGET); assert not fixture.effects()
            await fixture.callback(operation,chat=OTHER); assert not fixture.effects()
            await fixture.callback(operation,thread=20); assert not fixture.effects()
            start = len(fixture.session.calls); await fixture.callback(operation)
            assert isinstance(fixture.session.calls[start],AnswerCallbackQuery)
            assert len(fixture.effects())==1 and fixture.operation('topic_create')['status']=='done'
            await fixture.callback(operation); assert len(fixture.effects())==1
            checks = ['restart-restores-preview','foreign-actor-chat-thread-denied','ack-before-authorization','one-sdk-effect','owner-replay-no-resend']
        elif name == 'crash':
            await fixture.command('/topic_create Crash topic')
            operation = fixture.operation('topic_create')
            def crash_finish(*args: Any, **kwargs: Any) -> None:
                assert len(fixture.effects())==1 and isinstance(fixture.effects()[0],CreateForumTopic) and attempts[0]==0
                with connection(database) as db: assert db.execute('SELECT status FROM group_operations WHERE key=?', (operation['key'],)).fetchone()[0]=='sending'
                print(json.dumps({'phase':name,'stub_transport_effect':True,'durable_sending':True,'telegram_requests':False,'external_network_attempts':0}),flush=True)
                os._exit(77)
            fixture.app.store.finish = crash_finish  # type: ignore[method-assign]
            await fixture.callback(operation)
            raise AssertionError('Expected actual abrupt process exit')
        elif name == 'recover':
            operation = fixture.operation('topic_create'); assert operation['status']=='unknown'
            await fixture.callback(operation); assert not fixture.effects()
            assert 'неизвестен' in fixture.sent[-1][0].text
            checks = ['process-lock-reacquired','sending-recovers-as-unknown','unknown-owner-replay-no-effect','controlled-reconciliation-message']
    finally: await fixture.close()
    assert fixture.session.closed and fixture.app.closed and fixture.app.lock.file.closed and attempts[0]==0
    lock = ProcessLock(database); lock.close()
    return {'phase':name,'passed':True,'checks':checks,'telegram_requests':False,'external_network_attempts':attempts[0],
        'session_closed':fixture.session.closed,'application_closed':fixture.app.closed,'lock_released':fixture.app.lock.file.closed}


def main() -> None:
    if not __debug__: raise SystemExit('Fixture assertions must remain enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--phase',choices=['preview','confirm','crash','recover'],required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(phase(args.database,args.phase))))


if __name__ == '__main__': main()
