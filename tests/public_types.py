"""Static consumer of installed wheel: positive and expected negative type cases."""
from telegram_patterns import Maturity, VerificationLevel, RecipeCatalog, ErrorReport, OperationKind, safe_error_report
from telegram_patterns import AsyncTransport, OnceStore, ProviderAdapter, RefundProvider, SQLiteOnce
from telegram_patterns import StarterComponent, StarterPlan, StarterConflict, starter_components, create_starter
from telegram_patterns import RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline
import sqlite3
from telegram_patterns.aiogram import ActionButton, ButtonStyle, ChatType, UpdatePhase, action_menu

maturity: Maturity = 'experimental'
verification: VerificationLevel = 'sdk'
style: ButtonStyle = 'primary'
context: ChatType = 'private'
phase: UpdatePhase = 'handled'

recipes = RecipeCatalog().search(maturity=maturity, verification=verification)
markup = action_menu([ActionButton('Open', 'open', style=style)])
operation: OperationKind = 'write'
report: ErrorReport = safe_error_report(TimeoutError(), operation=operation)
store: OnceStore[sqlite3.Connection] = SQLiteOnce('fixture.sqlite')
component: StarterComponent = starter_components('bot')[0]
plan: StarterPlan = create_starter('new-project',library='supplied.whl',components=['text-form'],dry_run=True)
selected: tuple[str, ...] = plan.components
execution: RecipeRunPlan = plan_recipe('demo-recovery')
offline_checks: tuple[str, ...] = RecipeRunResult('demo-recovery', '0.13.0', 'sqlite', ('sqlite-one-effect',)).checks
offline_ready: bool = execution.offline_ready

# warn_unused_ignores ensures these are actually rejected by installed types.
bad_maturity: Maturity = 'sdk'  # type: ignore[assignment]
bad_phase: UpdatePhase = 'clicked'  # type: ignore[assignment]
bad_style: ButtonStyle = 'red'  # type: ignore[assignment]
bad_filter = RecipeCatalog().search(maturity='sdk')  # type: ignore[arg-type]
bad_operation: OperationKind = 'retry'  # type: ignore[assignment]
bad_recovery = safe_error_report(RuntimeError(), operation='retry')  # type: ignore[arg-type]
bad_store: OnceStore[sqlite3.Connection] = object()  # type: ignore[assignment]
bad_execution: RecipeRunPlan = object()  # type: ignore[assignment]
bad_recipe_run = run_recipe_offline('demo-recovery', timeout='fast')  # type: ignore[arg-type]

# Structured dialogs preserve public consumer types without importing internals.
from telegram_patterns.aiogram import FieldValue, NumberField, ContactField, DialogSubmission, dialog_form_router
from aiogram import Router
from typing import Mapping
dialog_value: FieldValue = {'latitude': 52.2, 'longitude': 21.0, 'horizontal_accuracy': None}
dialog_submission = DialogSubmission(100, 42, 42, 'fixture-intent', {'number': '12.5', 'location': dialog_value})
dialog_snapshot: Mapping[str, FieldValue] = dialog_submission.values
dialog_json: dict[str, FieldValue] = dialog_submission.as_dict()
async def dialog_service(submission: DialogSubmission) -> str:
    return 'Consumer type fixture'
dialog_router: Router = dialog_form_router([NumberField('number', 'Number', 'Number?'), ContactField('contact', 'Contact', 'Contact?')], dialog_service)
bad_dialog_value: FieldValue = 1.0  # type: ignore[assignment]
bad_dialog_submit = dialog_form_router([NumberField('n', 'N', 'N?')], lambda submission: 'sync')  # type: ignore[arg-type,return-value]

from telegram_patterns import EntityKind, TextEntity, TextPayload, FormattedText, MessageBuilder, utf16_length, escape_html, escape_markdown_v2, split_formatted
entity_kind: EntityKind = 'bold'
formatted: FormattedText = MessageBuilder().text('😀 ').style('literal',entity_kind).build()
message_payload: TextPayload = formatted.as_kwargs()
message_parts: tuple[FormattedText, ...] = split_formatted(formatted)
message_entity: TextEntity = TextEntity('bold',3,7)
units: int = utf16_length(formatted.text)
html_literal: str = escape_html('<b>')
md_literal: str = escape_markdown_v2(')\\',context='link')
bad_entity_kind: EntityKind = 'HTML'  # type: ignore[assignment]
bad_message_builder = MessageBuilder().append('raw')  # type: ignore[arg-type]
bad_markdown_context = escape_markdown_v2('x',context='HTML')  # type: ignore[arg-type]

