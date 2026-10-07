"""Optional aiogram 3 adapters; no SDK import in the core package."""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Mapping, Sequence

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession
from aiogram.client.telegram import TEST
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart
from aiogram.methods import CreateInvoiceLink
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardMarkup, LabeledPrice, Message

from ._aiogram.api import InvalidAPIRequest, MethodSpec, build_request, method_catalog
from ._aiogram.calendar_keyboards import calendar_keyboard, time_slot_keyboard
from ._aiogram.dialog_fields import (
    ContactField,
    DateField,
    EmailField,
    FieldValue,
    FileField,
    LocationField,
    NumberField,
    PhoneField,
)
from ._aiogram.dialog_forms import DialogSubmission, dialog_form_router
from ._aiogram.events import UpdateObserver, UpdatePhase, UpdateTrace, event_router, update_kinds
from ._aiogram.forms import FormSubmission, InvalidField, TextField, text_form_router
from ._aiogram.fsm_storage import (
    AtomicFSMStorage,
    DialogLifetime,
    FSMConflict,
    FSMSnapshot,
    SnapshotFSMStorage,
    SnapshotStore,
)
from ._aiogram.inline_mode import (
    InlineAuthorizer,
    InlineCachePolicy,
    InlineChatType,
    InlineItem,
    InlinePage,
    InlineSearch,
    InlineSearchProvider,
    inline_articles,
    inline_query_router,
)
from ._aiogram.keyboard_layouts import KeyboardCapabilities, KeyboardLayout, action_layout, inline_layout, reply_layout
from ._aiogram.keyboards import (
    ActionButton,
    ButtonStyle,
    MenuPage,
    _callback_data,
    action_keyboard,
    action_menu,
    page_number,
    paginated_menu,
)
from ._aiogram.media import (
    DownloadedMedia,
    MediaFile,
    MediaItem,
    MediaKind,
    MediaSendRequest,
    download_media,
    media_album,
    media_edit,
    media_request,
)
from ._aiogram.native_keyboards import ChatType, inline_keyboard, input_prompt, remove_keyboard, reply_keyboard
from ._aiogram.navigation import (
    MessageNavigation,
    NavigationResult,
    NavigationScreen,
    NavigationState,
    navigation_router,
)
from ._aiogram.platform_operations import (
    PlatformAction,
    PlatformContract,
    PlatformEvent,
    PlatformHooks,
    PlatformLookup,
    PlatformObserver,
    PlatformPermit,
    PlatformReceipt,
    PlatformResult,
    PlatformScope,
    SecretToken,
    StoryPhotoUpload,
    StoryVideoUpload,
    execute_platform_action,
    managed_bot_link,
    platform_contracts,
    platform_event,
    platform_events_router,
)
from ._aiogram.polls import (
    PollBinding,
    PollChoice,
    PollEvent,
    PollKind,
    PollLocator,
    PollLookup,
    PollObservation,
    PollObserver,
    PollOptionAddition,
    PollOptionState,
    PollSpec,
    PollState,
    PollVote,
    poll_events_router,
    poll_option_added,
    poll_request,
    poll_state,
    poll_vote,
)
from ._aiogram.profiles import (
    BotProfile,
    BotProfilePatch,
    ChatProfile,
    ProfileAuthorizer,
    ProfileEditIncomplete,
    ProfilePhotos,
    ProfilePhotoSize,
    ProfileSource,
    UserProfile,
    chat_profile,
    read_bot_profile,
    read_profile_photos,
    update_bot_profile,
    user_profile,
)
from ._aiogram.selection_ui import selection_keyboard, selection_router
from .errors import AuthenticationRequired, InvalidType, PatternError, TransportFailure, ValidationFailure
from .settings import BotSettings

