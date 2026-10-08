"""python-telegram-bot: join request queries (Bot API 10.1) with a Mini App check and signed initData; no polling on import."""
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.ext import Application, ChatJoinRequestHandler, ContextTypes
from telegram_patterns import InvalidInitData, validate_init_data

QUERY_WINDOW, MARGIN = 10.0, 2.0  # seconds to call sendChatJoinRequestWebApp or answerChatJoinRequestQuery


class JoinVerification:
    """pending holds (chat_id, user_id) -> query_id; production keeps it in shared durable storage."""

    def __init__(self, *, web_app_url: str, bot_token: str, clock: Callable[[], float] = time.time) -> None:
        if not web_app_url.startswith('https://'):
            raise ValueError('The Mini App URL must be HTTPS')
        self.web_app_url, self.bot_token, self.clock = web_app_url, bot_token, clock
        self.pending: dict[tuple[int, int], str] = {}
        self.outcomes: list[tuple[int, int, str]] = []

    def attach(self, application: Application) -> None:  # type: ignore[type-arg]
        async def requested(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            request = update.chat_join_request
            query_id: Any = request.api_kwargs.get('query_id') if request is not None else None  # unknown to python-telegram-bot 22.8
            if request is None or not isinstance(query_id, str) or request.from_user.is_bot:
                return
            key = (request.chat.id, request.from_user.id)
            if self.clock() - request.date.timestamp() >= QUERY_WINDOW - MARGIN:
                self.outcomes.append((*key, 'expired'))  # too late: the request stays with administrators
                return
            self.pending[key] = query_id
            url = f'{self.web_app_url}?{urlencode({"chat_id": request.chat.id})}'
            try:
                await context.bot.do_api_request('sendChatJoinRequestWebApp', api_kwargs={'chat_join_request_query_id': query_id, 'web_app_url': url})
            except TelegramError:
                self.pending.pop(key, None)
                await context.bot.do_api_request('answerChatJoinRequestQuery', api_kwargs={'chat_join_request_query_id': query_id, 'result': 'queue'})
                self.outcomes.append((*key, 'queued'))

        application.add_handler(ChatJoinRequestHandler(requested))

    async def complete(self, bot: Bot, *, init_data: str, chat_id: int, passed: bool) -> str:
        """The Mini App backend calls this with raw initData; the user comes only from the signed data."""
        try:
            launch = validate_init_data(init_data, self.bot_token, max_age_seconds=600, now=int(self.clock()))
        except InvalidInitData:
            return 'invalid'
        query_id = self.pending.pop((chat_id, launch.user_id), None)
        if query_id is None:
            return 'unknown'
        result = 'approve' if passed else 'decline'
        try:
            await bot.do_api_request('answerChatJoinRequestQuery', api_kwargs={'chat_join_request_query_id': query_id, 'result': result})
        except TelegramError:
            self.outcomes.append((chat_id, launch.user_id, 'unanswered'))
            return 'unanswered'
        self.outcomes.append((chat_id, launch.user_id, result))
        return result
