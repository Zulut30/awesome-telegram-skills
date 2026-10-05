"""Execute the exact one-block copied dialog guide with real temp SQLite."""
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
    guide=args.skill.resolve()/'references/dialog-fields.md'
    blocks=re.findall(r'```python\n(.*?)```',guide.read_text(encoding='utf-8'),re.S)
    if len(blocks)!=1:raise ValueError('Expected one complete standalone dialog composition')
    module=ModuleType('dialog_fields_bot')
    exec(compile(blocks[0],str(guide),'exec'),module.__dict__)
    original=sys.modules.get('dialog_fields_bot')
    sys.modules['dialog_fields_bot']=module
    captured=io.StringIO()
    try:
        with redirect_stdout(captured):runpy.run_path(str(Path(__file__).resolve().parents[1]/'examples/python/offline_dialog_fields.py'),run_name='__main__')
    finally:
        if original is None:sys.modules.pop('dialog_fields_bot',None)
        else:sys.modules['dialog_fields_bot']=original
    result=json.loads(captured.getvalue())
    if not result['passed'] or result['network'] or result['business_effects']!=1 or result['field_types']!=7:
        raise ValueError('Copied dialog guide behavior failed')
    result['guide_blocks']=len(blocks)
    result['scope']='Exact copied code on actual Dispatcher and temporary file SQLite; author SDK/mock, no independent/live acceptance'
    print(json.dumps(result))


if __name__=='__main__':main()
