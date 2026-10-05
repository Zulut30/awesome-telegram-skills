"""Build offline recipe catalog/gallery. SDK requests and demo Dispatchers run locally."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tomllib
from aiogram.types import InlineKeyboardButton, KeyboardButton, CopyTextButton, DisabledButton, WebAppInfo
from telegram_patterns import RecipeCatalog
from telegram_patterns._offline_recipe import _FIXTURES
from telegram_patterns.aiogram import inline_keyboard, reply_keyboard, input_prompt, remove_keyboard, build_request

ROOT = Path(__file__).resolve().parents[1]
API = 'https://core.telegram.org/bots/api'
WEB = 'https://core.telegram.org/bots/webapps'
NAVIGATION = {
    'tasks': {'keyboards': 'Кнопки и раскладки', 'input': 'Ввод и формы', 'navigation': 'Возврат и навигация',
              'messages': 'Сообщения', 'media': 'Медиа и файлы', 'profiles': 'Профили', 'moderation': 'Группы и модерация',
              'payments': 'Платежные запросы', 'native': 'Native Mini Apps', 'recovery': 'Восстановление операций',
              'bot': 'Композиция бота', 'other': 'Другие API'},
    'contexts': {'private': 'Личный чат', 'group': 'Группа', 'supergroup': 'Супергруппа', 'channel': 'Канал',
                 'business': 'Business connection', 'mini-app': 'Mini App', 'backend': 'Backend без чата',
                 'unspecified': 'Уточнить контекст'},
    'sdks': {'aiogram': 'aiogram', 'python-core': 'Python core без SDK', 'telegram-webapp': 'Telegram WebApp (снимок)',
             'unspecified': 'SDK не указан'},
}
# Curated subset checked against official docs 2026-10-04. Unknown is never all chats.
CONTEXTS = {'sendMessage': ['private', 'group', 'supergroup', 'channel'],
            'sendPhoto': ['private', 'group', 'supergroup', 'channel'],
            'createForumTopic': ['private', 'supergroup'], 'editForumTopic': ['private', 'supergroup'],
            'restrictChatMember': ['supergroup'], 'createChatSubscriptionInviteLink': ['channel'],
            'getBusinessAccountGifts': ['business']}


def method_tasks(name: str) -> list[str]:
    """Discovery classification by method name; never a claim of a full workflow."""
    if any(word in name for word in ('Payment', 'Invoice', 'Star', 'Subscription')): return ['payments']
    if any(word in name for word in ('Photo', 'Video', 'Audio', 'Document', 'Media', 'Sticker', 'File', 'Story')): return ['media']
    if any(word in name for word in ('Member', 'ForumTopic', 'InviteLink', 'JoinRequest', 'Permissions')): return ['moderation']
    if name == 'getMe' or any(word in name for word in ('Profile', 'MyName', 'MyDescription', 'MyShortDescription')): return ['profiles']
    if 'Message' in name: return ['messages']
    return ['other']
IMPORTS = ('from aiogram.types import InlineKeyboardButton as Button, KeyboardButton, CopyTextButton, DisabledButton, WebAppInfo\n'
           'from telegram_patterns.aiogram import inline_keyboard, reply_keyboard, input_prompt, remove_keyboard, KeyboardLayout, inline_layout\n\n')
MANUAL = [
    ('two-columns', 'Две кнопки в ряд', 'кнопки 2 строки две раскладка', 'buttons = [Button(text=text, callback_data="menu:"+key) for text,key in [("Каталог","catalog"),("Помощь","help"),("Назад","back"),("Закрыть","close")]]\nmarkup = inline_layout(buttons, KeyboardLayout([2]))'),
    ('three-columns', 'Три кнопки в ряд', 'кнопки 3 строки три раскладка', 'buttons = [Button(text=str(n), callback_data=f"item:{n}") for n in range(1, 7)]\nmarkup = inline_layout(buttons, KeyboardLayout([3]))'),
    ('mixed-rows', 'Строки по одной, две и три кнопки', 'кнопки смешанная раскладка', 'buttons = [Button(text=str(n), callback_data=f"item:{n}") for n in range(1, 7)]\nmarkup = inline_layout(buttons, KeyboardLayout([1,2,3]))'),
    ('button-colors', 'Цветные кнопки: синий, зеленый, красный', 'цвета покрасить style primary success danger', 'markup = inline_keyboard([[Button(text="Основная", callback_data="a", style="primary"), Button(text="Готово", callback_data="b", style="success"), Button(text="Отмена", callback_data="c", style="danger")]])'),
    ('emoji-fallback', 'Custom emoji с запасным оформлением', 'premium emoji иконка entitlement', 'button = Button(text="Готово", callback_data="ok", icon_custom_emoji_id="123456789")\n# ID-пример заменяется реальным; entitlement по умолчанию не подтвержден.\nmarkup = inline_keyboard([[button]])'),
    ('reply-menu', 'Клавиатура под полем ввода', 'reply keyboard меню ввод подсказка', 'markup = reply_keyboard([["Каталог", "Помощь"], ["Закрыть"]], placeholder="Выберите действие")'),
    ('contact-location', 'Запрос контакта и геопозиции', 'контакт телефон location геопозиция private', 'markup = reply_keyboard([[KeyboardButton(text="Контакт", request_contact=True), KeyboardButton(text="Геопозиция", request_location=True)]], chat_type="private", one_time=True)'),
    ('force-reply', 'Ответ на конкретное сообщение', 'force reply ввод имя подсказка prompt', 'markup = input_prompt("Ваше имя")\n# Host сохраняет actor/chat/prompt.message_id и проверяет reply_to_message.'),
    ('remove-reply', 'Скрыть reply-клавиатуру', 'убрать скрыть клавиатура remove', 'markup = remove_keyboard()'),
    ('copy-disabled', 'Копирование и недоступная кнопка', 'copy disabled копировать выключить', 'markup = inline_keyboard([[Button(text="Копировать", copy_text=CopyTextButton(text="READY-CODE")), Button(text="Недоступно", disabled=DisabledButton())]])'),
    ('url-app', 'Ссылка и кнопка Mini App', 'url web_app ссылка приложение HTTPS private', 'markup = inline_keyboard([[Button(text="Документация", url="https://core.telegram.org/bots/api"), Button(text="Приложение", web_app=WebAppInfo(url="https://example.invalid/replace"))]], chat_type="private")'),
]


def build(root: Path = ROOT) -> dict:
    version = tomllib.loads((root / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    api = json.loads((root / 'catalog/telegram-capabilities.json').read_text(encoding='utf-8'))
    sdk_version = importlib.metadata.version('aiogram')
    if api['sdk'] != 'aiogram ' + sdk_version: raise ValueError('Installed SDK differs from catalog snapshot')
    fixtures = json.loads((root / 'catalog/bot-api-request-fixtures.json').read_text(encoding='utf-8'))['methods']
    spec = importlib.util.spec_from_file_location('fixture_materializer', ROOT / 'scripts/build_telegram_catalog.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    records = []
    def add(recipe_id, title, summary, category, language, keywords, code, verification, scope, sources, preview=None,
            *, tasks, contexts, sdk='aiogram', sdk_ver=None, api_version=None, source_files, check_files):
        keywords = list(dict.fromkeys([*keywords, *' '.join(NAVIGATION['tasks'][t] for t in tasks).lower().split(),
                                       *' '.join(NAVIGATION['contexts'][c] for c in contexts).lower().split()]))
        records.append({'id': recipe_id, 'title': title, 'summary': summary, 'category': category, 'language': language,
            'maturity': 'reference' if category == 'bot-api' or verification == 'not_run' else 'experimental',
            'keywords': keywords, 'code': code, 'verification': verification, 'scope': scope, 'sources': sources, 'preview': preview,
            'code_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(), 'tasks': tasks, 'contexts': contexts,
            'sdk': sdk, 'sdk_version': sdk_ver or sdk_version, 'api_version': api_version or 'bot:' + api['bot_api']['version'],
            'source_files': source_files, 'check_files': check_files})
    for key, title, tags, body in MANUAL:
        code = IMPORTS + body + '\n# В handler: await message.answer("Пример", reply_markup=markup)\n'
        namespace = {}; exec(compile(code, key, 'exec'), namespace)
        markup = namespace['markup'].model_dump(mode='json', exclude_none=True)
        add(key, title, 'Готовая разметка; обработку и права проверяет ваш handler.', 'keyboards', 'python', tags.split(), code,
            'sdk', 'Построено native SDK при генерации; helper context private по умолчанию. ForceReply/remove требуют host chat/actor correlation. Веб-превью не Telegram.',
            [API + '#inlinekeyboardbutton', API + '#replykeyboardmarkup'], markup,
            tasks=['input'] if key in {'contact-location', 'force-reply', 'remove-reply', 'reply-menu'} else ['keyboards', 'navigation'] if key == 'two-columns' else ['keyboards'],
            contexts=['unspecified'] if key in {'force-reply', 'remove-reply'} else ['private'],
            source_files=['recipes/bot-api/keyboards.md', 'packages/python/src/telegram_patterns/native_keyboards.py', 'packages/python/src/telegram_patterns/keyboard_layouts.py'],
            check_files=['scripts/build_recipe_gallery.py', 'packages/python/tests/test_native_features.py', 'packages/python/tests/test_keyboard_layouts.py'])
        if key == 'two-columns': records[-1]['keywords'] += ['назад', 'back']
    for method in api['bot_api']['methods']:
        name = method['name']
        request = build_request(name, helper.materialize(fixtures[name]))
        if request.__api_method__ != name: raise ValueError('Unexpected SDK method')
        text = (root / method['recipe']).read_text(encoding='utf-8')
        code = text.split('```python\n', 1)[1].split('```', 1)[0]
        add('api.' + name, name, 'Искусственные ID/данные: заменить перед отправкой. Проверить права и ограничения.', 'bot-api', 'python',
            [name, *method['fields'], 'api', 'запрос'], code, 'sdk', 'Native request построен; HTTP, права и весь business flow не проверены. Context tags — проверенный поднабор, не полная матрица разрешений.', [API + '#' + name.lower()],
            tasks=method_tasks(name), contexts=CONTEXTS.get(name, ['unspecified']), source_files=[method['recipe']],
            check_files=['scripts/build_recipe_gallery.py', 'scripts/build_telegram_catalog.py'])
    for method in api['mini_app']['methods']:
        path = method['path']
        code = ('import { TelegramNativeAPI } from "@awesome-telegram/patterns";\n'
            'declare const nativeApp: unknown; // Host передает свой WebApp.\nconst api = new TelegramNativeAPI(nativeApp);\n'
            f'if (api.supports("{path}")) {{\n  // Native сигнатура: {method["signature"]}\n'
            f'  // api.call("{path}", ...параметры_по_документации);\n}}\napi.dispose();\n')
        add('native.' + path, path, 'Native сигнатура: ' + method['signature'] + '. Минимальная версия ' + method['min_version'],
            'mini-app', 'typescript', [path, 'native', 'mini', 'app', method['signature']], code, 'not_run',
            'Справочный фрагмент. Аргументы, permissions/init/callback и реальный клиент требуют отдельного сценария; снимок не версия Telegram-клиента.', [method['url']],
            tasks=['navigation'] if path.startswith('BackButton.') else ['native'], contexts=['mini-app'], sdk='telegram-webapp',
            sdk_ver='snapshot:' + api['mini_app']['checked_date'], api_version='mini:' + method['min_version'],
            source_files=['recipes/mini-app/README.md', 'packages/typescript/src/native-api.ts'],
            check_files=['scripts/build_telegram_catalog.py', 'packages/typescript/tests/core.test.mjs'])
        if path.startswith('BackButton.'): records[-1]['keywords'] += ['назад', 'back']
    environment = dict(os.environ); environment.pop('BOT_TOKEN', None); environment['PYTHONUTF8'] = '1'
    for filename, offline, key, title in (
        ('keyboards_bot.py', 'offline_keyboards.py', 'demo-keyboards', 'Рабочий бот клавиатур и событий'),
        ('bot.py', 'offline_bot.py', 'demo-catalog', 'Каталог с пагинацией и callbacks'),
        ('form_bot.py', 'offline_form.py', 'demo-form', 'Форма с проверкой и подтверждением'),
        ('navigation_bot.py', 'offline_navigation.py', 'demo-navigation', 'Экраны и история в одном сообщении'),
        ('selection_bot.py', 'offline_selection.py', 'demo-selection', 'Переключатели, выбор, количество и подтверждение'),
        ('calendar_bot.py', 'offline_calendar.py', 'demo-calendar', 'Календарь и запись на свободное время'),
        ('dialog_fields_bot.py', 'offline_dialog_fields.py', 'demo-dialog-fields', 'Семь типов полей диалога'),
        ('media_bot.py', 'offline_media.py', 'demo-media', 'Фото, документы, альбомы и скачивание'),
        ('message_text_bot.py', 'offline_message_text.py', 'demo-message-text', 'Безопасные сообщения и разбиение текста'),
    ):
        result = subprocess.run([sys.executable, str(root / 'examples/python' / offline)], capture_output=True,
                                text=True, encoding='utf-8', env=environment, timeout=60)
        if result.returncode: raise ValueError('Offline recipe failed: ' + key)
        evidence = json.loads(result.stdout)
        if evidence.get('passed') is not True or evidence.get('network') is not False: raise ValueError('Invalid offline evidence')
        code = (root / 'examples/python' / filename).read_text(encoding='utf-8')
        add(key, title, 'Полная композиция с тем же Dispatcher для offline и polling.', 'scenarios', 'python',
            ['бот', 'пример', 'callback', 'форма' if key == 'demo-form' else 'меню', 'события'], code, 'mock',
            'Synthetic Dispatcher сценарий исполнен при генерации в private fixture. Telegram delivery/physical clients не проверены.', [API],
            tasks=['input', 'keyboards'] if key in {'demo-selection', 'demo-calendar', 'demo-dialog-fields'} else ['input'] if key == 'demo-form' else (['navigation', 'recovery'] if key == 'demo-navigation' else ['bot']), contexts=['private'],
            source_files=['examples/python/' + filename], check_files=['examples/python/' + offline])
        if key == 'demo-navigation':
            records[-1]['keywords'] += ['назад', 'история', 'одно', 'сообщение', 'owner', 'stale', 'recovery']
            records[-1]['source_files'].append('packages/python/src/telegram_patterns/navigation.py')
            records[-1]['check_files'].append('packages/python/tests/test_navigation.py')
        if key == 'demo-selection':
            records[-1]['keywords'] += ['toggle', 'multiselect', 'переключатель', 'количество', 'фильтр', 'подтверждение', 'выбор', 'confirmation', 'revision']
            records[-1]['source_files'] += ['packages/python/src/telegram_patterns/selection.py', 'packages/python/src/telegram_patterns/selection_aiogram.py']
            records[-1]['check_files'].append('packages/python/tests/test_selection.py')
        if key == 'demo-calendar':
            records[-1]['keywords'] += ['календарь', 'дата', 'время', 'слот', 'запись', 'timezone', 'DST', 'booking', 'receipt']
            records[-1]['source_files'] += ['packages/python/src/telegram_patterns/calendar.py', 'packages/python/src/telegram_patterns/calendar_aiogram.py', 'packages/python/src/telegram_patterns/slots.py']
            records[-1]['check_files'] += ['packages/python/tests/test_calendar.py', 'packages/python/tests/test_calendar_aiogram.py']
        if key == 'demo-dialog-fields':
            records[-1]['keywords'] += ['поля', 'число', 'email', 'телефон', 'файл', 'контакт', 'геопозиция', 'ForceReply', 'candidate', 'шаг']
            records[-1]['source_files'] += ['packages/python/src/telegram_patterns/dialog_fields.py', 'packages/python/src/telegram_patterns/dialog_forms.py']
            records[-1]['check_files'].append('packages/python/tests/test_dialog_forms.py')
        if key == 'demo-message-text':
            records[-1]['summary'] = 'Literal text + entities с UTF-16 offsets; интеграция в текущий Dispatcher, без polling на import.'
            records[-1]['tasks'] = ['bot']
            records[-1]['keywords'] += ['форматирование', 'экранирование', 'html', 'MarkdownV2', 'entities', 'UTF-16', 'custom', 'emoji', 'разбиение', 'сообщения']
            records[-1]['source_files'].append('packages/python/src/telegram_patterns/message_text.py')
            records[-1]['check_files'] += ['packages/python/tests/test_message_text.py', 'packages/python/tests/test_message_text_sdk.py']
            records[-1]['scope'] = 'Actual synthetic Dispatcher/StubSession и SDK wire serialization; delivery, Unicode asset metadata, entitlement и physical client не подтверждены.'
        if key == 'demo-media':
            records[-1]['summary'] = 'Typed media, literal captions, one compatible album, replacement and bounded explicit download; attach to current Dispatcher.'
            records[-1]['tasks'] = ['media']
            records[-1]['keywords'] += ['медиа', 'фото', 'документ', 'альбом', 'подпись', 'замена', 'скачивание', 'multipart', 'file_id']
            records[-1]['source_files'].append('packages/python/src/telegram_patterns/media_aiogram.py')
            records[-1]['check_files'].append('packages/python/tests/test_media.py')
            records[-1]['scope'] = 'Actual synthetic Dispatcher, SDK multipart bytes and bounded fixture stream; live upload/rendering/content validation/rights and real download unconfirmed.'
    recovery_file = root / 'examples/python/error_recovery.py'
    recovery = subprocess.run([sys.executable, str(recovery_file)], capture_output=True, text=True, encoding='utf-8', env=environment, timeout=60)
    if recovery.returncode: raise ValueError('Recovery fixture failed')
    evidence = json.loads(recovery.stdout)
    if not evidence.get('passed') or evidence.get('network') is not False or evidence.get('effect_count') != 1 or evidence.get('replayed') is not True:
        raise ValueError('Recovery fixture did not reconcile the same operation')
    add('demo-recovery', 'Потерянный ответ: сверка той же операции',
        'SQLite effect уже сохранен; unknown outcome сверяется тем же scoped ID без второго заказа.', 'scenarios', 'python',
        ['потерянный', 'ответ', 'timeout', 'сверка', 'reconcile', 'повтор', 'операция'], recovery_file.read_text(encoding='utf-8'),
        'mock', 'Локальная SQLite fixture; ACL/scope заданы искусственно. Нет HTTP, server session или доказательства exactly-once доставки.',
        [API], tasks=['recovery'], contexts=['backend'], sdk='python-core', sdk_ver=version, api_version='none',
        source_files=['examples/python/error_recovery.py', 'packages/python/src/telegram_patterns/sqlite_once.py'],
        check_files=['examples/python/error_recovery.py'])
    # Execution metadata describes fixtures and required live project input separately.
    import aiogram.methods as sdk_methods
    method_specs = {m['name']: m for m in api['bot_api']['methods']}
    rights = {
        'createForumTopic': ['В supergroup: administrator + can_manage_topics; private — отдельный допустимый контекст.'],
        'editForumTopic': ['В supergroup: administrator + can_manage_topics, кроме создателя темы; private — отдельный контекст.'],
        'restrictChatMember': ['Supergroup: бот administrator с правами ограничения участников.'],
        'getBusinessAccountGifts': ['Действующий Business connection и can_view_gifts_and_stars.'],
    }
    for record in records:
        native = record['category'] == 'mini-app'
        kind = 'reference' if native else 'sdk-request' if record['category'] == 'bot-api' else 'sdk-markup' if record['category'] == 'keyboards' else 'sqlite' if record['id'] == 'demo-recovery' else 'dispatcher'
        permissions = []
        live_data = []
        if kind == 'sdk-request':
            spec = method_specs[record['id'].removeprefix('api.')]
            live_data = list(spec['required'])
            model = getattr(sdk_methods, spec['sdk_class'])
            hints = sorted(set(re.findall(r'\bcan_[a-z_]+\b', model.__doc__ or '')))
            permissions = rights.get(spec['name'], ['SDK упоминает ' + ', '.join(hints) + '; обязательность и условия проверить в официальном методе.'] if hints else ['Права и контекст метода не полностью индексированы: проверить официальные ограничения.'])
        elif kind == 'sdk-markup':
            live_data = ['Реальные chat/actor, handler и callback/message correlation']
            permissions = ['Проверить фактический chat type, отправку и права автора действия.']
            if record['id'] == 'emoji-fallback': permissions.append('Реальный custom emoji ID и доступность; по умолчанию текстовый fallback.')
            if record['id'] in {'contact-location', 'url-app'}: permissions.append('Обычный private bot chat; соответствующее действие подтверждает пользователь.')
        elif kind == 'dispatcher':
            live_data = ['Текущий Dispatcher, реальные actor/chat и сервис приложения', 'Проверка объекта, автора и состояния до effect/replay']
            permissions = ['Прикладная авторизация сервиса; fixture actor не доказывает server ACL.']
        elif kind == 'sqlite':
            live_data = ['Путь к БД сервиса, проверенный actor scope и неизменяемый operation key']
            permissions = ['Авторизация до записи и возврата сохраненного результата.']
        else:
            live_data = ['Host Telegram.WebApp и аргументы: ' + record['summary'], 'Клиентская версия, launch mechanism и server auth/ACL приложения']
            if record['id'] in {'native.requestContact', 'native.requestWriteAccess'}:
                permissions = ['Пользователь подтверждает native запрос; наличие метода не означает согласие.']
            elif record['id'] == 'native.readTextFromClipboard':
                permissions = ['Запуск из attachment menu и действие пользователя.']
        record['execution'] = {
            'kind': kind,
            'dependencies': [] if kind == 'sqlite' else ['Предоставленный TypeScript tarball и host Mini App'] if native else ['aiogram==' + sdk_version],
            'offline_environment': [], 'offline_permissions': [],
            'offline_data': [] if native else ['Только поставляемые синтетические данные; реальные IDs и secrets не принимаются.'],
            'live_environment': [] if kind == 'sqlite' else ['HTTPS_APP_URL', 'TELEGRAM_WEBAPP_CONTEXT'] if native else ['BOT_TOKEN'],
            'live_permissions': permissions, 'live_data': live_data,
            'live_review': 'Live executor отсутствует. Перед интеграцией проверить источники, ограничения конкретного метода/контекста, auth и ACL; metadata не подтверждает права.',
            'effects': ['Локальные SDK объекты без HTTP'] if kind.startswith('sdk-') else ['Временные файлы/SQLite fixture, очищаемые после обычного завершения'] if kind == 'sqlite' else ['Synthetic Dispatcher + StubSession; временная fixture, без polling'] if kind == 'dispatcher' else ['Offline fragment execution недоступен без host/аргументов'],
        }
        if not native:
            record['source_files'] += ['packages/python/src/telegram_patterns/execution.py', 'packages/python/src/telegram_patterns/_offline_recipe.py']
        if record['id'] == 'demo-calendar':
            record['execution']['dependencies'].append('tzdata==2026.5 (calendar extra; pinned offline fixture)')
            record['execution']['effects'].append('Temporary file SQLite booking + receipt; both cleaned after normal completion')
    data = {'schema_version': 1, 'library_version': version, 'source_snapshot': api['checked_date'],
            'source_hashes': {'bot_api': api['bot_api']['source_sha256'], 'mini_app': api['mini_app']['source_sha256']},
            'recipes': records, 'navigation': NAVIGATION}
    RecipeCatalog(data)  # Validate packaged schema before any output writes.
    return data


def render_html(data: dict, repository_base: str = '../') -> str:
    embedded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return (ROOT / 'scripts/gallery-template.html').read_text(encoding='utf-8').replace('__CATALOG_JSON__', embedded).replace('__REPOSITORY_BASE__', repository_base)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Standalone gallery in an explicitly named NEW or existing output directory')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.output_dir and any(p.is_symlink() or bool(getattr(p, 'is_junction', lambda: False)()) for p in (args.output_dir, *args.output_dir.parents)):
        raise ValueError('Output directory links are not allowed')
    data = build()
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    html = render_html(data, 'files/' if args.output_dir else '../')
    if args.output_dir and (args.output_dir.is_symlink() or bool(getattr(args.output_dir, 'is_junction', lambda: False)())):
        raise ValueError('Output directory links are not allowed')
    output = args.output_dir.resolve() if args.output_dir else ROOT / 'gallery'
    products = {output / 'index.html': html}
    if args.output_dir:
        products[output / 'recipes.json'] = encoded
        for name in ('gallery.css', 'gallery.js'): products[output / name] = (ROOT / 'gallery' / name).read_text(encoding='utf-8')
        for record in data['recipes']:
            for name in (*record['source_files'], *record['check_files']):
                source = ROOT / name
                if any(p.is_symlink() or bool(getattr(p, 'is_junction', lambda: False)()) for p in (source, *source.parents)):
                    raise ValueError('Source links are not allowed')
                products[output / 'files' / name] = source.read_bytes()
    else:
        products[ROOT / 'packages/python/src/telegram_patterns/resources/request-fixtures.json'] = (ROOT / 'catalog/bot-api-request-fixtures.json').read_bytes()
        for name in sorted({name for names in _FIXTURES.values() for name in names}):
            products[ROOT / 'packages/python/src/telegram_patterns/resources/offline' / (name + '.txt')] = (ROOT / 'examples/python' / name).read_bytes()
        products[ROOT / 'packages/python/src/telegram_patterns/resources/recipes.json'] = encoded
        products[ROOT / 'catalog/recipe-gallery.json'] = encoded
    for path in products:
        if any(p.is_symlink() or bool(getattr(p, 'is_junction', lambda: False)()) for p in (path, *path.parents)):
            raise ValueError('Output links are not allowed')
    for path, content in products.items():
        if args.check:
            if not path.is_file() or (path.read_bytes() if isinstance(content, bytes) else path.read_text(encoding='utf-8')) != content: raise ValueError('Gallery output drift: ' + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes): path.write_bytes(content)
            else: path.write_text(content, encoding='utf-8')
    print(json.dumps({'passed': True, 'recipes': len(data['recipes']), 'sdk': sum(item['verification']=='sdk' for item in data['recipes']),
        'mock': sum(item['verification']=='mock' for item in data['recipes']), 'reference': sum(item['verification']=='not_run' for item in data['recipes']),
        'live': 0, 'telegram_network': False, 'mode': 'check' if args.check else 'write'}))


if __name__ == '__main__': main()
