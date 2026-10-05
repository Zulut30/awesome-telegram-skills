"""Execute the exact copied media guide on an actual synthetic Dispatcher."""
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
    guide=args.skill.resolve()/'references/media.md'
    blocks=re.findall(r'```python\n(.*?)```',guide.read_text(encoding='utf-8'),re.S)
    if len(blocks)!=1: raise ValueError('Expected one complete media composition')
    module=ModuleType('media_bot')
    exec(compile(blocks[0],str(guide),'exec'),module.__dict__)
    original=sys.modules.get('media_bot');sys.modules['media_bot']=module
    captured=io.StringIO()
    try:
        with redirect_stdout(captured): runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/python/offline_media.py'),run_name='__main__')
    finally:
        if original is None: sys.modules.pop('media_bot',None)
        else: sys.modules['media_bot']=original
    result=json.loads(captured.getvalue())
    flags=('photo_document_album_edit','caption_entities','explicit_parse_mode_none','bounded_stream_download',
           'private_context_guards','existing_dispatcher_preserved')
    if not result['passed'] or result['network'] or not result['session_closed'] or result['uploaded_parts']!=5 or not all(result[k] for k in flags):
        raise ValueError('Copied media composition failed')
    result['guide_blocks']=1
    result['scope']='Copied composition plus SDK multipart/content streams; author mock, not live/device/independent acceptance'
    print(json.dumps(result))


if __name__=='__main__': main()