# Media public exports retain typed sources and SDK requests.
from telegram_patterns.aiogram import MediaKind, MediaSendRequest, MediaFile, MediaItem, DownloadedMedia, media_request, media_album, media_edit, download_media
from aiogram import Bot
media_kind: MediaKind = 'photo'
media_source = MediaFile(media_kind, b'host-approved-bytes', filename='photo.png')
media_item = MediaItem(media_source, MessageBuilder().text('Literal caption').build())
media_send: MediaSendRequest = media_request(media_item,bot_id=100,chat_id=42)
media_group = media_album([media_item,media_item],bot_id=100,chat_id=42)
media_replacement = media_edit(media_item,bot_id=100,chat_id=42,message_id=1)
async def media_consumer(bot: Bot) -> DownloadedMedia:
    return await download_media(bot,'host-observed-id',max_bytes=100)
bad_media_kind: MediaKind = 'animation'  # type: ignore[assignment]
bad_media_source = MediaFile('photo',123,filename='x')  # type: ignore[arg-type]
bad_media_caption = MediaItem(media_source,'raw markdown')  # type: ignore[arg-type]
bad_media_request = media_request('raw request',bot_id=100,chat_id=42)  # type: ignore[arg-type]

# Profile snapshots, async current ACL and explicit own-bot patch.
from telegram_patterns.aiogram import ProfileSource, ProfileAuthorizer, UserProfile, ChatProfile, ProfilePhotoSize, ProfilePhotos, BotProfile, BotProfilePatch, ProfileEditIncomplete, user_profile, chat_profile, read_profile_photos, read_bot_profile, update_bot_profile
from aiogram.types import User, ChatFullInfo
profile_source: ProfileSource = 'update'
profile_user: UserProfile = user_profile(User(id=42,is_bot=False,first_name='Fixture'),source=profile_source)
async def profile_acl(actor_id: int, bot_id: int, method: str) -> bool:
    return actor_id==42 and bot_id==100 and method in ('read','setMyDescription')
profile_authorizer: ProfileAuthorizer = profile_acl
async def profile_consumer(bot: Bot, native: ChatFullInfo) -> BotProfile:
    snapshot: ChatProfile = chat_profile(native)
    page: ProfilePhotos = await read_profile_photos(bot,profile_user.id)
    current: BotProfile = await read_bot_profile(bot,language_code='ru')
    return await update_bot_profile(bot,BotProfilePatch(description='New'),actor_id=42,authorize=profile_authorizer,language_code='ru')
profile_size = ProfilePhotoSize(100,42,'opaque','unique',100,100)
profile_incomplete = ProfileEditIncomplete(('setMyName',),'setMyDescription')
bad_profile_source: ProfileSource = 'MTProto'  # type: ignore[assignment]
bad_profile_patch = BotProfilePatch(description=False)  # type: ignore[arg-type]
bad_profile_acl: ProfileAuthorizer = lambda actor, bot_id, method: True  # type: ignore[assignment,return-value]

# Inline search and modern polls through the optional public API.
from aiogram.types import InlineQuery, Message, Poll, PollAnswer
from telegram_patterns.aiogram import (InlineChatType, InlineAuthorizer, InlineSearchProvider, InlineCachePolicy,
    InlineItem, InlinePage, InlineSearch, inline_articles, inline_query_router, PollKind, PollChoice, PollSpec,
    PollOptionState, PollState, PollVote, PollOptionAddition, PollBinding, PollLocator, PollObservation,
    PollEvent, PollObserver, PollLookup, poll_request, poll_state, poll_vote, poll_option_added, poll_events_router)
