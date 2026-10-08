"""Join request queries: a bot assigned to join requests shows a Mini App check, then approves or declines; no polling on import."""
import time
from collections.abc import Callable
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import AnswerChatJoinRequestQuery, SendChatJoinRequestWebApp
from aiogram.types import ChatJoinRequest
from telegram_patterns import InvalidInitData, validate_init_data

QUERY_WINDOW = 10.0  # seconds to call sendChatJoinRequestWebApp or answerChatJoinRequestQuery
MARGIN = 2.0  # network time to the server; a later call is not attempted


class JoinVerification:
    """pending holds (chat_id, user_id) -> query_id; production keeps it in shared durable storage."""

    def __init__(self, *, web_app_url: str, bot_token: str, clock: Callable[[], float] = time.time) -> None:
        if not web_app_url.startswith('https://'):
            raise ValueError('The Mini App URL must be HTTPS')
        self.web_app_url, self.bot_token, self.clock = web_app_url, bot_token, clock
        self.pending: dict[tuple[int, int], str] = {}
        self.outcomes: list[tuple[int, int, str]] = []  # for administrators: queued, expired, approve, decline

    def attach(self, dispatcher: Dispatcher) -> Router:
        router = Router(name='join-verification')

        @router.chat_join_request()
        async def requested(request: ChatJoinRequest, bot: Bot) -> None:
            if not request.query_id or request.from_user.is_bot:
                return  # an ordinary request: administrators or approveChatJoinRequest decide
            key = (request.chat.id, request.from_user.id)
            if self.clock() - request.date.timestamp() >= QUERY_WINDOW - MARGIN:
                self.outcomes.append((*key, 'expired'))  # too late to answer: the request stays with administrators
                return
            self.pending[key] = request.query_id
            url = f'{self.web_app_url}?{urlencode({"chat_id": request.chat.id})}'
            try:
                await bot(SendChatJoinRequestWebApp(chat_join_request_query_id=request.query_id, web_app_url=url))
            except TelegramAPIError:
                # The Mini App could not be shown: leave the decision to administrators while the window is open.
                self.pending.pop(key, None)
                await bot(AnswerChatJoinRequestQuery(chat_join_request_query_id=request.query_id, result='queue'))
                self.outcomes.append((*key, 'queued'))

        dispatcher.include_router(router)
        return router

    async def complete(self, bot: Bot, *, init_data: str, chat_id: int, passed: bool) -> str:
        """The Mini App backend calls this with raw initData; the user comes only from the signed data."""
        try:
            launch = validate_init_data(init_data, self.bot_token, max_age_seconds=600, now=int(self.clock()))
        except InvalidInitData:
            return 'invalid'
        query_id = self.pending.pop((chat_id, launch.user_id), None)
        if query_id is None:
            return 'unknown'  # no request of this user in this chat, or it was already answered
        result = 'approve' if passed else 'decline'
        try:
            await bot(AnswerChatJoinRequestQuery(chat_join_request_query_id=query_id, result=result))
        except TelegramAPIError:
            self.outcomes.append((chat_id, launch.user_id, 'unanswered'))
            return 'unanswered'  # the query may have expired: administrators check the request
        self.outcomes.append((chat_id, launch.user_id, result))
        return result
