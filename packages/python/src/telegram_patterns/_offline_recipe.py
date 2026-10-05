"""Private installed worker for known synthetic cookbook fixtures; no live mode."""
from __future__ import annotations

from contextlib import redirect_stdout
from importlib.resources import files
import io
import ipaddress
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory

from .execution import plan_recipe
from .recipes import RecipeCatalog

_FIXTURES = {
    'demo-catalog': ('bot.py', 'offline_bot.py'),
    'demo-form': ('form_bot.py', 'offline_form.py'),
    'demo-keyboards': ('keyboards_bot.py', 'offline_keyboards.py'),
    'demo-navigation': ('navigation_bot.py', 'offline_navigation.py'),
    'demo-selection': ('selection_bot.py', 'offline_selection.py'),
    'demo-calendar': ('calendar_bot.py', 'offline_calendar.py'),
    'demo-dialog-fields': ('dialog_fields_bot.py', 'offline_dialog_fields.py'),
    'demo-message-text': ('message_text_bot.py', 'offline_message_text.py'),
    'demo-media': ('media_bot.py', 'offline_media.py'),
    'demo-profiles': ('profiles_bot.py', 'offline_profiles.py'),
    'demo-inline-search': ('inline_search_bot.py', 'offline_inline_search.py'),
    'demo-polls': ('polls_bot.py', 'offline_polls.py'),
    'demo-platform': ('platform_bot.py', 'offline_platform.py'),
    'demo-recovery': ('error_recovery.py',),
}
_ATTEMPTS = [0]
_AUDIT_INSTALLED = False


def _install_guards(*, sdk: bool) -> list[int]:
    global _AUDIT_INSTALLED
    # Local socketpair activity used by asyncio is permitted; external DNS/connect
    # and every real aiogram HTTP transport are denied before any fixture runs.
    attempts = _ATTEMPTS
    def audit(event: str, args: tuple) -> None:
        if event not in {'socket.connect', 'socket.getaddrinfo'}:
            return
        address = args[1][0] if event == 'socket.connect' and isinstance(args[1], tuple) else args[0] if event == 'socket.getaddrinfo' else None
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
        async def no_http(*args, **kwargs):
            attempts[0] += 1
            raise RuntimeError('Real Telegram HTTP transport is unavailable')
        AiohttpSession.make_request = no_http  # type: ignore[method-assign]
    return attempts


