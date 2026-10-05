# Python bot и test transport — 0.17.0

[Индекс всех символов](api-reference.md). Образцы ниже воспроизводятся через установленный wheel/tarball вне исходного дерева. Assert — проверка fixture, не бизнес-правило production приложения.

Нужны предоставленный wheel с aiogram extra и установленный совместимый SDK. В той же папке создайте bot_fixture.py из блока ниже, затем запускайте `python <FILE.py>`. Фиктивный token применяется только с StubSession: HTTP fallback отсутствует.

## Общая fixture — bot_fixture.py

```python
"""Общие synthetic SDK fixtures для примеров; ни одного HTTP fallback."""
from datetime import datetime, timezone
from aiogram.types import CallbackQuery, Chat, Message, Update, User

TOKEN = '100:API_REFERENCE_FIXTURE'
DATE = datetime(2026, 10, 4, tzinfo=timezone.utc)
ACTOR = User(id=42, is_bot=False, first_name='Fixture')
BOT_USER = User(id=100, is_bot=True, first_name='Fixture', username='reference_fixture_bot')

def message(text: str, *, index: int = 1) -> Update:
    return Update(update_id=index, message=Message(message_id=index, date=DATE,
        chat=Chat(id=42, type='private'), from_user=ACTOR, text=text))

def callback(data: str, reply: Message, *, index: int, actor: User = ACTOR) -> Update:
    return Update(update_id=index, callback_query=CallbackQuery(id=str(index), from_user=actor,
        chat_instance='fixture', message=reply, data=data))

def response(request):
    return Message(message_id=100, date=DATE, chat=Chat(id=request.chat_id, type='private'),
                   from_user=BOT_USER, text=request.text)
```

<a id="ref-bot_keyboards"></a>

## Клавиатуры, ввод и страницы — ref.bot_keyboards

Файл: `bot_keyboards.py`. Символы: `ActionButton`, `ButtonStyle`, `MenuPage`, `action_keyboard`, `action_menu`, `paginated_menu`, `page_number`, `ChatType`, `inline_keyboard`, `reply_keyboard`, `input_prompt`, `remove_keyboard`, `KeyboardLayout`, `KeyboardCapabilities`, `action_layout`, `inline_layout`, `reply_layout`

Границы: Aiogram extra; callbacks до 64 bytes, keys bounded ASCII, prefixes навигации и action различимы. Colors только primary/success/danger, emoji entitlement отдельный. Контекст chat/business/invoice передает host. Reply не вызывает callback_query; appearance в Telegram не проверяется.

```python
"""Строки 2/3, styles, reply-ввод и пагинация без доставки в Telegram."""
import json
from aiogram.types import InlineKeyboardButton
from telegram_patterns.aiogram import (
    ActionButton, ButtonStyle, MenuPage, action_keyboard, action_menu, paginated_menu, page_number,
    ChatType, inline_keyboard, reply_keyboard, input_prompt, remove_keyboard,
    KeyboardLayout, KeyboardCapabilities, action_layout, inline_layout, reply_layout,
)

style: ButtonStyle = 'success'
context: ChatType = 'private'
items = [ActionButton(str(index), 'item-' + str(index), style=style) for index in range(1, 7)]
single = action_keyboard('Открыть', 'catalog', style='primary')
assert single.inline_keyboard[0][0].callback_data == 'act:catalog'
for columns in (2, 3):
    menu = action_menu(items, columns=columns)
    assert len(menu.inline_keyboard[0]) == columns
page: MenuPage = paginated_menu(items, page_size=3, columns=3)
assert (page.page, page.page_count, page.total_items) == (0, 2, 6)
assert page_number(page.markup.inline_keyboard[-1][0].callback_data) == 1
assert page_number('invalid') is None
rows = [[InlineKeyboardButton(text='Открыть', callback_data='act:catalog')]]
assert inline_keyboard(rows, chat_type=context).inline_keyboard[0][0].text == 'Открыть'
assert reply_keyboard([['Назад', 'Отмена']], chat_type=context, placeholder='Выберите действие').keyboard
assert input_prompt('Введите тему').force_reply and remove_keyboard().remove_keyboard
# Новая композиция flat buttons; unknown capability сохраняет текстовый fallback.
layout = KeyboardLayout([2,3,1])
caps = KeyboardCapabilities(chat_type=context, styles=True)
mixed = action_layout(items,layout,prefix='item:',capabilities=caps)
assert [len(row) for row in mixed.inline_keyboard] == [2,3,1]
assert mixed.inline_keyboard[0][0].style == 'success'
native = [InlineKeyboardButton(text=str(i),callback_data=str(i)) for i in range(6)]
assert [len(row) for row in inline_layout(native,layout).inline_keyboard] == [2,3,1]
assert [len(row) for row in reply_layout(['A','B','C','D'],KeyboardLayout([3,1])).keyboard] == [3,1]
# Цвет — primary/success/danger, не RGB. Emoji требуют отдельного entitlement.
print(json.dumps({'passed': True, 'case': 'bot_keyboards', 'network': False}))
```

