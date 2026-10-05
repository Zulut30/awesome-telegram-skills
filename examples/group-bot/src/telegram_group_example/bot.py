"""Reviewed, context-bound group operations; SDK permissions are refreshed twice."""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatJoinRequest, ChatMemberUpdated, ForumTopic, Message, TelegramObject, Update
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import ActionButton, action_menu, build_request, event_router

from .storage import ProcessLock, io_call
from .store import Context, Refused, Store

RIGHT = {'topic_create':'can_manage_topics', 'topic_close':'can_manage_topics', 'topic_reopen':'can_manage_topics',
         'mute':'can_restrict_members', 'approve':'can_invite_users', 'decline':'can_invite_users', 'joins':'can_invite_users'}
STATUS = {'done':'Действие выполнено; повтор не отправлен.', 'unknown':'Результат Telegram неизвестен. Повтор запрещён; сверьте группу вручную.',
          'sending':'Операция уже начата. Пока нет сохранённого результата, повтор запрещён.', 'stale':'Подтверждение устарело. Проверьте объект и создайте новый предпросмотр.',
          'cancelled':'Действие отменено.', 'rejected':'Telegram отклонил действие. Автоматического повтора нет.',
          'draft':'Предпросмотр не был подтверждён доставленным сообщением.'}
HELP = ('Пример администратора группы.\n/rights — проверить права\n/topic_info — текущая тема\n'
        '/topic_create Название — создать тему\n/topic_close — закрыть текущую тему\n/topic_reopen — открыть текущую тему\n'
        '/joins — последние заявки\n/approve ID или /decline ID — рассмотреть заявку\n'
        '/mute в ответ на участника — ограничить его права на 10 минут.\n'
        'Изменения требуют личного подтверждения автора команды; оно действует 5 минут.')


class OwnedUpdates(BaseMiddleware):
    """Own active handlers until shutdown joins their SDK/SQLite cleanup."""
    def __init__(self, app: Application): self.app = app

    async def __call__(self, handler: Callable[[TelegramObject,dict[str,Any]],Awaitable[Any]], event: TelegramObject, data: dict[str,Any]) -> Any:
        if self.app.closing: return None
        task = asyncio.current_task()
        if task is None: raise RuntimeError('Update handler needs an owning task')
        self.app.inflight.add(task)
        try: return await handler(event,data)
        finally: self.app.inflight.discard(task)


