"""Check independently copied skill references through an installed PUBLIC package."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import re


async def navigation_check(namespace):
    from aiogram import Bot, Dispatcher, Router
    from aiogram.filters import Command
    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
    from aiogram.types import Update
    from telegram_patterns.testing import StubSession
    menu, router = namespace['menu'], namespace['router']
    existing = Router()
    @existing.message(Command('help'))
    async def help(message):
        await message.answer('Existing help preserved', parse_mode=None)
    dispatcher = Dispatcher()
    dispatcher.include_router(existing)
    dispatcher.include_router(router)
    def reply(request):
        return {'message_id': 100 if isinstance(request,SendMessage) else request.message_id, 'date':1,
                'chat':{'id':request.chat_id,'type':'private'},'from':{'id':100,'is_bot':True,'first_name':'Fixture'},
                'text':request.text}
    session=StubSession().respond(SendMessage,reply).respond(EditMessageText,reply).respond(AnswerCallbackQuery,True)
    async with Bot('100:PORTABLE_NAVIGATION_FIXTURE',session=session) as bot:
        try:
            initial=await menu.open(bot,42,42)
            async def click(target,index,actor=42,revision=None):
                state=menu.get_state(bot.id,42,42)
                data=f'{menu.prefix}{state.session_id}:{state.revision if revision is None else revision}:{target}'
                update=Update.model_validate({'update_id':index,'callback_query':{'id':str(index),'chat_instance':'fixture',
                    'from':{'id':actor,'is_bot':False,'first_name':'Actor'},'data':data,
                    'message':{'message_id':state.message_id,'date':1,'chat':{'id':42,'type':'private'},
                               'from':{'id':100,'is_bot':True,'first_name':'Fixture'}}}},context={'bot':bot})
                await dispatcher.feed_update(bot,update)
            await click('catalog',1,actor=43)
            assert menu.get_state(bot.id,42,42)==initial
            await click('catalog',2)
            assert menu.get_state(bot.id,42,42).history==('home',)
            await click('delivery',3)
            assert menu.get_state(bot.id,42,42).history==('home','catalog')
            await click('_back',4)
            assert menu.get_state(bot.id,42,42).screen=='catalog'
            confirmed=menu.get_state(bot.id,42,42)
            await click('catalog',5,revision=0)
            assert menu.get_state(bot.id,42,42)==confirmed
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':6,'message':{'message_id':20,'date':1,
                'chat':{'id':42,'type':'private'},'from':{'id':42,'is_bot':False,'first_name':'Owner'},'text':'/help',
                'entities':[{'type':'bot_command','offset':0,'length':5}]}},context={'bot':bot}))
            edits=[c for c in session.calls if isinstance(c,EditMessageText)]
            assert len(edits)==3 and all(c.message_id==initial.message_id and c.chat_id==42 for c in edits)
            assert session.calls[-1].text=='Existing help preserved'
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    return {'passed':True,'existing_dispatcher_preserved':True,'owner_and_stale_guards':True,'history_back':True,'session_closed':True,'edits':3}


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
    navigation_guide=skill/'references/message-navigation.md'
    navigation_blocks=re.findall(r'```python\n(.*?)```',navigation_guide.read_text(encoding='utf-8'),re.S) if navigation_guide.exists() else []
    if navigation_guide.exists() and len(navigation_blocks)!=1:raise ValueError('Update checker for navigation guide blocks')
    navigation_namespace={}
    for block in navigation_blocks:exec(compile(block,str(navigation_guide),'exec'),navigation_namespace)
    navigation=asyncio.run(navigation_check(navigation_namespace)) if navigation_blocks else None
    print(json.dumps({'passed':True,'network':False,'markdown_files':len(markdown),'python_blocks':len(blocks),
                      'layout_guide_blocks':len(layout_blocks),
                      'navigation_guide_blocks':len(navigation_blocks),'navigation':navigation,
                      'methods':len(namespace['methods']),'scope':'copied skill recipe execution; not independent agent decision evaluation'}))


if __name__ == '__main__': main()
