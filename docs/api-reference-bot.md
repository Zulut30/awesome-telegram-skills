# Python bot и test transport — 0.24.0

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **entitlement** — право на возможность (custom emoji, оплаченный доступ), которое проверяется отдельно от самого запроса; **fallback** — запасной вариант, если основная возможность недоступна.

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

Файл: `bot_runner.py`. Символы: `create_bot`, `run_bot`, `stars_invoice`

Границы: SDK polling через StubSession завершается после первого запроса; ни реального token, ни удаления webhook. Live требует отдельного процесса и проверки consumer/webhook. Runner закрывает session после успешного preflight. create_bot с test_environment=True направляет запросы в отдельное тестовое окружение Telegram; переданная session должна уже использовать TEST. Stars request не создает оплату, заказ или entitlement; consent и server ledger у host.

```python
"""Настоящий SDK polling через StubSession; останавливаем его после первого запроса."""
import asyncio
import json
from aiogram import Dispatcher
from aiogram.client.telegram import TEST
from aiogram.methods import GetMe, GetUpdates, SetMyCommands
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import create_bot, run_bot, stars_invoice, start_router
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
    # TELEGRAM_TEST_ENVIRONMENT=1 в BotSettings.from_env: отдельное тестовое окружение Telegram.
    test_bot = create_bot(BotSettings(TOKEN, test_environment=True), session=StubSession(api=TEST))
    assert '/test/' in test_bot.session.api.api_url(TOKEN, 'getMe')
    await test_bot.session.close()
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

Границы: Нужен extra aiogram. Проверяются владелец, бот, чат, тема, сообщение и ревизия; сначала ответ на callback (ACK), неизвестный результат редактирования замораживает меню, восстановление — явное, в том же сообщении. Состояние живет в одном процессе и цикле событий: после рестарта старые кнопки устаревают. Сессии, задачи и бизнес-права принадлежат приложению. После неизвестного результата первой отправки повтора нет; работа интерфейса в живом Telegram не подтверждена.

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

Границы: Черновик на сервере в одном процессе; точные проверки владельца, контекста, ревизии и токена подтверждения. Бизнес-операция, долговременное хранение и работа нескольких процессов не гарантируются. Текущие права, `resource_version` и идемпотентная транзакция принадлежат приложению; синтетический транспорт не доказывает доставку и отображение в Telegram.

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

Границы: Нужен extra aiogram; только разметка. Контроллер обязан привязать callback data к владельцу, контексту и ревизии; транзакция записи заново проверяет доступность. Запасной вариант по умолчанию просто не показывает недоступные дни. `disabled_buttons=True` требует поддержки, явно проверенной приложением; работа в живых клиентах не заявлена.

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

<a id="ref-bot_dialog_fields"></a>

## Число, email, телефон, дата, файл, контакт и геопозиция — ref.bot_dialog_fields

Файл: `bot_dialog_fields.py`. Символы: `FieldValue`, `NumberField`, `EmailField`, `PhoneField`, `DateField`, `FileField`, `ContactField`, `LocationField`, `DialogSubmission`, `dialog_form_router`

Границы: Нужен extra aiogram. Обычный личный чат; изоляция FSM и событий и долговечная бизнес-транзакция того же намерения — на стороне приложения. ForceReply связывается с автором и шагом; нативные значения требуют подтверждения. Метаданные и координаты не доказывают содержимое, личность или присутствие. Приемки в живых клиентах нет.

```python
"""Public mixed dialog API; synthetic parser/controller construction, no HTTP."""
import json
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Message
from telegram_patterns.aiogram import (FieldValue, NumberField, EmailField, PhoneField, DateField,
    FileField, ContactField, LocationField, DialogSubmission, dialog_form_router)

message=Message.model_validate({'message_id':1,'date':1,'chat':{'id':42,'type':'private'},
    'from':{'id':42,'is_bot':False,'first_name':'Owner'},
    'document':{'file_id':'opaque','file_unique_id':'unique','file_size':128},
    'contact':{'phone_number':'+48123456789','first_name':'Owner','user_id':42},
    'location':{'latitude':52.2,'longitude':21.0}})
fields: list[NumberField | EmailField | PhoneField | DateField | FileField | ContactField | LocationField] = [NumberField('number','Число','Число?',minimum=1,decimal_places=2),EmailField('email','Email','Email?'),
    PhoneField('phone','Телефон','Телефон?'),DateField('date','Дата','Дата?'),FileField('file','Файл','Файл?'),
    ContactField('contact','Контакт','Контакт?'),LocationField('geo','Место','Место?')]
