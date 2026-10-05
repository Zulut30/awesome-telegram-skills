"""Execute the exact copied poll guide through the synthetic durable host composition."""
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
    guide=args.skill.resolve()/'references/polls.md'
    blocks=re.findall(r'```python\n(.*?)```',guide.read_text(encoding='utf-8'),re.S)
    if len(blocks)!=1: raise ValueError('Expected one complete poll composition')
    module=ModuleType('polls_bot'); exec(compile(blocks[0],str(guide),'exec'),module.__dict__)
    original=sys.modules.get('polls_bot'); sys.modules['polls_bot']=module; captured=io.StringIO()
    try:
        with redirect_stdout(captured):
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/python/offline_polls.py'),run_name='__main__')
    finally:
        if original is None: sys.modules.pop('polls_bot',None)
        else: sys.modules['polls_bot']=original
    result=json.loads(captured.getvalue())
    flags=('modern_quiz','own_poll_binding','persistent_vote_ids','anonymous_limits','unknown_addition_not_guessed',
           'durable_host_dedup','unknown_send_no_retry','fresh_acl','existing_dispatcher_preserved')
    if not result['passed'] or result['network'] or not result['session_closed'] or not all(result[key] for key in flags):
        raise ValueError('Copied poll composition failed')
    result.update(guide_blocks=1,scope='Exact copied guide, actual Dispatcher and temporary host SQLite; author mock, not live/complete voter ledger/independent acceptance')
    print(json.dumps(result))


if __name__=='__main__': main()
