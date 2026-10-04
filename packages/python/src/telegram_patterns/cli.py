"""Local CLI: recipe discovery, NEW project scaffolding and read-only diagnostics."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile

from .errors import PatternError, ValidationFailure, safe_error_report
from .recipes import RecipeCatalog
from .settings import BotSettings
from .starter import create_starter
from .starter_components import StarterConflict, starter_components


def doctor(target: str | Path = '.', *, require_token: bool = False) -> dict:
    root = Path(target).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValidationFailure('Doctor expects a project directory')
    checks = []
    def check(name, status, detail): checks.append({'name': name, 'status': status, 'detail': detail})
    check('python', 'pass' if sys.version_info >= (3, 11) else 'fail', '.'.join(map(str, sys.version_info[:3])))
    check('library', 'pass', importlib.metadata.version('awesome-telegram-patterns'))
    try:
        sdk = importlib.metadata.version('aiogram')
        major, minor = map(int, sdk.split('.')[:2])
        check('aiogram', 'pass' if major == 3 and minor >= 31 else 'fail', sdk)
        if sdk != '3.31.0': check('sdk-tested-version', 'warn', 'This release was tested on aiogram 3.31.0; verify your SDK separately')
        from . import aiogram as adapter
        check('python-exports', 'pass' if all(callable(getattr(adapter, name, None)) for name in ('command_router', 'action_menu', 'run_bot')) else 'fail', 'Public library adapters')
    except importlib.metadata.PackageNotFoundError:
        check('aiogram', 'fail', 'Install the provided local library with its aiogram extra')
    except ImportError:
        check('python-exports', 'fail', 'Library/SDK import failed; inspect dependency compatibility')
    pyproject = root / 'pyproject.toml'
    if pyproject.is_file():
        try: tomllib.loads(pyproject.read_text(encoding='utf-8')); check('pyproject', 'pass', 'TOML parsed; project code not executed')
        except (ValueError, UnicodeError): check('pyproject', 'fail', 'Invalid TOML')
    else: check('pyproject', 'warn', 'No pyproject.toml; existing projects may use another dependency format')
    try:
        BotSettings.from_env()
        check('token-format', 'pass', 'Present in environment; only local format checked')
    except ValueError:
        check('token-format', 'fail' if require_token else 'warn', 'Missing/invalid BOT_TOKEN; value not displayed; token not sent')
    mini = root / 'mini-app/package.json'
    if mini.is_file():
        try:
            data = json.loads(mini.read_text(encoding='utf-8'))
            valid = isinstance(data, dict) and '@awesome-telegram/patterns' in data.get('dependencies', {})
            check('mini-app-manifest', 'pass' if valid else 'fail', 'TypeScript manifest; no npm installation performed')
        except (ValueError, UnicodeError): check('mini-app-manifest', 'fail', 'Invalid package.json')
        node = shutil.which('node')
        check('npm', 'pass' if shutil.which('npm.cmd' if os.name == 'nt' else 'npm') else 'fail', 'PATH availability; packages are not installed by doctor')
        if node:
            environment = dict(os.environ); environment.pop('NODE_OPTIONS', None)
            try:
                result = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=10, env=environment)
                import re
                match = re.fullmatch(r'v(\d+)\.\d+\.\d+', result.stdout.strip())
                check('node', 'pass' if result.returncode == 0 and match and int(match.group(1)) >= 20 else 'fail',
                      match.group(0) if match else 'Cannot identify Node version; requires >=20')
            except (OSError, subprocess.TimeoutExpired): check('node', 'fail', 'Cannot read Node version')
        else: check('node', 'fail', 'Node >=20 missing from PATH')
    return {'passed': not any(item['status'] == 'fail' for item in checks), 'network': False, 'checks': checks,
            'limits': 'No Telegram token validity/webhook/polling, deployment, project-code execution, backend auth or real-client check'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    recipes = commands.add_parser('recipes', help='Search bundled recipes; never executes them')
    recipes.add_argument('query', nargs='?', default=''); recipes.add_argument('--category'); recipes.add_argument('--language')
    recipes.add_argument('--verification'); recipes.add_argument('--limit', type=int, default=20); recipes.add_argument('--show')
    recipes.add_argument('--maturity', choices=('stable', 'experimental', 'reference'))
    init = commands.add_parser('init', help='Create a NEW project; no install/network/overwrite')
    init.add_argument('target', nargs='?'); init.add_argument('--library'); init.add_argument('--template', choices=('bot', 'bot-mini-app'), default='bot')
    init.add_argument('--typescript'); init.add_argument('--dry-run', action='store_true')
    init.add_argument('--component', action='append', help='Repeat a selectable component ID; dependencies are included')
    init.add_argument('--list-components', action='store_true', help='List the closed starter registry; no filesystem or network')
    diagnostics = commands.add_parser('doctor', help='Read-only local diagnostics; never prints token')
    diagnostics.add_argument('target', nargs='?', default='.'); diagnostics.add_argument('--require-token', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'recipes':
            catalog = RecipeCatalog()
            if args.show:
                recipe = catalog.get(args.show)
                print(f'{recipe.title}\n{recipe.maturity} / {recipe.verification}: {recipe.scope}\n\n{recipe.code}')
            else:
                found = catalog.search(args.query, category=args.category, language=args.language, verification=args.verification, maturity=args.maturity, limit=args.limit)
                print(json.dumps({'version': catalog.library_version, 'matches': len(found), 'recipes': [
                    {'id': item.id, 'title': item.title, 'category': item.category, 'maturity': item.maturity, 'verification': item.verification, 'scope': item.scope} for item in found]}, ensure_ascii=False))
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
        print(json.dumps({'passed': False, 'error': 'StarterConflict', 'reason': error.reason,
                          'detail': str(error), 'failure': safe_error_report(error, operation='read').as_dict(),
                          'supported_components': [item.id for item in starter_components()]}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (PatternError, ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, tarfile.TarError) as error:
        # Do not expose config/env payloads or arbitrary exception text.
        print(json.dumps({'passed': False, 'error': type(error).__name__, 'failure': safe_error_report(error, operation='write' if args.command == 'init' and not args.dry_run else 'read').as_dict(), 'detail': 'Invalid input, existing target or unavailable local artifact. No existing files replaced; failed new project creation may leave partial files.'}), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
