"""Local CLI: recipe discovery, NEW project scaffolding and read-only diagnostics."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tarfile
import zipfile

from importlib.resources import files

from .diagnostics import diagnose
from .errors import PatternError, safe_error_report
from .recipes import RecipeCatalog
from .execution import plan_recipe, run_recipe_offline
from .starter import create_starter
from .starter_components import StarterConflict, starter_components


def doctor(target: str | Path = '.', *, require_token: bool = False) -> dict:
    return diagnose(target, require_token=require_token)


_PROBLEMS = {
    'installation': ('Пакет установлен не полностью: нет встроенного ресурса.',
                     'Переустановите awesome-telegram-patterns из полного wheel или checkout.'),
    'target-exists': ('Каталог проекта уже существует.', 'init создает только новый каталог: укажите другой путь.'),
    'artifact': ('Переданный wheel или tarball поврежден или не является архивом пакета.',
                 'Укажите файл, собранный из awesome-telegram-patterns, или каталог packages/python.'),
    'filesystem': ('Не удалось прочитать или записать файл.', 'Проверьте путь и права доступа.'),
    'input': ('Команда получила неподходящие данные.', 'Проверьте аргументы: telegram-patterns <команда> --help.'),
}
_RECOVERY = {
    'fix-input': 'Исправьте аргументы и повторите команду.',
    'reconcile': 'Проверьте, что уже создано, прежде чем повторять команду.',
    'use-fallback': 'Эта возможность здесь недоступна; выберите другой способ.',
}


def _problem(error: BaseException) -> str:
    if isinstance(error, FileNotFoundError) and error.filename is not None:
        package = Path(str(files('telegram_patterns'))).resolve()
        try:
            Path(error.filename).resolve().relative_to(package)
            return 'installation'
        except ValueError:
            return 'filesystem'
    if isinstance(error, FileExistsError):
        return 'target-exists'
    if isinstance(error, (zipfile.BadZipFile, tarfile.TarError)):
        return 'artifact'
    if isinstance(error, OSError):
        return 'filesystem'
    return 'input'


def _echo(text: str) -> None:
    """stderr may be a redirected legacy-encoded console; never fail while reporting."""
    encoding = getattr(sys.stderr, 'encoding', None)
    print(text.encode(encoding, 'backslashreplace').decode(encoding) if encoding else text, file=sys.stderr)


def _report(payload: dict, *, as_json: bool) -> None:
    if as_json:
        # ASCII JSON stays decodable across redirected console encodings.
        print(json.dumps(payload), file=sys.stderr)
        return
    failure = payload['failure']
    summary, hint = _PROBLEMS[payload['problem']]
    if payload.get('reason'):  # known starter conflict: its own explanation is already actionable
        lines = [f"Ошибка: {payload['detail']}", f"Что сделать: {_RECOVERY.get(failure['recovery'], hint)}"]
    else:
        lines = [f'Ошибка: {summary}']
        if payload['problem'] == 'input':
            lines.append(f"Причина: {failure['message']}")
        lines.append(f'Что сделать: {hint}')
    if failure['outcome'] == 'unknown':
        lines.append('Новый каталог мог быть создан частично; существующие файлы не заменялись.')
    lines.append('Машиночитаемый отчет: добавьте --json.')
    _echo('\n'.join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', help='Print errors as one ASCII JSON object on stderr')
    commands = parser.add_subparsers(dest='command', required=True)
    recipes = commands.add_parser('recipes', parents=[common], help='Search bundled recipes; never executes them')
    recipes.add_argument('query', nargs='?', default=''); recipes.add_argument('--category'); recipes.add_argument('--language')
    recipes.add_argument('--verification'); recipes.add_argument('--limit', type=int, default=20); recipes.add_argument('--show')
    recipes.add_argument('--maturity', choices=('stable', 'experimental', 'reference'))
    for field in ('task', 'context', 'sdk', 'sdk-version', 'api-version'):
        recipes.add_argument('--' + field, help='Exact catalog metadata; not permission/compatibility proof')
    init = commands.add_parser('init', parents=[common], help='Create a NEW project; no install/network/overwrite')
    init.add_argument('target', nargs='?'); init.add_argument('--library'); init.add_argument('--template', choices=('bot', 'bot-mini-app'), default='bot')
    init.add_argument('--typescript'); init.add_argument('--dry-run', action='store_true')
    init.add_argument('--component', action='append', help='Repeat a selectable component ID; dependencies are included')
    init.add_argument('--list-components', action='store_true', help='List the closed starter registry; no filesystem or network')
    diagnostics = commands.add_parser('doctor', parents=[common], help='Read-only local diagnostics; never prints token')
    diagnostics.add_argument('target', nargs='?', default='.'); diagnostics.add_argument('--require-token', action='store_true')
    run_recipe = commands.add_parser('run-recipe', parents=[common], help='Show prerequisites; --offline runs only a bundled fixture')
    run_recipe.add_argument('recipe_id')
    run_recipe.add_argument('--offline', action='store_true')
    run_recipe.add_argument('--timeout', type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        if args.command == 'recipes':
            catalog = RecipeCatalog()
            if args.show:
                recipe = catalog.get(args.show)
                print(f'{recipe.title}\n{recipe.maturity} / {recipe.verification}: {recipe.scope}\n\n{recipe.code}')
            else:
                found = catalog.search(args.query, category=args.category, language=args.language, verification=args.verification, maturity=args.maturity, limit=args.limit,
                                       task=args.task, context=args.context, sdk=args.sdk, sdk_version=args.sdk_version, api_version=args.api_version)
                print(json.dumps({'version': catalog.library_version, 'matches': len(found), 'recipes': [
                    {'id': item.id, 'title': item.title, 'category': item.category, 'maturity': item.maturity, 'verification': item.verification, 'scope': item.scope,
                     'tasks': item.tasks, 'contexts': item.contexts, 'sdk': item.sdk, 'sdk_version': item.sdk_version, 'api_version': item.api_version,
                     'source_files': item.source_files, 'check_files': item.check_files} for item in found]}, ensure_ascii=False))
        elif args.command == 'run-recipe':
            from dataclasses import asdict
            execution_plan = plan_recipe(args.recipe_id)
            # -I ignores PYTHONUTF8 on Windows; ASCII JSON preserves every Unicode
            # value while remaining decodable across redirected console encodings.
            print(json.dumps({'stage': 'plan', **asdict(execution_plan), 'offline_ready': execution_plan.offline_ready}), flush=True)
            if args.offline:
                result = run_recipe_offline(args.recipe_id, timeout=args.timeout)
                print(json.dumps({'stage': 'result', **asdict(result)}))
        elif args.command == 'init':
            if args.list_components:
                if args.target or args.library or args.typescript or args.component or args.dry_run:
                    raise StarterConflict('listing-input')
                from dataclasses import asdict
                print(json.dumps({'components': [asdict(item) for item in starter_components()], 'network': False}, ensure_ascii=False))
                return 0
            if not args.target or not args.library: raise StarterConflict('missing-input')
            plan = create_starter(args.target, library=args.library, template=args.template, typescript=args.typescript,
                                  dry_run=args.dry_run, components=args.component)
            print(json.dumps({'created': plan.created, 'target': str(plan.target), 'template': plan.template,
                              'library_version': plan.library_version, 'files': plan.files, 'components': plan.components,
                              'requested_components': plan.requested_components, 'network': False}))
        else:
            report = doctor(args.target, require_token=args.require_token)
            print(json.dumps(report)); return 0 if report['passed'] else 1
    except StarterConflict as error:
        _report({'passed': False, 'error': 'StarterConflict', 'problem': 'input', 'reason': error.reason,
                 'detail': str(error), 'failure': safe_error_report(error, operation='read').as_dict(),
                 'supported_components': [item.id for item in starter_components()]}, as_json=args.json)
        return 2
    except (PatternError, ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, tarfile.TarError) as error:
        # Do not expose config/env payloads or arbitrary exception text.
        problem = _problem(error)
        operation = 'write' if args.command == 'init' and not args.dry_run and problem != 'installation' else 'read'
        _report({'passed': False, 'error': type(error).__name__, 'problem': problem,
                 'failure': safe_error_report(error, operation=operation).as_dict(),
                 'detail': 'Invalid input, existing target or unavailable local artifact. No existing files replaced; failed new project creation may leave partial files.'},
                as_json=args.json)
        return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