<a id="ref-bot_actions"></a>

## Команды и callback композиция — ref.bot_actions

Файл: `bot_actions.py`. Символы: `Action`, `ActionResult`, `callback_router`, `start_router`, `CommandReply`, `command_menu`, `command_router`, `Responder`, `StubSession`

Границы: Добавляйте Router в существующий Dispatcher. Command menu устанавливается явно с выбранным scope. ACK убирает spinner, service проверяет actor/object/revision/idempotency. Notify выбирает безопасный доступный канал; пример использует только synthetic private message.

```python
"""Тот же Dispatcher: команды и callback ACK до owner-bound сервиса."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from telegram_patterns.aiogram import Action, ActionResult, callback_router, start_router, CommandReply, command_menu, command_router
from telegram_patterns.testing import Responder, StubSession
from bot_fixture import BOT_USER, TOKEN, callback, message, response

async def main() -> None:
    responder: Responder = response
    session = StubSession().respond(GetMe, BOT_USER).respond(SendMessage, responder).respond(AnswerCallbackQuery, True)
    dispatcher = Dispatcher()
    replies = [CommandReply('help', 'Справка', 'Публичная справка')]
    assert command_menu(replies)[0].command == 'help'
    async def execute(action: Action) -> ActionResult:
        assert isinstance(session.calls[-1], AnswerCallbackQuery)  # Spinner ACK уже отправлен.
        return ActionResult('accepted' if action.actor_id == 42 and action.key == 'catalog' else 'denied', 'Публичный ответ')
    async def notify(query, result: ActionResult) -> None:
        assert query.message is not None
        await query.message.answer(result.text, parse_mode=None)
    dispatcher.include_router(start_router('Публичное начало'))
    dispatcher.include_router(command_router(replies))
    dispatcher.include_router(callback_router(execute, notify))
    async with Bot(TOKEN, session=session) as bot:
        try:
            await dispatcher.feed_update(bot, message('/start'))
            await dispatcher.feed_update(bot, message('/help', index=2))
            reply = response(SendMessage(chat_id=42, text='Меню'))
            await dispatcher.feed_update(bot, callback('act:catalog', reply, index=3))
            assert [type(c).__name__ for c in session.calls][-2:] == ['AnswerCallbackQuery', 'SendMessage']
        finally: await dispatcher.fsm.close()
    assert session.closed
    stream = session.stream_content('https://fixture.invalid')
    try: await anext(stream)
    except AssertionError: pass
    else: raise AssertionError('File streaming should have no fallback')
    finally: await stream.aclose()
    print(json.dumps({'passed': True, 'case': 'bot_actions', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-bot_runner"></a>

## Polling lifecycle и Stars request — ref.bot_runner

Файл: `bot_runner.py`. Символы: `run_bot`, `stars_invoice`

Границы: SDK polling через StubSession завершается после первого запроса; ни реального token, ни удаления webhook. Live требует отдельного процесса и проверки consumer/webhook. Runner закрывает session после успешного preflight. Stars request не создает оплату, заказ или entitlement; consent и server ledger у host.

```python
"""Настоящий SDK polling через StubSession; останавливаем его после первого запроса."""
import asyncio
import json
from aiogram import Dispatcher
from aiogram.methods import GetMe, GetUpdates, SetMyCommands
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import run_bot, stars_invoice, start_router
from telegram_patterns.testing import StubSession
from bot_fixture import BOT_USER, TOKEN