__all__ = [
    "FSMSnapshot",
    "FSMConflict",
    "SnapshotStore",
    "AtomicFSMStorage",
    "SnapshotFSMStorage",
    "DialogLifetime",
    "Action",
    "ActionResult",
    "callback_router",
    "start_router",
    "CommandReply",
    "command_menu",
    "command_router",
    "create_bot",
    "run_bot",
    "stars_invoice",
    "ActionButton",
    "ButtonStyle",
    "MenuPage",
    "action_keyboard",
    "action_menu",
    "paginated_menu",
    "page_number",
    "FormSubmission",
    "InvalidField",
    "TextField",
    "text_form_router",
    "FieldValue",
    "NumberField",
    "EmailField",
    "PhoneField",
    "DateField",
    "FileField",
    "ContactField",
    "LocationField",
    "DialogSubmission",
    "dialog_form_router",
    "ChatType",
    "inline_keyboard",
    "reply_keyboard",
    "input_prompt",
    "remove_keyboard",
    "KeyboardLayout",
    "KeyboardCapabilities",
    "action_layout",
    "inline_layout",
    "reply_layout",
    "NavigationScreen",
    "NavigationState",
    "NavigationResult",
    "MessageNavigation",
    "navigation_router",
    "selection_keyboard",
    "selection_router",
    "calendar_keyboard",
    "time_slot_keyboard",
    "MediaKind",
    "MediaSendRequest",
    "MediaFile",
    "MediaItem",
    "DownloadedMedia",
    "media_request",
    "media_album",
    "media_edit",
    "download_media",
    "ProfileSource",
    "ProfileAuthorizer",
    "UserProfile",
    "ChatProfile",
    "ProfilePhotoSize",
    "ProfilePhotos",
    "BotProfile",
    "BotProfilePatch",
    "ProfileEditIncomplete",
    "user_profile",
    "chat_profile",
    "read_profile_photos",
    "read_bot_profile",
    "update_bot_profile",
    "InlineChatType",
    "InlineAuthorizer",
    "InlineSearchProvider",
    "InlineCachePolicy",
    "InlineItem",
    "InlinePage",
    "InlineSearch",
    "inline_articles",
    "inline_query_router",
    "PollKind",
    "PollChoice",
    "PollSpec",
    "PollOptionState",
    "PollState",
    "PollVote",
    "PollOptionAddition",
    "PollBinding",
    "PollLocator",
    "PollObservation",
    "PollEvent",
    "PollObserver",
    "PollLookup",
    "poll_request",
    "poll_state",
    "poll_vote",
    "poll_option_added",
    "poll_events_router",
    "PlatformContract",
    "PlatformScope",
    "PlatformPermit",
    "PlatformAction",
    "PlatformReceipt",
    "PlatformResult",
    "PlatformHooks",
    "SecretToken",
    "PlatformEvent",
    "PlatformLookup",
    "PlatformObserver",
    "platform_contracts",
    "execute_platform_action",
    "managed_bot_link",
    "platform_event",
    "platform_events_router",
    "StoryPhotoUpload",
    "StoryVideoUpload",
    "MethodSpec",
    "InvalidAPIRequest",
    "method_catalog",
    "build_request",
    "UpdatePhase",
    "UpdateTrace",
    "UpdateObserver",
    "update_kinds",
    "event_router",
]


@dataclass(frozen=True)
class Action:
    actor_id: int
    key: str


@dataclass(frozen=True)
class ActionResult:
    status: Literal["accepted", "denied", "stale", "replayed"]
    text: str


def callback_router(
    execute: Callable[[Action], Awaitable[ActionResult]],
    notify: Callable[[CallbackQuery, ActionResult], Awaitable[None]],
    *,
    prefix: str = "act:",
) -> Router:
    """ACK first; execute enforces object owner/version/idempotence itself.

    notify chooses a safe response channel including inline/inaccessible cases.
    Errors propagate to the application's error handling, after ACK.
    """
    _callback_data("k", prefix)
    router = Router()

    @router.callback_query(F.data.startswith(prefix))
    async def handle(query: CallbackQuery) -> None:
        await query.answer()  # Spinner ACK; no assertion of business success.
        key = (query.data or "")[len(prefix) :]
        try:
            _callback_data(key, prefix)
        except ValueError:
            await notify(query, ActionResult("stale", "Кнопка недействительна. Откройте актуальное меню."))
            return
        result = await execute(Action(actor_id=query.from_user.id, key=key))
        await notify(query, result)

    return router


def start_router(text: str, keyboard: InlineKeyboardMarkup | None = None) -> Router:
    """Small stateless /start, with plain text independent of global parse mode."""
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(text, parse_mode=None, reply_markup=keyboard)

    return router