value:FieldValue=fields[0].restore('12,50')
values={'number':value,'email':fields[1].restore('Case@EXAMPLE.COM'),'phone':fields[2].restore('+48 123 456 789'),
    'date':fields[3].restore('2024-02-29'),'file':fields[4].read(message),'contact':fields[5].read(message),'geo':fields[6].read(message)}
submission=DialogSubmission(100,42,42,'example-intent',values)
assert submission.values['number']=='12.5'
assert json.loads(json.dumps(submission.as_dict()))['contact']['user_id']==42
async def host_submit(s:DialogSubmission)->str:
    # Replace with host current ACL + durable operation_id transaction.
    raise RuntimeError('Reference construction does not run business effects')
dispatcher=Dispatcher(events_isolation=SimpleEventIsolation())
dispatcher.include_router(dialog_form_router(fields,host_submit))
print(json.dumps({'passed':True,'case':'bot_dialog_fields','network':False,'field_types':len(fields),'constructed_router':True}))
```

<a id="ref-bot_media"></a>

## Медиа, альбомы и ограниченное скачивание — ref.bot_media

Файл: `bot_media.py`. Символы: `MediaKind`, `MediaSendRequest`, `MediaFile`, `MediaItem`, `DownloadedMedia`, `media_request`, `media_album`, `media_edit`, `download_media`

Границы: Нужен extra aiogram; запросы ничего не отправляют сами. Типизированная загрузка байтов или `file_id` того же бота; проверки кодека и прав нет. Альбом — от 2 до 10 совместимых элементов, подпись — до 1024 единиц UTF-16, загрузка в inline отклоняется. Явное ограниченное скачивание с серверов Telegram закрывает поток; локальной файловой системы, URL, преобразования `unique_id` и автоматического повтора нет. Приложение сохраняет нативную маршрутизацию и права и проверяет фактическое содержимое.

```python
"""All public media symbols against SDK objects and a synthetic byte stream."""
import asyncio
import json
from aiogram import Bot
from aiogram.methods import GetFile, SendPhoto
from telegram_patterns import MessageBuilder
from telegram_patterns.aiogram import (
    MediaKind, MediaSendRequest, MediaFile, MediaItem, DownloadedMedia,
    media_request, media_album, media_edit, download_media,
)
from telegram_patterns.testing import StubSession


class MediaSession(StubSession):
    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b'actual fixture bytes'


