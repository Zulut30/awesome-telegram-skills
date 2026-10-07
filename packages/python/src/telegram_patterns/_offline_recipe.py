"""Private installed worker for known synthetic cookbook fixtures; no live mode."""

from __future__ import annotations

import io
import ipaddress
import json
import runpy
import sys
from contextlib import redirect_stdout
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .execution import plan_recipe
from .recipes import RecipeCatalog

_FIXTURES = {
    'demo-catalog': ('bot.py', 'offline_bot.py'),
    'demo-form': ('form_bot.py', 'offline_form.py'),
    'demo-keyboards': ('keyboards_bot.py', 'offline_keyboards.py'),
    'demo-navigation': ('navigation_bot.py', 'offline_navigation.py'),
    'demo-selection': ('selection_bot.py', 'offline_selection.py'),
    'demo-calendar': ('calendar_bot.py', 'offline_calendar.py'),
    'demo-dialog-restart': ('dialog_restart_bot.py', 'offline_dialog_restart.py'),
    'demo-dialog-fields': ('dialog_fields_bot.py', 'offline_dialog_fields.py'),
    'demo-message-text': ('message_text_bot.py', 'offline_message_text.py'),
    'demo-media': ('media_bot.py', 'offline_media.py'),
    'demo-profiles': ('profiles_bot.py', 'offline_profiles.py'),
    'demo-inline-search': ('inline_search_bot.py', 'offline_inline_search.py'),
    'demo-polls': ('polls_bot.py', 'offline_polls.py'),
    'demo-platform': ('platform_bot.py', 'offline_platform.py'),
    'demo-ai-stream': ('ai_stream_bot.py', 'offline_ai_stream.py'),
    'demo-rich-message': ('rich_message_bot.py', 'offline_rich_message.py'),
    'demo-ephemeral': ('ephemeral_bot.py', 'offline_ephemeral.py'),
    'demo-community': ('community_bot.py', 'offline_community.py'),
    'demo-stars-subscription': ('stars_subscription_bot.py', 'offline_stars_subscription.py'),
    'demo-guest-reply': ('guest_bot.py', 'offline_guest.py'),
    'demo-bot-relay': ('bot_relay_bot.py', 'offline_bot_relay.py'),
    'demo-live-photo': ('live_photo_bot.py', 'offline_live_photo.py'),
    'demo-join-query': ('join_query_bot.py', 'offline_join_query.py'),
    'demo-poll-media': ('poll_media_bot.py', 'offline_poll_media.py'),
    'demo-recovery': ('error_recovery.py',),
    'ptb-demo-catalog': ('ptb_catalog_bot.py', 'offline_ptb_catalog.py'),
    'ptb-demo-selection': ('ptb_selection_bot.py', 'offline_ptb_selection.py'),
    'ptb-demo-message-text': ('ptb_message_text_bot.py', 'offline_ptb_message_text.py'),
    'ptb-demo-rich-message': ('ptb_rich_message_bot.py', 'offline_ptb_rich_message.py'),
    'ptb-demo-ephemeral': ('ptb_ephemeral_bot.py', 'offline_ptb_ephemeral.py'),
    'ptb-demo-stars-subscription': ('ptb_stars_subscription_bot.py', 'offline_ptb_stars_subscription.py'),
    'ptb-demo-community': ('ptb_community_bot.py', 'offline_ptb_community.py'),
    'ptb-demo-join-query': ('ptb_join_query_bot.py', 'offline_ptb_join_query.py'),
    'ptb-demo-recovery': ('ptb_recovery_bot.py', 'offline_ptb_recovery.py'),
}
_ATTEMPTS = [0]
_AUDIT_INSTALLED = False