inline_context: InlineChatType = 'sender'
inline_item = InlineItem('a','A','Shareable',shareable=True)
inline_search = InlineSearch([inline_item],secret=b'host-persistent-typechecking-key32',revision='v1',cache=InlineCachePolicy())
async def inline_acl(actor: int, item: InlineItem) -> bool: return actor==42
inline_authorizer: InlineAuthorizer = inline_acl
async def inline_provider(query: InlineQuery) -> InlineSearch: return inline_search
inline_search_provider: InlineSearchProvider = inline_provider
async def inline_consumer(query: InlineQuery) -> InlinePage:
    page = await inline_search.page(query,bot_id=100,authorize=inline_authorizer)
    articles = inline_articles(page)
    request = page.answer_request(query,bot_id=100)
    return page
inline_router = inline_query_router(inline_search_provider,authorize=inline_authorizer)
poll_kind: PollKind = 'quiz'
poll_spec = PollSpec('Even numbers',[PollChoice('2'),'3','4'],kind=poll_kind,correct_option_ids=[0,2],allows_multiple_answers=True)
poll_send = poll_request(poll_spec,chat_id=42)
poll_binding = PollBinding(100,'poll',42,10,False,'regular')
async def poll_lookup(locator: PollLocator) -> PollBinding | None: return poll_binding
async def poll_observer(event: PollEvent) -> None: pass
poll_lookup_host: PollLookup = poll_lookup
poll_observer_host: PollObserver = poll_observer
poll_router = poll_events_router(poll_lookup_host,poll_observer_host)
def poll_consumer(native: Poll, answer: PollAnswer, message: Message) -> PollObservation:
    state: PollState = poll_state(native)
    option: PollOptionState = state.options[0]
    vote: PollVote = poll_vote(answer)
    addition: PollOptionAddition = poll_option_added(message)
    return vote
bad_inline_context: InlineChatType = 'backend'  # type: ignore[assignment]
bad_inline_item = InlineItem('a','A','Text',shareable='yes')  # type: ignore[arg-type]
bad_inline_acl: InlineAuthorizer = lambda actor,item: True  # type: ignore[assignment,return-value]
bad_poll_kind: PollKind = 'survey'  # type: ignore[assignment]
bad_poll_spec = PollSpec('Q',['A'],correct_option_ids=['0'])  # type: ignore[list-item]
bad_poll_observer: PollObserver = lambda event: None  # type: ignore[assignment,return-value]

# Scoped native platform operations preserve existing Bot/Dispatcher and host hooks.
from aiogram.methods import CreateForumTopic
from telegram_patterns.aiogram import (PlatformContract, PlatformScope, PlatformPermit, PlatformAction,
    PlatformReceipt, PlatformResult, PlatformHooks, SecretToken, PlatformEvent, PlatformLookup,
    PlatformObserver, StoryPhotoUpload, StoryVideoUpload, platform_contracts, execute_platform_action,
    managed_bot_link, platform_event, platform_events_router)
platform_scope = PlatformScope(100,42,'typed-topic',chat_id=-100)
platform_action = PlatformAction(platform_scope,CreateForumTopic(chat_id=-100,name='Topic'))
platform_contract: PlatformContract = platform_contracts()[0]
class TypedPlatformHost:
    async def authorize(self, action: PlatformAction) -> PlatformPermit:
        return PlatformPermit(allowed=False)
    async def claim(self, action: PlatformAction, permit: PlatformPermit) -> bool:
        return False
    async def record(self, action: PlatformAction, receipt: PlatformReceipt) -> None:
        pass
platform_hooks: PlatformHooks = TypedPlatformHost()
async def platform_consumer(bot: Bot) -> PlatformResult:
    result: PlatformResult = await execute_platform_action(bot,platform_action,platform_hooks)
    return result
async def platform_lookup(event: PlatformEvent) -> PlatformScope | None:
    return platform_scope
async def platform_observer(event: PlatformEvent, scope: PlatformScope) -> None:
    pass
platform_lookup_host: PlatformLookup = platform_lookup
platform_observer_host: PlatformObserver = platform_observer
platform_router = platform_events_router(platform_lookup_host,platform_observer_host)
bad_platform_scope = PlatformScope('bot',42,'typed')  # type: ignore[arg-type]
bad_platform_permit = PlatformPermit(allowed='yes')  # type: ignore[arg-type]
bad_platform_lookup: PlatformLookup = lambda event: platform_scope  # type: ignore[assignment,return-value]
