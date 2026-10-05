"""Local CLI: recipe discovery, NEW project scaffolding and read-only diagnostics."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tarfile
import zipfile

from .diagnostics import diagnose
from .errors import PatternError, safe_error_report
from .recipes import RecipeCatalog
from .starter import create_starter
from .starter_components import StarterConflict, starter_components


def doctor(target: str | Path = '.', *, require_token: bool = False) -> dict:
    return diagnose(target, require_token=require_token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    recipes = commands.add_parser('recipes', help='Search bundled recipes; never executes them')
    recipes.add_argument('query', nargs='?', default=''); recipes.add_argument('--category'); recipes.add_argument('--language')
    recipes.add_argument('--verification'); recipes.add_argument('--limit', type=int, default=20); recipes.add_argument('--show')
    recipes.add_argument('--maturity', choices=('stable', 'experimental', 'reference'))
    for field in ('task', 'context', 'sdk', 'sdk-version', 'api-version'):
        recipes.add_argument('--' + field, help='Exact catalog metadata; not permission/compatibility proof')
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
                found = catalog.search(args.query, category=args.category, language=args.language, verification=args.verification, maturity=args.maturity, limit=args.limit,
                                       task=args.task, context=args.context, sdk=args.sdk, sdk_version=args.sdk_version, api_version=args.api_version)
                print(json.dumps({'version': catalog.library_version, 'matches': len(found), 'recipes': [
                    {'id': item.id, 'title': item.title, 'category': item.category, 'maturity': item.maturity, 'verification': item.verification, 'scope': item.scope,
                     'tasks': item.tasks, 'contexts': item.contexts, 'sdk': item.sdk, 'sdk_version': item.sdk_version, 'api_version': item.api_version,
                     'source_files': item.source_files, 'check_files': item.check_files} for item in found]}, ensure_ascii=False))
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
