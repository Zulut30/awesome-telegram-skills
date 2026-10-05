"""Verify an exact copied platform guide, Dispatcher and temporary host SQLite."""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import sys
import tempfile
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ('durable_intents', 'unknown_send_no_retry', 'current_actor_acl',
         'fresh_native_rights', 'financial_quote_budget', 'scoped_event_dedup',
         'existing_dispatcher_preserved', 'user_confirmed_managed_link')


def composition(guide: Path) -> str:
    blocks = re.findall(r'```python\n(.*?)```', guide.read_text(encoding='utf-8'), re.S)
    if len(blocks) != 1: raise ValueError('Expected one complete platform composition')
    expected = (ROOT / 'examples/python/platform_bot.py').read_text(encoding='utf-8')
    if blocks[0] != expected:
        raise ValueError('Copied platform composition differs from the reviewed source')
    return blocks[0]


def execute(guide: Path) -> dict:
    source = composition(guide)  # Exact source check before compile/exec.
    module = ModuleType('platform_bot')
    exec(compile(source, str(guide), 'exec'), module.__dict__)
    original = sys.modules.get('platform_bot')
    sys.modules['platform_bot'] = module
    captured = io.StringIO()
    try:
        with redirect_stdout(captured):
            runpy.run_path(str(ROOT / 'examples/python/offline_platform.py'), run_name='__main__')
    finally:
        if original is None: sys.modules.pop('platform_bot', None)
        else: sys.modules['platform_bot'] = original
    result = json.loads(captured.getvalue())
    if (not result['passed'] or result['network'] or not result['session_closed']
            or result['families'] != 7 or result['contracts'] != 51
            or not all(result[key] for key in FLAGS)):
        raise ValueError('Copied platform composition failed')
    return result


def operations(guide: Path) -> dict:
    text = guide.read_text(encoding='utf-8')
    source = composition(guide)
    cases = []
    with tempfile.TemporaryDirectory(prefix='platform guide proof ') as folder:
        target = Path(folder) / 'copied skill' / 'references'
        target.mkdir(parents=True)
        marker = target.parent / 'host-owned.txt'
        marker.write_bytes(b'preserve host content\x00\xff')
        original = marker.read_bytes()
        copied = target / 'platform-operations.md'
        copied.write_text(text, encoding='utf-8')
        copied_before = copied.read_bytes()
        result = execute(copied)
        assert result['confirmed_operations'] == 7
        assert copied.read_bytes() == copied_before and marker.read_bytes() == original
        cases.extend(('exact-copied-guide-executed', 'caller-files-byte-preserved'))
        for label, document in (
            ('missing-block-rejected', text.replace('```python\n' + source + '```', 'No composition')),
            ('tampered-block-rejected-before-execution', text.replace(source, 'raise RuntimeError("must not execute")\n' + source)),
            ('duplicate-block-rejected', text + '\n```python\n' + source + '```\n'),
        ):
            copied.write_text(document, encoding='utf-8')
            before = copied.read_bytes()
            try: composition(copied)
            except ValueError: pass
            else: raise AssertionError('Invalid guide was accepted: ' + label)
            assert copied.read_bytes() == before and marker.read_bytes() == original
            cases.append(label)
    return {'passed': True, 'temporary_operations': cases, 'caller_files_preserved': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill', type=Path)
    args = parser.parse_args()
    guide = args.skill.resolve(strict=True) / 'references/platform-operations.md'
    result = execute(guide)
    result.update(guide_blocks=1, composition_sha256=hashlib.sha256(composition(guide).encode()).hexdigest(),
        helper_operations=operations(guide),
        scope='Exact copied guide and actual SDK/Dispatcher/file SQLite fixtures; no live rights, financial settlement, physical devices or independent acceptance')
    print(json.dumps(result))


if __name__ == '__main__': main()