@dataclass(frozen=True, slots=True)
class CommandReply:
    """One stateless plain-text command; no implied authorization or dialog."""

    command: str
    description: str
    text: str
    keyboard: InlineKeyboardMarkup | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, str) or not re.fullmatch(r"[a-z0-9_]{1,32}", self.command):
            raise ValidationFailure(
                "Command must contain 1..32 lowercase ASCII letters/digits/underscores, without '/'"
            )
        if not isinstance(self.description, str) or not self.description.strip() or len(self.description) > 256:
            raise ValidationFailure("Command description must contain 1..256 characters")
        try:
            valid_text = (
                isinstance(self.text, str)
                and bool(self.text.strip())
                and len(self.text.encode('utf-16-le')) // 2 <= 4096
            )
        except UnicodeError:
            valid_text = False
        if not valid_text:
            raise ValidationFailure("Command reply must contain nonempty plain text up to 4096 UTF-16 units")
        if self.keyboard is not None and not isinstance(self.keyboard, InlineKeyboardMarkup):
            raise InvalidType("Use InlineKeyboardMarkup for command keyboard")


def _commands(commands: Sequence[CommandReply]) -> tuple[CommandReply, ...]:
    replies = tuple(commands)
    if not replies or len(replies) > 100 or any(not isinstance(item, CommandReply) for item in replies):
        raise ValidationFailure("Use 1..100 CommandReply items")
    if len({item.command for item in replies}) != len(replies):
        raise ValidationFailure("Command names must be unique")
    return replies


def command_menu(commands: Sequence[CommandReply]) -> list[BotCommand]:
    """Requests only; caller explicitly chooses setMyCommands scope/language."""
    return [BotCommand(command=item.command, description=item.description) for item in _commands(commands)]


def command_router(commands: Sequence[CommandReply]) -> Router:
    """Attach to the existing Dispatcher; Command preserves bot-mention filtering."""
    router = Router()

    def responder(reply: CommandReply) -> Callable[[Message], Awaitable[None]]:
        text = reply.text
        keyboard = reply.keyboard.model_copy(deep=True) if reply.keyboard is not None else None

        async def handle(message: Message) -> None:
            await message.answer(text, parse_mode=None, reply_markup=keyboard)

        return handle

    for reply in _commands(commands):
        router.message.register(responder(reply), Command(reply.command))
    return router


def create_bot(settings: BotSettings, *, session: BaseSession | None = None) -> Bot:
    """Bot for these settings; test_environment targets https://api.telegram.org/bot<token>/test/<method>.

    The Telegram test environment is separate: it needs its own account and a bot made with its @BotFather.
    A supplied session must already target it (api=aiogram.client.telegram.TEST); it is never rewritten.
    """
    if not isinstance(settings, BotSettings):
        raise InvalidType("Use BotSettings")
    if settings.test_environment:
        if session is None:
            session = AiohttpSession(api=TEST)
        elif '/test/' not in session.api.base:
            raise ValidationFailure("Test environment needs a session created with api=aiogram.client.telegram.TEST")
    return Bot(token=settings.token, session=session)


