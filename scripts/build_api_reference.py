"""Generate standalone Russian API reference; fail on uncovered public exports."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'catalog/api-reference.json'
SECTION = {'core': ('api-reference-core.md', 'Python core'),
           'bot': ('api-reference-bot.md', 'Python bot и test transport'),
           'typescript': ('api-reference-typescript.md', 'TypeScript Mini App')}


def public_inventory() -> dict[str, tuple[str, ...]]:
    result = {}
    for file, module in [('__init__', 'telegram_patterns'), ('aiogram', 'telegram_patterns.aiogram'), ('testing', 'telegram_patterns.testing')]:
        tree = ast.parse((ROOT / f'packages/python/src/telegram_patterns/{file}.py').read_text(encoding='utf-8'))
        value = next(n.value for n in tree.body if isinstance(n, ast.Assign) and
                     any(isinstance(t, ast.Name) and t.id == '__all__' for t in n.targets))
        result[module] = tuple(ast.literal_eval(value))
    result['telegram_patterns.cli'] = ('doctor',)
    text = (ROOT / 'packages/typescript/src/index.ts').read_text(encoding='utf-8')
    result['@awesome-telegram/patterns'] = tuple(name.strip() for match in re.finditer(r'export (?:type )?\{([^}]+)\}', text)
                                               for name in match.group(1).split(','))
    return result


def build() -> tuple[dict[str, str], dict]:
    spec = json.loads(SPEC.read_text(encoding='utf-8'))
    version = json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))['library_version']
    if spec['schema_version'] != 1 or spec['library_version'] != version:
        raise ValueError('Reference schema/version differs from supplied library')
    expected = {(module, name) for module, names in public_inventory().items() for name in names}
    ts_exports = (ROOT / 'packages/typescript/src/index.ts').read_text(encoding='utf-8')
    type_exports = {name.strip() for match in re.finditer(r'export type \{([^}]+)\}', ts_exports)
                    for name in match.group(1).split(',')}
    seen = set(); groups = set(); entries = []; products = {}
    intro = (f'# Справочник API {version}\n\n'
             'Публичные imports, самостоятельные минимальные композиции и границы каждого символа. '
             'Все группы experimental. Рецепты ref.* принадлежат этому справочнику; cookbook RecipeCatalog '
             'отдельно содержит Telegram requests/layouts. Исполненные fixtures не доказывают live/device/provider acceptance.\n\n'
             'Выберите раздел; не подключайте SDK/фреймворк ради core или узкой правки:\n\n')
    intro += '\n'.join(f'- [{title}]({file})' for file, title in SECTION.values()) + '\n\n'
    intro += '| Символ | Импорт | Минимальная композиция / рецепт | Назначение |\n| --- | --- | --- | --- |\n'
    bodies = {key: f'# {title} — {version}\n\n[Индекс всех символов](api-reference.md). '
                       'Образцы ниже воспроизводятся через установленный wheel/tarball вне исходного дерева. '
                       'Assert — проверка fixture, не бизнес-правило production приложения.\n\n'
              for key, (_, title) in SECTION.items()}
    bodies['core'] += ('Установите предоставленный локальный wheel без aiogram. Для core_starter.py передайте '
                       'путь к нему как первый аргумент: `python core_starter.py "<PROVIDED_WHEEL>"`. '
                       'Остальные файлы запускаются `python <FILE.py>`. core_doctor намеренно проверяет SDK-free окружение.\n\n')
    bodies['bot'] += ('Нужны предоставленный wheel с aiogram extra и установленный совместимый SDK. '
                     'В той же папке создайте bot_fixture.py из блока ниже, затем запускайте `python <FILE.py>`. '
                     'Фиктивный token применяется только с StubSession: HTTP fallback отсутствует.\n\n'
                     '## Общая fixture — bot_fixture.py\n\n```python\n' +
                     (ROOT / 'examples/api-reference/python/bot_fixture.py').read_text(encoding='utf-8').rstrip() + '\n```\n\n')
    bodies['typescript'] += ('Установите предоставленный local tarball в отдельный consumer, сохраните файлы в src/, '
                            'добавьте ESM package.json и compile с strict, ES2022, NodeNext и DOM libs. '
                            'Bridge требует настоящий Document; выполняйте exports в браузере, остальные fixtures '
                            'также могут исполняться в Node с Response. Общий check.ts:\n\n```typescript\n' +
                            (ROOT / 'examples/api-reference/typescript/check.ts').read_text(encoding='utf-8').rstrip() + '\n```\n\n')
    bodies['typescript'] += ('## Entry — run.ts\n\nСохраните рядом с check.ts и пятью файлами раздела. '
                            'После strict compile импортируйте runReference из dist/run.js в browser ESM entry '
                            'и вызовите `await runReference(document)`. Bundler текущего проекта разрешает package import; '
                            'plain browser требует import map к установленному dist/index.js и link к styles.css. '
                            'Созданные fixture DOM и listeners удаляются; production UI/state предоставляет host.\n\n```typescript\n' +
                            (ROOT / 'examples/api-reference/typescript/run.ts').read_text(encoding='utf-8').rstrip() + '\n```\n\n')
    for group in spec['groups']:
        identifier = group['id']; section = group['section']
        if identifier in groups or section not in SECTION or not re.fullmatch(r'[a-z][a-z_]+', identifier):
            raise ValueError('Invalid/duplicate reference recipe')
        groups.add(identifier)
        supplied = ROOT / group['example']
        if any(p.is_symlink() or bool(getattr(p, 'is_junction', lambda: False)()) for p in (supplied, *supplied.parents)):
            raise ValueError('Reference source links are not allowed')
        path = supplied.resolve(strict=True)
        if not path.is_relative_to(ROOT / 'examples/api-reference'):
            raise ValueError('Reference example path escaped owned directory')
        code = path.read_text(encoding='utf-8')
        if not group['limits'].strip(): raise ValueError('Reference lacks limits')
        if path.suffix == '.py':
            tree = ast.parse(code)
            bindings = {(node.module, name.name) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                        for name in node.names}
            used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        else:
            bindings = {('@awesome-telegram/patterns', name.strip().removeprefix('type ').strip())
                        for match in re.finditer(r'import\s*\{([^}]+)\}\s*from\s*[\'"]@awesome-telegram/patterns[\'"]', code, re.S)
                        for name in match.group(1).split(',')}
            used = set(re.findall(r'\b[A-Za-z][A-Za-z0-9_]+\b', re.sub(r'import\s*\{[^}]+\}[^;]+;', '', code, flags=re.S)))
        symbols = []
        for module, values in group['api'].items():
            for name, intent in values.items():
                key = module, name
                if key in seen or key not in expected or key not in bindings or name not in used or not intent.strip():
                    raise ValueError('Missing/duplicate/unreferenced documented import: ' + module + '.' + name)
                seen.add(key); symbols.append(name)
                kind = 'type' if module.startswith('@') and name in type_exports else 'value'
                statement = f'import {"type " if kind == "type" else ""}{{{name}}} from "{module}"' if module.startswith('@') else f'from {module} import {name}'
                record = {'module': module, 'name': name, 'import': statement, 'recipe': 'ref.' + identifier,
                          'example': group['example'], 'limits': group['limits'], 'intent': intent,
                          'example_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'kind': kind}
                entries.append(record)
                intro += f'| `{name}` | `{statement}` | [{record["recipe"]}]({SECTION[section][0]}#ref-{identifier}) | {intent} |\n'
        language = 'python' if path.suffix == '.py' else 'typescript'
        bodies[section] += (f'<a id="ref-{identifier}"></a>\n\n## {group["title"]} — ref.{identifier}\n\n'
                            f'Файл: `{path.name}`. Символы: ' + ', '.join(f'`{name}`' for name in symbols) + '\n\n'
                            'Границы: ' + group['limits'] + '\n\n' +
                            f'```{language}\n{code.rstrip()}\n```\n\n')
    if seen != expected:
        raise ValueError('Public export documentation drift: ' + repr(sorted(expected - seen)))
    intro += ('\n## CLI и CSS\n\n'
              '`python -m telegram_patterns recipes "две кнопки"` читает cookbook, не исполняет код. '
              '`python -m telegram_patterns init "<NEW_PATH>" --library "<PROVIDED_WHEEL>" --dry-run` '
              'показывает все файлы; без dry-run создает новый каталог. '
              '`python -m telegram_patterns doctor "<PROJECT>"` делает local diagnosis без repairs/HTTP. '
              'Изменение существующего проекта и live запуск — отдельные действия. Commands/exit codes проверяются installed CLI.\n\n'
              'CSS entry: `@awesome-telegram/patterns/styles.css`. В bundler: '
              '`import "@awesome-telegram/patterns/styles.css";`; в browser consumer подключите link к скопированному '
              'CSS из resolved subpath. CSS не создает UI и не заменяет host state. '
              'Import resolution и настоящий browser stylesheet проверяются отдельно.\n\n'
              'Type-only TypeScript exports существуют в declarations, без runtime JavaScript binding. '
              'Imports типов используют `type`. Python Literal/Protocol '
              'annotations проверяются Mypy; это не runtime validation внешнего JSON.\n')
    products['api-reference.md'] = intro
    for section, body in bodies.items(): products[SECTION[section][0]] = body.rstrip() + '\n'
    index = {'schema_version': 1, 'library_version': version, 'symbols': entries,
             'python_symbols': sum(not item['module'].startswith('@') for item in entries),
             'typescript_symbols': sum(item['module'].startswith('@') for item in entries),
             'recipes': len(groups), 'additional_entries': ['CLI recipes', 'CLI init', 'CLI doctor', 'styles.css'],
             'evidence': 'Installed type/runtime/DOM consumers; no independent agent or physical client proof'}
    return products, index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true')
    args = parser.parse_args(); products, index = build()
    outputs = {ROOT / 'catalog/api-reference-index.json': json.dumps(index, ensure_ascii=False, indent=2) + '\n'}
    for name, content in products.items():
        outputs[ROOT / 'docs' / name] = content
        outputs[ROOT / '.agents/skills/telegram-code-patterns/references' / name] = content
    for path, value in outputs.items():
        if any(p.is_symlink() or bool(getattr(p, 'is_junction', lambda: False)()) for p in (path, *path.parents)):
            raise ValueError('Reference output links are not allowed')
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != value: raise ValueError('Reference output drift: ' + path.name)
        else: path.write_text(value, encoding='utf-8', newline='\n')
    print(json.dumps({'passed': True, 'symbols': len(index['symbols']), 'recipes': index['recipes'],
                      'python': index['python_symbols'], 'typescript': index['typescript_symbols'], 'check': args.check}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
