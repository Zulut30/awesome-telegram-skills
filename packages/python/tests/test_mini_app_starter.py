"""bot-mini-app starter: Vite dev loop files, the generated backend checking initData and the menu button rules.

The browser loop (Vite dev server, hot update, proxy, built dist) runs in tests/starter-dev-loop.mjs.
"""

from __future__ import annotations

import hmac
import importlib.util
import io
import json
import os
import re
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import ANY, patch
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher
from aiogram.methods import SetChatMenuButton
from aiohttp.test_utils import make_mocked_request

from telegram_patterns import BotSettings, ValidationFailure, create_starter
from telegram_patterns.testing import StubSession

TOKEN = '100:MINI_APP_FIXTURE'
PLACEHOLDER = re.compile(r'__[A-Z][A-Z_]+__')


def signed(fields, token=TOKEN):
    secret = hmac.digest(b'WebAppData', token.encode(), 'sha256')
    check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
    return urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})


def launch(first_name='Анна', age=0):
    user = json.dumps({'id': 42, 'first_name': first_name}, ensure_ascii=False)
    return signed({'auth_date': str(int(time.time()) - age), 'user': user})


class StarterFixture(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        library = self.root / 'library'
        library.mkdir()
        (library / 'pyproject.toml').write_text(
            '[project]\nname="awesome-telegram-patterns"\nversion="0.10.0"\n', encoding='utf-8'
        )
        self.tarball = self.root / 'patterns.tgz'
        data = json.dumps({'name': '@awesome-telegram/patterns', 'version': '0.10.0'}).encode()
        with tarfile.open(self.tarball, 'w:gz') as archive:
            member = tarfile.TarInfo('package/package.json')
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        self.library = library

    def generate(self, template):
        target = self.root / template
        create_starter(
            target,
            library=self.library,
            typescript=self.tarball if template == 'bot-mini-app' else None,
            template=template,
        )
        return target, {
            p.relative_to(target).as_posix(): p.read_text(encoding='utf-8') for p in target.rglob('*') if p.is_file()
        }

    def load_server(self, target):
        spec = importlib.util.spec_from_file_location(f'mini_app_server_{id(self)}', target / 'mini_app_server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class MiniAppTemplateTests(StarterFixture):
    def test_mini_template_has_vite_dev_loop_and_backend(self):
        _, files = self.generate('bot-mini-app')
        self.assertIn('mini_app_server.py', files)
        self.assertIn('mini-app/vite.config.ts', files)
        for name, text in files.items():
            self.assertIsNone(PLACEHOLDER.search(text), name)
        package = json.loads(files['mini-app/package.json'])
        self.assertEqual(package['devDependencies'], {'typescript': '7.0.2', 'vite': '8.3.3'})
        self.assertEqual(package['scripts']['dev'], 'vite')
        self.assertEqual(package['scripts']['build'], 'tsc -p tsconfig.json && vite build')
        html = files['mini-app/index.html']
        sdk = html.index('<script src="https://telegram.org/js/telegram-web-app.js?64"></script>')
        self.assertLess(sdk, html.index('<script type="module" src="/src/main.ts">'), 'SDK before other scripts')
        config = json.loads(files['mini-app/tsconfig.json'])['compilerOptions']
        self.assertEqual(
            (config['types'], config['noEmit'], config['moduleResolution']), (['vite/client'], True, 'bundler')
        )
        vite = files['mini-app/vite.config.ts']
        self.assertIn("loadEnv(mode, '..', 'MINI_APP_')", vite)
        self.assertIn("{'/api': `http://127.0.0.1:${env.MINI_APP_API_PORT || '8080'}`}", vite)
        self.assertNotIn('allowedHosts: true', vite)
        main = files['mini-app/src/main.ts']
        self.assertIn("import '@awesome-telegram/patterns/styles.css';", main)
        self.assertIn("headers:()=>({'X-Init-Data':initData})", main)
        self.assertIn('import.meta.hot.accept()', main)
        self.assertIn('import.meta.hot.dispose(disposeApp)', main)
        self.assertIn('from mini_app_server import run_with_mini_app', files['app.py'])
        self.assertIn('await run_with_mini_app(dispatcher, settings, commands=commands)', files['app.py'])
        self.assertIn('"mini_app_server"', files['pyproject.toml'])
        self.assertIn('MINI_APP_API_PORT=8080', files['.env.example'])
        self.assertIn('# MINI_APP_URL=http://', files['.env.example'])
        self.assertIn("report['mini_app_backend'] = backend", files['offline.py'])
        readme = files['README.md']
        self.assertIn('## Mini App за 15 минут: тестовое окружение Telegram', readme)
        minutes = [int(value) for value in re.findall(r'\| (\d+) мин \|', readme)]
        self.assertEqual(len(minutes), 7)
        self.assertLessEqual(sum(minutes), 15)
        for anchor in ('#testing-mini-apps', '#debug-mode-for-mini-apps'):
            self.assertIn('https://core.telegram.org/bots/webapps' + anchor, readme)

    def test_bot_template_keeps_plain_polling(self):
        _, files = self.generate('bot')
        self.assertNotIn('mini_app_server.py', files)
        self.assertFalse(any(name.startswith('mini-app/') for name in files))
        for name, text in files.items():
            self.assertIsNone(PLACEHOLDER.search(text), name)
            self.assertNotIn('MINI_APP', text, name)
        self.assertIn('from telegram_patterns.aiogram import run_bot', files['app.py'])
        self.assertIn('await run_bot(dispatcher, settings, commands=commands)', files['app.py'])
        self.assertIn('В шаблоне bot каталога mini-app нет.', files['README.md'])
        self.assertNotIn('mini_app', files['offline.py'])


class MiniAppBackendTests(StarterFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.target, _ = self.generate('bot-mini-app')
        self.server = self.load_server(self.target)

    async def me(self, init_data=None, settings=None):
        app = self.server.create_web_app(settings or BotSettings(TOKEN))
        headers = {} if init_data is None else {'X-Init-Data': init_data}
        response = await self.server.me(make_mocked_request('GET', '/api/me', headers=headers, app=app))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.status, json.loads(response.text)

    async def test_only_signed_fresh_init_data_identifies_the_user(self):
        status, body = await self.me(launch())
        self.assertEqual(status, 200)
        self.assertEqual((body['user_id'], body['first_name']), (42, 'Анна'))
        changed = launch().replace('auth_date=', 'auth_date=9')
        cases = {
            None: 'authentication-required',
            '': 'authentication-required',
            'user=%7B%7D': 'init-data-invalid',
            changed: 'init-data-invalid',
            launch(age=7200): 'init-data-invalid',
        }
        for header, code in cases.items():
            with self.subTest(header=header and header[:12]):
                self.assertEqual(await self.me(header), (401, {'code': code, 'message': ANY}))
        foreign = await self.me(launch(), settings=BotSettings('200:OTHER_BOT_FIXTURE'))
        self.assertEqual(foreign[1]['code'], 'init-data-invalid', 'initData of another bot is refused')

    async def test_built_frontend_is_served_from_the_same_origin(self):
        dist = self.root / 'dist'
        empty = self.server.create_web_app(BotSettings(TOKEN), static_dir=dist)
        found = await empty.router.resolve(make_mocked_request('GET', '/'))
        self.assertIsNotNone(found.http_exception, 'nothing is served before npm run build')
        (dist / 'assets').mkdir(parents=True)
        (dist / 'index.html').write_text('<!doctype html>', encoding='utf-8')
        (dist / 'assets/index.js').write_text('export {}', encoding='utf-8')
        built = self.server.create_web_app(BotSettings(TOKEN), static_dir=dist)
        for path in ('/', '/assets/index.js', '/api/me'):
            with self.subTest(path=path):
                match = await built.router.resolve(make_mocked_request('GET', path))
                self.assertIsNone(match.http_exception)

    def test_menu_button_url_follows_the_environment(self):
        production, test = BotSettings(TOKEN), BotSettings(TOKEN, test_environment=True)
        cases = [
            ('', production, None),
            ('https://example.com/app', production, 'https://example.com/app'),
            ('http://192.168.1.10:5173', test, 'http://192.168.1.10:5173'),
            ('https://example.com/app', test, 'https://example.com/app'),
        ]
        for url, settings, expected in cases:
            with self.subTest(url=url), patch.dict(os.environ, {'MINI_APP_URL': url}):
                self.assertEqual(self.server.mini_app_url(settings), expected)
        for url, settings in (('http://192.168.1.10:5173', production), ('ftp://example.com', test), ('app', test)):
            with self.subTest(url=url), patch.dict(os.environ, {'MINI_APP_URL': url}):
                with self.assertRaisesRegex(ValidationFailure, 'MINI_APP_URL'):
                    self.server.mini_app_url(settings)

    def test_env_file_is_read_and_environment_wins(self):
        (self.target / '.env').write_text(
            '# comment\nexport MINI_APP_URL="https://from-file.example/app"\nMINI_APP_API_PORT=9090\n', encoding='utf-8'
        )
        with patch.dict(os.environ, {}, clear=False):
            for name in ('MINI_APP_URL', 'MINI_APP_API_PORT'):
                os.environ.pop(name, None)
            self.assertEqual(self.server.env_value('MINI_APP_URL'), 'https://from-file.example/app')
            self.assertEqual(self.server.env_value('MINI_APP_API_PORT', '8080'), '9090')
            self.assertEqual(self.server.env_value('MISSING', 'default'), 'default')
            os.environ['MINI_APP_API_PORT'] = '7070'
            self.assertEqual(self.server.env_value('MINI_APP_API_PORT', '8080'), '7070')

    async def test_bot_sets_the_menu_button_and_always_stops_the_backend(self):
        session = StubSession().respond(SetChatMenuButton, True)
        stopped = []

        class Runner:
            async def cleanup(self):
                stopped.append(True)

        async def start_web_app(settings):
            return Runner()

        async def run_bot(dispatcher, settings, *, commands):
            async with Bot(TOKEN, session=session) as bot:
                await dispatcher.emit_startup(bot=bot)
            raise RuntimeError('polling stopped')

        dispatcher = Dispatcher()
        with (
            patch.dict(os.environ, {'MINI_APP_URL': 'http://192.168.1.10:5173'}),
            patch.object(self.server, 'start_web_app', start_web_app),
            patch.object(self.server, 'run_bot', run_bot),
            patch('builtins.print'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'polling stopped'):
                await self.server.run_with_mini_app(dispatcher, BotSettings(TOKEN, test_environment=True), commands=[])
        self.assertEqual(stopped, [True])
        [call] = session.calls
        self.assertEqual((call.menu_button.type, call.menu_button.web_app.url), ('web_app', 'http://192.168.1.10:5173'))
        self.assertIsNone(call.chat_id, 'default menu button of private chats')


if __name__ == '__main__':
    sys.exit(unittest.main())
