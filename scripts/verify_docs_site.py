"""Check built documentation links, source hashes and complete skill/API discovery."""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self, raw: str):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.resources: list[str] = []
        self.links: list[str] = []
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            if values['id'] in self.ids:
                raise ValueError('Duplicate HTML ID: ' + values['id'])
            self.ids.add(values['id'])
        if tag == 'a' and values.get('href'):
            self.links.append(values['href'])
        if tag in {'img', 'script'} and values.get('src'):
            self.resources.append(values['src'])
        if tag == 'link' and values.get('rel') == 'stylesheet':
            self.resources.append(values['href'])


def verify(site: Path) -> dict:
    site = site.resolve()
    manifest = json.loads((site / 'site-manifest.json').read_text(encoding='utf-8'))
    errors: list[str] = []
    pages: dict[Path, Page] = {}
    for name, digest in manifest['files'].items():
        file = (site / name).resolve()
        if not file.is_relative_to(site) or not file.is_file() or file.is_symlink():
            errors.append('Unavailable or unsafe artifact: ' + name)
        elif hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            errors.append('Changed artifact: ' + name)
    for name in manifest['pages']:
        file = site / name
        try:
            pages[file.resolve()] = Page(file.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            errors.append(name + ': ' + str(error))
    links = 0
    for file, page in pages.items():
        for href in (*page.links, *page.resources):
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                continue
            links += 1
            target = (file.parent / unquote(parsed.path)).resolve() if parsed.path else file
            if target.is_dir():
                target /= 'index.html'
            if not target.is_relative_to(site) or not target.is_file():
                errors.append(f'{file.relative_to(site)}: missing {href}')
            elif parsed.fragment and target in pages and unquote(parsed.fragment) not in pages[target].ids:
                errors.append(f'{file.relative_to(site)}: missing anchor {href}')
    skills = json.loads((site / 'sources/components.json').read_text(encoding='utf-8'))
    if skills['library_version'] != manifest['version']:
        errors.append('Published catalog version differs from documentation')
    skill_pages = [name for name in manifest['pages'] if name.startswith('skills/') and name.count('/') == 2]
    if len(skill_pages) != manifest['skills']:
        errors.append('Not every skill has a detail page')
    component_pages = [name for name in manifest['pages'] if name.startswith('library/components/')]
    if len(component_pages) != manifest['component_groups']:
        errors.append('Not every component has a detail page')
    api = json.loads((site / 'api-reference-index.json').read_text(encoding='utf-8'))
    if len(api['symbols']) != manifest['api_symbols']:
        errors.append('API index is incomplete')
    search = json.loads((site / 'search-index.json').read_text(encoding='utf-8'))
    for result in search:
        parsed = urlsplit(result['path'])
        target = (site / parsed.path).resolve()
        if target not in pages or (parsed.fragment and parsed.fragment not in pages[target].ids):
            errors.append('Search destination unavailable: ' + result['path'])
    for name in ['llms.txt', 'llms-full.txt', 'for-agents/index.html', 'sitemap.xml', 'robots.txt']:
        if not (site / name).is_file():
            errors.append('Agent/documentation entrypoint missing: ' + name)
    result = {'passed': not errors, 'version': manifest['version'], 'skills': manifest['skills'], 'components': manifest['component_groups'], 'api_symbols': manifest['api_symbols'], 'recipes': manifest['recipes'], 'pages': len(pages), 'local_links_checked': links, 'search_entries': len(search), 'artifact_files': len(manifest['files']), 'errors': errors}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify(args.site)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
