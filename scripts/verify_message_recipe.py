"""Execute the exact copied one-block message composition on a local Dispatcher."""
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill',type=Path)
    args=parser.parse_args()
    guide=args.skill.resolve()/'references/message-text.md'
    blocks=re.findall(r'```python\n(.*?)```',guide.read_text(encoding='utf-8'),re.S)
    if len(blocks)!=1: raise ValueError('Expected one complete message composition')
    module=ModuleType('message_text_bot')
    exec(compile(blocks[0],str(guide),'exec'),module.__dict__)
    original=sys.modules.get('message_text_bot')
    sys.modules['message_text_bot']=module
    captured=io.StringIO()
    try:
        with redirect_stdout(captured): runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/python/offline_message_text.py'),run_name='__main__')
    finally:
        if original is None: sys.modules.pop('message_text_bot',None)
        else: sys.modules['message_text_bot']=original
    result=json.loads(captured.getvalue())
    flags=('literal_injection','utf16_offsets','split_preserves_entities','explicit_parse_mode_none',
           'emoji_capability_fallback','existing_dispatcher_preserved','private_context_guards')
    if not result['passed'] or result['network'] or not result['session_closed'] or result['chunks']<2 or not all(result[k] for k in flags):
        raise ValueError('Copied message composition failed')
    result['guide_blocks']=len(blocks)
    result['scope']='Exact copied composition plus SDK serialization; author mock, not live/device/independent acceptance'
    print(json.dumps(result))


if __name__=='__main__': main()