async def run_bot(
    dispatcher: Dispatcher,
    settings: BotSettings,
    *,
    commands: Sequence[BotCommand] | None = None,
    session: BaseSession | None = None,
    workflow_data: Mapping[str, Any] | None = None,
    polling_timeout: int = 10,
    handle_signals: bool = True,
    handle_as_tasks: bool = True,
    tasks_concurrency_limit: int | None = None,
    shutdown_timeout: float = 10.0,
    verify_token: bool = True,
) -> None:
    """One polling bot; owns/always closes its session after successful preflight.

    No webhook deletion or update dropping. Commands=None preserves existing menu;
    an explicit list replaces DEFAULT scope menu. Use SDK directly for other scopes.
    SDK polling ACK is not a durable acceptance/transaction guarantee.
    verify_token=True calls getMe first: a rejected token raises AuthenticationRequired
    and an unreachable API TransportFailure, before menus or polling, without the token.
    settings.test_environment uses the separate Telegram test environment; a supplied
    session must then already target it (api=aiogram.client.telegram.TEST).
    """
    if not isinstance(dispatcher, Dispatcher) or not isinstance(settings, BotSettings):
        raise InvalidType("Use the existing Dispatcher and BotSettings")
    if type(polling_timeout) is not int or polling_timeout <= 0:
        raise ValidationFailure("Polling timeout must be a positive integer")
    if type(handle_signals) is not bool or type(handle_as_tasks) is not bool or type(verify_token) is not bool:
        raise ValidationFailure("Polling flags must be bool")
    if tasks_concurrency_limit is not None and (
        type(tasks_concurrency_limit) is not int or tasks_concurrency_limit <= 0
    ):
        raise ValidationFailure("Concurrency limit must be a positive integer")
    if type(shutdown_timeout) not in {int, float} or not math.isfinite(shutdown_timeout) or shutdown_timeout <= 0:
        raise ValidationFailure("Shutdown timeout must be positive and finite")
    data = dict(workflow_data or {})
    reserved = {
        'bot',
        'bots',
        'dispatcher',
        'close_bot_session',
        'handle_signals',
        'handle_as_tasks',
        'polling_timeout',
        'tasks_concurrency_limit',
        'backoff_config',
        'allowed_updates',
    }
    if reserved.intersection(data):
        raise ValidationFailure("Workflow data must not override SDK polling parameters")
    menu = list(commands) if commands is not None else None
    if menu is not None and (len(menu) > 100 or any(not isinstance(item, BotCommand) for item in menu)):
        raise ValidationFailure("Use up to 100 BotCommand items")
    bot = create_bot(settings, session=session)
    try:
        if verify_token:
            failure: PatternError | None = None
            try:
                await bot.me()  # cached: start_polling does not repeat getMe
            except TelegramUnauthorizedError:
                failure = AuthenticationRequired(
                    'Telegram test environment rejected the bot token: it is separate from the main one, '
                    'create a test bot with @BotFather from a test account'
                    if settings.test_environment
                    else 'Telegram rejected the bot token: check BOT_TOKEN or issue a new one with @BotFather'
                )
            except TelegramNetworkError:
                failure = TransportFailure('Telegram Bot API is unreachable: check the network, proxy or API server')
            if failure is not None:
                raise failure  # outside the handler: the SDK error may carry the token URL
        if menu is not None:
            await bot.set_my_commands(menu)
        polling = asyncio.create_task(
            dispatcher.start_polling(
                bot,
                close_bot_session=False,
                polling_timeout=polling_timeout,
                handle_signals=handle_signals,
                handle_as_tasks=handle_as_tasks,
                tasks_concurrency_limit=tasks_concurrency_limit,
                **data,
            )
        )
        try:
            # Cancelling SDK's outer task directly can orphan its polling children.
            await asyncio.shield(polling)
        except asyncio.CancelledError:
            stopping = asyncio.create_task(dispatcher.stop_polling())
            try:
                # Startup failure can complete polling without setting SDK's
                # stopped signal. Race both tasks rather than wait indefinitely.
                await asyncio.wait({polling, stopping}, timeout=shutdown_timeout, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (polling, stopping):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(polling, stopping, return_exceptions=True)
            raise
    finally:
        await bot.session.close()


def stars_invoice(
    title: str, description: str, payload: str, stars: int, *, monthly_subscription: bool = False
) -> CreateInvoiceLink:
    """Construct a request; consent, order validation and grant are server duties."""
    if not isinstance(title, str) or not 1 <= len(title) <= 32:
        raise ValidationFailure("Title must contain 1..32 characters")
    if not isinstance(description, str) or not 1 <= len(description) <= 255:
        raise ValidationFailure("Description must contain 1..255 characters")
    if not isinstance(payload, str) or not 1 <= len(payload.encode("utf-8")) <= 128:
        raise ValidationFailure("Payload must contain 1..128 bytes")
    if type(stars) is not int or stars <= 0 or (monthly_subscription and stars > 10000):
        raise ValidationFailure("Invalid Stars amount")
    return CreateInvoiceLink(
        title=title,
        description=description,
        payload=payload,
        currency="XTR",
        provider_token="",
        prices=[LabeledPrice(label=title, amount=stars)],
        subscription_period=2592000 if monthly_subscription else None,
    )
