"""Launch models and signed backend identity stay separate; SDK updates are synthetic."""
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Update
from telegram_patterns import ValidationFailure
from telegram_shop_example.launch import launch_configuration, launch_url, screen_hint
from telegram_shop_example.offline import TOKEN, stub
from telegram_shop_example.payments import payment_router
from telegram_shop_example.store import Store


class LaunchTests(unittest.IsolatedAsyncioTestCase):
    def test_owned_launch_models_distinguish_menu_main_inline_and_reply(self):
        config=launch_configuration('https://shop.invalid/','fixture_bot',hint='orders')
        self.assertEqual(config['menu'].menu_button.web_app.url,'https://shop.invalid/?tgWebAppStartParam=orders')
        self.assertEqual(config['inline'].inline_keyboard[0][0].web_app.url,config['menu'].menu_button.web_app.url)
        self.assertEqual(config['reply'].keyboard[0][0].web_app.url,config['menu'].menu_button.web_app.url)
        self.assertEqual(config['main_link'],'https://t.me/fixture_bot?startapp=orders')
        self.assertEqual(config['bot_link'],'https://t.me/fixture_bot?start=orders')
        for value in ('admin','user_77','order_'+('1'*36),'x'*65,'https://foreign.invalid/','../orders',42):
            with self.subTest(value=value), self.assertRaises(ValidationFailure):screen_hint(value)
        for value in ('http://shop.invalid/','https://u:p@shop.invalid/','https://shop.invalid/?role=admin','https://shop.invalid/#orders'):
            with self.assertRaises(ValidationFailure):launch_url(value)
        self.assertEqual(screen_hint(None),'catalog')

    async def test_start_payload_is_a_bounded_screen_hint_and_group_launch_is_not_sent(self):
        with tempfile.TemporaryDirectory(prefix='shop-launch-') as temporary:
            store=Store(Path(temporary)/'shop.sqlite',TOKEN,terms_version='v1')
            session=stub();bot=Bot(TOKEN,session=session);dispatcher=Dispatcher()
            dispatcher.include_router(payment_router(store,shop_url='https://shop.invalid/',terms='Terms',support='Support'))
            try:
                for index,(payload,expected) in enumerate([('orders','orders'),('catalog','catalog'),('user_77','catalog'),('','catalog'),('x'*65,'catalog')]):
                    update=Update.model_validate({'update_id':index,'message':{'message_id':index,'date':int(time.time()),'chat':{'id':42,'type':'private'},'from':{'id':42,'is_bot':False,'first_name':'Fixture'},'text':'/start '+payload}})
                    await dispatcher.feed_update(bot,update)
                    sent=[call for call in session.calls if isinstance(call,SendMessage)][-1]
                    url=sent.reply_markup.inline_keyboard[0][0].web_app.url
                    self.assertEqual(parse_qs(urlsplit(url).query),{'tgWebAppStartParam':[expected]})
                before=len(session.calls)
                update=Update.model_validate({'update_id':77,'message':{'message_id':77,'date':int(time.time()),'chat':{'id':-77,'type':'group','title':'Fixture'},'from':{'id':42,'is_bot':False,'first_name':'Fixture'},'text':'/start orders'}})
                await dispatcher.feed_update(bot,update);self.assertEqual(len(session.calls),before)
                self.assertEqual(store.orders(42),[],'launching never creates a business object')
            finally:
                await dispatcher.fsm.close();await session.close()