def _execute(recipe_id: str) -> dict:
    plan = plan_recipe(recipe_id)
    if not plan.offline_ready:
        raise RuntimeError('Offline prerequisites failed')
    attempts = _install_guards(sdk=plan.kind != 'sqlite')
    catalog = RecipeCatalog()
    recipe = catalog.get(recipe_id)
    checks = []
    if plan.kind == 'sdk-request':
        from aiogram.types import BufferedInputFile
        from .api import build_request
        def materialize(value):
            if isinstance(value, dict):
                if set(value) == {'__fixture_file__'}:
                    return BufferedInputFile(b'OFFLINE_FIXTURE_NOT_REAL_MEDIA', filename='fixture.bin')
                return {k: materialize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [materialize(v) for v in value]
            return value
        fixtures = json.loads(files('telegram_patterns').joinpath('resources/request-fixtures.json').read_text(encoding='utf-8'))['methods']
        method = recipe_id.removeprefix('api.')
        request = build_request(method, materialize(fixtures[method]))
        assert request.__api_method__ == method
        checks.append('sdk-request:' + method)
    elif plan.kind == 'sdk-markup':
        from aiogram.types import InlineKeyboardButton, KeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ForceReply, ReplyKeyboardRemove
        from .native_keyboards import inline_keyboard, reply_keyboard, input_prompt, remove_keyboard
        from .keyboard_layouts import KeyboardLayout, inline_layout
        preview = recipe.preview
        assert preview is not None
        markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ForceReply | ReplyKeyboardRemove
        if 'inline_keyboard' in preview:
            widths = {'two-columns':(2,), 'three-columns':(3,), 'mixed-rows':(1,2,3)}
            if recipe_id in widths:
                buttons = [InlineKeyboardButton.model_validate(b) for row in preview['inline_keyboard'] for b in row]
                markup = inline_layout(buttons,KeyboardLayout(widths[recipe_id]))
                checks.append('native-layout-pattern')
            else:
                markup = inline_keyboard([[InlineKeyboardButton.model_validate(b) for b in row] for row in preview['inline_keyboard']])
        elif 'keyboard' in preview:
            markup = reply_keyboard([[KeyboardButton.model_validate(b) for b in row] for row in preview['keyboard']],
                                    placeholder=preview.get('input_field_placeholder'), one_time=bool(preview.get('one_time_keyboard')))
        elif 'force_reply' in preview:
            markup = input_prompt(preview.get('input_field_placeholder'))
        elif 'remove_keyboard' in preview:
            markup = remove_keyboard()
        else:
            raise RuntimeError('Unknown markup fixture')
        assert markup.model_dump(mode='json', exclude_none=True) == preview
        checks.append('sdk-markup:' + recipe_id)
    elif plan.kind in {'dispatcher', 'sqlite'}:
        supplied = _FIXTURES[recipe_id]
        with TemporaryDirectory(prefix='fixture-', dir=Path.cwd()) as folder:
            for name in supplied:
                (Path(folder) / name).write_bytes(files('telegram_patterns').joinpath('resources/offline/' + name + '.txt').read_bytes())
            original_path = sys.path[:]
            sys.path.insert(0, folder)  # Only the freshly copied trusted bundle.
            output = io.StringIO()
            try:
                with redirect_stdout(output):
                    runpy.run_path(str(Path(folder) / supplied[-1]), run_name='__main__')
            finally:
                sys.path[:] = original_path
        evidence = json.loads(output.getvalue())
        assert evidence['passed'] is True and evidence['network'] is False
        if plan.kind == 'dispatcher':
            assert evidence['session_closed'] is True
            checks.extend(('dispatcher-composition', 'session-closed'))
            if recipe_id == 'demo-calendar':
                assert evidence['business_effects'] == 1 and evidence['durable_replay'] and evidence['owner_stale_guards']
                checks.extend(('calendar-date-time-back', 'sqlite-slot-one-booking', 'durable-receipt-replay'))
            if recipe_id == 'demo-dialog-fields':
                assert evidence['business_effects'] == 1 and evidence['field_types'] == 7 and evidence['owner_step_guards'] and evidence['unknown_receipt_same_intent']
                checks.extend(('seven-dialog-field-types', 'native-candidate-confirmation', 'same-intent-one-sqlite-effect'))
            if recipe_id == 'demo-message-text':
                assert evidence['chunks'] > 1 and all(evidence[k] for k in ('literal_injection', 'utf16_offsets', 'split_preserves_entities', 'explicit_parse_mode_none', 'emoji_capability_fallback', 'existing_dispatcher_preserved', 'private_context_guards'))
                checks.extend(('literal-user-insertions', 'utf16-entities-lossless-partition', 'explicit-default-parse-mode-override', 'custom-emoji-fallback'))
            if recipe_id == 'demo-media':
                assert evidence['uploaded_parts'] == 5 and all(evidence[k] for k in ('photo_document_album_edit','caption_entities','explicit_parse_mode_none','bounded_stream_download','private_context_guards','existing_dispatcher_preserved'))
                checks.extend(('photo-document-album-edit','literal-caption-default-override','bounded-content-stream'))
            if recipe_id == 'demo-profiles':
                assert evidence['photo_upload_bytes'] == 634 and all(evidence[k] for k in ('unknown_fields_preserved', 'profile_photos', 'localized_omission_clear', 'fresh_method_acl', 'new_avatar_upload_removal', 'unknown_edit_reconciliation', 'private_context_guards', 'existing_dispatcher_preserved'))
                checks.extend(('nullable-profile-observations', 'own-bot-per-method-acl', 'localized-omission-clear', 'new-avatar-upload-removal', 'explicit-unknown-edit-reconciliation'))
            if recipe_id == 'demo-inline-search':
                assert all(evidence[key] for key in ('personal_cache', 'scoped_pagination', 'fresh_acl', 'private_items_excluded', 'unknown_answer_no_retry', 'existing_dispatcher_preserved', 'feedback_is_optional'))
                checks.extend(('shareable-only-personal-cache', 'scoped-fixed-expiry-cursor', 'fresh-host-acl-no-native-retry'))
            if recipe_id == 'demo-polls':
                assert all(evidence[key] for key in ('modern_quiz', 'own_poll_binding', 'persistent_vote_ids', 'anonymous_limits', 'unknown_addition_not_guessed', 'durable_host_dedup', 'unknown_send_no_retry', 'fresh_acl', 'existing_dispatcher_preserved'))
                checks.extend(('own-bot-modern-quiz', 'persistent-id-vote-retraction', 'unknown-association-not-guessed', 'host-sqlite-dedup-unknown-intent'))
            if recipe_id == 'demo-platform':
                assert evidence['families'] == 7 and evidence['contracts'] == 51 and evidence['confirmed_operations'] == 7
                assert all(evidence[key] for key in ('durable_intents', 'unknown_send_no_retry', 'current_actor_acl', 'fresh_native_rights', 'financial_quote_budget', 'scoped_event_dedup', 'existing_dispatcher_preserved', 'user_confirmed_managed_link'))
                checks.extend(('seven-native-platform-families', 'current-method-rights-host-acl', 'sqlite-intent-budget-no-retry', 'scoped-event-dedup'))
        else:
            assert evidence['effect_count'] == 1 and evidence['replayed'] is True
            checks.extend(('sqlite-one-effect', 'same-key-replay'))
    else:
        raise RuntimeError('No offline executor for this reference')
    assert attempts[0] == 0
    return {'passed': True, 'recipe_id': recipe_id, 'library_version': plan.library_version,
            'kind': plan.kind, 'checks': checks, 'telegram_requests': False,
            'external_network_attempts': attempts[0]}


def main() -> None:
    if sys.argv[1] == '--all-python':
        reports = [_execute(r.id) for r in RecipeCatalog().recipes if r.execution and r.execution['kind'] != 'reference']
        print(json.dumps({'passed': True, 'recipes': len(reports), 'reports': reports, 'telegram_requests': False}))
    else:
        print(json.dumps(_execute(sys.argv[1])))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Offline verification needs assertions enabled')
    main()
