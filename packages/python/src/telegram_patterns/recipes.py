"""Search packaged recipes without SDK imports, execution, secrets or network."""
from __future__ import annotations
from dataclasses import dataclass
from importlib.resources import files
import json
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit


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
    verification: str
    scope: str
    sources: tuple[str, ...]
    preview_json: str | None = None

    @property
    def preview(self) -> dict[str, Any] | None:
        """Independent copy; modifying a preview never changes the catalog."""
        return json.loads(self.preview_json) if self.preview_json is not None else None


class RecipeCatalog:
    """Read-only recipe records; SDK/mock/live levels have distinct scopes."""
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        if data is None:
            data = json.loads(files('telegram_patterns').joinpath('resources/recipes.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('recipes'), list):
            raise ValueError('Unsupported recipe catalog')
        if not isinstance(data.get('library_version'), str): raise ValueError('Missing catalog version')
        self._version = data['library_version']
        records, seen = [], set()
        for item in data['recipes']:
            if not isinstance(item, dict): raise ValueError('Invalid recipe record')
            fields = ('id', 'title', 'summary', 'category', 'language', 'code', 'verification', 'scope')
            if any(not isinstance(item.get(key), str) or not item[key].strip() for key in fields):
                raise ValueError('Invalid recipe fields')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', item['id']) or item['id'] in seen:
                raise ValueError('Invalid or duplicate recipe ID')
            if item['verification'] not in {'sdk', 'mock', 'live', 'not_run'}: raise ValueError('Unknown verification level')
            if item['language'] not in {'python', 'typescript'}: raise ValueError('Unknown recipe language')
            if any(not isinstance(item.get(key), list) or any(not isinstance(value, str) for value in item[key]) for key in ('keywords', 'sources')):
                raise ValueError('Use string lists for keywords and sources')
            if any(urlsplit(url).scheme != 'https' or not urlsplit(url).hostname or urlsplit(url).username for url in item['sources']):
                raise ValueError('Recipe sources must be HTTPS URLs without credentials')
            preview = item.get('preview')
            if preview is not None and not isinstance(preview, dict): raise ValueError('Invalid recipe preview')
            records.append(Recipe(**{key: item[key] for key in fields}, keywords=tuple(item['keywords']), sources=tuple(item['sources']),
                                  preview_json=json.dumps(preview, ensure_ascii=False) if preview is not None else None))
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
               verification: str | None = None, limit: int = 20) -> tuple[Recipe, ...]:
        if not isinstance(query, str) or len(query) > 512 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('Use a query up to 512 characters and a limit of 1..1000')
        if any(value is not None and not isinstance(value, str) for value in (category, language, verification)):
            raise ValueError('Recipe filters must be strings')
        terms, found = normalize(query).split(), []
        for order, recipe in enumerate(self._records):
            if any(value is not None and getattr(recipe, key) != value for key, value in
                   (('category', category), ('language', language), ('verification', verification))): continue
            title, keywords = normalize(recipe.title), normalize(' '.join(recipe.keywords))
            text = normalize(' '.join((recipe.id, recipe.title, recipe.summary, recipe.category, recipe.language, keywords)))
            if not all(term in text for term in terms): continue
            score = sum(10 * (term in title) + 3 * (term in keywords) for term in terms)
            found.append((-score, order, recipe))
        return tuple(item[2] for item in sorted(found)[:limit])
