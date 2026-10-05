"""Check independently copied skill references through an installed PUBLIC package."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill', type=Path)
    args = parser.parse_args()
    skill = args.skill.resolve()
    markdown = list(skill.rglob('*.md'))
    for file in markdown:
        for reference in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            if '://' in reference or reference.startswith('#'): continue
            target = (file.parent / reference.split('#')[0]).resolve()
            if not target.is_relative_to(skill) or not target.is_file():
                raise ValueError('Copied skill has an invalid local reference')
    namespace = {}
    recipe = skill / 'references/keyboard-recipes.md'
    blocks = re.findall(r'```python\n(.*?)```', recipe.read_text(encoding='utf-8'), re.S)
    if len(blocks) != 2: raise ValueError('Update recipe checker for changed Python blocks')
    for block in blocks: exec(compile(block, str(recipe), 'exec'), namespace)
    if list(map(len, namespace['two'].inline_keyboard)) != [2,2,2]: raise ValueError('Two-column recipe failed')
    if list(map(len, namespace['three'].inline_keyboard)) != [3,3]: raise ValueError('Three-column recipe failed')
    if namespace['request'].__api_method__ != 'sendMessage': raise ValueError('Request recipe failed')
    if namespace['confirm'].inline_keyboard[0][0].style != 'success': raise ValueError('Style recipe failed')
    if not namespace['prompt'].force_reply or not namespace['hidden'].remove_keyboard: raise ValueError('Input recipe failed')
    layout_guide = skill / 'references/keyboard-layouts.md'
    layout_blocks = re.findall(r'```python\n(.*?)```', layout_guide.read_text(encoding='utf-8'), re.S) if layout_guide.exists() else []
    if layout_guide.exists() and len(layout_blocks) != 2: raise ValueError('Update checker for changed layout guide blocks')
    layout_namespace = {}
    for block in layout_blocks: exec(compile(block,str(layout_guide),'exec'),layout_namespace)
    if layout_blocks:
        if list(map(len,layout_namespace['mixed'].inline_keyboard)) != [2,3,1,1]: raise ValueError('Mixed layout guide failed')
        if layout_namespace['unknown'].style is not None or layout_namespace['unknown'].icon_custom_emoji_id is not None: raise ValueError('Unknown presentation fallback failed')
        if layout_namespace['shown'].style != 'success': raise ValueError('Verified style guide failed')
    print(json.dumps({'passed':True,'network':False,'markdown_files':len(markdown),'python_blocks':len(blocks),
                      'layout_guide_blocks':len(layout_blocks),
                      'methods':len(namespace['methods']),'scope':'copied skill recipe execution; not independent agent decision evaluation'}))


if __name__ == '__main__': main()
