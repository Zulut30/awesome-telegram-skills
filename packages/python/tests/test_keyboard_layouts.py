"""SDK serialization, context refusals and immutable source compositions."""
import asyncio
import json
import unittest

from aiogram import Bot
from aiogram.types import InlineKeyboardButton as Inline, KeyboardButton as Reply, WebAppInfo, KeyboardButtonRequestUsers
from aiogram.utils.keyboard import InlineKeyboardBuilder
from telegram_patterns.aiogram import (ActionButton, KeyboardCapabilities, KeyboardLayout, action_layout, action_menu,
    inline_layout, reply_layout, inline_keyboard)


class KeyboardLayoutTests(unittest.TestCase):
    def test_width_patterns_match_installed_sdk_and_preserve_order(self):
        source = [Inline(text=str(i),callback_data=str(i)) for i in range(13)]
        for widths,repeat in (((2,),False),((3,),False),((2,3,1),False),((2,3,1),True)):
            result = inline_layout(source,KeyboardLayout(widths,repeat))
            sdk = InlineKeyboardBuilder().add(*source).adjust(*widths,repeat=repeat).as_markup()
            self.assertEqual(result.model_dump(exclude_none=True),sdk.model_dump(exclude_none=True))
            self.assertEqual([b.callback_data for r in result.inline_keyboard for b in r],[str(i) for i in range(13)])
        self.assertEqual([len(r) for r in inline_layout(source[:7],KeyboardLayout((2,3,1))).inline_keyboard],[2,3,1,1])

    def test_presentation_fallback_and_scope_do_not_modify_source(self):
        source = Inline(text='Подтвердить',callback_data='confirm',style='success',icon_custom_emoji_id='12345')
        unknown = inline_layout([source]).inline_keyboard[0][0]
        self.assertIsNone(unknown.style); self.assertIsNone(unknown.icon_custom_emoji_id)
        for client,entitlement,expected in ((False,True,None),(True,False,None),(True,True,'12345')):
            caps = KeyboardCapabilities(chat_type='supergroup',styles=True,custom_emoji=client,emoji_entitlement_verified=entitlement)
            result = inline_layout([source],capabilities=caps).inline_keyboard[0][0]
            self.assertEqual(result.style,'success'); self.assertEqual(result.icon_custom_emoji_id,expected)
        self.assertEqual(source.style,'success'); self.assertEqual(source.icon_custom_emoji_id,'12345')
        result.text = 'changed'; self.assertEqual(source.text,'Подтвердить')
        # Existing builders preserve their previous style behavior.
        self.assertEqual(inline_keyboard([[source]]).inline_keyboard[0][0].style,'success')
        self.assertEqual(action_menu([ActionButton('A','a',style='danger')]).inline_keyboard[0][0].style,'danger')

    def test_invalid_presentation_is_rejected_before_fallback(self):
        for fields in ({'style':'#ff0000'},{'icon_custom_emoji_id':'invalid'},{'colour':'red'}):
            with self.subTest(fields=fields),self.assertRaises(ValueError): inline_layout([Inline(text='A',callback_data='a',**fields)])
        with self.assertRaises(ValueError): reply_layout([Reply(text='A',style='blue')])

    def test_layout_and_capability_types_limits_and_snapshot(self):
        widths = [2,3]; layout = KeyboardLayout(widths)
        widths[0] = 8; self.assertEqual(layout.widths,(2,3))
        for value in ((),(0,),(9,),(True,),(2.0,),'23',None):
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)): KeyboardLayout(value)
        for flags in ({'repeat':1},{'repeat':'yes'}):
            with self.assertRaises(TypeError): KeyboardLayout(**flags)
        for fields in ({'styles':1},{'business':'no'},{'custom_emoji':'yes'},{'emoji_entitlement_verified':1},{'chat_type':'unknown'}):
            with self.assertRaises((ValueError,TypeError)): KeyboardCapabilities(**fields)
        for items in ([],[Inline(text='A',callback_data='a')]*101,'abc'):
            with self.assertRaises((ValueError,TypeError)): inline_layout(items)

    def test_native_action_and_context_checks_still_apply_after_composition(self):
        first = Inline(text='A',callback_data='a')
        pay = Inline(text='Оплатить',pay=True)
        with self.assertRaises(ValueError): inline_layout([first,pay],KeyboardLayout((1,)),invoice=True)
        self.assertTrue(inline_layout([pay,first],invoice=True).inline_keyboard[0][0].pay)
        web = Inline(text='Mini App',web_app=WebAppInfo(url='https://example.invalid'))
        with self.assertRaises(ValueError): inline_layout([web],capabilities=KeyboardCapabilities(chat_type='supergroup'))
        with self.assertRaises(ValueError): inline_layout([Inline(text='A',callback_data='a',url='https://example.invalid')])
        with self.assertRaises(ValueError): inline_layout([Inline(text='A',callback_data='😀'*17)])

    def test_reply_requests_plain_labels_and_scoped_ids(self):
        contact = Reply(text='Контакт',request_contact=True,style='primary')
        caps = KeyboardCapabilities(styles=True)
        result = reply_layout(['Каталог','Помощь',contact],KeyboardLayout((2,1)),capabilities=caps,placeholder='Выберите действие')
        self.assertEqual([len(r) for r in result.keyboard],[2,1]); self.assertTrue(result.keyboard[1][0].request_contact)
        self.assertEqual(result.keyboard[1][0].style,'primary')
        self.assertIsNone(reply_layout([contact]).keyboard[0][0].style)
        for context in (KeyboardCapabilities(chat_type='supergroup'),KeyboardCapabilities(business=True)):
            with self.assertRaises(ValueError): reply_layout([contact],capabilities=context)
        shared = Reply(text='Users',request_users=KeyboardButtonRequestUsers(request_id=5))
        with self.assertRaises(ValueError): reply_layout([shared,shared],KeyboardLayout((1,)))

    def test_action_keys_boundaries_and_real_sdk_wire_are_preserved(self):
        actions = [ActionButton('Удалить','delete',style='danger',custom_emoji_id='12345'),ActionButton('Отмена','cancel')]
        result = action_layout(actions,KeyboardLayout((1,)),prefix='op:',capabilities=KeyboardCapabilities(styles=True))
        bot = Bot('100:OFFLINE_FIXTURE')
        try:
            wire = json.loads(bot.session.prepare_value(result,bot,{}))
            self.assertEqual(wire['inline_keyboard'][0][0],{'text':'Удалить','style':'danger','callback_data':'op:delete'})
            self.assertEqual(wire['inline_keyboard'][1][0]['callback_data'],'op:cancel')
        finally: asyncio.run(bot.session.close())
        with self.assertRaises(ValueError): action_layout([actions[0],actions[0]])
        with self.assertRaises(ValueError): action_layout(actions,prefix='x'*63+':')
        with self.assertRaises(TypeError): action_layout([Inline(text='A',callback_data='a')])


if __name__=='__main__': unittest.main()
