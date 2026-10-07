"""python-telegram-bot adapter (extra `ptb`): markup from Bot API JSON and an offline transport for tests.

The SDK-free core (telegram_patterns.markup, selection, calendar, slots, message_text, rich_message, ephemeral,
stars_subscription, sqlite_once, initdata) works the same under python-telegram-bot; this module only converts
its JSON to PTB objects and lets an Application run without Telegram. Fields that the installed PTB release does
not know yet (for example `disabled` buttons of Bot API 10.3) travel in api_kwargs and reach the wire unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from telegram import ForceReply, InlineKeyboardMarkup, MessageEntity, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, ApplicationBuilder, Defaults
from telegram.request import BaseRequest, RequestData

from .errors import InvalidType, ValidationFailure
from .message_text import FormattedText

__all__ = ['ptb_markup', 'ptb_inline_markup', 'ptb_text', 'StubRequest', 'offline_application']

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | ForceReply
Responder = Callable[[dict[str, Any]], Any]
_KINDS: tuple[tuple[str, type[Markup]], ...] = (
    ('inline_keyboard', InlineKeyboardMarkup),
    ('keyboard', ReplyKeyboardMarkup),
    ('remove_keyboard', ReplyKeyboardRemove),
    ('force_reply', ForceReply),
)


def ptb_markup(markup: Mapping[str, Any]) -> Markup:
    """The PTB object for markup JSON from telegram_patterns.markup (or any Bot API reply_markup)."""
    if not isinstance(markup, Mapping):
        raise InvalidType('Expected reply_markup JSON')
    kinds = [kind for key, kind in _KINDS if key in markup]
    if len(kinds) != 1:
        raise ValidationFailure('Markup JSON must be exactly one of inline, reply, remove or force reply')
    if 'inline_keyboard' in markup and not markup['inline_keyboard']:
        # python-telegram-bot would send {} here; editing a message without reply_markup removes its keyboard.
        raise ValidationFailure('Empty inline keyboard: pass reply_markup=None instead')
    result = kinds[0].de_json(json.loads(json.dumps(dict(markup))), None)
    if result is None:
        raise ValidationFailure('Markup JSON was not accepted by python-telegram-bot')
    return result


def ptb_inline_markup(markup: Mapping[str, Any]) -> InlineKeyboardMarkup:
    """The InlineKeyboardMarkup for inline markup JSON: what edit_message_text and edit_message_reply_markup accept."""
    if not isinstance(markup, Mapping) or 'inline_keyboard' not in markup:
        raise ValidationFailure('Expected inline keyboard JSON')
    result = ptb_markup(markup)
    assert isinstance(result, InlineKeyboardMarkup)
    return result


def ptb_text(formatted: FormattedText) -> dict[str, Any]:
    """text, entities and parse_mode=None for send_message/edit_message_text: literal text under any Defaults."""
    if not isinstance(formatted, FormattedText):
        raise InvalidType('Expected FormattedText from MessageBuilder or split()')
    data = formatted.as_kwargs()
    entities = tuple(
        entity for entity in (MessageEntity.de_json(item, None) for item in data['entities']) if entity is not None
    )
    return {'text': data['text'], 'entities': entities, 'parse_mode': None}


class StubRequest(BaseRequest):
    """Registered answers per Bot API method; an unregistered call fails and nothing reaches the network.

    calls keeps (method, parameters) in order, with parameters as python-telegram-bot puts them on the wire.
    """

    def __init__(self, *, me: Mapping[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self._responses: dict[str, Any] = {
            'getMe': dict(me or {'id': 1, 'is_bot': True, 'first_name': 'Fixture', 'username': 'fixture_bot'})
        }

    def respond(self, method: str, response: Any | Responder) -> StubRequest:
        """response is the `result` value or a callable that receives the parameters and returns it."""
        if not isinstance(method, str) or not method:
            raise InvalidType('Use a Bot API method name')
        self._responses[method] = response
        return self

    def fail(self, method: str, description: str, *, error_code: int = 400) -> StubRequest:
        """Answer the method with a Telegram error, as the server would."""
        self._responses[method] = _Failure(error_code, description)
        return self

    @property
    def read_timeout(self) -> float | None:
        return None

    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        self.closed = True

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: RequestData | None = None,
        read_timeout: Any = None,
        write_timeout: Any = None,
        connect_timeout: Any = None,
        pool_timeout: Any = None,
    ) -> tuple[int, bytes]:
        name = url.rsplit('/', 1)[-1]
        parameters = dict(request_data.parameters) if request_data is not None else {}
        if name != 'getMe':
            self.calls.append((name, parameters))
        if name not in self._responses:
            raise AssertionError(f'No offline response registered for {name}')
        response = self._responses[name]
        if isinstance(response, _Failure):
            return response.error_code, json.dumps(
                {'ok': False, 'error_code': response.error_code, 'description': response.description}
            ).encode()
        result = response(parameters) if callable(response) else response
        return 200, json.dumps({'ok': True, 'result': result}).encode()


class _Failure:
    def __init__(self, error_code: int, description: str) -> None:
        self.error_code, self.description = error_code, description


def offline_application(
    token: str = '1:OFFLINE_FIXTURE', *, request: StubRequest | None = None, defaults: Defaults | None = None
) -> tuple[Application[Any, Any, Any, Any, Any, Any], StubRequest]:
    """An Application whose bot talks only to StubRequest and that has no updater; feed it with process_update.

    defaults are the project's Defaults (parse_mode and others), so a test sees what production would send.
    """
    stub = request or StubRequest()
    builder = ApplicationBuilder().token(token).request(stub).get_updates_request(StubRequest()).updater(None)
    if defaults is not None:
        builder = builder.defaults(defaults)
    return builder.build(), stub
