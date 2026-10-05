"""Read-only recipe plans and explicit isolated runs of bundled offline fixtures."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from .errors import InvalidCompletion, TimeoutFailure, UnsupportedCapability, ValidationFailure
from .recipes import RecipeCatalog

_SYSTEM_ENV = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC'}


@dataclass(frozen=True, slots=True)
class RecipeRunPlan:
    recipe_id: str
    library_version: str
    kind: str
    dependencies: tuple[str, ...]
    offline_environment: tuple[str, ...]
    offline_permissions: tuple[str, ...]
    offline_data: tuple[str, ...]
    live_environment: tuple[str, ...]
    live_permissions: tuple[str, ...]
    live_data: tuple[str, ...]
    live_review: str
    effects: tuple[str, ...]
    sources: tuple[str, ...]
    blocked_reasons: tuple[str, ...]

    @property
    def offline_ready(self) -> bool:
        return not self.blocked_reasons


@dataclass(frozen=True, slots=True)
class RecipeRunResult:
    recipe_id: str
    library_version: str
    kind: str
    checks: tuple[str, ...]
    passed: bool = True
    telegram_requests: bool = False


def plan_recipe(recipe_id: str) -> RecipeRunPlan:
    """Describe the installed cookbook; reads no token, dotenv or application file."""
    if not isinstance(recipe_id, str):
        raise ValidationFailure('Use a recipe ID')
    catalog = RecipeCatalog()
    recipe = catalog.get(recipe_id)
    execution = recipe.execution
    if execution is None:
        raise UnsupportedCapability('This recipe has no declared execution plan')
    blocked = []
    if execution['kind'] == 'reference':
        blocked.append('native-host-and-arguments-required')
    if recipe.sdk == 'aiogram':
        try:
            installed = importlib.metadata.version('aiogram')
        except importlib.metadata.PackageNotFoundError:
            blocked.append('aiogram-extra-required')
        else:
            if installed != recipe.sdk_version:
                blocked.append('sdk-differs-from-checked-fixture')
    if recipe.id == 'demo-calendar':
        try:
            data_version = importlib.metadata.version('tzdata')
        except importlib.metadata.PackageNotFoundError:
            blocked.append('calendar-extra-required')
        else:
            if data_version != '2026.5':
                blocked.append('calendar-data-differs-from-checked-fixture')
    return RecipeRunPlan(recipe.id, catalog.library_version, execution['kind'],
                         dependencies=tuple(execution['dependencies']),
                         offline_environment=tuple(execution['offline_environment']),
                         offline_permissions=tuple(execution['offline_permissions']),
                         offline_data=tuple(execution['offline_data']),
                         live_environment=tuple(execution['live_environment']),
                         live_permissions=tuple(execution['live_permissions']),
                         live_data=tuple(execution['live_data']), effects=tuple(execution['effects']),
                         live_review=execution['live_review'], sources=recipe.sources,
                         blocked_reasons=tuple(blocked))


def run_recipe_offline(recipe_id: str, *, timeout: float = 60.0) -> RecipeRunResult:
    """Run a closed bundled fixture, never recipe.code or user application code.

    Requires an installed wheel in the current interpreter. Child -I/-B ignores
    source PYTHONPATH/user-site/cwd, receives only system environment and owns a
    temporary cwd. Native reference fragments are refused before child creation.
    This is a trusted-package offline helper, not an OS sandbox for untrusted code.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 120:
        raise ValidationFailure('Use a timeout of 1..120 seconds')
    plan = plan_recipe(recipe_id)
    if not plan.offline_ready:
        raise UnsupportedCapability('Offline prerequisites are not met; inspect plan_recipe')
    environment = {key: value for key, value in os.environ.items() if key.upper() in _SYSTEM_ENV}
    environment['PYTHONUTF8'] = '1'
    try:
        with TemporaryDirectory(prefix='telegram-offline-recipe-') as folder:
            result = subprocess.run([sys.executable, '-I', '-B', '-m', 'telegram_patterns._offline_recipe', recipe_id],
                                    cwd=folder, env=environment, capture_output=True, text=True,
                                    encoding='utf-8', timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        raise TimeoutFailure('Offline fixture exceeded its deadline') from None
    if result.returncode or len(result.stdout) > 256 * 1024:
        raise InvalidCompletion('Offline fixture failed; no raw child output is reflected')
    try:
        report = json.loads(result.stdout)
        checks = report['checks']
        valid = (report['passed'] is True and report['recipe_id'] == plan.recipe_id and
                 report['library_version'] == plan.library_version and report['kind'] == plan.kind and
                 report['telegram_requests'] is False and report['external_network_attempts'] == 0 and
                 isinstance(checks, list) and checks and all(isinstance(c, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', c) for c in checks))
        if not valid:
            raise ValueError('Invalid completion')
    except (KeyError, TypeError, ValueError):
        raise InvalidCompletion('Offline fixture returned invalid completion') from None
    return RecipeRunResult(plan.recipe_id, plan.library_version, plan.kind, tuple(checks))
