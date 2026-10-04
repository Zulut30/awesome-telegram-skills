"""Optional aiogram test transport; strictly local, never falls back to HTTP."""
from __future__ import annotations

import inspect
from typing import Any, AsyncGenerator, Awaitable, Callable

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods.base import TelegramMethod
from pydantic import TypeAdapter

Responder = object | Callable[[TelegramMethod[Any]], object | Awaitable[object]]


class StubSession(BaseSession):
    """Record methods, require explicit responses and validate SDK return types.

    Fixtures are artificial API responses, not evidence of live Telegram behavior.
    """
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.closed = False
        self._responders: dict[type[TelegramMethod[Any]], Responder] = {}

    def respond(self, method: type[TelegramMethod[Any]], response: Responder) -> StubSession:
        if not isinstance(method, type) or not issubclass(method, TelegramMethod):
            raise TypeError("Register an aiogram TelegramMethod class")
        self._responders[method] = response
        return self

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if self.closed:
            raise RuntimeError("Stub session is closed")
        self.calls.append(method)
        if type(method) not in self._responders:
            raise AssertionError(f"Unexpected Telegram method: {type(method).__name__}")
        response = self._responders[type(method)]
        value = response(method) if callable(response) else response
        if inspect.isawaitable(value):
            value = await value
        # Use SDK/Pydantic coercion, including API integer timestamps in Message.
        return TypeAdapter(method.__returning__).validate_python(value, context={'bot': bot})

    async def close(self) -> None:
        self.closed = True

    async def stream_content(self, url: str, headers: dict[str, Any] | None = None,
                             timeout: int = 30, chunk_size: int = 65536,
                             raise_for_status: bool = True) -> AsyncGenerator[bytes, None]:
        # Keep an async-generator signature while rejecting unsupported file I/O.
        if False:
            yield b''
        raise AssertionError("File streaming is not configured in StubSession")
