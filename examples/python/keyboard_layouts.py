"""Install public 0.14 API; construct and serialize rows through synthetic SDK transport."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message
from telegram_patterns.aiogram import ActionButton, KeyboardCapabilities, KeyboardLayout, action_layout, reply_layout
from telegram_patterns.testing import StubSession


async def main() -> None:
    items = [ActionButton(str(i),'item-'+str(i),style='primary',custom_emoji_id='12345') for i in range(6)]
    capabilities = KeyboardCapabilities(styles=True,custom_emoji=True,emoji_entitlement_verified=False)
    session = StubSession()
    session.respond(SendMessage,lambda method: Message(message_id=10,date=datetime(2026,10,5,tzinfo=timezone.utc),
        chat=Chat(id=method.chat_id,type='private'),text=method.text))
    shapes = []
    async with Bot('100:OFFLINE_LAYOUT_FIXTURE',session=session) as bot:
        for widths,repeat in (((2,),False),((3,),False),((2,3,1),False),((2,1),True)):
            markup = action_layout(items,KeyboardLayout(widths,repeat),capabilities=capabilities)
            wire = json.loads(bot.session.prepare_value(markup,bot,{}))
            assert all(b['style']=='primary' and 'icon_custom_emoji_id' not in b for r in wire['inline_keyboard'] for b in r)
            shapes.append([len(row) for row in markup.inline_keyboard])
            await bot.send_message(42,'Offline rows',reply_markup=markup)
        plain = action_layout(items)
        assert all(b.style is None and b.icon_custom_emoji_id is None for r in plain.inline_keyboard for b in r)
        await bot.send_message(42,'Unknown presentation fallback',reply_markup=plain)
        reply = reply_layout(['Каталог','Помощь','Закрыть'],KeyboardLayout([2,1]),placeholder='Выберите действие')
        assert [len(row) for row in reply.keyboard]==[2,1]
        await bot.send_message(42,'Reply input',reply_markup=reply)
    assert session.closed and len(session.calls)==6 and shapes==[[2,2,2],[3,3],[2,3,1],[2,1,2,1]]
    print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'methods':6,'shapes':shapes,
        'emoji_entitlement':'unverified/fallback','client':'synthetic SDK serialization, no live rendering'}))


if __name__=='__main__': asyncio.run(main())