def _install_guards(*, sdk: bool, ptb: bool = False) -> list[int]:
    global _AUDIT_INSTALLED
    # Local socketpair activity used by asyncio is permitted; external DNS/connect
    # and every real aiogram HTTP transport are denied before any fixture runs.
    attempts = _ATTEMPTS

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event not in {'socket.connect', 'socket.getaddrinfo'}:
            return
        address = (
            args[1][0]
            if event == 'socket.connect' and isinstance(args[1], tuple)
            else args[0]
            if event == 'socket.getaddrinfo'
            else None
        )
        if address in {'localhost', '127.0.0.1', '::1', None}:
            return
        try:
            if ipaddress.ip_address(address).is_loopback:
                return
        except ValueError:
            pass
        attempts[0] += 1
        raise RuntimeError('External network is unavailable in offline recipes')

    if not _AUDIT_INSTALLED:
        sys.addaudithook(audit)
        _AUDIT_INSTALLED = True
    if sdk:
        from aiogram.client.session.aiohttp import AiohttpSession

        async def no_http(*args: Any, **kwargs: Any) -> Any:
            attempts[0] += 1
            raise RuntimeError('Real Telegram HTTP transport is unavailable')

        AiohttpSession.make_request = no_http  # type: ignore[method-assign]
    if ptb:
        from telegram.request import HTTPXRequest

        async def no_ptb_http(*args: Any, **kwargs: Any) -> Any:
            attempts[0] += 1
            raise RuntimeError('Real Telegram HTTP transport is unavailable')

        HTTPXRequest.do_request = no_ptb_http  # type: ignore[method-assign]
    return attempts