class Application:
    def __init__(self, database: Path, bot_id: int, chats: set[int], *, now: Callable[[], float] = time.time):
        self.lock = ProcessLock(database)
        self.closed = False
        self.closing = False
        self.inflight: set[asyncio.Task[Any]] = set()
        try:
            self.store = Store(database,bot_id,chats,now=now)
            self.store.recover()
            self.dispatcher = Dispatcher()
            self.dispatcher.update.outer_middleware(OwnedUpdates(self))
            self.chat_locks: dict[int, asyncio.Lock] = {}
            router = Router(name='reviewed-group-commands')

            @router.message(Command('group_help','rights','topic_info','topic_create','topic_close','topic_reopen','joins','approve','decline','mute'))
            async def command(message: Message, command: CommandObject, bot: Bot, event_update: Update) -> None:
                await self.message(message,command,bot,event_update.update_id)

            self.dispatcher.include_router(router)
            self.dispatcher.include_router(event_router({'callback_query':self.callback,'chat_join_request':self.join_request,
                'chat_member':self.member,'my_chat_member':self.member}))

            # Migration service messages are observed separately from commands.
            migration = Router(name='group-migration')
            @migration.message()
            async def migration_message(message: Message) -> None:
                if message.migrate_to_chat_id or message.migrate_from_chat_id:
                    old = message.chat.id if message.migrate_to_chat_id else message.migrate_from_chat_id
                    new = message.migrate_to_chat_id or message.chat.id
                    if old is not None:
                        async with self.chat_lock(old): await io_call(self.store.migrate,old,new)
            self.dispatcher.include_router(migration)
        except BaseException:
            self.lock.close()
            raise

    def chat_lock(self, chat: int) -> asyncio.Lock:
        # Only configured chats can acquire persistent locks through handlers.
        return self.chat_locks.setdefault(chat,asyncio.Lock())

    def context(self, message: Message, bot: Bot, *, actor_id: int | None = None) -> Context:
        if bot.id != self.store.bot_id or message.chat.type != 'supergroup' or message.business_connection_id:
            raise Refused('Этот пример работает только в настроенных supergroup через Bot API.')
        if message.sender_chat or message.from_user is None or (actor_id is None and message.from_user.is_bot):
            raise Refused('Нужно действие от личного аккаунта администратора. Анонимный sender_chat не даёт полномочий.')
        if actor_id is not None and (message.from_user.id != bot.id or not message.from_user.is_bot):
            raise Refused('Подтверждение должно находиться в сообщении этого бота.')
        identity = message.from_user.id if actor_id is None else actor_id
        if type(identity) is not int or identity <= 0:
            raise Refused('Личность инициатора недоступна.')
        if message.is_topic_message and (message.message_thread_id is None or message.message_thread_id <= 0):
            raise Refused('Контекст темы недоступен.')
        return Context(bot.id,message.chat.id,message.message_thread_id or 0,identity,bool(message.chat.is_forum))

    async def notify(self, bot: Bot, context: Context, text: str, **kwargs: Any) -> Message:
        params: dict[str, Any] = {'chat_id':context.chat_id,'text':text,'parse_mode':None,**kwargs}
        if context.thread_id: params['message_thread_id'] = context.thread_id
        return await bot(build_request('sendMessage',params))

    async def authorize(self, bot: Bot, context: Context, action: str, payload: dict[str, Any] | None = None) -> None:
        await io_call(self.store.ensure,context)
        right = RIGHT.get(action)
        if action.startswith('topic_') and (not context.forum or (action != 'topic_create' and context.thread_id in {0,1})):
            raise Refused('Нужна forum supergroup и конкретная тема; General этот пример не изменяет.')
        for identity,label in ((bot.id,'У бота'),(context.actor_id,'У инициатора')):
            try:
                async with asyncio.timeout(3):
                    member = await bot(build_request('getChatMember',{'chat_id':context.chat_id,'user_id':identity}))
            except (TelegramAPIError,TimeoutError):
                raise Refused('Не удалось проверить текущие права. Изменение не отправлено.') from None
            if member.user.id != identity or member.status not in {'creator','administrator'}:
                raise Refused(label+' нет прав администратора. Изменение не отправлено.')
            if right and member.status != 'creator' and not getattr(member,right,False):
                raise Refused(label+' нет '+right+'. Изменение не отправлено.')
        if action == 'mute' and payload is not None:
            target = (payload or {}).get('user')
            if type(target) is not int or target <= 0 or target in {bot.id,context.actor_id}:
                raise Refused('Нужен другой обычный участник группы.')
            try:
                async with asyncio.timeout(3):
                    member = await bot(build_request('getChatMember',{'chat_id':context.chat_id,'user_id':target}))
            except (TelegramAPIError,TimeoutError):
                raise Refused('Статус участника не проверен. Изменение не отправлено.') from None
            if member.user.id != target or member.user.is_bot or member.status != 'member':
                raise Refused('Пример не ограничивает администраторов, ботов и уже ограниченных/вышедших участников.')

    async def message(self, message: Message, command: CommandObject, bot: Bot, update_id: int) -> None:
        # Ignore unrelated groups; do not collect their state or create per-chat locks.
        if message.chat.id not in self.store.chats: return
        context: Context | None = None
        async with self.chat_lock(message.chat.id):
            try:
                context = self.context(message,bot)
                await io_call(self.store.ensure,context)
                name,args = command.command,command.args
                if name == 'group_help': await self.notify(bot,context,HELP); return
                if name == 'topic_info':
                    await self.notify(bot,context,f'Группа {context.chat_id}; тема {context.thread_id or "General"}; forum={context.forum}. Состояние другой темы не используется.'); return
                await self.authorize(bot,context,name)
                if name == 'rights':
                    await self.notify(bot,context,'Бот и инициатор — администраторы. Для конкретного действия нужное право перепроверяется отдельно.'); return
                if name == 'joins':
                    rows = await io_call(self.store.pending,context)
                    await self.notify(bot,context,'Свежие заявки (до 30):\n'+'\n'.join(str(r['user']) for r in rows) if rows else 'Свежих наблюдаемых заявок нет. Проверьте can_invite_users и доставку chat_join_request.'); return
                payload: dict[str, Any] = {}
                if name == 'topic_create':
                    if not args or not 1 <= len(args) <= 128 or any(ord(c)<32 for c in args): raise Refused('Название темы: 1–128 символов без управляющих знаков.')
                    payload = {'name':args}
                    preview = f'Создать тему «{args}» в группе {context.chat_id}?'
                elif name in {'topic_close','topic_reopen'}:
                    preview = f'{"Закрыть" if name=="topic_close" else "Открыть"} тему {context.thread_id} в группе {context.chat_id}?'
                elif name in {'approve','decline'}:
                    if not args or not re.fullmatch(r'[1-9][0-9]{0,15}',args): raise Refused('Укажите ID из /joins.')
                    payload = await io_call(self.store.join,context,int(args))
                    preview = f'{"Принять" if name=="approve" else "Отклонить"} заявку пользователя {payload["user"]} от {payload["stamp"]} в группе {context.chat_id}?'
                elif name == 'mute':
                    reply = message.reply_to_message
                    if reply is None or reply.chat.id != context.chat_id or (reply.message_thread_id or 0) != context.thread_id or reply.sender_chat or reply.from_user is None or reply.from_user.is_bot:
                        raise Refused('Ответьте /mute на сообщение обычного участника в этой же группе и теме.')
                    payload = {'user':reply.from_user.id}
                    await self.authorize(bot,context,name,payload)
                    preview = f'Ограничить права участника {payload["user"]} в группе {context.chat_id} на 10 минут?'
                else: return
                # update_id may reset after an idle week; chat/message identity persists.
                operation,created = await io_call(self.store.prepare,context,message.message_id,name,payload)
                if not created:
                    await self.notify(bot,context,STATUS.get(operation['status'],'Используйте уже выданное подтверждение.')); return
                key = operation['key']
                markup = action_menu([ActionButton('Подтвердить','confirm_'+key),ActionButton('Отмена','cancel_'+key)],prefix='grp:',columns=2)
                prompt = await self.notify(bot,context,preview+'\nПодтверждение автора действует 5 минут. Права будут проверены снова.',reply_markup=markup)
                if prompt.chat.id != context.chat_id or (prompt.message_thread_id or 0) != context.thread_id or prompt.from_user is None or prompt.from_user.id != bot.id:
                    raise Refused('Ответ предпросмотра не совпадает с контекстом. Действие не запущено.')
                await io_call(self.store.bind,key,prompt.message_id)
            except Refused as error:
                if context is None:
                    # A controlled explanation, still without granting anonymous authority.
                    context = Context(bot.id,message.chat.id,message.message_thread_id or 0,0,bool(message.chat.is_forum))
                with suppress(TelegramAPIError,TimeoutError): await self.notify(bot,context,str(error))
            except (TelegramAPIError,TimeoutError):
                if context is not None:
                    with suppress(TelegramAPIError,TimeoutError): await self.notify(bot,context,'Не удалось доставить ответ. Действие не запускается без сохранённого подтверждения.')
            except sqlite3.Error:
                if context is not None:
                    with suppress(TelegramAPIError,TimeoutError): await self.notify(bot,context,'Хранилище недоступно. Новое действие не запущено; сохранённые операции требуют сверки.')

    async def callback(self, query: CallbackQuery, bot: Bot) -> None:
        if not query.data or not query.data.startswith('grp:'): return
        # ACK is transport acknowledgement, not approval. If it fails, stop here.
        try:
            async with asyncio.timeout(3): await query.answer()
        except (TelegramAPIError,TimeoutError): return
        if not isinstance(query.message,Message) or query.from_user.is_bot or query.message.chat.id not in self.store.chats: return
        context: Context | None = None
        async with self.chat_lock(query.message.chat.id):
            try:
                context = self.context(query.message,bot,actor_id=query.from_user.id)
                match = re.fullmatch(r'grp:(confirm|cancel)_([0-9a-f]{16})',query.data)
                if match is None: raise Refused('Некорректное подтверждение.')
                key = match[2]
                operation = await io_call(self.store.owned,context,key,query.message.message_id)
                if match[1] == 'cancel':
                    status = await io_call(self.store.cancel,context,key,query.message.message_id)
                else:
                    payload = json.loads(operation['payload'])
                    # Refresh actor and bot permissions before both effect and replay.
                    await self.authorize(bot,context,operation['action'],payload)
                    status = await self.execute(bot,context,operation,query.message.message_id)
                await self.notify(bot,context,STATUS.get(status,'Проверьте состояние операции.'))
            except Refused as error:
                if context is not None:
                    with suppress(TelegramAPIError,TimeoutError): await self.notify(bot,context,str(error))
            except (TelegramAPIError,TimeoutError):
                pass  # Outcome is already stored, or sending remains recoverable as unknown.
            except sqlite3.Error:
                if context is not None:
                    with suppress(TelegramAPIError,TimeoutError): await self.notify(bot,context,'Результат не удалось сохранить. Повтор запрещён; проверьте хранилище и группу вручную.')

    async def execute(self, bot: Bot, context: Context, operation: dict[str, Any], prompt: int) -> str:
        action,payload = operation['action'],json.loads(operation['payload'])
        params: dict[str, Any] = {'chat_id':context.chat_id}
        if action == 'topic_create':
            method = 'createForumTopic'; params['name'] = payload['name']
        elif action in {'topic_close','topic_reopen'}:
            method = 'closeForumTopic' if action=='topic_close' else 'reopenForumTopic'
            params['message_thread_id'] = context.thread_id
        elif action in {'approve','decline'}:
            method = 'approveChatJoinRequest' if action=='approve' else 'declineChatJoinRequest'
            params['user_id'] = payload['user']
        elif action == 'mute':
            method = 'restrictChatMember'; params.update(user_id=payload['user'],until_date=int(self.store.now())+600,
                use_independent_chat_permissions=True,permissions={name:False for name in (
                    'can_send_messages','can_send_audios','can_send_documents','can_send_photos','can_send_videos',
                    'can_send_video_notes','can_send_voice_notes','can_send_polls','can_send_other_messages','can_add_web_page_previews',
                    'can_react_to_messages','can_edit_tag','can_change_info','can_invite_users','can_pin_messages','can_manage_topics')})
        else: raise Refused('Действие не поддерживается.')
        request = build_request(method,params)
        claimed = await io_call(self.store.claim,context,operation['key'],prompt)
        if claimed != 'claimed': return claimed
        status,result = 'unknown',{}
        try:
            async with asyncio.timeout(5): response = await bot(request)
            if action == 'topic_create':
                if isinstance(response,ForumTopic) and response.message_thread_id > 0:
                    status,result = 'done',{'topic_id':response.message_thread_id}
            elif response is True: status = 'done'
        except (TelegramBadRequest,TelegramForbiddenError,TelegramRetryAfter):
            status = 'rejected'  # Explicit API rejection; never retry automatically.
        except asyncio.CancelledError:
            # Persist unknown before unwinding and releasing the database owner.
            await io_call(self.store.finish,operation['key'],'unknown')
            raise
        except Exception:
            status = 'unknown'  # SDK/network failure or malformed response after dispatch.
        await io_call(self.store.finish,operation['key'],status,result)
        return status

    async def join_request(self, request: ChatJoinRequest, bot: Bot, event_update: Update) -> None:
        if bot.id != self.store.bot_id or request.chat.type != 'supergroup' or request.chat.id not in self.store.chats or request.from_user.is_bot: return
        if request.query_id:
            # Urgent queueing must not wait behind a moderator's SDK call. SQLite
            # updates compare versions, so an older queue receipt cannot overwrite
            # a newer request/membership; queue never grants group membership.
            await self.observe_request(request,bot,event_update.update_id)
            return
        async with self.chat_lock(request.chat.id):
            await self.observe_request(request,bot,event_update.update_id)

    async def observe_request(self, request: ChatJoinRequest, bot: Bot, update_id: int) -> None:
        stamp = int(request.date.timestamp())
        fresh = await io_call(self.store.observe_join,request.chat.id,request.from_user.id,stamp,update_id,query=bool(request.query_id))
        if not fresh or not request.query_id: return
        # Assigned processing is deliberately queued, never automatically approved.
        accepted = False
        try:
            if 0 <= self.store.now()-stamp < 7:
                async with asyncio.timeout(3):
                    accepted = await bot(build_request('answerChatJoinRequestQuery',{'chat_join_request_query_id':request.query_id,'result':'queue'})) is True
        except asyncio.CancelledError:
            await io_call(self.store.finish_queue,request.chat.id,request.from_user.id,stamp,update_id,accepted=False)
            raise
        except Exception: pass
        await io_call(self.store.finish_queue,request.chat.id,request.from_user.id,stamp,update_id,accepted=accepted)

    async def member(self, event: ChatMemberUpdated, bot: Bot, event_update: Update) -> None:
        if bot.id != self.store.bot_id or event.chat.id not in self.store.chats: return
        async with self.chat_lock(event.chat.id):
            await io_call(self.store.membership,event.chat.id,event.new_chat_member.user.id,int(event.date.timestamp()),event_update.update_id)

    async def close(self) -> None:
        if not self.closed:
            self.closing = True
            # Polling can spawn concurrent update tasks. Wait for their owned local
            # writes and uncertain SDK outcomes before releasing the OS lock.
            tasks = tuple(task for task in self.inflight if task is not asyncio.current_task())
            for task in tasks: task.cancel()
            try:
                if tasks: await asyncio.gather(*tasks,return_exceptions=True)
                await self.dispatcher.fsm.close()
            finally: self.lock.close(); self.closed = True


async def live(database: Path, chats: set[int]) -> None:
    settings = BotSettings.from_env()
    app = Application(database,int(settings.token.split(':',1)[0]),chats)
    try:
        async with Bot(settings.token) as bot:
            # Do not delete webhook or pending updates. Existing consumers need owner coordination.
            try:
                await app.dispatcher.start_polling(bot,allowed_updates=app.dispatcher.resolve_used_update_types(),close_bot_session=False)
            finally: await app.close()  # Join handlers before the Bot session closes.
    finally: await app.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='Reviewed single-process supergroup bot; explicit allowed chat IDs required')
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--chat',type=int,action='append',required=True,help='Allowed negative group ID; repeat for each group')
    args = parser.parse_args()
    asyncio.run(live(args.database,set(args.chat)))


if __name__ == '__main__': main()