async def main():
    session=MediaSession()
    bot=Bot('100:MEDIA_REFERENCE',session=session)
    kind: MediaKind='photo'
    item=MediaItem(MediaFile(kind,'opaque',bot_id=bot.id),MessageBuilder().style('Фото','bold').build())
    request: MediaSendRequest=media_request(item,bot_id=bot.id,chat_id=42)
    assert isinstance(request,SendPhoto) and request.parse_mode is None
    native=item.as_input_media(bot.id)
    assert native.caption_entities is not None and native.caption_entities[0].length==4
    assert len(media_album([item,item],bot_id=bot.id,chat_id=42).media)==2
    assert media_edit(item,bot_id=bot.id,inline_message_id='inline_fixture').inline_message_id=='inline_fixture'
    session.respond(GetFile,{'file_id':'opaque','file_unique_id':'unique','file_size':20,'file_path':'documents/fixture.txt'})
    try:
        downloaded: DownloadedMedia=await download_media(bot,'opaque',max_bytes=20)
        assert downloaded.data==b'actual fixture bytes' and downloaded.bot_id==bot.id
    finally:
        await bot.session.close()
    print(json.dumps({'case':'bot_media','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__': asyncio.run(main())
```

<a id="ref-bot_profiles"></a>

## Профили и разрешенное оформление собственного бота — ref.bot_profiles

Файл: `bot_profiles.py`. Символы: `ProfileSource`, `ProfileAuthorizer`, `UserProfile`, `ChatProfile`, `ProfilePhotoSize`, `ProfilePhotos`, `BotProfile`, `BotProfilePatch`, `ProfileEditIncomplete`, `user_profile`, `chat_profile`, `read_profile_photos`, `read_bot_profile`, `update_bot_profile`

Границы: Нужен extra aiogram; неизменяемые выбранные факты SDK, различие `bool`/`None`, источник и время не авторизуют пользователя. Явные нативные чтения сохраняют видимость и запасную локаль. Запись в профиль собственного бота требует свежей личности и текущих прав приложения на каждый метод; `None` пропускает поле, пустая строка очищает локаль, аватар — глобальный, из новых байтов. Кодек и содержимое, сериализация, кеши и сверка — на стороне приложения; последовательные записи и чтение не атомарны, отмена или отклоненный `await` не откатывает эффекты. Business, MTProto, редактирования произвольного профиля и живой проверки нет.

```python
"""Every public profile symbol, native reads and one explicitly authorized write."""
import asyncio
import json
from aiogram import Bot
from aiogram.methods import GetMe, GetMyName, GetMyDescription, GetMyShortDescription, GetUserProfilePhotos, SetMyDescription
from aiogram.types import User, ChatFullInfo
from telegram_patterns import safe_error_report
from telegram_patterns.aiogram import (
    ProfileSource, ProfileAuthorizer, UserProfile, ChatProfile, ProfilePhotoSize, ProfilePhotos,
    BotProfile, BotProfilePatch, ProfileEditIncomplete, user_profile, chat_profile,
    read_profile_photos, read_bot_profile, update_bot_profile,
)
from telegram_patterns.testing import StubSession


async def main():
    session = StubSession()
    bot = Bot('100:PROFILE_REFERENCE', session=session)
    source: ProfileSource = 'update'
    user: UserProfile = user_profile(User(id=42, is_bot=False, first_name='Example'), source=source)
    assert user.is_premium is None and user.username is None
    chat: ChatProfile = chat_profile(ChatFullInfo.model_validate({'id': 42, 'type': 'private', 'accent_color_id': 0,
        'max_reaction_count': 11, 'accepted_gift_types': {k: False for k in ('unlimited_gifts', 'limited_gifts', 'unique_gifts', 'premium_subscription', 'gifts_from_channels')}}))
    assert chat.bio is None and chat.permissions is None
    size = ProfilePhotoSize(bot.id, user.id, 'opaque', 'unique', 100, 100)
    assert size.as_media().as_input(bot.id) == 'opaque'
    session.respond(GetMe, {'id': 100, 'is_bot': True, 'first_name': 'Bot'})
    state = {'description': 'Original'}
    session.respond(GetMyName, {'name': 'Localized name'}).respond(GetMyShortDescription, {'short_description': 'Short'})
    session.respond(GetMyDescription, lambda request: {'description': state['description']})
    session.respond(GetUserProfilePhotos, {'total_count': 0, 'photos': []})
    def update(request): state['description'] = request.description; return True
    session.respond(SetMyDescription, update)
    async def authorize(actor_id: int, bot_id: int, method: str) -> bool:
        return actor_id == user.id and bot_id == bot.id and method in ('read', 'setMyDescription')
    acl: ProfileAuthorizer = authorize
    try:
        photos: ProfilePhotos = await read_profile_photos(bot, user.id)
        assert photos.total_count == 0 and photos.photos == ()
        profile: BotProfile = await read_bot_profile(bot, language_code='ru')
        assert profile.user.source == 'getMe' and profile.user.is_premium is None
        assert profile.photos is None
        with_photos = await read_bot_profile(bot, language_code='ru', include_photos=True)
        assert with_photos.photos is not None and with_photos.photos.total_count == 0 and with_photos.photos.user_id == bot.id
        updated = await update_bot_profile(bot, BotProfilePatch(description='New'), actor_id=user.id, authorize=acl, language_code='ru')
        assert updated.description == 'New' and updated.name == profile.name
        incomplete = ProfileEditIncomplete(('setMyName',), 'setMyDescription')
        assert safe_error_report(incomplete, operation='write').recovery == 'reconcile'
    finally:
        await bot.session.close()
    print(json.dumps({'case': 'bot_profiles', 'passed': True, 'network': False, 'session_closed': session.closed}))


if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-bot_inline_search"></a>

## Inline-поиск и shareable results — ref.bot_inline_search

Файл: `bot_inline_search.py`. Символы: `InlineChatType`, `InlineAuthorizer`, `InlineSearchProvider`, `InlineCachePolicy`, `InlineItem`, `InlinePage`, `InlineSearch`, `inline_articles`, `inline_query_router`

Границы: Личные элементы по умолчанию нельзя делиться; персональный кеш Telegram не делает отправленное inline-сообщение секретным. Текущие права, ревизии каталога и прав, долговечный секрет, сроки, конкурентность и хранилище принадлежат приложению. Персональные курсоры привязаны к пользователю, боту, запросу, контексту и каталогу; общий кеш полностью публичный, для всех контекстов и не зависит от пользователя. Положительный серверный кеш может повторить старые результаты, не обращаясь к боту, поэтому выдача с текущими ограничениями прав использует `cache_time=0`. Срок цепочки курсоров не продлевается; устаревший, запрещенный или просроченный запрос получает пустой персональный ответ, а не автоматический перезапуск. Статьи передаются буквально, проверенные метаданные emoji — по явному согласию; повтора нативного ответа, учета выбранных результатов и живой проверки приватности нет.

```python
"""All public inline symbols with personal pagination and one native answer."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, InputTextMessageContent, Update, User
from telegram_patterns.aiogram import (InlineChatType, InlineAuthorizer, InlineSearchProvider, InlineCachePolicy,
                                      InlineItem, InlinePage, InlineSearch, inline_articles, inline_query_router)
from telegram_patterns.testing import StubSession


async def main():
    context: InlineChatType='sender'
    native=InlineQuery(id='q1',from_user=User(id=42,is_bot=False,first_name='Reader'),query='',offset='',chat_type=context)
    catalog=InlineSearch([InlineItem('a','A','Shared A',shareable=True),InlineItem('b','B','Shared B',shareable=True),
                         InlineItem('private','Private','Never sent')],secret=b'host-persistent-reference-secret32',revision='v1',
                        page_size=1,cache=InlineCachePolicy())
    async def allow(actor:int,item:InlineItem)->bool: return actor==42
    authorize: InlineAuthorizer=allow
    async def load(query:InlineQuery)->InlineSearch: return catalog
    provider: InlineSearchProvider=load
    page: InlinePage=await catalog.page(native,bot_id=100,authorize=authorize)
    assert [item.id for item in page.items]==['a'] and len(page.next_offset.encode())<=64
    articles=inline_articles(page)
    content=articles[0].input_message_content
    assert isinstance(content,InputTextMessageContent) and content.parse_mode is None
    following=native.model_copy(update={'id':'q2','offset':page.next_offset})
    assert (await catalog.page(following,bot_id=100,authorize=authorize)).items[0].id=='b'
    session=StubSession().respond(AnswerInlineQuery,True); bot=Bot('100:INLINE_REFERENCE',session=session)
    dispatcher=Dispatcher(); dispatcher.include_router(inline_query_router(provider,authorize=authorize))
    try:
        await dispatcher.feed_update(bot,Update(update_id=1,inline_query=native))
        answer=session.calls[0]
        assert isinstance(answer,AnswerInlineQuery) and answer.is_personal and answer.cache_time==0
    finally:
        await dispatcher.fsm.close(); await bot.session.close()
    print(json.dumps({'case':'bot_inline_search','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__': asyncio.run(main())
```

<a id="ref-bot_polls"></a>

## Опросы, quiz и доступные события — ref.bot_polls

Файл: `bot_polls.py`. Символы: `PollKind`, `PollChoice`, `PollSpec`, `PollOptionState`, `PollState`, `PollVote`, `PollOptionAddition`, `PollBinding`, `PollLocator`, `PollObservation`, `PollEvent`, `PollObserver`, `PollLookup`, `poll_request`, `poll_state`, `poll_vote`, `poll_option_added`, `poll_events_router`

Границы: От 1 до 12 начальных вариантов, quiz с несколькими правильными ответами без их сокращения, переголосование и rich media SDK; нативные лимиты проверяются отдельно от локальных. Ограничения «только участники канала» и по странам и явно заявленный контекст чата, темы или Business не доказывают серверных прав. Постоянные ID вариантов и личности голосующих (пользователь или чат); `None` и сообщенный ноль остаются сырыми и, возможно, неизвестными. Приложение регистрирует подтвержденные ответы собственного `SendPoll`, находит текущую привязку и транзакционно сохраняет квитанцию Update. Недоступный `poll_message` не позволяет выдумать связь; анонимные, чужие и непривязанные события не дают реестра голосов. Нет `getPoll`, неявного `stopPoll`, просмотра истории, подсчета голосов, повтора создания, ввода-вывода медиа и обещания живой доставки.

```python
"""All public poll symbols, native quiz and available scoped observations."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.types import Message, Poll, PollAnswer, Update
from telegram_patterns.aiogram import (PollKind, PollChoice, PollSpec, PollOptionState, PollState, PollVote,
    PollOptionAddition, PollBinding, PollLocator, PollObservation, PollEvent, PollObserver, PollLookup,
    poll_request, poll_state, poll_vote, poll_option_added, poll_events_router)
from telegram_patterns.testing import StubSession


async def main():
    kind: PollKind='quiz'
    request=poll_request(PollSpec('Even numbers',[PollChoice('2'),'3','4'],kind=kind,correct_option_ids=[0,2],
                        allows_multiple_answers=True),chat_id=42)
    assert request.correct_option_ids==[0,2] and request.correct_option_id is None
    native=Poll.model_validate({'id':'p','question':'Q','options':[{'text':'A','voter_count':0,'persistent_id':'stable-a'}],
        'total_voter_count':1,'is_closed':False,'is_anonymous':False,'type':'regular','allows_multiple_answers':False,
        'allows_revoting':True,'members_only':False})
    state: PollState=poll_state(native); option: PollOptionState=state.options[0]
    assert option.persistent_id=='stable-a' and state.correct_option_ids is None
    answer=PollAnswer.model_validate({'poll_id':'p','option_ids':[0],'option_persistent_ids':['stable-a'],
                                     'user':{'id':42,'is_bot':False,'first_name':'Voter'}})
    selection: PollVote=poll_vote(answer); observation: PollObservation=selection
    assert selection.option_persistent_ids==('stable-a',)
    sent=Message.model_validate({'message_id':10,'date':1780000000,'chat':{'id':42,'type':'private'},
                                 'from':{'id':100,'is_bot':True,'first_name':'Bot'},'poll':native})
    binding=PollBinding.from_message(sent,bot_id=100)
    service=sent.model_copy(update={'poll':None}).model_dump(mode='json',by_alias=True)
    service['poll_option_added']={'option_persistent_id':'stable-new','option_text':'B','poll_message':{
        'chat':{'id':42,'type':'private'},'message_id':10,'date':0}}
    addition: PollOptionAddition=poll_option_added(Message.model_validate(service))
    assert addition.poll_id is None and addition.message_id==10
    events=[]
    async def lookup(locator:PollLocator)->PollBinding|None:
        return binding if locator.bot_id==100 and locator.poll_id==binding.poll_id else None
    async def observe(event:PollEvent)->None: events.append(event)
    host_lookup: PollLookup=lookup; host_observer: PollObserver=observe
    assert PollEvent(1,binding,observation).binding==binding
    session=StubSession(); bot=Bot('100:POLL_REFERENCE',session=session); dispatcher=Dispatcher()
    dispatcher.include_router(poll_events_router(host_lookup,host_observer))
    try:
        await dispatcher.feed_update(bot,Update(update_id=2,poll_answer=answer))
        assert len(events)==1 and events[0].update_id==2 and not session.calls
    finally:
        await dispatcher.fsm.close(); await bot.session.close()
    print(json.dumps({'case':'bot_polls','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__': asyncio.run(main())
```

<a id="ref-bot_platform"></a>

## Темы, реакции, заявки и специальные операции — ref.bot_platform

Файл: `bot_platform.py`. Символы: `PlatformContract`, `PlatformScope`, `PlatformPermit`, `PlatformAction`, `PlatformReceipt`, `PlatformResult`, `PlatformHooks`, `SecretToken`, `PlatformEvent`, `PlatformLookup`, `PlatformObserver`, `platform_contracts`, `execute_platform_action`, `managed_bot_link`, `platform_event`, `platform_events_router`, `StoryPhotoUpload`, `StoryVideoUpload`

Границы: Закрытый список из 51 метода Bot API в семи семействах; нативные запросы SDK и текущие права конкретного метода, а не произвольный MTProto или история аккаунта. Текущие права, ресурс, ревизия, связи подключений и дочерних ботов, проверка медиа и допустимая активность принадлежат приложению. Запись требует атомарной долговечной заявки на отправку; бюджет, согласие и котировка приложения перепроверяются до нативного ввода-вывода. Локальное резервирование и свежая нативная котировка не гарантируют атомарного удаленного списания или финансовых расчетов. Неизвестный результат, квитанция или падение остаются тем же намерением: без автоматического повтора, отката, сверки и глобального inbox/outbox. Запрос на вступление использует исходное время получения и оставшийся нативный срок; личные темы поддерживают только явно разрешенные методы. Создание управляемого бота требует нативного подтверждения пользователя; repr токена скрыт, но хранение и сериализация секрета в приложении остаются явными. Загрузка историй использует проверенный вложенный multipart SDK; кодек, размеры, содержимое и время жизни файла — обязанности приложения. События сохраняют неизвестные и анонимные факты; текущая привязка, дедупликация, порядок и отзыв — на стороне приложения, без выведенного автора и истории голосов или аккаунта. Экспериментальные доказательства автора (SDK, mock, браузер) отделены от живых прав, реальных устройств, удаленного списания и независимой приемки людьми или ИИ.

```python
"""Public platform API, mandatory host hooks and native multipart story bridge."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import CreateForumTopic, GetChat, GetChatMember, GetManagedBotToken, GetMe, PostStory
from aiogram.types import BufferedInputFile, InputFile, Update
from telegram_patterns.aiogram import (PlatformContract, PlatformScope, PlatformPermit, PlatformAction,
    PlatformReceipt, PlatformResult, PlatformHooks, SecretToken, PlatformEvent, PlatformLookup, PlatformObserver,
    platform_contracts, execute_platform_action, managed_bot_link, platform_event, platform_events_router,
    StoryPhotoUpload, StoryVideoUpload)
from telegram_patterns.testing import StubSession


async def main():
    contract:PlatformContract=platform_contracts()[0]
    assert contract.family=='topics' and contract.verification=='sdk'
    scope=PlatformScope(100,42,'reference-topic',chat_id=-100)
    action=PlatformAction(scope,CreateForumTopic(chat_id=-100,name='Topic'))
    class Host:
        def __init__(self):self.claimed=set();self.receipts=[]
        async def authorize(self,action:PlatformAction)->PlatformPermit:
            return PlatformPermit(allowed=action.scope.actor_id==42,managed_bot_bound=True)
        async def claim(self,action:PlatformAction,permit:PlatformPermit)->bool:
            key=(action.scope.bot_id,action.scope.operation_id)
            if key in self.claimed:return False
            self.claimed.add(key);return True  # Memory fixture; production host persists atomically.
        async def record(self,action:PlatformAction,receipt:PlatformReceipt)->None:self.receipts.append(receipt)
    host=Host();hooks:PlatformHooks=host
    bot_user={'id':100,'is_bot':True,'first_name':'Bot','username':'fixture_bot','can_manage_bots':True}
    types={'unlimited_gifts':True,'limited_gifts':True,'unique_gifts':True,'premium_subscription':True,'gifts_from_channels':True}
    session=StubSession().respond(GetMe,bot_user).respond(GetChat,{'id':-100,'type':'supergroup','is_forum':True,
        'accent_color_id':0,'max_reaction_count':1,'accepted_gift_types':types})
    session.respond(GetChatMember,{'status':'creator','user':bot_user,'is_anonymous':False})
    session.respond(CreateForumTopic,{'message_thread_id':17,'name':'Topic','icon_color':7322096})
    session.respond(GetManagedBotToken,'500:REFERENCE_SECRET_TOKEN_123456789')
    bot=Bot('100:PLATFORM_REFERENCE_FIXTURE',session=session);dispatcher=Dispatcher();seen=[]
    async def locate(event:PlatformEvent)->PlatformScope|None:
        return PlatformScope(100,42,'reference-event',chat_id=-100,message_thread_id=17)
    async def observed(event:PlatformEvent,scope:PlatformScope)->None:seen.append(event.kind)
    lookup:PlatformLookup=locate;observer:PlatformObserver=observed
    dispatcher.include_router(platform_events_router(lookup,observer))
    try:
        result:PlatformResult=await execute_platform_action(bot,action,hooks)
        receipt:PlatformReceipt=result.receipt
        assert receipt.result_id==17 and len(host.receipts)==1
        secret_result=await execute_platform_action(bot,PlatformAction(PlatformScope(100,42,'reference-secret',owner_id=42,child_bot_id=500),GetManagedBotToken(user_id=500)),hooks)
        assert isinstance(secret_result.value,SecretToken) and 'SECRET' not in repr(secret_result.value)
        assert secret_result.value.reveal().startswith('500:')  # Explicit host secret-store handoff, not logging.
        assert '%26' in managed_bot_link('ManagerBot','ExampleBot',name='Example & Bot')
        for content in (StoryPhotoUpload(photo=BufferedInputFile(b'PHOTO','photo.jpg')),
                        StoryVideoUpload(video=BufferedInputFile(b'VIDEO','video.mp4'),duration=1)):
            request=PostStory(business_connection_id='fixture',content=content,active_period=21600,parse_mode=None)
            files:dict[str,InputFile]={};encoded=bot.session.prepare_value(request.model_dump(warnings=False),bot,files)
            data=json.loads(encoded);key=data['content'][content.type].removeprefix('attach://')
            uploaded=files[key]
            assert isinstance(uploaded,BufferedInputFile) and uploaded.data in (b'PHOTO',b'VIDEO')
        update=Update.model_validate({'update_id':1,'message':{'message_id':10,'message_thread_id':17,'date':1780000000,
            'chat':{'id':-100,'type':'supergroup'},'forum_topic_created':{'name':'Topic','icon_color':7322096}}})
        event=platform_event(update,bot_id=100);assert isinstance(event,PlatformEvent) and event.kind=='forum_topic_created'
        await dispatcher.feed_update(bot,update);assert seen==['forum_topic_created']
    finally:await dispatcher.fsm.close();await bot.session.close()
    print(json.dumps({'case':'bot_platform','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__':asyncio.run(main())
```

<a id="ref-bot_fsm_storage"></a>

## Атомарное состояние и восстановление диалога — ref.bot_fsm_storage

Файл: `bot_fsm_storage.py`. Символы: `FSMSnapshot`, `FSMConflict`, `SnapshotStore`, `AtomicFSMStorage`, `SnapshotFSMStorage`, `DialogLifetime`

Границы: Структурное хранилище приложения, точный шестиполевой ключ SDK, одна CAS-запись состояния и данных (сравнение с заменой); JSON до 64 КиБ. Словарь в примере только показывает контракт и не сохраняется; отдельная файловая SQLite и доказательство с тремя процессами — в рецепте восстановления диалога. Сохраняйте изоляцию событий, миграции и надгробные записи, права и дедупликацию бизнес-эффекта; обещания exactly-once в живой или распределенной системе нет.

```python
import asyncio
import json
from typing import Any, Mapping
from aiogram.fsm.storage.base import StorageKey
from telegram_patterns.aiogram import (AtomicFSMStorage, DialogLifetime, FSMSnapshot,
    FSMConflict, SnapshotStore, SnapshotFSMStorage)


class DemonstrationStore:
    # Contract fixture only; a dict is explicitly not persistent across restart.
    def __init__(self) -> None:
        self.records: dict[StorageKey, FSMSnapshot] = {}

    async def read(self, key: StorageKey) -> FSMSnapshot:
        return self.records.get(key, FSMSnapshot(None, {}, 0))

    async def compare_and_set(self, key: StorageKey, expected_revision: int,
                              state: str | None, data: Mapping[str, Any]) -> FSMSnapshot:
        if (await self.read(key)).revision != expected_revision:
            raise FSMConflict('Stale local revision')
        result = FSMSnapshot(state, data, expected_revision + 1)
        self.records[key] = result
        return result

    async def close(self) -> None:
        pass


async def main() -> None:
    store: SnapshotStore = DemonstrationStore()
    storage = SnapshotFSMStorage(store)
    atomic: AtomicFSMStorage = storage
    key = StorageKey(bot_id=100, chat_id=42, user_id=42)
    policy = DialogLifetime(60, clock=lambda: 100.0)
    old = await atomic.read_snapshot(key)
    saved = await atomic.commit_snapshot(key, old, 'form', {'host': 'ru', 'form': {
        'step': 1, 'schema_version': 3, 'lifetime': policy.start()}})
    assert saved.revision == 1 and saved.data['form']['lifetime']['expires_at'] == 160.0
    try:
        await atomic.commit_snapshot(key, old, 'stale', {})
    except FSMConflict:
        pass
    else:
        raise AssertionError('Stale write accepted')
    assert await storage.get_state(key) == 'form' and not policy.expired(saved.data['form']['lifetime'])
    await storage.close()
    print(json.dumps({'case': 'bot_fsm_storage', 'passed': True, 'network': False}))


if __name__ == '__main__': asyncio.run(main())
```
