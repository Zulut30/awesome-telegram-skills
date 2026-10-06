"""Execute exact standalone guide in copied files and actual restarted processes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ('separate_process_restart', 'resumed_answers', 'original_deadline_preserved', 'operation_ids_match',
         'expired_draft_removed', 'expired_pending_preserved', 'version_refused_without_reset',
         'host_data_preserved', 'existing_dispatcher_preserved')


def composition(guide: Path) -> str:
    blocks = re.findall(r'```python\n(.*?)```', guide.read_text(encoding='utf-8'), re.S)
    expected = (ROOT / 'examples/python/dialog_restart_bot.py').read_text(encoding='utf-8')
    if len(blocks) != 1 or blocks[0] != expected:
        raise ValueError('Expected one exact reviewed dialog restart composition')
    return blocks[0]


def execute(guide: Path) -> dict:
    code = composition(guide)
    with tempfile.TemporaryDirectory(prefix='copied restart guide ') as folder:
        target = Path(folder)
        (target / 'dialog_restart_bot.py').write_text(code, encoding='utf-8')
        offline = target / 'offline_dialog_restart.py'
        offline.write_bytes((ROOT / 'examples/python/offline_dialog_restart.py').read_bytes())
        environment = {k: v for k, v in os.environ.items() if k.upper() in
            {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL'}}
        environment['PYTHONUTF8'] = '1'
        bootstrap = ('import runpy,sys;from pathlib import Path;'
            'p=Path(sys.argv[1]).resolve(strict=True);sys.path.insert(0,str(p.parent));'
            'sys.argv=sys.argv[1:];runpy.run_path(str(p),run_name="__main__")')
        run = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap, str(offline)], cwd=target,
            env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
        if run.returncode: raise RuntimeError(run.stdout + run.stderr)
        result = json.loads(run.stdout)
    if (not result['passed'] or result['network'] or not result['session_closed']
            or result['processes'] != 3 or result['business_effects'] != 1 or not all(result[k] for k in FLAGS)):
        raise ValueError('Copied dialog restart composition failed')
    return result


def operations(guide: Path) -> dict:
    document = guide.read_text(encoding='utf-8'); code = composition(guide); cases = []
    with tempfile.TemporaryDirectory(prefix='restart helper operations ') as folder:
        target = Path(folder) / 'copied skill' / 'references'; target.mkdir(parents=True)
        marker = target.parent / 'host-owned.txt'; marker.write_bytes(b'host-owned\x00\xff')
        before_marker = marker.read_bytes(); copied = target / 'dialog-restart.md'
        copied.write_text(document, encoding='utf-8'); before = copied.read_bytes()
        assert execute(copied)['operation_ids_match']
        assert copied.read_bytes() == before and marker.read_bytes() == before_marker
        cases.extend(('exact-copied-guide-executed-in-three-processes', 'caller-files-byte-preserved'))
        for label, altered in (
            ('missing-block-rejected', document.replace('```python\n' + code + '```', 'No example')),
            ('tampered-block-rejected-before-execution', document.replace(code, 'raise RuntimeError("must not run")\n' + code)),
            ('duplicate-block-rejected', document + '\n```python\n' + code + '```\n'),
        ):
            copied.write_text(altered, encoding='utf-8'); before = copied.read_bytes()
            try: composition(copied)
            except ValueError: pass
            else: raise AssertionError('Invalid copied guide accepted')
            assert copied.read_bytes() == before and marker.read_bytes() == before_marker
            cases.append(label)
    return {'passed': True, 'temporary_operations': cases, 'caller_files_preserved': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('skill', type=Path); args = parser.parse_args()
    guide = args.skill.resolve(strict=True) / 'references/dialog-restart.md'
    result = execute(guide)
    result.update(guide_blocks=1, composition_sha256=hashlib.sha256(composition(guide).encode()).hexdigest(),
        helper_operations=operations(guide), scope='Exact standalone code, installed SDK, three processes and local file SQLite; author checks, no live/device/independent/distributed acceptance')
    print(json.dumps(result))


if __name__ == '__main__': main()
