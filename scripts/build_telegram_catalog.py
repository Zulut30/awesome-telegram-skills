"""Build searchable API coverage and SDK-valid request-only recipes; no Telegram calls.

Run with the aiogram extra. --mini-app-html imports a saved OFFICIAL documentation
snapshot; normal/check runs use the retained metadata index, without network.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
from importlib.metadata import version
import json
from pathlib import Path
import re
import warnings

from aiogram.types import BufferedInputFile, InputFile, Update
from pydantic.json_schema import GenerateJsonSchema, PydanticJsonSchemaWarning
from telegram_patterns.aiogram import build_request, method_catalog

ROOT = Path(__file__).resolve().parents[1]
MINI_URL = 'https://core.telegram.org/bots/webapps'
MODULE_VERSIONS = {'BackButton': '6.1', 'SettingsButton': '6.10', 'BottomButton': '6.1',
    'HapticFeedback': '6.1', 'CloudStorage': '6.9', 'BiometricManager': '7.2', 'LocationManager': '8.0',
    'Accelerometer': '8.0', 'DeviceOrientation': '8.0', 'Gyroscope': '8.0',
    'DeviceStorage': '9.0', 'SecureStorage': '9.0'}


class FixtureSchema(GenerateJsonSchema):
    """Describe opaque SDK InputFile for fixtures without bypassing validation."""
    def is_instance_schema(self, schema):
        if schema['cls'] is InputFile:
            return {'title': 'InputFile', 'format': 'binary'}
        return super().is_instance_schema(schema)


class MiniParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section, self.anchor, self.heading, self.cell, self.row = '', '', None, None, None
        self.tables = []
    def handle_starttag(self, tag, attrs):
        if tag in {'h3', 'h4'}:
            self.heading, self.anchor = [], ''
        elif tag == 'a' and self.heading is not None:
            self.anchor = dict(attrs).get('name', self.anchor)
        elif tag == 'tr': self.row = []
        elif tag in {'td', 'th'} and self.row is not None: self.cell = []
    def handle_data(self, text):
        if self.heading is not None: self.heading.append(text)
        if self.cell is not None: self.cell.append(text)
    def handle_endtag(self, tag):
        if tag in {'h3', 'h4'} and self.heading is not None:
            self.section = ''.join(self.heading).strip()
            self.heading = None
        elif tag in {'td', 'th'} and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row:
            self.tables.append((self.section, self.anchor, self.row))
            self.row = None


def mini_index(html: str) -> dict:
    parser = MiniParser()
    parser.feed(html)
    methods, events, properties = {}, {}, []
    for section, anchor, row in parser.tables:
        if len(row) < 2: continue
        signature, kind = row[:2]
        name = signature.split('(')[0].removesuffix(' NEW').strip()
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9]*', name): continue
        if name in {'Field', 'Event', 'Method', 'eventType'}: continue
        url = MINI_URL + '#' + anchor
        description = row[2] if len(row) > 2 else ''
        if section == 'Events Available for Mini Apps':
            gates = re.findall(r'\b(\d+\.\d+)\+', kind)
            events[name] = {'name': name, 'min_version': gates[0] if gates else '6.0', 'url': url}
            continue
        if section != 'Initializing Mini Apps' and section not in MODULE_VERSIONS:
            if kind == 'Function': raise ValueError('Unmapped Mini App module: ' + section)
            continue
        if kind != 'Function':
            properties.append({'owner': 'WebApp' if section == 'Initializing Mini Apps' else section,
                               'name': name, 'type': kind, 'url': url})
            continue
        gates = re.findall(r'\b(\d+\.\d+)\+', description)
        minimum = gates[0] if gates else MODULE_VERSIONS.get(section, '6.0')
        owners = [''] if section == 'Initializing Mini Apps' else (['MainButton', 'SecondaryButton'] if section == 'BottomButton' else [section])
        for owner in owners:
            path = f'{owner}.{name}' if owner else name
            if owner == 'SecondaryButton' and tuple(map(int, minimum.split('.'))) < (7, 10): minimum = '7.10'
            methods[path] = {'path': path, 'signature': signature.removesuffix(' NEW'), 'min_version': minimum, 'url': url}
    if not {'ready', 'showPopup', 'BackButton.show', 'LocationManager.getLocation'}.issubset(methods):
        raise ValueError('Mini App documentation layout changed; required methods missing')
    if not {'themeChanged', 'viewportChanged'}.issubset(events):
        raise ValueError('Mini App event table not found')
    return {'source': MINI_URL, 'source_sha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
            'checked_date': '2026-10-04', 'scope': 'WebApp functions, named native modules, events and properties; not MTProto',
            'methods': sorted(methods.values(), key=lambda value: value['path']),
            'events': sorted(events.values(), key=lambda value: value['name']), 'properties': properties}


def fixture(schema: dict, definitions: dict, name: str = '', depth: int = 0):
    if depth > 30: raise ValueError('Recursive required fixture: ' + name)
    if '$ref' in schema: return fixture(definitions[schema['$ref'].split('/')[-1]], definitions, name, depth + 1)
    if 'const' in schema: return schema['const']
    if 'enum' in schema: return schema['enum'][0]
    if 'anyOf' in schema or 'oneOf' in schema:
        alternatives = schema.get('anyOf', schema.get('oneOf'))
        errors = []
        for candidate in alternatives:
            if candidate.get('type') == 'null': continue
            try: return fixture(candidate, definitions, name, depth + 1)
            except (KeyError, ValueError) as error: errors.append(error)
        raise ValueError('Unsupported fixture union: ' + name)
    kind = schema.get('type')
    if schema.get('format') == 'binary': return {'__fixture_file__': 'fixture.bin'}
    if kind == 'object':
        if schema.get('title') == 'InputRichMessage': return {'html': '<b>Пример</b>'}
        properties = schema.get('properties', {})
        keys = list(schema.get('required', []))
        # SDK tagged unions require their literal type even when it has a default.
        keys += [key for key, value in properties.items() if 'const' in value and key not in keys]
        return {key: fixture(properties[key], definitions, key, depth + 1) for key in keys}
    if kind == 'array': return [fixture(schema.get('items', {}), definitions, name, depth + 1)] * max(1, schema.get('minItems', 1))
    if kind in {'integer', 'number'}: return max(1, schema.get('minimum', 1))
    if kind == 'boolean': return True
    if kind == 'null': return None
    if kind == 'string':
        if schema.get('format') == 'date-time': return '2026-10-04T12:00:00Z'
        if schema.get('format') == 'date': return '2026-10-04'
        if name == 'currency': return 'XTR'
        if name == 'format': return 'static'
        if name == 'action': return 'typing'
        if name == 'emoji': return '👍'
        if name in {'url', 'link'}: return 'https://example.invalid/replace-before-use'
        if name in {'photo', 'video', 'audio', 'document', 'sticker', 'animation', 'voice', 'video_note'}: return 'FIXTURE_FILE_ID_REPLACE'
        if name in {'name', 'short_name'}: return 'fixture_name'
        return 'FIXTURE_REPLACE'
    # InputFile intentionally uses a custom SDK schema without JSON shape.
    if 'InputFile' in schema.get('title', '') or name in {'png_sticker', 'sticker', 'photo', 'video', 'certificate'}:
        return {'__fixture_file__': 'fixture.bin'}
    raise ValueError(f'Unsupported fixture schema for {name}: {schema}')


def materialize(value):
    if isinstance(value, dict):
        if set(value) == {'__fixture_file__'}:
            return BufferedInputFile(b'OFFLINE_FIXTURE_NOT_REAL_MEDIA', filename=value['__fixture_file__'])
        return {key: materialize(item) for key, item in value.items()}
    if isinstance(value, list): return [materialize(item) for item in value]
    return value


def python_value(value):
    if isinstance(value, dict):
        if set(value) == {'__fixture_file__'}:
            return 'BufferedInputFile(b"OFFLINE_FIXTURE_NOT_REAL_MEDIA", filename="fixture.bin")'
        return '{' + ', '.join(repr(key) + ': ' + python_value(item) for key, item in value.items()) + '}'
    if isinstance(value, list): return '[' + ', '.join(python_value(item) for item in value) + ']'
    return repr(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mini-app-html', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    index = json.loads((ROOT / '.agents/skills/telegram-bot-api/references/api-index.json').read_text(encoding='utf-8'))
    mini_path = ROOT / 'catalog/mini-app-index.json'
    mini = mini_index(args.mini_app_html.read_text(encoding='utf-8')) if args.mini_app_html else json.loads(mini_path.read_text(encoding='utf-8'))
    specs = {item.name: item for item in method_catalog()}
    if set(specs) != {item['name'] for item in index['methods']}:
        raise ValueError('Official API and installed SDK method sets differ; inspect the delta')
    import aiogram.methods as native_methods
    import aiogram.types as native_types
    entries, recipes, files = [], {}, {}
    for item in index['methods']:
        spec = specs[item['name']]
        model = getattr(native_methods, spec.sdk_class)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', PydanticJsonSchemaWarning)
            schema = model.model_json_schema(schema_generator=FixtureSchema)
        parameters = {name: fixture(schema['properties'][name], schema.get('$defs', {}), name) for name in spec.required}
        try:
            request = build_request(spec.name, materialize(parameters))
        except ValueError:
            raise ValueError('Generated SDK fixture invalid: ' + spec.name) from None
        if request.__api_method__ != spec.name: raise ValueError('Unexpected SDK request type')
        if set(item['fields']) - set(spec.fields): raise ValueError('SDK fields missing: ' + spec.name)
        recipes[spec.name] = parameters
        path = 'recipes/bot-api/methods/' + spec.name + '.md'
        entries.append({**item, 'sdk_class': spec.sdk_class, 'required': list(spec.required), 'recipe': path,
                        'verification': 'sdk_request_constructed; no HTTP, rights or business-flow proof'})
        files[ROOT / path] = (f'# {spec.name}\n\n[Официальные ограничения]({spec.url}). SDK: aiogram {version("aiogram")} / {spec.sdk_class}.\n\n'
            'Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.\n\n'
            '```python\nfrom aiogram.types import BufferedInputFile\nfrom telegram_patterns.aiogram import build_request\n\n'
            f'parameters = {python_value(parameters)}\nrequest = build_request("{spec.name}", parameters)\n'
            '# В async handler текущего проекта после проверки контекста/прав:\n# result = await bot(request)\n```\n\n'
            'Обязательные параметры SDK: ' + (', '.join('`' + name + '`' for name in spec.required) or 'нет') + '.\n\n'
            'Все параметры официального снимка: ' + (', '.join('`' + name + '`' for name in item['fields']) or 'нет') + '.\n')
    types = []
    for item in index['types']:
        sdk = getattr(native_types, item['name'], None)
        if sdk is None: raise ValueError('SDK type missing: ' + item['name'])
        fields = getattr(sdk, 'model_fields', {})
        accepted = set(fields) | {field.alias for field in fields.values() if isinstance(field.alias, str)}
        if set(item['fields']) - accepted: raise ValueError('SDK type fields missing: ' + item['name'])
        types.append({**item, 'sdk_available': True})
    catalog = {'schema_version': 1, 'checked_date': '2026-10-04', 'sdk': 'aiogram ' + version('aiogram'),
               'bot_api': {'version': index['bot_api_version'], 'source': index['source'], 'source_sha256': index['source_sha256'],
                           'methods': entries, 'types': types,
                           'update_kinds': [name for name in Update.model_fields if name != 'update_id']}, 'mini_app': mini,
               'scope': 'All documented Bot API methods/types and native Mini App calls; SDK request recipes are not live workflow tests',
               'external_payments': {'status': 'skills; provider implementations require own API/testing',
                                     'skills': ['telegram-cryptopay', 'telegram-platega', 'telegram-yookassa']},
               'user_account': {'status': 'separate MTProto task/session; never substituted for Bot API', 'skill': 'telegram-user-client'}}
    files[ROOT / 'catalog/telegram-capabilities.json'] = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    files[ROOT / 'catalog/bot-api-request-fixtures.json'] = json.dumps({'scope': 'SDK-only synthetic requests; never send unchanged', 'methods': recipes}, ensure_ascii=False, indent=2) + '\n'
    files[mini_path] = json.dumps(mini, ensure_ascii=False, indent=2) + '\n'
    definitions = {item['path']: {'minVersion': item['min_version'], 'url': item['url']} for item in mini['methods']}
    files[ROOT / 'packages/typescript/src/native-catalog.ts'] = (
        '// Generated by scripts/build_telegram_catalog.py from official metadata.\n'
        'const definitions = ' + json.dumps(definitions, ensure_ascii=False, indent=2) + ' as const;\n'
        'export const TELEGRAM_NATIVE_METHODS = Object.freeze(Object.fromEntries(Object.entries(definitions).map(([key,value]) => [key,Object.freeze(value)]))) as Readonly<typeof definitions>;\n'
        'export type TelegramNativeMethod = keyof typeof definitions;\n'
        'export const TELEGRAM_NATIVE_EVENTS = Object.freeze(' + json.dumps([item['name'] for item in mini['events']]) + ' as const);\n'
        'export type TelegramNativeEvent = typeof TELEGRAM_NATIVE_EVENTS[number];\n')
    event_definitions = {item['name']: {'minVersion': item['min_version'], 'url': item['url']} for item in mini['events']}
    files[ROOT / 'packages/typescript/src/native-catalog.ts'] += ('const eventDefinitions = ' + json.dumps(event_definitions, indent=2)
        + ' as const;\nexport const TELEGRAM_NATIVE_EVENT_DETAILS = Object.freeze(Object.fromEntries(Object.entries(eventDefinitions).map(([key,value]) => [key,Object.freeze(value)]))) as Readonly<typeof eventDefinitions>;\n')
    files[ROOT / 'recipes/mini-app/README.md'] = ('# Native Mini App API\n\n'
        'Каталог функций текущего официального client API. `TelegramNativeAPI` проверяет version gate и наличие метода; permissions, параметры, результат callback и жизненный цикл экрана проверяет вызывающий код. Сигнатуры здесь справочные; wrapper не подменяет их полной TypeScript схемой SDK.\n\n'
        '```typescript\nimport { TelegramNativeAPI } from "@awesome-telegram/patterns";\ndeclare const nativeApp: unknown; // Host передает свой Telegram.WebApp.\nconst api = new TelegramNativeAPI(nativeApp);\nif (api.supports("HapticFeedback.selectionChanged")) {\n  api.call("HapticFeedback.selectionChanged");\n}\nconst unsubscribe = api.supports("onEvent") && api.supports("offEvent")\n  ? api.listen("themeChanged", () => { /* перечитать тему */ }) : () => {};\n// При уходе с экрана:\nunsubscribe();\napi.dispose();\n```\n\n'
        '| Путь | Native сигнатура | Минимальная версия | Документация |\n| --- | --- | --- | --- |\n'
        + ''.join(f'| `{item["path"]}` | `{item["signature"]}` | {item["min_version"]} | [Telegram]({item["url"]}) |\n' for item in mini['methods'])
        + '\n## События\n\n' + ', '.join(f'`{item["name"]}`' for item in mini['events']) + '.\n\n'
        'Обычный браузер и mock не подтверждают поддержку настоящим Telegram-клиентом. Методы с user interaction / init / permissions вызывайте в указанном документацией порядке; callback может означать отказ или отмену, а отсутствие синхронной ошибки не означает успех. Отписки для `onClick`/`onEvent`, вызванных напрямую через call, принадлежат вам; listen управляет только своими подписками.\n')
    readme = '# Все методы Bot API\n\nСнимок ' + index['bot_api_version'] + ', ' + str(len(entries)) + ' методов. Для каждой строки есть Python пример построения запроса через публичный API библиотеки. Значения искусственные; Telegram HTTP/права/бизнес-сценарии ими не проверены. Практические примеры клавиатур: [keyboards.md](keyboards.md).\n\n| Метод | Обязательные параметры SDK |\n| --- | --- |\n'
    readme += ''.join('| [' + item['name'] + '](methods/' + item['name'] + '.md) | ' + (', '.join(item['required']) or '—') + ' |\n' for item in entries)
    files[ROOT / 'recipes/bot-api/README.md'] = readme
    for path, content in files.items():
        if not path.resolve().is_relative_to(ROOT.resolve()): raise ValueError('Output outside repository')
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != content: raise ValueError('Generated output drift: ' + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
    print(json.dumps({'passed': True, 'methods': len(entries), 'types': len(types), 'mini_app_methods': len(mini['methods']),
                      'mini_app_events': len(mini['events']), 'mode': 'check' if args.check else 'write', 'network': False}))


if __name__ == '__main__': main()
