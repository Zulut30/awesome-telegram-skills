"""Execute the exact copied profile guide against an actual synthetic Dispatcher."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import runpy
import sys
from types import ModuleType


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill', type=Path)
    args = parser.parse_args()
    guide = args.skill.resolve()/'references/profiles.md'
    blocks = re.findall(r'```python\n(.*?)```', guide.read_text(encoding='utf-8'), re.S)
    if len(blocks) != 1: raise ValueError('Expected one complete profile composition')
    module = ModuleType('profiles_bot')
    exec(compile(blocks[0], str(guide), 'exec'), module.__dict__)
    original = sys.modules.get('profiles_bot'); sys.modules['profiles_bot'] = module
    captured = io.StringIO()
    try:
        with redirect_stdout(captured):
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/python/offline_profiles.py'), run_name='__main__')
    finally:
        if original is None: sys.modules.pop('profiles_bot', None)
        else: sys.modules['profiles_bot'] = original
    result = json.loads(captured.getvalue())
    flags = ('unknown_fields_preserved', 'profile_photos', 'localized_omission_clear', 'fresh_method_acl',
             'new_avatar_upload_removal', 'unknown_edit_reconciliation', 'private_context_guards', 'existing_dispatcher_preserved')
    if not result['passed'] or result['network'] or not result['session_closed'] or result['photo_upload_bytes'] != 634 or not all(result[k] for k in flags):
        raise ValueError('Copied profile composition failed')
    result['guide_blocks'] = 1
    result['scope'] = 'Copied composition, actual Dispatcher, locale state and SDK new-file multipart; author mock, not live/device/independent acceptance'
    print(json.dumps(result))


if __name__ == '__main__': main()