async def main() -> None:
    requested = asyncio.Event()
    async def updates(request):
        requested.set()
        await asyncio.sleep(0.01)
        return []
    session = StubSession().respond(GetMe, BOT_USER).respond(GetUpdates, updates).respond(SetMyCommands, True)
    dispatcher = Dispatcher(); dispatcher.include_router(start_router('Fixture'))
    invoice = stars_invoice('Тест', 'Публичный пример', 'server-order-1', 1)
    assert invoice.currency == 'XTR' and invoice.prices[0].amount == 1
    # Конструирование invoice не создает заказ, платеж или доступ.
    running = asyncio.create_task(run_bot(dispatcher, BotSettings(TOKEN), session=session, commands=[], handle_signals=False))
    try:
        await asyncio.wait_for(requested.wait(), timeout=5)
        await dispatcher.stop_polling()
        await asyncio.wait_for(running, timeout=5)
    finally:
        if not running.done(): running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await dispatcher.fsm.close()
    assert session.closed and any(isinstance(c, GetUpdates) for c in session.calls)
    print(json.dumps({'passed': True, 'case': 'bot_runner', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-bot_form"></a>

## Ввод, review и owner-bound submit — ref.bot_form

Файл: `bot_form.py`. Символы: `TextField`, `InvalidField`, `FormSubmission`, `text_form_router`

Границы: Private chat, 1..10 уникальных TextField, включенный actor-scoped FSM isolation. Max_length в UTF-16; validator synchronous. MemoryStorage и list — fixture, не durable заявка. Service проверяет ACL и эффект/replay; unknown outcome сохраняет operation identity до сверки.

```python
"""MemoryStorage fixture: ввод, проверка, review и защита от чужой кнопки."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import User
from telegram_patterns.aiogram import FormSubmission, InvalidField, TextField, text_form_router
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, callback, message, response

async def main() -> None:
    replies = []
    def respond(request):
        result = response(request); replies.append((request, result)); return result
    submissions: list[FormSubmission] = []
    def validate(value: str) -> str:
        if value.lower() not in {'python', 'typescript'}: raise InvalidField('Выберите Python или TypeScript.')
        return value.lower()
    field = TextField('topic', 'Тема', 'Python или TypeScript?', validate=validate)
    assert field.read(' Python ') == 'python'
    async def submit(value: FormSubmission) -> str:
        assert value.actor_id == value.chat_id == 42 and value.bot_id == 100
        submissions.append(value); return 'Fixture проверена; заявка не сохранялась.'
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(text_form_router([field], submit, name='reference'))
    session = StubSession().respond(SendMessage, respond).respond(AnswerCallbackQuery, True)
    async with Bot(TOKEN, session=session) as bot:
        try:
            for index, text in enumerate(('/apply', 'wrong', 'Python'), 1):
                await dispatcher.feed_update(bot, message(text, index=index))
            request, reply = replies[-1]
            data = request.reply_markup.inline_keyboard[0][0].callback_data
            outsider = User(id=43, is_bot=False, first_name='Other')
            await dispatcher.feed_update(bot, callback(data, reply, index=4, actor=outsider))
            assert not submissions
            await dispatcher.feed_update(bot, callback(data, reply, index=5))
            await dispatcher.feed_update(bot, callback(data, reply, index=6))
            assert len(submissions) == 1 and submissions[0].values['topic'] == 'python'
        finally: await dispatcher.fsm.close()
    assert session.closed
    print(json.dumps({'passed': True, 'case': 'bot_form', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-bot_events"></a>

## Metadata событий и фаз — ref.bot_events

Файл: `bot_events.py`. Символы: `UpdatePhase`, `UpdateTrace`, `UpdateObserver`, `update_kinds`, `event_router`

Границы: Observer регистрируется на dispatcher.update. IDs opt-in; без текста/contacts/initData/raw exception. Best-effort не durable inbox/audit. Router subscription/rights/allowed_updates и ACK/auth остаются у host, Bot API не читает историю user account.

```python
"""Metadata observer на update; received/handled без содержимого сообщения."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage
from telegram_patterns.aiogram import UpdatePhase, UpdateTrace, UpdateObserver, update_kinds, event_router
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, message, response

async def main() -> None:
    traces: list[UpdateTrace] = []
    async def record(trace: UpdateTrace) -> None: traces.append(trace)
    async def reply(value) -> None: await value.answer('Публичный ответ', parse_mode=None)
    observer = UpdateObserver(record)
    phase: UpdatePhase = 'received'
    await observer.emit(UpdateTrace(update_id=0, kind='fixture', phase=phase))
    dispatcher = Dispatcher(); dispatcher.update.outer_middleware(observer)
    dispatcher.include_router(event_router({'message': reply}))
    update = message('/observe'); assert update_kinds(update) == ('message',)
    session = StubSession().respond(SendMessage, response)
    async with Bot(TOKEN, session=session) as bot:
        try: await dispatcher.feed_update(bot, update)
        finally: await dispatcher.fsm.close()
    assert [t.phase for t in traces] == ['received', 'received', 'handled']
    assert all(t.actor_id is None and t.chat_id is None for t in traces)
    # best-effort observation, не durable audit или подписка на историю.
    print(json.dumps({'passed': True, 'case': 'bot_events', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-bot_methods"></a>

## SDK catalog и request construction — ref.bot_methods

Файл: `bot_methods.py`. Символы: `MethodSpec`, `InvalidAPIRequest`, `method_catalog`, `build_request`

Границы: Catalog отражает установленный SDK, не server rights. Builder отклоняет неизвестные top-level fields; nested validation принадлежит SDK. InputFile не читается автоматически. HTTP/send/лимиты/доступ и provider workflow не появляются от construction.

```python
"""SDK request construction; ничего не отправляется и file не читается."""
import json
from aiogram.methods import SendMessage
from telegram_patterns.aiogram import MethodSpec, InvalidAPIRequest, method_catalog, build_request

catalog = method_catalog()
spec: MethodSpec = next(item for item in catalog if item.name == 'sendMessage')
assert 'chat_id' in spec.required and spec.sdk_class == 'SendMessage' and spec.url.startswith('https://')
request = build_request(spec.name, {'chat_id': 42, 'text': 'Публичная fixture', 'parse_mode': None})
assert isinstance(request, SendMessage) and request.chat_id == 42 and request.text == 'Публичная fixture'
try: build_request(spec.name, {'chat_id': 42, 'text': 'Fixture', 'invented': True})
except InvalidAPIRequest: pass
else: raise AssertionError('Unknown field accepted')
# SDK validation не подтверждает права, доставку, rate limits или оплату.
print(json.dumps({'passed': True, 'case': 'bot_methods', 'network': False}))
```

<a id="ref-bot_navigation"></a>

## Экраны и история в одном сообщении — ref.bot_navigation

Файл: `bot_navigation.py`. Символы: `NavigationScreen`, `NavigationState`, `NavigationResult`, `MessageNavigation`, `navigation_router`

Границы: Optional aiogram. Owner/bot/chat/thread/message/revision guards, ACK first, unknown edit freeze and explicit same-message recovery. State lives in one process/event loop; restart leaves old buttons stale. Host owns sessions/tasks and business ACL. No automatic resend after unknown initial send; no live UI proof.

```python
"""Owner/version/history in one bot message; explicit recovery after unknown edit."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import User
from telegram_patterns.aiogram import (
    ActionButton, MessageNavigation, NavigationResult, NavigationScreen,
    NavigationState, navigation_router,
)
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, callback, response


async def main() -> None:
    session = StubSession().respond(AnswerCallbackQuery, True).respond(SendMessage, response).respond(EditMessageText, response)
    dispatcher = Dispatcher()
    menu = MessageNavigation([
        NavigationScreen('home', 'Главная', [ActionButton('Каталог', 'catalog')]),
        NavigationScreen('catalog', 'Каталог'),
    ])
    results: list[NavigationResult] = []
    async def result(query, feedback: NavigationResult) -> None:
        results.append(feedback)
    dispatcher.include_router(navigation_router(menu, on_result=result))
    async with Bot(TOKEN, session=session) as bot:
        try:
            initial: NavigationState = await menu.open(bot, 42, 42)
            reply = response(SendMessage(chat_id=42, text='Главная'))
            def key(target: str) -> str:
                state = menu.get_state(bot.id, 42, 42)
                assert state is not None
                return f'{menu.prefix}{state.session_id}:{state.revision}:{target}'
            old = key('catalog')
            await dispatcher.feed_update(bot, callback(old, reply, index=1, actor=User(id=43, is_bot=False, first_name='Other')))
            assert results[-1].status == 'denied' and results[-1].state is None
            await dispatcher.feed_update(bot, callback(old, reply, index=2))
            assert results[-1].state is not None
            assert results[-1].state.history == ('home',)
            await dispatcher.feed_update(bot, callback(key('_back'), reply, index=3))
            assert results[-1].state is not None
            assert results[-1].state.screen == 'home'
            await dispatcher.feed_update(bot, callback(old, reply, index=4))
            assert results[-1].status == 'stale'
            def lost(request): raise TimeoutError('PRIVATE_FIXTURE')
            session.respond(EditMessageText, lost)
            await dispatcher.feed_update(bot, callback(key('catalog'), reply, index=5))
            assert results[-1].status == 'unknown'
            session.respond(EditMessageText, response)
            recovered = await menu.open(bot, 42, 42)
            assert (recovered.message_id, recovered.screen, recovered.phase) == (initial.message_id, 'home', 'ready')
            assert len([c for c in session.calls if isinstance(c, SendMessage)]) == 1
            assert await menu.discard(bot.id, 42, 42)
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    print(json.dumps({'passed': True, 'case': 'bot_navigation', 'network': False}))


if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-bot_selection"></a>

## Составная клавиатура и Router выбора — ref.bot_selection

Файл: `bot_selection.py`. Символы: `selection_keyboard`, `selection_router`

Границы: Single-process server draft; exact owner/context/revision and confirmation token guards. No automatic business operation, persistence or multiworker guarantee. Current ACL/resource_version/idempotency transaction belongs to host; synthetic transport does not prove live delivery or rendering.

```python
"""SDK UI over a server-owned draft; effect hook is application-owned."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionResult, SelectionSpec
from telegram_patterns.aiogram import selection_keyboard, selection_router
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, callback, response


async def main() -> None:
    menu = SelectionMenu(SelectionSpec([SelectionOption('a','Alpha'),SelectionOption('b','Beta')],
        toggles={'notify':'Уведомлять'},min_selected=1), SelectionContext(100,42,42,100))
    initial = selection_keyboard(menu.state)
    assert len(initial.inline_keyboard[0]) == 2
    results: list[SelectionResult] = []
    intents: list[str] = []
    async def feedback(query, result: SelectionResult) -> None:
        results.append(result)
        if result.status == 'confirmed':
            assert result.state is not None and result.state.operation_id is not None
            intents.append(result.state.operation_id)  # Local fixture, no dangerous business effect.
    dispatcher = Dispatcher()
    dispatcher.include_router(selection_router(menu,on_result=feedback))
    session = StubSession().respond(AnswerCallbackQuery,True).respond(EditMessageText,response)
    async with Bot(TOKEN,session=session) as bot:
        try:
            reply = response(EditMessageText(text='Fixture',chat_id=42,message_id=100))
            for index,action in enumerate(('s:a','t:notify','q:inc','ask'),start=1):
                await dispatcher.feed_update(bot,callback(menu.state.callback(action),reply,index=index))
            state=menu.state
            assert state.confirmation_id is not None
            data=state.callback('y:'+state.confirmation_id)
            await dispatcher.feed_update(bot,callback(data,reply,index=5))
            await dispatcher.feed_update(bot,callback(data,reply,index=6))
            assert results[-2].status=='confirmed' and results[-1].status=='stale' and len(intents)==1
            assert len([m for m in session.calls if isinstance(m,EditMessageText)])==5
            assert selection_keyboard(menu.state).inline_keyboard==[]
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    print(json.dumps({'passed':True,'case':'bot_selection','network':False,'business_effects':0}))


if __name__=='__main__':
    asyncio.run(main())
```

<a id="ref-bot_calendar"></a>

## Кнопки календаря и времени — ref.bot_calendar

Файл: `bot_calendar.py`. Символы: `calendar_keyboard`, `time_slot_keyboard`

Границы: Optional aiogram; markup only. Callback data must be owner/context/revision bound by controller; the booking transaction rechecks availability. Default weekday fallback omits unavailable days. disabled_buttons=True requires explicit host-verified support; no live/device claim.

```python
"""Markup only: controller and transaction still validate callbacks on the server."""
from datetime import date, datetime, timedelta, timezone
import json
from telegram_patterns import CalendarMonth, TimeSlot
from telegram_patterns.aiogram import calendar_keyboard, time_slot_keyboard

month = CalendarMonth(2026, 10, 'UTC', [date(2026, 10, 6)])
calendar = calendar_keyboard(month, lambda day: 'calendar:' + day.isoformat())
assert calendar.inline_keyboard[0][0].callback_data == 'calendar:2026-10-06'
start = datetime(2026, 10, 6, 8, tzinfo=timezone.utc)
slots = time_slot_keyboard([TimeSlot('morning', start, start + timedelta(minutes=30))], 'UTC', lambda slot: 'time:' + slot.key)
assert slots.inline_keyboard[0][0].callback_data == 'time:morning'
print(json.dumps({'passed': True, 'case': 'bot_calendar', 'network': False,
                  'calendar_rows': len(calendar.inline_keyboard), 'slot_rows': len(slots.inline_keyboard)}))
```
