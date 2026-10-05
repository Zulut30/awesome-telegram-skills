"""Own polls and scoped observations; host owns durable intent, binding and receipts."""
from __future__ import annotations
import asyncio
from typing import Awaitable, Callable, cast
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendPoll
from aiogram.types import Message
from telegram_patterns import InvalidCompletion, InvalidType, safe_error_report
from telegram_patterns.aiogram import (ChatType, PollBinding, PollLookup, PollObserver, PollSpec,
                                      poll_events_router, poll_request)

Authorizer = Callable[[int, int, str], Awaitable[bool]]
Claim = Callable[[Message, SendPoll], Awaitable[bool]]
Confirm = Callable[[Message, PollBinding], Awaitable[None]]
MarkUnknown = Callable[[Message], Awaitable[None]]


def polls_router(authorize: Authorizer, claim: Claim, confirm: Confirm, mark_unknown: MarkUnknown,
                 lookup: PollLookup, observe: PollObserver) -> Router:
    router = Router(name='own-polls-example')
    commands = Router(name='own-polls-commands')
    commands.message.filter(F.chat.type.in_({'private','supergroup'}), F.from_user.is_bot == False)

    async def create(message: Message, spec: PollSpec) -> None:
        if message.from_user is None:
            return
        bot = message.bot
        if bot is None:
            raise InvalidType('Host Dispatcher must mount the message to its Bot')
        if await authorize(message.from_user.id,message.chat.id,'send') is not True:
            await message.answer('Недостаточно прав.',parse_mode=None)
            return
        request = poll_request(spec,chat_id=message.chat.id,chat_type=cast(ChatType,message.chat.type),
                               message_thread_id=message.message_thread_id,
                               business_connection_id=message.business_connection_id)
        # Host persists a scoped intent BEFORE sending. Replay/pending/unknown
        # must return False; a new attempt must never reuse a different payload.
        if await claim(message,request) is not True:
            await message.answer('Запрос уже принят. Проверьте его статус.',parse_mode=None)
            return
        try:
            sent = await bot(request)
            binding = PollBinding.from_message(sent,bot_id=bot.id)
            if binding.kind != spec.kind or binding.is_anonymous != spec.is_anonymous:
                raise InvalidCompletion('Own poll response does not match its request')
            # Host transaction records the binding and confirmed receipt.
            await confirm(message,binding)
        except asyncio.CancelledError:
            await mark_unknown(message)
            raise
        except Exception as error:
            await mark_unknown(message)
            await message.answer(safe_error_report(error,operation='write').message,parse_mode=None)
            return

    @commands.message(Command('poll'))
    async def regular(message: Message) -> None:
        await create(message,PollSpec('Когда встретиться?',['Утром','Днем','Вечером'],is_anonymous=False,
            allows_multiple_answers=True,allows_revoting=True,allow_adding_options=True))

    @commands.message(Command('quiz'))
    async def quiz(message: Message) -> None:
        await create(message,PollSpec('Какие числа четные?',['2','3','4'],kind='quiz',correct_option_ids=[0,2],
            allows_multiple_answers=True,explanation='2 и 4 делятся на 2 без остатка.',shuffle_options=True))

    router.include_router(commands)
    router.include_router(poll_events_router(lookup,observe))
    return router
