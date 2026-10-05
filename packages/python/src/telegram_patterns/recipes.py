"""Search packaged recipes without SDK imports, execution, secrets or network."""
from __future__ import annotations
from .errors import ValidationFailure
from dataclasses import dataclass
from importlib.resources import files
import json
import re
import unicodedata
from typing import Any, Literal, TypeAlias, cast
from urllib.parse import urlsplit

Maturity: TypeAlias = Literal['stable', 'experimental', 'reference']
VerificationLevel: TypeAlias = Literal['sdk', 'mock', 'browser', 'live', 'not_run']


def normalize(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold().replace('ё', 'е')


@dataclass(frozen=True, slots=True)
class Recipe:
    id: str
    title: str
    summary: str
    category: str
    language: str
    keywords: tuple[str, ...]
    code: str
    verification: VerificationLevel
    scope: str
    sources: tuple[str, ...]
    preview_json: str | None = None
    maturity: Maturity = 'experimental'
    tasks: tuple[str, ...] = ()
    contexts: tuple[str, ...] = ('unspecified',)
    sdk: str = 'unspecified'
    sdk_version: str = 'unspecified'
    api_version: str = 'unspecified'
    source_files: tuple[str, ...] = ()
    check_files: tuple[str, ...] = ()
    execution_json: str | None = None

    @property
    def execution(self) -> dict[str, Any] | None:
        """Detached prerequisite description; metadata itself never executes code."""
        return json.loads(self.execution_json) if self.execution_json is not None else None

    @property
    def preview(self) -> dict[str, Any] | None:
        """Independent copy; modifying a preview never changes the catalog."""
        return json.loads(self.preview_json) if self.preview_json is not None else None


class RecipeCatalog:
    """Read-only records; maturity is independent of verification evidence."""
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        if data is None:
            data = json.loads(files('telegram_patterns').joinpath('resources/recipes.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('recipes'), list):
            raise ValidationFailure('Unsupported recipe catalog')
        if not isinstance(data.get('library_version'), str): raise ValidationFailure('Missing catalog version')
        self._version = data['library_version']
        records, seen = [], set()
        for item in data['recipes']:
            if not isinstance(item, dict): raise ValidationFailure('Invalid recipe record')
            fields = ('id', 'title', 'summary', 'category', 'language', 'code', 'verification', 'scope')
            if any(not isinstance(item.get(key), str) or not item[key].strip() for key in fields):
                raise ValidationFailure('Invalid recipe fields')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', item['id']) or item['id'] in seen:
                raise ValidationFailure('Invalid or duplicate recipe ID')
            if item['verification'] not in {'sdk', 'mock', 'browser', 'live', 'not_run'}: raise ValidationFailure('Unknown verification level')
            # Never infer stable status from an SDK/mock/browser/live check.
            maturity = item.get('maturity', 'reference' if item['verification'] == 'not_run' or item['category'] == 'bot-api' else 'experimental')
            if not isinstance(maturity, str) or maturity not in {'stable', 'experimental', 'reference'}:
                raise ValidationFailure('Unknown recipe maturity')
            if item['language'] not in {'python', 'typescript'}: raise ValidationFailure('Unknown recipe language')
            if any(not isinstance(item.get(key), list) or any(not isinstance(value, str) for value in item[key]) for key in ('keywords', 'sources')):
                raise ValidationFailure('Use string lists for keywords and sources')
            if any(urlsplit(url).scheme != 'https' or not urlsplit(url).hostname or urlsplit(url).username for url in item['sources']):
                raise ValidationFailure('Recipe sources must be HTTPS URLs without credentials')
            preview = item.get('preview')
            if preview is not None and not isinstance(preview, dict): raise ValidationFailure('Invalid recipe preview')
            metadata: dict[str, Any] = {}
            execution = item.get('execution')
            if execution is not None:
                if not isinstance(execution, dict) or execution.get('kind') not in {'sdk-request', 'sdk-markup', 'dispatcher', 'sqlite', 'reference'}:
                    raise ValidationFailure('Invalid execution requirements')
                for field in ('dependencies', 'offline_environment', 'offline_permissions', 'offline_data', 'live_environment', 'live_permissions', 'live_data', 'effects'):
                    if not isinstance(execution.get(field), list) or any(not isinstance(v, str) or not 1 <= len(v) <= 1000 for v in execution[field]):
                        raise ValidationFailure('Execution requirements use nonempty string lists')
                if not isinstance(execution.get('live_review'), str) or not execution['live_review'].strip():
                    raise ValidationFailure('Live requirements need an explicit review boundary')
            metadata['execution_json'] = json.dumps(execution, ensure_ascii=False) if execution is not None else None
            for field, default in [('tasks', []), ('contexts', ['unspecified'])]:
                value = item.get(field, default)
                if not isinstance(value, list) or any(not isinstance(v, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', v) for v in value):
                    raise ValidationFailure('Recipe task/context must be slug lists')
                if field == 'contexts' and not value: raise ValidationFailure('Use an explicit unspecified context')
                metadata[field] = tuple(dict.fromkeys(value))
            for field in ('sdk', 'sdk_version', 'api_version'):
                value = item.get(field, 'unspecified')
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:+-]{1,80}', value):
                    raise ValidationFailure('Invalid recipe SDK/version metadata')
                metadata[field] = value
            for field in ('source_files', 'check_files'):
                value = item.get(field, [])
                if not isinstance(value, list) or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}', v)
                        or any(part in {'', '.', '..'} for part in v.split('/')) for v in value):
                    raise ValidationFailure('Recipe links must be relative repository paths without traversal')
                metadata[field] = tuple(dict.fromkeys(value))
            records.append(Recipe(**{key: item[key] for key in fields}, keywords=tuple(item['keywords']), sources=tuple(item['sources']),
                                  preview_json=json.dumps(preview, ensure_ascii=False) if preview is not None else None, maturity=cast(Maturity, maturity), **metadata))
            seen.add(item['id'])
        self._records = tuple(records)

    @property
    def library_version(self) -> str: return self._version

    @property
    def recipes(self) -> tuple[Recipe, ...]: return self._records

    def get(self, recipe_id: str) -> Recipe:
        for recipe in self._records:
            if recipe.id == recipe_id: return recipe
        raise KeyError('Unknown recipe ID')

    def search(self, query: str = '', *, category: str | None = None, language: str | None = None,
               verification: VerificationLevel | None = None, maturity: Maturity | None = None, limit: int = 20,
               task: str | None = None, context: str | None = None, sdk: str | None = None,
               sdk_version: str | None = None, api_version: str | None = None) -> tuple[Recipe, ...]:
        if not isinstance(query, str) or len(query) > 512 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationFailure('Use a query up to 512 characters and a limit of 1..1000')
        if any(value is not None and not isinstance(value, str) for value in (category, language, verification, maturity)):
            raise ValidationFailure('Recipe filters must be strings')
        if maturity is not None and maturity not in {'stable', 'experimental', 'reference'}:
            raise ValidationFailure('Unknown recipe maturity')
        if any(v is not None and (not isinstance(v, str) or not 1 <= len(v) <= 80) for v in (task, context, sdk, sdk_version, api_version)):
            raise ValidationFailure('Navigation filters must be nonempty strings up to 80 characters')
        terms, found = normalize(query).split(), []
        for order, recipe in enumerate(self._records):
            if any(value is not None and getattr(recipe, key) != value for key, value in
                   (('category', category), ('language', language), ('verification', verification), ('maturity', maturity),
                    ('sdk', sdk), ('sdk_version', sdk_version), ('api_version', api_version))): continue
            if task is not None and task not in recipe.tasks or context is not None and context not in recipe.contexts: continue
            title, keywords = normalize(recipe.title), normalize(' '.join(recipe.keywords))
            text = normalize(' '.join((recipe.id, recipe.title, recipe.summary, recipe.category, recipe.language, keywords,
                                      *recipe.tasks, *recipe.contexts, recipe.sdk, recipe.sdk_version, recipe.api_version)))
            if not all(term in text for term in terms): continue
            score = sum(10 * (term in title) + 3 * (term in keywords) for term in terms)
            found.append((-score, order, recipe))
        return tuple(item[2] for item in sorted(found)[:limit])
