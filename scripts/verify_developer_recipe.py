"""Execute owned catalog and maturity recipes from a copied skill through core API."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('skill',type=Path);args=parser.parse_args()
    reference=args.skill/'references/developer-tools.md'
    blocks=re.findall(r'```python\s*\n(.*?)\n```',reference.read_text(encoding='utf-8'),re.S)
    if len(blocks)!=1:raise RuntimeError('Expected exactly one owned developer recipe')
    scope={'__name__':'portable_catalog_recipe'}
    with redirect_stdout(io.StringIO()) as output:exec(compile(blocks[0],str(reference),'exec'),scope)
    if 'inline_keyboard' not in output.getvalue():raise RuntimeError('Copied recipe did not expose expected code')
    maturity=args.skill/'references/maturity.md'
    maturity_blocks=re.findall(r'```python\s*\n(.*?)\n```',maturity.read_text(encoding='utf-8'),re.S)
    if len(maturity_blocks)!=1:raise RuntimeError('Expected exactly one owned maturity recipe')
    exec(compile(maturity_blocks[0],str(maturity),'exec'),{'__name__':'portable_maturity_recipe'})
    print(json.dumps({'passed':True,'blocks':len(blocks)+len(maturity_blocks),'network':False,'public_api':'telegram_patterns.RecipeCatalog'}))

if __name__=='__main__':main()