def _execute(recipe_id: str) -> dict[str, Any]:
    plan = plan_recipe(recipe_id)
    if not plan.offline_ready:
        raise RuntimeError('Offline prerequisites failed')
    catalog = RecipeCatalog()
    recipe = catalog.get(recipe_id)
    ptb = recipe.sdk == 'python-telegram-bot'
    attempts = _install_guards(sdk=plan.kind not in {'sqlite', 'ptb-markup', 'application'}, ptb=ptb)
    checks: list[str] = []
    if plan.kind == 'sdk-request':
        from aiogram.types import BufferedInputFile

        from ._aiogram.api import build_request

        def materialize(value: Any) -> Any:
            if isinstance(value, dict):
                if set(value) == {'__fixture_file__'}:
                    return BufferedInputFile(b'OFFLINE_FIXTURE_NOT_REAL_MEDIA', filename='fixture.bin')
                return {k: materialize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [materialize(v) for v in value]
            return value

        fixtures = json.loads(
            files('telegram_patterns').joinpath('resources/request-fixtures.json').read_text(encoding='utf-8')
        )['methods']
        method = recipe_id.removeprefix('api.')
        request = build_request(method, materialize(fixtures[method]))
        assert request.__api_method__ == method
        checks.append('sdk-request:' + method)
    elif plan.kind == 'sdk-markup':
        from aiogram.types import (
            ForceReply,
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            KeyboardButton,
            ReplyKeyboardMarkup,
            ReplyKeyboardRemove,
        )

        from ._aiogram.keyboard_layouts import KeyboardLayout, inline_layout
        from ._aiogram.native_keyboards import inline_keyboard, input_prompt, remove_keyboard, reply_keyboard

        preview = recipe.preview
        assert preview is not None
        markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ForceReply | ReplyKeyboardRemove
        if 'inline_keyboard' in preview:
            widths = {'two-columns': (2,), 'three-columns': (3,), 'mixed-rows': (1, 2, 3)}
            if recipe_id in widths:
                buttons = [InlineKeyboardButton.model_validate(b) for row in preview['inline_keyboard'] for b in row]
                markup = inline_layout(buttons, KeyboardLayout(widths[recipe_id]))
                checks.append('native-layout-pattern')
            else:
                markup = inline_keyboard(
                    [[InlineKeyboardButton.model_validate(b) for b in row] for row in preview['inline_keyboard']]
                )
        elif 'keyboard' in preview:
            markup = reply_keyboard(
                [[KeyboardButton.model_validate(b) for b in row] for row in preview['keyboard']],
                placeholder=preview.get('input_field_placeholder'),
                one_time=bool(preview.get('one_time_keyboard')),
            )
        elif 'force_reply' in preview:
            markup = input_prompt(preview.get('input_field_placeholder'))
        elif 'remove_keyboard' in preview:
            markup = remove_keyboard()
        else:
            raise RuntimeError('Unknown markup fixture')
        assert markup.model_dump(mode='json', exclude_none=True) == preview
        checks.append('sdk-markup:' + recipe_id)
    elif plan.kind == 'ptb-markup':
        from .markup import force_reply_markup, inline_markup, remove_markup, reply_markup
        from .ptb import ptb_markup

        preview = recipe.preview
        assert preview is not None
        # Rebuild through the SDK-free checks, then python-telegram-bot: the wire JSON must not change.
        if 'inline_keyboard' in preview:
            core = inline_markup(preview['inline_keyboard'])
        elif 'keyboard' in preview:
            core = reply_markup(
                preview['keyboard'],
                placeholder=preview.get('input_field_placeholder'),
                one_time=bool(preview.get('one_time_keyboard')),
            )
        elif 'force_reply' in preview:
            core = force_reply_markup(preview.get('input_field_placeholder'))
        elif 'remove_keyboard' in preview:
            core = remove_markup()
        else:
            raise RuntimeError('Unknown markup fixture')
        assert core == preview and ptb_markup(core).to_dict() == preview
        checks.extend(('core-markup-json', 'ptb-markup:' + recipe_id))
    elif plan.kind in {'dispatcher', 'sqlite', 'application'}:
        supplied = _FIXTURES[recipe_id]
        with TemporaryDirectory(prefix='fixture-', dir=Path.cwd()) as folder:
            for name in supplied:
                (Path(folder) / name).write_bytes(
                    files('telegram_patterns').joinpath('resources/offline/' + name + '.txt').read_bytes()
                )
            original_path = sys.path[:]
            original_argv = sys.argv[:]
            sys.path.insert(0, folder)  # Only the freshly copied trusted bundle.
            sys.argv = [str(Path(folder) / supplied[-1])]  # Never forward runner/CLI arguments to a fixture.
            output = io.StringIO()
            try:
                with redirect_stdout(output):
                    runpy.run_path(str(Path(folder) / supplied[-1]), run_name='__main__')
            finally:
                sys.path[:] = original_path
                sys.argv[:] = original_argv
        evidence = json.loads(output.getvalue())
        assert evidence['passed'] is True and evidence['network'] is False
        if plan.kind == 'dispatcher':
            assert evidence['session_closed'] is True
            checks.extend(('dispatcher-composition', 'session-closed'))
            if recipe_id == 'demo-calendar':
                assert (
                    evidence['business_effects'] == 1 and evidence['durable_replay'] and evidence['owner_stale_guards']
                )
                checks.extend(('calendar-date-time-back', 'sqlite-slot-one-booking', 'durable-receipt-replay'))
            if recipe_id == 'demo-dialog-fields':
                assert (
                    evidence['business_effects'] == 1
                    and evidence['field_types'] == 7
                    and evidence['owner_step_guards']
                    and evidence['unknown_receipt_same_intent']
                )
                checks.extend(
                    ('seven-dialog-field-types', 'native-candidate-confirmation', 'same-intent-one-sqlite-effect')
                )
            if recipe_id == 'demo-dialog-restart':
                assert evidence['processes'] == 3 and evidence['business_effects'] == 1
                assert all(
                    evidence[k]
                    for k in (
                        'separate_process_restart',
                        'resumed_answers',
                        'original_deadline_preserved',
                        'operation_ids_match',
                        'expired_draft_removed',
                        'expired_pending_preserved',
                        'version_refused_without_reset',
                        'host_data_preserved',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(
                    ('three-process-restart', 'original-step-version-deadline', 'expired-pending-same-operation-id')
                )
            if recipe_id == 'demo-message-text':
                assert evidence['chunks'] > 1 and all(
                    evidence[k]
                    for k in (
                        'literal_injection',
                        'utf16_offsets',
                        'split_preserves_entities',
                        'explicit_parse_mode_none',
                        'emoji_capability_fallback',
                        'existing_dispatcher_preserved',
                        'private_context_guards',
                    )
                )
                checks.extend(
                    (
                        'literal-user-insertions',
                        'utf16-entities-lossless-partition',
                        'explicit-default-parse-mode-override',
                        'custom-emoji-fallback',
                    )
                )
            if recipe_id == 'demo-media':
                assert evidence['uploaded_parts'] == 5 and all(
                    evidence[k]
                    for k in (
                        'photo_document_album_edit',
                        'caption_entities',
                        'explicit_parse_mode_none',
                        'bounded_stream_download',
                        'private_context_guards',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(
                    ('photo-document-album-edit', 'literal-caption-default-override', 'bounded-content-stream')
                )
            if recipe_id == 'demo-profiles':
                assert evidence['photo_upload_bytes'] == 634 and all(
                    evidence[k]
                    for k in (
                        'unknown_fields_preserved',
                        'profile_photos',
                        'localized_omission_clear',
                        'fresh_method_acl',
                        'new_avatar_upload_removal',
                        'unknown_edit_reconciliation',
                        'private_context_guards',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(
                    (
                        'nullable-profile-observations',
                        'own-bot-per-method-acl',
                        'localized-omission-clear',
                        'new-avatar-upload-removal',
                        'explicit-unknown-edit-reconciliation',
                    )
                )
            if recipe_id == 'demo-inline-search':
                assert all(
                    evidence[key]
                    for key in (
                        'personal_cache',
                        'scoped_pagination',
                        'fresh_acl',
                        'private_items_excluded',
                        'unknown_answer_no_retry',
                        'existing_dispatcher_preserved',
                        'feedback_is_optional',
                    )
                )
                checks.extend(
                    ('shareable-only-personal-cache', 'scoped-fixed-expiry-cursor', 'fresh-host-acl-no-native-retry')
                )
            if recipe_id == 'demo-polls':
                assert all(
                    evidence[key]
                    for key in (
                        'modern_quiz',
                        'own_poll_binding',
                        'persistent_vote_ids',
                        'anonymous_limits',
                        'unknown_addition_not_guessed',
                        'durable_host_dedup',
                        'unknown_send_no_retry',
                        'fresh_acl',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(
                    (
                        'own-bot-modern-quiz',
                        'persistent-id-vote-retraction',
                        'unknown-association-not-guessed',
                        'host-sqlite-dedup-unknown-intent',
                    )
                )
            if recipe_id == 'demo-ai-stream':
                assert all(
                    evidence[key]
                    for key in (
                        'stop_closes_model_stream',
                        'stale_stop_ignored',
                        'one_generation_per_chat',
                        'bounded_queue',
                        'budget_checked_first',
                        'preview_429_paused',
                        'history_forget',
                        'prompt_not_logged',
                        'long_answer_split',
                        'shutdown_cancels',
                    )
                )
                checks.extend(
                    (
                        'draft-stream-stop-button',
                        'stop-closes-model-stream',
                        'bounded-queue-budget',
                        'final-message-split',
                    )
                )
            if recipe_id == 'demo-rich-message':
                assert all(
                    evidence[key]
                    for key in (
                        'sdk_wire_matches_builder',
                        'compact_table',
                        'collapsible_quote',
                        'details_block',
                        'document_block',
                        'button_row',
                        'fallback_text_and_keyboard',
                        'limits_enforced',
                        'callback_acknowledged',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('rich-blocks-sdk-wire', 'published-limits', 'text-fallback-keyboard'))
            if recipe_id == 'demo-ephemeral':
                assert evidence['ephemeral_answers'] == 2 and all(
                    evidence[key]
                    for key in (
                        'callback_query_named',
                        'replace_original',
                        'edit_by_reference',
                        'delete_by_reference',
                        'window_expired_alert',
                        'groups_only',
                        'callback_acknowledged',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('ephemeral-callback-answer', 'edit-delete-by-reference', 'fifteen-second-window'))
            if recipe_id == 'demo-community':
                assert (
                    evidence['joined_counted'] == 1
                    and evidence['community_id_bits'] > 32
                    and all(
                        evidence[key]
                        for key in (
                            'added_group',
                            'added_channel',
                            'bot_arrival_ignored',
                            'removed_without_fields',
                            'reconciled_from_get_chat',
                            'existing_dispatcher_preserved',
                        )
                    )
                )
                checks.extend(('community-service-messages', 'channel-post-events', 'get-chat-reconciliation'))
            if recipe_id == 'demo-stars-subscription':
                assert all(
                    evidence[key]
                    for key in (
                        'monthly_invoice',
                        'checkout_grants_nothing',
                        'charge_grants_period',
                        'renewal_extends',
                        'duplicate_ignored',
                        'canceled_keeps_paid_month',
                        'failed_notifies_and_expires',
                        'refund_withdraws_its_month',
                        'state_round_trips_json',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('stars-subscription-charges', 'bot-subscription-updated', 'refund-withdraws-charge'))
            if recipe_id == 'demo-guest-reply':
                assert evidence['guest_answers'] == 2 and all(
                    evidence[key]
                    for key in (
                        'reply_context_used',
                        'one_reply_per_query',
                        'separate_update_type',
                        'no_send_message_to_foreign_chat',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('guest-message-update', 'one-reply-per-query'))
            if recipe_id == 'demo-bot-relay':
                assert evidence['answers'] == 4 and all(
                    evidence[key]
                    for key in (
                        'dedup',
                        'pause_per_peer',
                        'depth_limit',
                        'endless_peer_bounded',
                        'self_ignored',
                        'person_resets',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('bot-to-bot-loop-guard', 'endless-peer-bounded'))
            if recipe_id == 'demo-live-photo':
                assert all(
                    evidence[key]
                    for key in (
                        'received_saved',
                        'missing_static_photo_refused',
                        'resent_by_file_id',
                        'album_of_live_photos',
                        'url_refused',
                        'upload_size_checked',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('live-photo-sdk-wire', 'live-photo-album', 'no-url-source'))
            if recipe_id == 'demo-join-query':
                assert all(
                    evidence[key]
                    for key in (
                        'mini_app_shown',
                        'signed_user_only',
                        'approve_once',
                        'decline_on_failed_check',
                        'stale_query_untouched',
                        'ordinary_request_ignored',
                        'queue_when_mini_app_fails',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('join-query-mini-app', 'signed-init-data', 'ten-second-window'))
            if recipe_id == 'demo-poll-media':
                assert evidence['option_media'] == 3 and all(
                    evidence[key]
                    for key in (
                        'description_media',
                        'explanation_media',
                        'link_only_in_options',
                        'explanation_needs_quiz',
                        'incoming_media_kinds',
                        'existing_dispatcher_preserved',
                    )
                )
                checks.extend(('poll-option-media', 'poll-media-types'))
            if recipe_id == 'demo-platform':
                assert (
                    evidence['families'] == 7 and evidence['contracts'] == 51 and evidence['confirmed_operations'] == 7
                )
                assert all(
                    evidence[key]
                    for key in (
                        'durable_intents',
                        'unknown_send_no_retry',
                        'current_actor_acl',
                        'fresh_native_rights',
                        'financial_quote_budget',
                        'scoped_event_dedup',
                        'existing_dispatcher_preserved',
                        'user_confirmed_managed_link',
                    )
                )
                checks.extend(
                    (
                        'seven-native-platform-families',
                        'current-method-rights-host-acl',
                        'sqlite-intent-budget-no-retry',
                        'scoped-event-dedup',
                    )
                )
        elif plan.kind == 'application':
            # Every claim a python-telegram-bot fixture prints is a checked boolean; the transport is closed.
            assert evidence['session_closed'] is True and evidence['sdk'] == 'python-telegram-bot'
            assert all(value is True for key, value in evidence.items() if isinstance(value, bool) and key != 'network')
            checks.extend(('ptb-application', 'stub-request-closed'))
        else:
            assert evidence['effect_count'] == 1 and evidence['replayed'] is True
            checks.extend(('sqlite-one-effect', 'same-key-replay'))
    else:
        raise RuntimeError('No offline executor for this reference')
    assert attempts[0] == 0
    return {
        'passed': True,
        'recipe_id': recipe_id,
        'library_version': plan.library_version,
        'kind': plan.kind,
        'checks': checks,
        'telegram_requests': False,
        'external_network_attempts': attempts[0],
    }


def main() -> None:
    if sys.argv[1] == '--all-python':
        reports = [
            _execute(r.id) for r in RecipeCatalog().recipes if r.execution and r.execution['kind'] != 'reference'
        ]
        print(json.dumps({'passed': True, 'recipes': len(reports), 'reports': reports, 'telegram_requests': False}))
    else:
        print(json.dumps(_execute(sys.argv[1])))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Offline verification needs assertions enabled')
    main()
