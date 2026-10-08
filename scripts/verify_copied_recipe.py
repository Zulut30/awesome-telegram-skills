"""Execute the Python recipes of an independently copied skill through the installed package.

    python scripts/verify_copied_recipe.py RECIPE COPIED_SKILL
    python scripts/verify_copied_recipe.py --list

A composition recipe takes the single fenced Python block of its guide in the copied skill's references, loads it
as the module that examples/python/offline_<name>.py imports, runs that offline scenario on a real Dispatcher and
checks the documented result. Reviewed compositions must equal examples/python/<module>.py byte for byte before
they run; their helper operations show in a temporary copy that missing, tampered and duplicated blocks are refused
without touching the caller's files. The keyboard and developer recipes run their blocks with direct assertions.
Every recipe prints one JSON report; nothing reaches Telegram.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
import runpy
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared helpers live next to this script
from _environment import minimal_environment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples/python'
BLOCK = re.compile(r'```python\n(.*?)```', re.S)


def blocks_of(path: Path) -> list[str]:
    return BLOCK.findall(path.read_text(encoding='utf-8'))


@dataclass(frozen=True)
class Composition:
    guide: str  # file under references/ of the copied skill
    module: str  # name the offline scenario imports; examples/python/<module>.py is the reviewed source
    accept: Callable[[dict], bool]  # documented result beyond passed, no network and a closed session
    scope: str
    reviewed: bool = False  # the block must equal the reviewed source; helper operations are reported
    processes: bool = False  # the scenario restarts processes, so it runs in a separate interpreter
    operations_accept: Callable[[dict], bool] = lambda result: True

    @property
    def offline(self) -> Path:
        return EXAMPLES / f"offline_{self.module.removesuffix('_bot')}.py"

    def composition(self, guide: Path) -> str:
        blocks = blocks_of(guide)
        if len(blocks) != 1:
            raise ValueError(f'Expected one complete {self.module} composition')
        if self.reviewed and blocks[0] != (EXAMPLES / f'{self.module}.py').read_text(encoding='utf-8'):
            raise ValueError(f'Copied {self.module} composition differs from the reviewed source')
        return blocks[0]

    def execute(self, guide: Path) -> dict:
        source = self.composition(guide)  # exact source check before compile/exec
        result = self.run_processes(source) if self.processes else self.run_here(source, guide)
        if (not result['passed'] or result['network'] or not result['session_closed'] or not self.accept(result)):
            raise ValueError(f'Copied {self.module} composition failed')
        return result

    def run_here(self, source: str, guide: Path) -> dict:
        module = ModuleType(self.module)
        exec(compile(source, str(guide), 'exec'), module.__dict__)
        original = sys.modules.get(self.module)
        sys.modules[self.module] = module
        captured = io.StringIO()
        try:
            with redirect_stdout(captured):
                runpy.run_path(str(self.offline), run_name='__main__')
        finally:
            if original is None:
                sys.modules.pop(self.module, None)
            else:
                sys.modules[self.module] = original
        return json.loads(captured.getvalue())

    def run_processes(self, source: str) -> dict:
        with tempfile.TemporaryDirectory(prefix='copied guide ') as folder:
            target = Path(folder)
            (target / f'{self.module}.py').write_text(source, encoding='utf-8')
            offline = target / self.offline.name
            offline.write_bytes(self.offline.read_bytes())
            environment = minimal_environment()
            environment['PYTHONUTF8'] = '1'
            bootstrap = ('import runpy,sys;from pathlib import Path;'
                         'p=Path(sys.argv[1]).resolve(strict=True);sys.path.insert(0,str(p.parent));'
                         'sys.argv=sys.argv[1:];runpy.run_path(str(p),run_name="__main__")')
            run = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap, str(offline)], cwd=target, env=environment,
                                 capture_output=True, text=True, encoding='utf-8', timeout=90, check=False)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr)
            return json.loads(run.stdout)

    def operations(self, guide: Path) -> dict:
        """Run the copied guide in a temporary skill copy and refuse broken copies of it."""
        text, source, cases = guide.read_text(encoding='utf-8'), self.composition(guide), []
        with tempfile.TemporaryDirectory(prefix='guide operations ') as folder:
            target = Path(folder) / 'copied skill' / 'references'
            target.mkdir(parents=True)
            marker = target.parent / 'host-owned.txt'
            marker.write_bytes(b'host-owned\x00\xff')
            owned = marker.read_bytes()
            copied = target / self.guide
            copied.write_text(text, encoding='utf-8')
            before = copied.read_bytes()
            if not self.operations_accept(self.execute(copied)):
                raise ValueError(f'Copied {self.module} composition failed in a temporary copy')
            if copied.read_bytes() != before or marker.read_bytes() != owned:
                raise AssertionError('The copied guide run changed caller files')
            executed = 'exact-copied-guide-executed' + ('-in-three-processes' if self.processes else '')
            cases.extend((executed, 'caller-files-byte-preserved'))
            for label, document in (
                ('missing-block-rejected', text.replace('```python\n' + source + '```', 'No composition')),
                ('tampered-block-rejected-before-execution', text.replace(source, 'raise RuntimeError("must not run")\n' + source)),
                ('duplicate-block-rejected', text + '\n```python\n' + source + '```\n'),
            ):
                copied.write_text(document, encoding='utf-8')
                before = copied.read_bytes()
                try:
                    self.composition(copied)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Invalid copied guide accepted: ' + label)
                if copied.read_bytes() != before or marker.read_bytes() != owned:
                    raise AssertionError('Refusing a copied guide changed caller files')
                cases.append(label)
        return {'passed': True, 'temporary_operations': cases, 'caller_files_preserved': True}

    def __call__(self, skill: Path) -> dict:
        guide = skill / 'references' / self.guide
        result = self.execute(guide)
        result['guide_blocks'] = 1
        if self.reviewed:
            result['composition_sha256'] = hashlib.sha256(self.composition(guide).encode()).hexdigest()
            result['helper_operations'] = self.operations(guide)
        result['scope'] = self.scope
        return result


def flags(*names: str) -> Callable[[dict], bool]:
    return lambda result: all(result[name] for name in names)


def keyboard(skill: Path) -> dict:
    """Keyboard recipes and layout, navigation, selection and calendar guides; every local link must resolve."""
    markdown = list(skill.rglob('*.md'))
    for file in markdown:
        for reference in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            if '://' in reference or reference.startswith('#'):
                continue
            target = (file.parent / reference.split('#')[0]).resolve()
            if not target.is_relative_to(skill) or not target.is_file():
                raise ValueError('Copied skill has an invalid local reference')

    def guide(name: str, count: int, *, optional: bool = True) -> tuple[list[str], dict]:
        path = skill / 'references' / name
        if optional and not path.exists():
            return [], {}
        found = blocks_of(path)
        if len(found) != count:
            raise ValueError(f'Update the recipe checker for changed blocks of {name}')
        namespace: dict = {}
        for block in found:
            exec(compile(block, str(path), 'exec'), namespace)
        return found, namespace

    blocks, namespace = guide('keyboard-recipes.md', 2, optional=False)
    if list(map(len, namespace['two'].inline_keyboard)) != [2, 2, 2]:
        raise ValueError('Two-column recipe failed')
    if list(map(len, namespace['three'].inline_keyboard)) != [3, 3]:
        raise ValueError('Three-column recipe failed')
    if namespace['request'].__api_method__ != 'sendMessage':
        raise ValueError('Request recipe failed')
    if namespace['confirm'].inline_keyboard[0][0].style != 'success':
        raise ValueError('Style recipe failed')
    if not namespace['prompt'].force_reply or not namespace['hidden'].remove_keyboard:
        raise ValueError('Input recipe failed')
    layout_blocks, layout = guide('keyboard-layouts.md', 2)
    if layout_blocks:
        if list(map(len, layout['mixed'].inline_keyboard)) != [2, 3, 1, 1]:
            raise ValueError('Mixed layout guide failed')
        if layout['unknown'].style is not None or layout['unknown'].icon_custom_emoji_id is not None:
            raise ValueError('Unknown presentation fallback failed')
        if layout['shown'].style != 'success':
            raise ValueError('Verified style guide failed')
    navigation_blocks, navigation_namespace = guide('message-navigation.md', 1)
    navigation = asyncio.run(navigation_check(navigation_namespace)) if navigation_blocks else None
    selection_blocks, selection_namespace = guide('selection-controls.md', 1)
    selection = asyncio.run(selection_check(selection_namespace)) if selection_blocks else None
    calendar_blocks, calendar = guide('calendar-slots.md', 1)
    if calendar_blocks:
        assert calendar['replay'].replayed and calendar['receipt'].value == calendar['replay'].value
        assert calendar['booking'].status == 'active'
        assert len(calendar['month'].allowed_dates) == 1
        assert calendar['calendar_markup'].inline_keyboard[0][0].callback_data == 'date:2026-10-25'
        assert 'UTC+02:00' in calendar['time_markup'].inline_keyboard[0][0].text
    return {'passed': True, 'network': False, 'markdown_files': len(markdown), 'python_blocks': len(blocks),
            'layout_guide_blocks': len(layout_blocks),
            'navigation_guide_blocks': len(navigation_blocks), 'navigation': navigation,
            'selection_guide_blocks': len(selection_blocks), 'selection': selection,
            'calendar_guide_blocks': len(calendar_blocks),
            'calendar': {'passed': True, 'file_sqlite_booking': True, 'durable_replay': True, 'dst_offsets': True,
                         'unavailable_date': True} if calendar_blocks else None,
            'methods': len(namespace['methods']),
            'scope': 'copied skill recipe execution; not independent agent decision evaluation'}


async def navigation_check(namespace: dict) -> dict:
    from aiogram import Bot, Dispatcher, Router
    from aiogram.filters import Command
    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
    from aiogram.types import Update
    from telegram_patterns.testing import StubSession

    menu, router = namespace['menu'], namespace['router']
    existing = Router()

    @existing.message(Command('help'))
    async def help(message):
        await message.answer('Existing help preserved', parse_mode=None)

    dispatcher = Dispatcher()
    dispatcher.include_router(existing)
    dispatcher.include_router(router)

    def reply(request):
        return {'message_id': 100 if isinstance(request, SendMessage) else request.message_id, 'date': 1,
                'chat': {'id': request.chat_id, 'type': 'private'}, 'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'},
                'text': request.text}

    session = StubSession().respond(SendMessage, reply).respond(EditMessageText, reply).respond(AnswerCallbackQuery, True)
    async with Bot('100:PORTABLE_NAVIGATION_FIXTURE', session=session) as bot:
        try:
            initial = await menu.open(bot, 42, 42)

            async def click(target, index, actor=42, revision=None):
                state = menu.get_state(bot.id, 42, 42)
                data = f'{menu.prefix}{state.session_id}:{state.revision if revision is None else revision}:{target}'
                update = Update.model_validate({'update_id': index, 'callback_query': {
                    'id': str(index), 'chat_instance': 'fixture', 'from': {'id': actor, 'is_bot': False, 'first_name': 'Actor'},
                    'data': data, 'message': {'message_id': state.message_id, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
                                              'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}}}}, context={'bot': bot})
                await dispatcher.feed_update(bot, update)

            await click('catalog', 1, actor=43)
            assert menu.get_state(bot.id, 42, 42) == initial
            await click('catalog', 2)
            assert menu.get_state(bot.id, 42, 42).history == ('home',)
            await click('delivery', 3)
            assert menu.get_state(bot.id, 42, 42).history == ('home', 'catalog')
            await click('_back', 4)
            assert menu.get_state(bot.id, 42, 42).screen == 'catalog'
            confirmed = menu.get_state(bot.id, 42, 42)
            await click('catalog', 5, revision=0)
            assert menu.get_state(bot.id, 42, 42) == confirmed
            await dispatcher.feed_update(bot, Update.model_validate({'update_id': 6, 'message': {
                'message_id': 20, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
                'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'}, 'text': '/help',
                'entities': [{'type': 'bot_command', 'offset': 0, 'length': 5}]}}, context={'bot': bot}))
            edits = [call for call in session.calls if isinstance(call, EditMessageText)]
            assert len(edits) == 3 and all(call.message_id == initial.message_id and call.chat_id == 42 for call in edits)
            assert session.calls[-1].text == 'Existing help preserved'
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    return {'passed': True, 'existing_dispatcher_preserved': True, 'owner_and_stale_guards': True, 'history_back': True,
            'session_closed': True, 'edits': 3}


async def selection_check(namespace: dict) -> dict:
    from aiogram import Bot, Dispatcher, Router
    from aiogram.filters import Command
    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
    from aiogram.types import Update
    from telegram_patterns.testing import StubSession

    menu, router = namespace['menu'], namespace['router']
    existing = Router()

    @existing.message(Command('help'))
    async def help(message):
        await message.answer('Selection help preserved', parse_mode=None)

    dispatcher = Dispatcher()
    dispatcher.include_router(existing)
    dispatcher.include_router(router)

    def reply(request):
        return {'message_id': 100, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
                'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}, 'text': request.text}

    session = StubSession().respond(AnswerCallbackQuery, True).respond(EditMessageText, reply).respond(SendMessage, reply)
    async with Bot('100:PORTABLE_SELECTION_FIXTURE', session=session) as bot:
        try:
            index = 0

            async def click(action, actor=42, data=None):
                nonlocal index
                index += 1
                update = Update.model_validate({'update_id': index, 'callback_query': {
                    'id': str(index), 'chat_instance': 'fixture', 'from': {'id': actor, 'is_bot': False, 'first_name': 'Owner'},
                    'data': data or menu.state.callback(action),
                    'message': {'message_id': 100, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
                                'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}}}}, context={'bot': bot})
                await dispatcher.feed_update(bot, update)

            before = menu.state
            await click('s:alpha', actor=43)
            assert menu.state is before
            old = before.callback('s:alpha')
            await click('s:alpha')
            accepted = menu.state
            await click('s:alpha', data=old)
            assert menu.state is accepted
            for action in ('s:beta', 't:notify', 'q:inc', 'f:basic', 'ask'):
                await click(action)
            pending = menu.state
            assert pending.confirmation_id is not None
            confirmation = pending.callback('y:' + pending.confirmation_id)
            await click('refresh', data=confirmation)
            final = menu.state
            await click('refresh', data=confirmation)
            assert menu.state is final
            assert final.phase == 'confirmed' and final.selected == ('alpha', 'beta') and final.quantity == 2
            assert dict(final.toggles)['notify'] and final.operation_id is not None
            await dispatcher.feed_update(bot, Update.model_validate({'update_id': 99, 'message': {
                'message_id': 99, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
                'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'}, 'text': '/help'}}, context={'bot': bot}))
            assert session.calls[-1].text == 'Selection help preserved'
            assert all(call.message_id == 100 for call in session.calls if isinstance(call, EditMessageText))
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    return {'passed': True, 'existing_dispatcher_preserved': True, 'owner_stale_guards': True,
            'composite_fields': True, 'confirmation_once': True, 'session_closed': True, 'business_effects': 0}


def developer(skill: Path) -> dict:
    """Catalog and maturity recipes through the core API only (no SDK needed)."""
    reference = skill / 'references/developer-tools.md'
    blocks = blocks_of(reference)
    if len(blocks) != 1:
        raise RuntimeError('Expected exactly one owned developer recipe')
    with redirect_stdout(io.StringIO()) as output:
        exec(compile(blocks[0], str(reference), 'exec'), {'__name__': 'portable_catalog_recipe'})
    if 'inline_keyboard' not in output.getvalue():
        raise RuntimeError('Copied recipe did not expose expected code')
    maturity = skill / 'references/maturity.md'
    maturity_blocks = blocks_of(maturity)
    if len(maturity_blocks) != 1:
        raise RuntimeError('Expected exactly one owned maturity recipe')
    exec(compile(maturity_blocks[0], str(maturity), 'exec'), {'__name__': 'portable_maturity_recipe'})
    return {'passed': True, 'blocks': len(blocks) + len(maturity_blocks), 'network': False,
            'public_api': 'telegram_patterns.RecipeCatalog'}


RECIPES: dict[str, Callable[[Path], dict]] = {
    'dialog': Composition(
        'dialog-fields.md', 'dialog_fields_bot',
        lambda result: result['business_effects'] == 1 and result['field_types'] == 7,
        'Exact copied code on actual Dispatcher and temporary file SQLite; author SDK/mock, no independent/live acceptance'),
    'dialog-restart': Composition(
        'dialog-restart.md', 'dialog_restart_bot',
        lambda result: result['processes'] == 3 and result['business_effects'] == 1 and flags(
            'separate_process_restart', 'resumed_answers', 'original_deadline_preserved', 'operation_ids_match',
            'expired_draft_removed', 'expired_pending_preserved', 'version_refused_without_reset',
            'host_data_preserved', 'existing_dispatcher_preserved')(result),
        'Exact standalone code, installed SDK, three processes and local file SQLite; author checks, no live/device/independent/distributed acceptance',
        reviewed=True, processes=True, operations_accept=lambda result: result['operation_ids_match']),
    'inline-search': Composition(
        'inline-search.md', 'inline_search_bot',
        flags('personal_cache', 'scoped_pagination', 'fresh_acl', 'private_items_excluded', 'unknown_answer_no_retry',
              'existing_dispatcher_preserved', 'feedback_is_optional'),
        'Exact copied guide, actual Dispatcher and synthetic native answer; author mock, not live/cache/device/independent acceptance'),
    'media': Composition(
        'media.md', 'media_bot',
        lambda result: result['uploaded_parts'] == 5 and flags(
            'photo_document_album_edit', 'caption_entities', 'explicit_parse_mode_none', 'bounded_stream_download',
            'private_context_guards', 'existing_dispatcher_preserved')(result),
        'Copied composition plus SDK multipart/content streams; author mock, not live/device/independent acceptance'),
    'message': Composition(
        'message-text.md', 'message_text_bot',
        lambda result: result['chunks'] >= 2 and flags(
            'literal_injection', 'utf16_offsets', 'split_preserves_entities', 'explicit_parse_mode_none',
            'emoji_capability_fallback', 'existing_dispatcher_preserved', 'private_context_guards')(result),
        'Exact copied composition plus SDK serialization; author mock, not live/device/independent acceptance'),
    'platform': Composition(
        'platform-operations.md', 'platform_bot',
        lambda result: result['families'] == 7 and result['contracts'] == 51 and flags(
            'durable_intents', 'unknown_send_no_retry', 'current_actor_acl', 'fresh_native_rights', 'financial_quote_budget',
            'scoped_event_dedup', 'existing_dispatcher_preserved', 'user_confirmed_managed_link')(result),
        'Exact copied guide and actual SDK/Dispatcher/file SQLite fixtures; no live rights, financial settlement, physical devices or independent acceptance',
        reviewed=True, operations_accept=lambda result: result['confirmed_operations'] == 7),
    'poll': Composition(
        'polls.md', 'polls_bot',
        flags('modern_quiz', 'own_poll_binding', 'persistent_vote_ids', 'anonymous_limits', 'unknown_addition_not_guessed',
              'durable_host_dedup', 'unknown_send_no_retry', 'fresh_acl', 'existing_dispatcher_preserved'),
        'Exact copied guide, actual Dispatcher and temporary host SQLite; author mock, not live/complete voter ledger/independent acceptance'),
    'profile': Composition(
        'profiles.md', 'profiles_bot',
        lambda result: result['photo_upload_bytes'] == 634 and flags(
            'unknown_fields_preserved', 'profile_photos', 'localized_omission_clear', 'fresh_method_acl',
            'new_avatar_upload_removal', 'unknown_edit_reconciliation', 'private_context_guards',
            'existing_dispatcher_preserved')(result),
        'Copied composition, actual Dispatcher, locale state and SDK new-file multipart; author mock, not live/device/independent acceptance'),
    'keyboard': keyboard,
    'developer': developer,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('recipe', nargs='?', choices=sorted(RECIPES))
    parser.add_argument('skill', nargs='?', type=Path, help='copied skill directory, e.g. a copy of telegram-code-patterns')
    parser.add_argument('--list', action='store_true', help='print recipe names and the guides they read')
    args = parser.parse_args()
    if args.list:
        for name, recipe in sorted(RECIPES.items()):
            print(name, recipe.guide if isinstance(recipe, Composition) else recipe.__doc__.splitlines()[0])
        return 0
    if args.recipe is None or args.skill is None:
        parser.error('RECIPE and COPIED_SKILL are required')
    print(json.dumps(RECIPES[args.recipe](args.skill.resolve(strict=True))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
