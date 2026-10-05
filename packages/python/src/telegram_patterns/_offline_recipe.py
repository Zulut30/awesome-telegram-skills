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
