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
