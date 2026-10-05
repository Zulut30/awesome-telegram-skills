"""Execute the exact copied inline guide through the synthetic host Dispatcher."""
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
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('skill',type=Path); args=parser.parse_args()
    guide=args.skill.resolve()/'references/inline-search.md'
    blocks=re.findall(r'```python\n(.*?)```',guide.read_text(encoding='utf-8'),re.S)
    if len(blocks)!=1: raise ValueError('Expected one complete inline composition')
    module=ModuleType('inline_search_bot'); exec(compile(blocks[0],str(guide),'exec'),module.__dict__)
    original=sys.modules.get('inline_search_bot'); sys.modules['inline_search_bot']=module; captured=io.StringIO()
    try:
        with redirect_stdout(captured):
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/python/offline_inline_search.py'),run_name='__main__')
    finally:
        if original is None: sys.modules.pop('inline_search_bot',None)
        else: sys.modules['inline_search_bot']=original
    result=json.loads(captured.getvalue())
    flags=('personal_cache','scoped_pagination','fresh_acl','private_items_excluded','unknown_answer_no_retry','existing_dispatcher_preserved','feedback_is_optional')
    if not result['passed'] or result['network'] or not result['session_closed'] or not all(result[key] for key in flags):
        raise ValueError('Copied inline composition failed')
    result.update(guide_blocks=1,scope='Exact copied guide, actual Dispatcher and synthetic native answer; author mock, not live/cache/device/independent acceptance')
    print(json.dumps(result))


if __name__=='__main__': main()
