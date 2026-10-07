"""Build and verify the local wheel/tarball through fresh consumer environments.

Requires Python >=3.11, uv, Node/npm and installed workspace dev dependencies.
Consumers are kept in a temporary directory for inspection; no publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-browser', action='store_true', help='Verify distributions without installed Chrome; report the skipped browser check')
    args = parser.parse_args()
    python_meta = tomllib.loads((ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']
    ts_meta = json.loads((ROOT / 'packages/typescript/package.json').read_text(encoding='utf-8'))
    catalog = json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))
    example = json.loads((ROOT / 'examples/mini-app/package.json').read_text(encoding='utf-8'))
    version = python_meta['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a numeric release version')
    if ts_meta['version'] != version or catalog['library_version'] != version or example['dependencies'][ts_meta['name']] != version:
        raise ValueError('Synchronize Python, TypeScript, catalog and example versions first')
    for component in catalog['components']:
        source = (ROOT / component['source']).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file():
            raise ValueError(f"Invalid component source: {component['id']}")

    uv, npm = shutil.which('uv'), shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    node = shutil.which('node')
    if not all((uv, npm, node)):
        raise RuntimeError('uv and Node/npm must be available on PATH')
    output = ROOT / 'output' / f'pattern-library-{version}'
    artifacts = output / 'dist'
    artifacts.mkdir(parents=True, exist_ok=True)
    # resolve(): macOS temp dirs live under /var, a symlink to /private/var; compare canonical paths.
    consumers = Path(tempfile.mkdtemp(prefix=f'telegram-patterns-{version}-')).resolve()
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    environment.pop('BOT_TOKEN', None)
    environment['PYTHONUTF8'] = '1'
    stages = []

    def run(label: str, command: list[str], cwd: Path = ROOT, *, timeout: float = 180) -> str:
        print(f'Checking: {label}', flush=True)
        try:
            result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired as error:
            def partial(value: str | bytes | None) -> str:
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            log = partial(error.stdout) + partial(error.stderr) + f'\nTIMEOUT after {error.timeout} seconds\n'
            (output / f'{label}.log').write_text(log, encoding='utf-8')
            stages.append({'stage': label, 'exit_code': 124, 'timed_out': True, 'timeout_seconds': error.timeout})
            raise RuntimeError(f'{label} timed out; partial output saved to {output / (label + ".log")}') from error
        log = result.stdout + result.stderr
        (output / f'{label}.log').write_text(log, encoding='utf-8')
        stages.append({'stage': label, 'exit_code': result.returncode})
        if result.returncode:
            # The tail goes to the CI log: the consumers directory is temporary and not uploaded.
            sys.stderr.write(f'--- last lines of {label}.log ---\n' + '\n'.join(log.splitlines()[-60:]) + '\n')
            raise RuntimeError(f'{label} failed; inspect {output / (label + ".log")}')
        return log

    def python_in(folder: Path) -> Path:
        return folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    report = {'version': version, 'consumers': str(consumers), 'stages': stages, 'browser': 'skipped' if args.skip_browser else 'pending', 'passed': False}
    try:
        run('workspace-build', [npm, 'run', 'build'])
        run('wheel-build', [uv, 'build', '--wheel', '--out-dir', str(artifacts), str(ROOT / 'packages/python')])
        run('tarball-build', [npm, 'pack', '--ignore-scripts', '-w', ts_meta['name'], '--pack-destination', str(artifacts)])
        wheel = artifacts / f'awesome_telegram_patterns-{version}-py3-none-any.whl'
        tarball = artifacts / f'awesome-telegram-patterns-{version}.tgz'
        if not wheel.is_file() or not tarball.is_file():
            raise RuntimeError('Expected wheel/tarball was not built')
        report['distribution_contract'] = json.loads(run('distribution-contract', [sys.executable, str(ROOT / 'scripts/verify_distribution_contract.py'), '--wheel', str(wheel), '--tarball', str(tarball)], consumers))

        core = consumers / 'core'
        run('core-environment', [uv, 'venv', '--python', sys.executable, str(core)])
        run('core-install', [uv, 'pip', 'install', '--python', str(python_in(core)), str(wheel), 'tzdata==2026.5'])
        smoke = consumers / 'core_smoke.py'
        smoke.write_text('''import importlib.util, json, sys
from pathlib import Path
import telegram_patterns
from telegram_patterns import BotSettings, validate_init_data, RecipeCatalog, create_starter, starter_components, StarterComponent
assert importlib.util.find_spec('aiogram') is None
assert Path(telegram_patterns.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
assert BotSettings.from_env(environ={'BOT_TOKEN':'100:CORE_FIXTURE'}).token=='100:CORE_FIXTURE'
assert len(RecipeCatalog().recipes)==311
assert RecipeCatalog().search('две кнопки')[0].id=='two-columns'
assert RecipeCatalog().get('two-columns').maturity=='experimental'
assert RecipeCatalog().get('api.sendPhoto').maturity=='reference'
assert not RecipeCatalog().search(maturity='stable')
assert callable(create_starter)
assert len(starter_components())==15 and isinstance(starter_components()[0],StarterComponent)
raw='auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test&hash=46d2ea5e32911ec8d30999b56247654460c0d20949b6277af519e76271182803'
assert validate_init_data(raw,'42:TEST',now=1650385342).user_id==42
print(json.dumps({'core_without_sdk':True,'python':sys.version.split()[0]}))
''', encoding='utf-8')
        run('core-smoke', [str(python_in(core)), str(smoke), str(core)], consumers)
        report['doctor_consumer'] = json.loads(run('doctor-consumer', [str(python_in(core)), str(ROOT / 'scripts/verify_doctor_consumer.py'),
            '--wheel', str(wheel), '--tarball', str(tarball), '--output', str(consumers / 'doctor')], consumers))
        recovery = json.loads(run('error-recovery', [str(python_in(core)), str(ROOT / 'examples/python/error_recovery.py')], consumers))
        if not recovery['passed'] or recovery['network'] or recovery['effect_count'] != 1 or not recovery['replayed']:
            raise RuntimeError('Installed core error reconciliation example failed')
        report['error_recovery'] = recovery
        custom_adapters = consumers / 'custom_adapters.py'
        custom_adapters.write_text((ROOT / 'examples/python/custom_adapters.py').read_text(encoding='utf-8'), encoding='utf-8')
        extensions = json.loads(run('custom-adapters', [str(python_in(core)), str(custom_adapters)], consumers))
        if not extensions['passed'] or extensions['network'] or extensions['custom_storage_effects'] != 1 or extensions['remote_effects'] != 1 or extensions['payment_granted']:
            raise RuntimeError('Installed core custom adapters failed')
        report['custom_adapters'] = extensions
        core_console = core / ('Scripts/telegram-patterns.exe' if os.name == 'nt' else 'bin/telegram-patterns')
        report['core_cli'] = json.loads(run('core-cli', [str(core_console), 'recipes', 'две кнопки'], consumers))
        if report['core_cli']['recipes'][0]['id'] != 'two-columns':
            raise RuntimeError('Core console recipe search failed')
        report['maturity_cli'] = json.loads(run('maturity-cli', [str(core_console), 'recipes', '--maturity', 'experimental'], consumers))
        if len(report['maturity_cli']['recipes']) != 20 or any(item['maturity'] != 'experimental' for item in report['maturity_cli']['recipes']):
            raise RuntimeError('Installed maturity CLI filter failed')
        database = consumers / 'booking.sqlite'
        first = json.loads(run('booking-first', [str(python_in(core)), str(ROOT / 'examples/python/booking.py'), str(database)], consumers))
        repeated = json.loads(run('booking-replay', [str(python_in(core)), str(ROOT / 'examples/python/booking.py'), str(database)], consumers))
        if first['replayed'] or not repeated['replayed'] or first['result'] != repeated['result']:
            raise RuntimeError('Booking example did not replay its persisted result')

        sdk = consumers / 'sdk'
        run('sdk-environment', [uv, 'venv', '--python', sys.executable, str(sdk)])
        run('sdk-install', [uv, 'pip', 'install', '--python', str(python_in(sdk)), str(wheel), 'aiogram==3.31.0', 'tzdata==2026.5'])
        run('typing-install', [uv, 'pip', 'install', '--python', str(python_in(sdk)), 'mypy==2.4.0'])
        run('python-typecheck', [str(python_in(sdk)), '-m', 'mypy', '--follow-imports=silent', '--no-incremental', str(ROOT / 'packages/python/src/telegram_patterns')], consumers)
        public_python_types = consumers / 'public_types.py'
        public_python_types.write_text((ROOT / 'tests/public_types.py').read_text(encoding='utf-8'), encoding='utf-8')
        run('python-consumer-typecheck', [str(python_in(sdk)), '-m', 'mypy', '--follow-imports=silent', '--warn-unused-ignores', '--no-incremental', str(public_python_types)], consumers)
        run('custom-adapter-typecheck', [str(python_in(sdk)), '-m', 'mypy', '--follow-imports=silent', '--no-incremental', str(custom_adapters)], consumers)
        report['recipe_execution'] = json.loads(run('recipe-execution-consumer', [sys.executable, str(ROOT / 'scripts/verify_recipe_execution.py'), '--core-python', str(python_in(core)), '--sdk-python', str(python_in(sdk)), '--output', str(consumers / 'recipe-execution')], consumers))
        run('api-reference-build', [sys.executable, str(ROOT / 'scripts/build_api_reference.py'), '--check'])
        reference_command = [str(python_in(sdk)), str(ROOT / 'scripts/verify_api_reference.py'),
            '--wheel', str(wheel), '--tarball', str(tarball), '--core-python', str(python_in(core)),
            '--sdk-python', str(python_in(sdk)), '--output', str(consumers / 'api-reference')]
        if args.skip_browser:
            reference_command.append('--skip-browser')
        report['api_reference'] = json.loads(run('api-reference-consumer', reference_command, consumers))
        run('sdk-origin', [str(python_in(sdk)), '-c', 'import sys,telegram_patterns;from pathlib import Path;assert Path(telegram_patterns.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve());print(telegram_patterns.__file__)', str(sdk)], consumers)
        # Includes bounded real subprocess restart/CLI consumers; keep the suite
        # deadline distinct from each individual operation's timeout.
        python_log = run('python-tests', [str(python_in(sdk)), '-m', 'unittest', 'discover', '-s', str(ROOT / 'packages/python/tests'), '-v'], consumers, timeout=450)
        run('sdk-dependencies', [uv, 'pip', 'check', '--python', str(python_in(sdk))])
        offline = json.loads(run('offline-bot', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_bot.py')], consumers))
        if not offline['passed'] or offline['network'] or not offline['session_closed']:
            raise RuntimeError('Offline bot composition did not pass')
        report['offline_bot'] = offline
        form = json.loads(run('offline-form', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_form.py')], consumers))
        if not form['passed'] or form['network'] or form['applications'] != 1 or not form['session_closed']:
            raise RuntimeError('Offline form composition did not pass')
        report['offline_form'] = form
        keyboards = json.loads(run('offline-keyboards', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_keyboards.py')], consumers))
        if not keyboards['passed'] or keyboards['network'] or not keyboards['session_closed']:
            raise RuntimeError('Keyboard cookbook composition did not pass')
        report['offline_keyboards'] = keyboards
        layouts = json.loads(run('keyboard-layouts', [str(python_in(sdk)), str(ROOT / 'examples/python/keyboard_layouts.py')], consumers))
        if not layouts['passed'] or layouts['network'] or not layouts['session_closed'] or layouts['methods'] != 6:
            raise RuntimeError('Installed keyboard layout composition failed')
        report['keyboard_layouts'] = layouts
        navigation = json.loads(run('message-navigation', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_navigation.py')], consumers))
        if not navigation['passed'] or navigation['network'] or not navigation['session_closed'] or not all(navigation[k] for k in ('owner_guard','stale_guard','history_back','unknown_edit_recovery','single_message')):
            raise RuntimeError('Installed message navigation composition failed')
        report['message_navigation'] = navigation
        selection = json.loads(run('selection-controls', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_selection.py')], consumers))
        if not selection['passed'] or selection['network'] or not selection['session_closed'] or selection['business_effects'] != 0 or not all(selection[k] for k in ('toggle','multiselect','quantity','filters','owner_guard','stale_guard','fresh_rules','confirmation_once','single_message')):
            raise RuntimeError('Installed composite selection scenario failed')
        report['selection_controls'] = selection
        calendar = json.loads(run('calendar-slots', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_calendar.py')], consumers))
        if not calendar['passed'] or calendar['network'] or not calendar['session_closed'] or calendar['business_effects'] != 1 or not all(calendar[k] for k in ('date_time_back','unavailable_date','month_navigation','owner_stale_guards','schedule_confirmation_guard','durable_replay','existing_dispatcher_preserved','unknown_edit_recovery','single_message')):
            raise RuntimeError('Installed calendar and transactional booking scenario failed')
        report['calendar_slots'] = calendar
        dialog = json.loads(run('dialog-fields', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_dialog_fields.py')], consumers))
        if not dialog['passed'] or dialog['network'] or not dialog['session_closed'] or dialog['field_types'] != 7 or dialog['business_effects'] != 1 or not all(dialog[k] for k in ('owner_step_guards','native_candidate_confirmation','back_cancel','unknown_receipt_same_intent','existing_dispatcher_preserved','host_data_preserved')):
            raise RuntimeError('Installed seven-field dialog scenario failed')
        report['dialog_fields'] = dialog
        restart = json.loads(run('dialog-restart', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_dialog_restart.py')], consumers))
        if (not restart['passed'] or restart['network'] or not restart['session_closed'] or restart['processes'] != 3
                or restart['business_effects'] != 1 or not all(restart[k] for k in ('separate_process_restart', 'resumed_answers',
                    'original_deadline_preserved', 'operation_ids_match', 'expired_draft_removed', 'expired_pending_preserved',
                    'version_refused_without_reset', 'host_data_preserved', 'existing_dispatcher_preserved'))):
            raise RuntimeError('Installed restart-safe dialog composition failed')
        report['dialog_restart'] = restart
        message_text = json.loads(run('message-text', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_message_text.py')], consumers))
        if not message_text['passed'] or message_text['network'] or not message_text['session_closed'] or message_text['chunks'] < 2 or not all(message_text[k] for k in ('literal_injection','utf16_offsets','split_preserves_entities','explicit_parse_mode_none','emoji_capability_fallback','existing_dispatcher_preserved','private_context_guards')):
            raise RuntimeError('Installed literal messages and lossless partition failed')
        report['message_text'] = message_text
        media = json.loads(run('media', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_media.py')], consumers))
        if not media['passed'] or media['network'] or not media['session_closed'] or media['uploaded_parts'] != 5 or not all(media[k] for k in ('photo_document_album_edit','caption_entities','explicit_parse_mode_none','bounded_stream_download','private_context_guards','existing_dispatcher_preserved')):
            raise RuntimeError('Installed media composition failed')
        report['media'] = media
        profiles = json.loads(run('profiles', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_profiles.py')], consumers))
        if not profiles['passed'] or profiles['network'] or not profiles['session_closed'] or profiles['photo_upload_bytes'] != 634 or not all(profiles[k] for k in ('unknown_fields_preserved', 'profile_photos', 'localized_omission_clear', 'fresh_method_acl', 'new_avatar_upload_removal', 'unknown_edit_reconciliation', 'private_context_guards', 'existing_dispatcher_preserved')):
            raise RuntimeError('Installed profile composition failed')
        report['profiles'] = profiles
        inline_search = json.loads(run('inline-search', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_inline_search.py')], consumers))
        if not inline_search['passed'] or inline_search['network'] or not inline_search['session_closed'] or not all(inline_search[k] for k in ('personal_cache', 'scoped_pagination', 'fresh_acl', 'private_items_excluded', 'unknown_answer_no_retry', 'existing_dispatcher_preserved', 'feedback_is_optional')):
            raise RuntimeError('Installed inline_search composition failed')
        report['inline_search'] = inline_search
        polls = json.loads(run('polls', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_polls.py')], consumers))
        if not polls['passed'] or polls['network'] or not polls['session_closed'] or not all(polls[k] for k in ('modern_quiz', 'own_poll_binding', 'persistent_vote_ids', 'anonymous_limits', 'unknown_addition_not_guessed', 'durable_host_dedup', 'unknown_send_no_retry', 'fresh_acl', 'existing_dispatcher_preserved')):
            raise RuntimeError('Installed polls composition failed')
        report['polls'] = polls
        platform = json.loads(run('platform', [str(python_in(sdk)), str(ROOT / 'examples/python/offline_platform.py')], consumers))
        if (not platform['passed'] or platform['network'] or not platform['session_closed']
                or platform['families'] != 7 or platform['contracts'] != 51 or platform['confirmed_operations'] != 7
                or not all(platform[k] for k in ('durable_intents', 'unknown_send_no_retry', 'current_actor_acl', 'fresh_native_rights', 'financial_quote_budget', 'scoped_event_dedup', 'existing_dispatcher_preserved', 'user_confirmed_managed_link'))):
            raise RuntimeError('Installed seven-family platform composition failed')
        report['platform'] = platform
        report['telegram_catalog'] = json.loads(run('telegram-catalog', [str(python_in(sdk)), str(ROOT / 'scripts/build_telegram_catalog.py'), '--check'], consumers))
        report['recipe_gallery'] = json.loads(run('recipe-gallery', [str(python_in(sdk)), str(ROOT / 'scripts/build_recipe_gallery.py'), '--check'], consumers))
        gallery_command = [str(python_in(sdk)), str(ROOT / 'scripts/verify_gallery_export.py'), '--output', str(consumers / 'gallery-export')]
        if args.skip_browser: gallery_command.append('--skip-browser')
        # Two complete SDK fixture generations plus CLI and browser acceptance.
        report['gallery_export'] = json.loads(run('gallery-export-consumer', gallery_command, consumers, timeout=720))
        starter_root = consumers / 'starters'
        report['starter_cli'] = json.loads(run('starter-cli', [str(python_in(sdk)), str(ROOT / 'scripts/verify_starter_consumer.py'), '--wheel', str(wheel), '--tarball', str(tarball), '--output', str(starter_root)], consumers))
        # Resolve the generated PEP dependency against the supplied local wheel.
        run('starter-python-install', [uv, 'pip', 'install', '--python', str(python_in(sdk)), str(starter_root / 'bot-mini-app')], consumers)
        mini_starter = starter_root / 'bot-mini-app/mini-app'
        run('starter-typescript-install', [npm, 'install', '--ignore-scripts', '--no-audit', '--no-fund'], mini_starter)
        run('starter-typecheck', [npm, 'run', 'typecheck'], mini_starter)
        run('starter-build', [npm, 'run', 'build'], mini_starter)
        selected_root = consumers / 'selected-starters'
        report['selected_starter'] = json.loads(run('selected-starter-cli', [str(python_in(sdk)), str(ROOT / 'scripts/verify_selected_starter.py'), '--wheel', str(wheel), '--tarball', str(tarball), '--output', str(selected_root)], consumers))
        selected_project = selected_root / 'all selected'
        selected_sdk = consumers / 'selected-sdk'
        run('selected-starter-environment', [uv, 'venv', '--python', sys.executable, str(selected_sdk)])
        run('selected-starter-python-install', [uv, 'pip', 'install', '--python', str(python_in(selected_sdk)), str(selected_project), 'aiogram==3.31.0'], consumers)
        run('selected-starter-python-origin', [str(python_in(selected_sdk)), '-c', 'import app,sys,asyncio;from pathlib import Path;assert Path(app.__file__).resolve().is_relative_to(Path(sys.prefix).resolve());dp,commands=app.create_app();assert len(commands)==7;asyncio.run(dp.fsm.close());print("Installed generated app and all selected modules compose outside the project tree")'], consumers)
        selected_mini = selected_project / 'mini-app'
        run('selected-starter-typescript-install', [npm, 'install', '--ignore-scripts', '--no-audit', '--no-fund'], selected_mini)
        run('selected-starter-typecheck', [npm, 'run', 'typecheck'], selected_mini)
        run('selected-starter-build', [npm, 'run', 'build'], selected_mini)
        copied_skill = consumers / 'portable-skill/telegram-code-patterns'
        shutil.copytree(ROOT / '.agents/skills/telegram-code-patterns', copied_skill)
        report['portable_dialog_restart_recipe'] = json.loads(run('portable-dialog-restart-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_dialog_restart_recipe.py'), str(copied_skill)], consumers))
        report['portable_platform_recipe'] = json.loads(run('portable-platform-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_platform_recipe.py'), str(copied_skill)], consumers))
        report['portable_inline_search_recipe'] = json.loads(run('portable-inline-search-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_inline_search_recipe.py'), str(copied_skill)], consumers))
        report['portable_poll_recipe'] = json.loads(run('portable-poll-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_poll_recipe.py'), str(copied_skill)], consumers))
        blocks = re.findall(r'```python\r?\n(.*?)```', (copied_skill / 'references/errors.md').read_text(encoding='utf-8'), re.S)
        if len(blocks) != 1:
            raise RuntimeError('Expected one standalone error handling example')
        error_example = consumers / 'portable_error_example.py'
        error_example.write_text(blocks[0], encoding='utf-8')
        run('portable-error-recipe', [str(python_in(core)), str(error_example)], consumers)
        report['portable_keyboard_recipe'] = json.loads(run('portable-keyboard-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_keyboard_recipe.py'), str(copied_skill)], consumers))
        report['portable_dialog_recipe'] = json.loads(run('portable-dialog-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_dialog_recipe.py'), str(copied_skill)], consumers))
        report['portable_profile_recipe'] = json.loads(run('portable-profile-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_profile_recipe.py'), str(copied_skill)], consumers))
        report['portable_media_recipe'] = json.loads(run('portable-media-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_media_recipe.py'), str(copied_skill)], consumers))
        report['portable_message_recipe'] = json.loads(run('portable-message-recipe', [str(python_in(sdk)), str(ROOT / 'scripts/verify_message_recipe.py'), str(copied_skill)], consumers))
        report['portable_developer_recipe'] = json.loads(run('portable-developer-recipe', [str(python_in(core)), str(ROOT / 'scripts/verify_developer_recipe.py'), str(copied_skill)], consumers))

        client = consumers / 'typescript'
        client.mkdir()
        (client / 'package.json').write_text(json.dumps({'name': 'local-pattern-consumer', 'private': True, 'type': 'module'}), encoding='utf-8')
        run('typescript-install', [npm, 'install', str(tarball), f"typescript@{ts_meta['devDependencies']['typescript']}", '--ignore-scripts', '--no-audit', '--no-fund'], client)
        # Same behavior suite, exercising the PUBLIC installed package rather than
        # ../dist from a source checkout. No component implementation is copied.
        suite = (ROOT / 'packages/typescript/tests/core.test.mjs').read_text(encoding='utf-8')
        needle = "from '../dist/index.js'"
        if suite.count(needle) != 1:
            raise RuntimeError('Update the public-package test entrypoint')
        (client / 'core.test.mjs').write_text(suite.replace(needle, "from '@awesome-telegram/patterns'"), encoding='utf-8')
        ts_log = run('typescript-tests', [node, '--test', '--test-reporter=tap', 'core.test.mjs'], client)
        # Compile the real composition example against the INSTALLED declarations.
        (client / 'index.ts').write_text((ROOT / 'examples/mini-app/src/index.ts').read_text(encoding='utf-8'), encoding='utf-8')
        (client / 'native-recipes.ts').write_text((ROOT / 'examples/mini-app/src/native-recipes.ts').read_text(encoding='utf-8'), encoding='utf-8')
        (client / 'public-types.ts').write_text((ROOT / 'tests/public-types.ts').read_text(encoding='utf-8'), encoding='utf-8')
        (client / 'tsconfig.json').write_text(json.dumps({'compilerOptions': {'target': 'ES2022', 'module': 'NodeNext', 'moduleResolution': 'NodeNext', 'lib': ['ES2022', 'DOM'], 'strict': True, 'exactOptionalPropertyTypes': True, 'noUncheckedIndexedAccess': True, 'outDir': 'compiled', 'noEmitOnError': True}, 'include': ['index.ts', 'native-recipes.ts', 'public-types.ts']}), encoding='utf-8')
        run('consumer-typecheck', [node, str(client / 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.json', '--noEmit'], client)
        run('native-example-build', [node, str(client / 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.json'], client)
        (client / 'native-recipes-consumer.mjs').write_text((ROOT / 'tests/native-recipes-consumer.mjs').read_text(encoding='utf-8'), encoding='utf-8')
        report['native_recipes'] = json.loads(run('native-example-test', [node, 'native-recipes-consumer.mjs'], client))
        run('packaged-style', [node, '--input-type=module', '-e', "import {readFile} from 'node:fs/promises';const css=await readFile(new URL(import.meta.resolve('@awesome-telegram/patterns/styles.css')),'utf8');if(!css.trim())throw Error('empty style');console.log('public CSS export works')"], client)
        if not args.skip_browser:
            run('browser-tests', [npm, 'run', 'test:browser'])
            report['browser'] = json.loads((output / 'browser/report.json').read_text(encoding='utf-8'))
            run('gallery-browser', [node, str(ROOT / 'tests/gallery-browser.mjs')], timeout=420)
            report['gallery_browser'] = json.loads((output / 'gallery-browser/report.json').read_text(encoding='utf-8'))
            run('starter-browser', [node, str(ROOT / 'tests/starter-browser.mjs'), str(mini_starter)])
            report['starter_browser'] = json.loads((output / 'starter-browser/report.json').read_text(encoding='utf-8'))
            run('selected-starter-browser', [node, str(ROOT / 'tests/selected-starter-browser.mjs'), str(selected_mini)])
            report['selected_starter_browser'] = json.loads((output / 'selected-starter-browser/report.json').read_text(encoding='utf-8'))
        report['python_tests'] = int(re.search(r'Ran (\d+) tests?', python_log).group(1))
        report['typescript_tests'] = int(re.search(r'# tests (\d+)', ts_log).group(1))
        report['artifacts'] = [{'name': file.name, 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()} for file in (wheel, tarball)]
        report['passed'] = True
        print(f"PASS {version}: wheel/tarball consumers, {report['python_tests']} Python and {report['typescript_tests']} TypeScript tests; browser={report['browser'] if args.skip_browser else 'passed'}", flush=True)
    finally:
        (output / 'distribution-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Report: {output / "distribution-report.json"}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
