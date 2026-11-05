# Python core — 0.27.0

Термины: **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **entitlement** — право на возможность (custom emoji, оплаченный доступ), которое проверяется отдельно от самого запроса; **fallback** — запасной вариант, если основная возможность недоступна.

[Индекс всех символов](api-reference.md). Образцы ниже воспроизводятся через установленный wheel/tarball вне исходного дерева. Assert — проверка fixture, не бизнес-правило production приложения.

Установите предоставленный локальный wheel без aiogram. Для core_starter.py передайте путь к нему как первый аргумент: `python core_starter.py "<PROVIDED_WHEEL>"`. Остальные файлы запускаются `python <FILE.py>`. Для core_calendar нужна IANA-база Europe/Warsaw: при ее отсутствии установите calendar extra того же wheel; aiogram не требуется. core_doctor намеренно проверяет SDK-free окружение.

<a id="ref-core_identity"></a>

## Конфигурация и проверенный запуск — ref.core_identity

Файл: `core_identity.py`. Символы: `BotSettings`, `InvalidInitData`, `VerifiedLaunch`, `validate_init_data`, `validate_init_data_signature`, `TELEGRAM_PUBLIC_KEYS`

Границы: HMAC fixture без Telegram; token только на backend, raw initData проверяется до session/ACL. BotSettings repr скрывает token, сериализация не становится безопасной. VerifiedLaunch — результат проверки, ручной DTO не подтверждает identity. Сторонняя проверка Ed25519 знает только bot_id и опубликованный ключ Telegram; она требует extra signature (cryptography), без него сообщает UnsupportedCapability. Пример подписан ключом из тестов aiogram, а не ключом Telegram.

```python
"""Искусственная HMAC-подпись и независимый вектор Ed25519 для локального примера, без Telegram и login."""
import hmac
import json
from urllib.parse import urlencode
from telegram_patterns import (BotSettings, InvalidInitData, TELEGRAM_PUBLIC_KEYS, UnsupportedCapability, VerifiedLaunch,
                               validate_init_data, validate_init_data_signature)

settings = BotSettings.from_env(environ={'BOT_TOKEN': '100:REFERENCE_FIXTURE'})
fields = {'auth_date': '1000', 'user': json.dumps({'id': 42})}
check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
secret = hmac.digest(b'WebAppData', settings.token.encode(), 'sha256')
raw = urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})
launch: VerifiedLaunch = validate_init_data(raw, settings.token, now=1001)
assert (launch.user_id, launch.auth_date, launch.user['id']) == (42, 1000, 42)
try:
    validate_init_data(raw + '&user=duplicate', settings.token, now=1001)
except InvalidInitData:
    pass
else:
    raise AssertionError('Ambiguous launch accepted')
assert 'REFERENCE_FIXTURE' not in repr(settings)
# Сторонняя проверка без токена бота: подпись Ed25519 и bot_id. Вектор и ключ из тестов aiogram, не ключ Telegram.
signed = ('auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test'
          '&signature=JQ0JR2tjC65yq_jNZV0wuJVX6J-SWPMV0mprUXG34g-NvxL4RcF1Rz5n4VVo00VRghEUBf5t___uoeb1-jU_Cw')
fixture_key = bytes.fromhex('4112765021341e5415e772cd65903f6b94e3ea1c2ab669e6d3e18ee2db00da61')
assert len(TELEGRAM_PUBLIC_KEYS['production']) == 32  # настоящая initData проверяется этим ключом
third_party: VerifiedLaunch | None
try:
    third_party = validate_init_data_signature(signed, 42, public_key=fixture_key, now=1650385342)
except UnsupportedCapability:
    third_party = None  # без extra signature (cryptography) функция сообщает, что Ed25519 недоступна
else:
    assert (third_party.user_id, third_party.query_id) == (42, 'test')
# Настоящие initData приходят от Telegram; ACL/session/replay проверяет backend.
print(json.dumps({'passed': True, 'case': 'core_identity', 'network': False}))
```

<a id="ref-core_message_text"></a>

## Безопасные сообщения и длинный текст — ref.core_message_text

Файл: `core_message_text.py`. Символы: `EntityKind`, `TextEntity`, `TextPayload`, `FormattedText`, `MessageBuilder`, `utf16_length`, `escape_html`, `escape_markdown_v2`, `split_formatted`

Границы: Готовит текст с entities и parse_mode=None без зависимости от SDK. Лимит в единицах UTF-16 консервативный; неделимая entity или последовательность Unicode больше лимита вызывает ошибку. Распространенные emoji и комбинируемые последовательности не разрезаются, полная сегментация UAX29 не обещана. Проект сам проверяет доверие к ссылкам, метаданные стикера и запасного варианта, entitlement и контекст для custom emoji; по умолчанию используется обычный emoji. Сеть, повторы, доставку и права доступа компонент не обещает.

```python
"""All SDK-free message exports; no network, parser, Unicode asset or rights proof."""
import json
from telegram_patterns import (EntityKind, TextEntity, TextPayload, FormattedText, MessageBuilder,
    utf16_length, escape_html, escape_markdown_v2, split_formatted)

kind: EntityKind = 'bold'
value = MessageBuilder().text('😀 ').style('<b>literal</b>_*', kind).text('\n'+'text '*1000).build()
parts = split_formatted(value)
assert ''.join(p.text for p in parts) == value.text
assert value.entities[0].offset == 3
payload: TextPayload = parts[0].as_kwargs()
assert payload['parse_mode'] is None and payload['entities'][0]['offset'] == 3
assert all(utf16_length(p.text)<=4096 for p in parts)
raw = FormattedText('link', (TextEntity('text_link',0,4,url='https://example.com'),))
assert raw.as_kwargs()['entities'][0]['url']=='https://example.com'
assert escape_html('<b>&"')=='&lt;b&gt;&amp;&quot;'
assert escape_markdown_v2('_*')=='\\_\\*'
assert escape_markdown_v2('`\\',context='code')=='\\`\\\\'
assert escape_markdown_v2(')\\',context='link')=='\\)\\\\'
emoji=MessageBuilder().custom_emoji('👍','123456789').build()
assert emoji.as_kwargs()['entities']==[]
assert emoji.as_kwargs(custom_emoji_entitlement_verified=True)['entities'][0]['type']=='custom_emoji'
print(json.dumps({'case':'core_message_text','passed':True,'network':False,'chunks':len(parts)}))
```

<a id="ref-core_rich_message"></a>

## Rich-сообщения и запасной текст — ref.core_rich_message

Файл: `core_rich_message.py`. Символы: `RichMessageBuilder`, `RichMessage`, `RichButton`, `RichButtonStyle`, `RichSpan`, `RichText`

Границы: Строит InputRichMessage для sendRichMessage (Bot API 10.1+) без зависимости от SDK: заголовки, абзацы, списки и чек-листы, таблицы, ряды кнопок, обычные и сворачиваемые цитаты, details, документы по file_id или URL, код, разделитель и подвал. build() проверяет опубликованные лимиты: 500 блоков с вложенными, 16 уровней, 50 медиа, 20 столбцов, 32768 символов, 1–8 кнопок в ряду. Ссылки только HTTP(S). Запасной вариант — FormattedText и inline-клавиатура для sendMessage. Отображение в клиентах, право отправлять rich-сообщения от имени Business и загрузку новых файлов проверяет проект.

```python
"""SDK-free rich message blocks and their text fallback; no network and no Telegram rendering proof."""
import json
from telegram_patterns import (FormattedText, RichButton, RichButtonStyle, RichMessage, RichMessageBuilder, RichSpan,
                               RichText)

style: RichButtonStyle = 'success'
status: RichText = ['Статус: ', RichSpan('bold', 'оплачен')]
details = RichMessageBuilder().paragraph('Возврат в течение 14 дней.')
message: RichMessage = (RichMessageBuilder().heading('Заказ №42', size=1).paragraph(status)
                        .table([['Товар', 'Цена'], ['Книга', '500 ₽']], compact=True)
                        .checklist([('Оплата', True), ('Доставка', False)])
                        .quote('Длинный комментарий', expandable=True).details('Подробнее', details)
                        .document('FIXTURE_FILE_ID', caption='Чек')
                        .buttons([RichButton('Подтвердить', callback_data='order:confirm:42', style=style)]).build())
payload = message.as_input()  # rich_message для sendRichMessage; SDK модели проверяют ее перед отправкой
assert [block['type'] for block in payload['blocks']][:3] == ['heading', 'paragraph', 'table']
assert payload['blocks'][2]['is_compact'] is True and message.media_count == 1
fallback: FormattedText = message.fallback()  # тот же текст для sendMessage, где rich-сообщение недоступно
assert 'Товар | Цена' in fallback.text and fallback.split()[0].as_kwargs()['parse_mode'] is None
assert message.fallback_keyboard()[0][0]['callback_data'] == 'order:confirm:42'
try:
    RichMessageBuilder().table([['x'] * 21])
except ValueError:
    pass
else:
    raise AssertionError('Telegram allows at most 20 table columns')
print(json.dumps({'case': 'core_rich_message', 'passed': True, 'network': False, 'blocks': message.block_count}))
```

<a id="ref-core_ephemeral"></a>

## Эфемерные сообщения в группах — ref.core_ephemeral

Файл: `core_ephemeral.py`. Символы: `ephemeral_parameters`, `EphemeralTrigger`, `EphemeralMessageRef`, `EphemeralNotAllowed`

Границы: Правила Bot API 10.2+ без SDK: эфемерное сообщение видит один участник группы или супергруппы и бот. Бот без прав администратора отвечает в течение 15 секунд и называет повод: callback_query_id нажатия или ephemeral_message_id эфемерной команды; администратор пишет любому участнику-человеку в любое время. Замена исходного сообщения — только для свежего нажатия на обычном сообщении. Доставка не гарантирована, ID может повториться после удаления или истечения; права администратора и время события проект передает сам.

```python
"""SDK-free ephemeral message rules: who may receive one and how to address edits; no network."""
import json
from telegram_patterns import EphemeralMessageRef, EphemeralNotAllowed, EphemeralTrigger, ephemeral_parameters

press = EphemeralTrigger.callback('fixture-query', received_at=100.0)
extra = ephemeral_parameters(chat_type='supergroup', receiver_user_id=7, trigger=press, now=101.0)
# sendMessage(chat_id=..., text=..., **extra): only user 7 sees the answer.
assert extra == {'ephemeral_message_parameters': {'receiver_user_id': 7, 'callback_query_id': 'fixture-query'}}
command = EphemeralTrigger.reply_to(55, received_at=100.0)
assert ephemeral_parameters(chat_type='group', receiver_user_id=7, trigger=command, now=110.0)['reply_parameters'] == {'ephemeral_message_id': 55}
try:
    ephemeral_parameters(chat_type='supergroup', receiver_user_id=7, trigger=press, now=116.0)
except EphemeralNotAllowed:
    pass  # a non-administrator bot has 15 seconds; then answer with an alert or an ordinary message
else:
    raise AssertionError('Late ephemeral answer accepted')
sent = EphemeralMessageRef(chat_id=-1001, receiver_user_id=7, ephemeral_message_id=5)  # Message.ephemeral_message_id
assert sent.target() == {'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5}  # editEphemeralMessage*/delete
print(json.dumps({'case': 'core_ephemeral', 'passed': True, 'network': False}))
```

<a id="ref-core_stars_subscription"></a>

## Подписка Stars и платный доступ — ref.core_stars_subscription

Файл: `core_stars_subscription.py`. Символы: `StarsSubscription`, `StarsCharge`, `RenewalState`, `SubscriptionEventRejected`, `STARS_SUBSCRIPTION_PERIOD`

Границы: Модель без SDK для подписки Telegram Stars: одна подписка — пользователь и invoice_payload. Каждое рекуррентное SuccessfulPayment дает полуоткрытый период [дата сообщения, subscription_expiration_date); повтор того же charge ничего не продлевает, тот же ID с другими данными отклоняется. BotSubscriptionUpdated (Bot API 10.2+: canceled, active, failed) меняет только ожидание следующего списания, а не оплаченное время. RefundedPayment снимает период своего charge, в том числе если пришел раньше платежа. Хранение (as_dict/from_dict), порядок событий и сверка через getStarTransactions — задача проекта.

```python
"""SDK-free paid access from a Stars subscription: charges, renewal states and refunds; no network."""
import json
from telegram_patterns import STARS_SUBSCRIPTION_PERIOD, RenewalState, StarsCharge, StarsSubscription, SubscriptionEventRejected

paid_at = 1_790_000_000  # Message.date of the successful_payment service message
charge = {'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:7', 'telegram_payment_charge_id': 'fixture-charge',
          'subscription_expiration_date': paid_at + STARS_SUBSCRIPTION_PERIOD, 'is_recurring': True, 'is_first_recurring': True}
sub = StarsSubscription(user_id=7, invoice_payload='pro:7').record_payment(charge, user_id=7, paid_at=paid_at)
assert sub.has_access(paid_at) and sub.access_until(paid_at) == paid_at + STARS_SUBSCRIPTION_PERIOD
assert sub.record_payment(charge, user_id=7, paid_at=paid_at) is sub  # a repeated charge extends nothing
canceled = sub.record_update({'user': {'id': 7}, 'invoice_payload': 'pro:7', 'state': 'canceled'})  # BotSubscriptionUpdated
assert canceled.has_access(paid_at + 1) and not canceled.renews(paid_at + 1)  # the paid month stays
renewal: RenewalState = canceled.renewal
first: StarsCharge = canceled.charges[0]
assert renewal == 'canceled' and first.first and first.amount == 250
refunded = sub.record_refund({'currency': 'XTR', 'invoice_payload': 'pro:7', 'telegram_payment_charge_id': 'fixture-charge'}, user_id=7)
assert not refunded.has_access(paid_at + 1)
try:
    sub.record_update({'user': {'id': 8}, 'invoice_payload': 'pro:7', 'state': 'failed'})
except SubscriptionEventRejected:
    pass  # another user's event changes nothing
else:
    raise AssertionError('Foreign subscription event accepted')
assert StarsSubscription.from_dict(json.loads(json.dumps(sub.as_dict()))) == sub  # the host stores this JSON
print(json.dumps({'case': 'core_stars_subscription', 'passed': True, 'network': False}))
```

<a id="ref-core_texts"></a>

## Тексты компонентов: русский, английский и замена строк — ref.core_texts

Файл: `core_texts.py`. Символы: `Texts`, `TextLocale`, `default_texts`

Границы: Каталог содержит фразы, которые видит пользователь бота: шаги и ошибки форм, навигация, составной выбор, календарь, пагинация, публичные сообщения об ошибках, подпись документа в rich-fallback. Сообщения CLI, doctor и шаблонов starter адресованы разработчику и остаются русскими. Замена обязана сохранить плейсхолдеры исходной фразы, значения вставляются как обычный текст. Язык выбирает проект: один Texts на язык, переданный компоненту; автоматического определения по language_code нет.

```python
"""SDK-free component texts: English catalog, one replaced phrase, a localized selection and error report; no network."""
import json
from telegram_patterns import (SelectionContext, SelectionMenu, SelectionOption, SelectionSpec, TextLocale, Texts,
                               ValidationFailure, default_texts, safe_error_report, selection_markup)

locale: TextLocale = 'en'  # the project picks the language; nothing is guessed from language_code
texts = Texts(locale, {'selection.cancel': 'Never mind'})  # one Texts per user language, built once at startup
assert texts('form.step', number=1, total=3, prompt='Your name?') == 'Step 1/3. Your name?\n/back — go back · /cancel — cancel'
assert set(default_texts('ru')) == set(default_texts('en'))  # every key exists in both locales
try:
    Texts('en', {'form.step': 'Next question'})  # drops {number}, {total} and {prompt}
except ValidationFailure:
    pass  # a broken translation fails at startup, not in a user's chat
else:
    raise AssertionError('Override without placeholders accepted')
menu = SelectionMenu(SelectionSpec([SelectionOption('tea', 'Tea')], texts=texts), SelectionContext(100, 7, 7, 1))
assert menu.state.text() == 'Choose options.\nSelected: nothing\nQuantity: 1\nFilter: All'
assert selection_markup(menu.state)['inline_keyboard'][-1][-1]['text'] == 'Never mind'
assert safe_error_report(ValidationFailure('detail'), texts=texts).message == 'Check the input data.'
# aiogram routers take the same object: text_form_router(..., texts=texts), dialog_form_router(..., texts=texts).
print(json.dumps({'case': 'core_texts', 'passed': True, 'network': False}))
```

<a id="ref-core_markup"></a>

## Клавиатуры как JSON для любого SDK — ref.core_markup

Файл: `core_markup.py`. Символы: `inline_button`, `reply_button`, `layout_rows`, `inline_markup`, `reply_markup`, `force_reply_markup`, `remove_markup`, `paginated_markup`, `MarkupPage`, `markup_page_number`, `selection_markup`

Границы: Ядро без SDK строит reply_markup в формате Bot API JSON с теми же проверками, что и aiogram-адаптер: одно действие на inline-кнопку, callback_data 1–64 байта UTF-8, HTTPS Mini App только в обычном личном чате, 1–8 кнопок в ряду и до 100 кнопок, иконка custom emoji только с подтвержденным entitlement. JSON совпадает с выводом telegram_patterns.aiogram; aiogram превращает его в модели через model_validate, python-telegram-bot — через telegram_patterns.ptb.ptb_markup. Права, авторизацию callback и разбор нажатий делает приложение.

```python
"""SDK-free keyboards as Bot API JSON: the same reply_markup for aiogram, python-telegram-bot or raw HTTP; no network."""
import json
from telegram_patterns import (MarkupPage, SelectionContext, SelectionMenu, SelectionOption, SelectionSpec, ValidationFailure,
                               force_reply_markup, inline_button, inline_markup, layout_rows, markup_page_number, paginated_markup,
                               remove_markup, reply_button, reply_markup, selection_markup)

buttons = [inline_button(name, callback_data=f'menu:{key}') for name, key in [('Каталог', 'catalog'), ('Помощь', 'help'), ('Назад', 'back')]]
menu = inline_markup(layout_rows(buttons, (2,)))
assert menu == {'inline_keyboard': [[{'text': 'Каталог', 'callback_data': 'menu:catalog'}, {'text': 'Помощь', 'callback_data': 'menu:help'}],
                                    [{'text': 'Назад', 'callback_data': 'menu:back'}]]}
icon = inline_button('Готово', callback_data='ok', icon_custom_emoji_id='5368324170671202286')
assert 'icon_custom_emoji_id' not in inline_markup([[icon]])['inline_keyboard'][0][0]  # no verified entitlement: text only
ask = reply_markup([[reply_button('Отправить контакт', request_contact=True)], ['Отмена']], one_time=True)
assert ask['keyboard'][0][0] == {'text': 'Отправить контакт', 'request_contact': True}
assert force_reply_markup('Ваше имя')['force_reply'] is True and remove_markup() == {'remove_keyboard': True, 'selective': False}
try:
    inline_markup([[inline_button('Приложение', web_app='https://example.com/app')]], chat_type='group')
except ValidationFailure:
    pass  # Mini App buttons need an ordinary private chat
else:
    raise AssertionError('Web App button accepted in a group')
page: MarkupPage = paginated_markup([(f'Товар {n}', f'item-{n}') for n in range(1, 8)], page=1, page_size=3)
assert (page.page, page.page_count) == (1, 3) and page.markup['inline_keyboard'][-1][1] == {'text': 'Далее →', 'callback_data': 'page:2'}
assert markup_page_number('page:2') == 2 and markup_page_number('page:../2') is None
draft = SelectionMenu(SelectionSpec([SelectionOption('a', 'Alpha'), SelectionOption('b', 'Beta')], max_selected=1),
                      SelectionContext(100, 7, 7, 50))
assert selection_markup(draft.state)['inline_keyboard'][0][0]['text'] == '□ Alpha'  # the same rows as selection_keyboard
print(json.dumps({'case': 'core_markup', 'passed': True, 'network': False}))
```

<a id="ref-core_storage"></a>

## Локальная операция SQLite и повтор — ref.core_storage

Файл: `core_storage.py`. Символы: `OnceResult`, `OperationConflict`, `SQLiteOnce`, `OnceStore`

Границы: Сервер задает область действия, автора и источник события. `run_guarded` проверяет текущие права до операции и повтора в одной транзакции записи; ревизия проверяется для новой операции. Атомарность относится только к переданному соединению SQLite: без HTTP, другого хранилища и управления транзакцией из обработчика. Файл, миграции и хранение истории принадлежат приложению.

```python
"""SQLite effect/replay; scope/ACL здесь заранее выбраны для публичной fixture."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from telegram_patterns import OnceResult, OnceStore, OperationConflict, SQLiteOnce

with TemporaryDirectory() as folder:
    path = Path(folder) / 'fixture.sqlite'
    concrete = SQLiteOnce(path)
    store: OnceStore[sqlite3.Connection] = concrete
    store.initialize()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE entries(label TEXT)')
        db.execute('CREATE TABLE access(actor INTEGER PRIMARY KEY, allowed INTEGER)')
        db.execute('INSERT INTO access VALUES (42, 1)')
    def apply(transaction: sqlite3.Connection) -> dict[str, str]:
        transaction.execute('INSERT INTO entries VALUES (?)', ('public-fixture',))
        return {'status': 'recorded'}
    result: OnceResult = store.run('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply)
    replay = store.run('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply)
    assert result.value == replay.value and not result.replayed and replay.replayed
    def check(transaction: sqlite3.Connection, replayed: bool) -> bool:
        # Actor is server-validated; replay still checks CURRENT access in the writer transaction.
        return transaction.execute('SELECT allowed FROM access WHERE actor=42').fetchone()[0] == 1
    guarded = concrete.run_guarded('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply, check=check)
    assert guarded.replayed and guarded.value == result.value
    try:
        store.run('fixture-actor:42', 'operation-1', {'label': 'changed'}, apply)
    except OperationConflict:
        pass
    else:
        raise AssertionError('Changed payload accepted')
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == 1
# HTTP/другой connection не входят в эту транзакцию; авторизация до replay.
print(json.dumps({'passed': True, 'case': 'core_storage', 'network': False}))
```

<a id="ref-core_delivery"></a>

## Надежный прием событий и владение обработкой — ref.core_delivery

Файл: `core_delivery.py`. Символы: `SQLiteInbox`, `InboxState`, `InboxReason`, `InboxReceipt`, `InboxClaim`, `InboxRecord`, `InboxConflict`, `InboxLeaseLost`, `WebhookReceiver`, `WebhookResponse`, `WebhookCode`, `create_aiohttp_webhook_app`

Границы: Прием, повторы и карантин хранятся в SQLite без обязательного SDK. Схема inbox 2 атомарно обновляет схему 1, сохраняя события и leases. `priority` выбирает полосу; `priorities=None` сохраняет прежний FIFO всех полос, явный tuple ограничивает отбор. Дубль сохраняет первую полосу и время приема. Фоновый обработчик проверяет семантику события и обеспечивает идемпотентность бизнес-операции. Внутренняя `payload_version` не является версией Bot API. Необязательный HTTP-адаптер требует установки aiohttp приложением; тесты используют локальный сервер. Схема, срок хранения, TLS, workers, deadline, остановка и ручной перезапуск событий принадлежат приложению. Единственная внешняя доставка и срок ответа Telegram не гарантируются.

```python
"""SDK-free receipt, replay, quarantine and fenced processing; no Telegram HTTP."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_patterns import (
    InboxClaim,
    InboxConflict,
    InboxLeaseLost,
    InboxReason,
    InboxReceipt,
    InboxRecord,
    InboxState,
    SQLiteInbox,
    WebhookCode,
    WebhookReceiver,
    WebhookResponse,
    create_aiohttp_webhook_app,
)

with TemporaryDirectory() as directory:
    inbox = SQLiteInbox(Path(directory) / 'delivery.sqlite')
    inbox.initialize()
    receiver = WebhookReceiver(inbox, bot_id=100, secret_token='fixture_only')
    response: WebhookResponse = receiver.receive(b'{"update_id":1,"message":{}}', 'fixture_only')
    code: WebhookCode = response.code
    assert code == 'accepted' and response.accepted
    receipt: InboxReceipt = inbox.receive(100, 1, {'update_id': 1, 'message': {}})
    assert receipt.duplicate
    try:
        inbox.receive(100, 1, {'update_id': 1, 'message': {'text': 'different'}})
    except InboxConflict:
        pass
    else:
        raise AssertionError('Changed payload accepted')
    first = inbox.claim(100, 'worker-one', lease_seconds=1, now=10)
    # received_at defaults to real UTC, so this synthetic clock is intentionally too early.
    assert first is None
    fresh = inbox.receive(100, 2, {'update_id': 2, 'message': {}}, now=10)
    assert fresh.state == 'pending'
    claimed = inbox.claim(100, 'worker-one', lease_seconds=1, now=10)
    assert isinstance(claimed, InboxClaim)
    replacement = inbox.claim(100, 'worker-two', now=11)
    assert replacement is not None and replacement.attempt == 2
    try:
        inbox.complete(claimed, now=11)
    except InboxLeaseLost:
        pass
    else:
        raise AssertionError('Expired worker completed the event')
    # A real worker would SDK-decode; this minimal fixture models a controlled decode failure.
    reason: InboxReason = 'decode-failed'
    inbox.quarantine(replacement, reason=reason, now=11)
    record = inbox.get(100, 2)
    assert isinstance(record, InboxRecord)
    state: InboxState = record.state
    assert state == 'quarantined' and record.reason == reason
    # An explicit lane can serve urgent work while the normal lane stays pending.
    inbox.receive(100, 3, {'update_id': 3, 'message': {}}, now=12)
    urgent = inbox.receive(100, 4, {'update_id': 4, 'pre_checkout_query': {}}, priority=1, now=13)
    assert urgent.priority == 1
    duplicate = inbox.receive(100, 4, {'update_id': 4, 'pre_checkout_query': {}}, priority=0, now=900)
    stored = inbox.get(100, 4)
    assert duplicate.duplicate and duplicate.priority == 1
    assert stored is not None and stored.priority == 1 and stored.received_at == 13
    urgent_claim = inbox.claim(100, 'urgent-worker', priorities=(1,), now=14)
    assert urgent_claim is not None and urgent_claim.update_id == 4
    inbox.complete(urgent_claim, now=14)
    normal_claim = inbox.claim(100, 'normal-worker', priorities=(0,), now=14)
    assert normal_claim is not None and normal_claim.update_id == 3
    inbox.complete(normal_claim, now=14)
    # Default selection remains FIFO across all lanes, without numeric priority sorting.
    inbox.receive(100, 5, {'update_id': 5, 'message': {}}, now=15)
    inbox.receive(100, 6, {'update_id': 6, 'pre_checkout_query': {}}, priority=255, now=16)
    fifo = inbox.claim(100, 'default-worker', now=17)
    assert fifo is not None and fifo.update_id == 5
    inbox.complete(fifo, now=17)
    # Optional adapter is importable without aiohttp; actual HTTP belongs to separate extra consumer tests.
    assert callable(create_aiohttp_webhook_app)
print(json.dumps({'passed': True, 'case': 'core_delivery', 'network': False}))
```

<a id="ref-core_errors"></a>

## Безопасные ошибки и восстановление — ref.core_errors

Файл: `core_errors.py`. Символы: `PatternError`, `ValidationFailure`, `InvalidType`, `AuthenticationRequired`, `PermissionDenied`, `UnsupportedCapability`, `ConflictFailure`, `TimeoutFailure`, `TransportFailure`, `UnknownOutcome`, `InvalidCompletion`, `safe_error_report`, `ErrorReport`, `ErrorCategory`, `ErrorCode`, `ErrorOutcome`, `RecoveryAction`, `OperationKind`

Границы: Передавайте реальный operation kind. Report не копирует developer text и не делает retry. Timeout/cancel/невалидный feedback после возможной записи оставляют unknown outcome и требуют сверки той же операции; локальный отказ должен произойти до эффекта.

```python
"""Классификация без сериализации текста исключения и без повторной записи."""
import json
from telegram_patterns import (
    AuthenticationRequired, ConflictFailure, ErrorCategory, ErrorCode, ErrorOutcome,
    ErrorReport, InvalidCompletion, InvalidType, OperationKind, PatternError,
    PermissionDenied, RecoveryAction, TimeoutFailure, TransportFailure, UnknownOutcome,
    UnsupportedCapability, ValidationFailure, safe_error_report,
)

operation: OperationKind = 'write'
errors = [PatternError('PRIVATE_FIXTURE'), ValidationFailure('PRIVATE_FIXTURE'),
          InvalidType('PRIVATE_FIXTURE'), AuthenticationRequired('PRIVATE_FIXTURE'),
          PermissionDenied('PRIVATE_FIXTURE'), UnsupportedCapability('PRIVATE_FIXTURE'),
          ConflictFailure('PRIVATE_FIXTURE'), TimeoutFailure('PRIVATE_FIXTURE'),
          TransportFailure('PRIVATE_FIXTURE'), UnknownOutcome('PRIVATE_FIXTURE'),
          InvalidCompletion('PRIVATE_FIXTURE')]
for error in errors:
    value: ErrorReport = error.report(operation=operation)
    category: ErrorCategory = value.category
    code: ErrorCode = value.code
    outcome: ErrorOutcome = value.outcome
    recovery: RecoveryAction = value.recovery
    assert value == safe_error_report(error, operation=operation)
    assert category and code and recovery and 'PRIVATE_FIXTURE' not in json.dumps(value.as_dict())
    if outcome == 'unknown': assert recovery == 'reconcile'
assert safe_error_report(ValidationFailure(), operation=operation).outcome == 'rejected'
assert safe_error_report(InvalidCompletion(), operation=operation).outcome == 'unknown'
print(json.dumps({'passed': True, 'case': 'core_errors', 'network': False}))
```

<a id="ref-core_extensions"></a>

## Transport и provider интерфейсы проекта — ref.core_extensions

Файл: `core_extensions.py`. Символы: `AsyncTransport`, `ProviderAdapter`, `RefundProvider`

Границы: Структурные Protocol не создают ресурсы и не обещают provider idempotency. Fixture отвергает все события; реальный adapter проверяет официальный wire/auth contract. Signed event не означает оплату/доступ, refund — отдельная операция.

```python
"""Структурные интерфейсы; модель fixture не является платежным протоколом."""
import asyncio
import json
from typing import Mapping
from telegram_patterns import AsyncTransport, ProviderAdapter, RefundProvider

class LocalTransport:
    async def send(self, request: str) -> str:
        return request

class FixtureProvider:
    def __init__(self, transport: AsyncTransport[str, str]): self.transport = transport
    async def create(self, request: str, *, operation_id: str) -> str:
        return await self.transport.send('fixture:' + operation_id)
    async def get(self, provider_id: str) -> str:
        return await self.transport.send(provider_id)
    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> str | None:
        # Проверяемый отказ без выдуманной подписи/доверия к внешнему событию.
        return None
    async def refund(self, request: str, *, operation_id: str) -> str:
        return await self.transport.send('fixture-refund:' + operation_id)

async def main() -> None:
    transport: AsyncTransport[str, str] = LocalTransport()
    implementation = FixtureProvider(transport)
    provider: ProviderAdapter[str, str, str] = implementation
    refunds: RefundProvider[str, str] = implementation
    invoice = await provider.create('public-product', operation_id='server-operation-1')
    assert await provider.get(invoice) == invoice
    assert provider.verify_event(b'untrusted', {}) is None
    assert await refunds.refund(invoice, operation_id='server-refund-1') == 'fixture-refund:server-refund-1'
    # Нет remote effect, provider idempotency, оплаты или выдачи доступа.
    print(json.dumps({'passed': True, 'case': 'core_extensions', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
```

<a id="ref-core_recipes"></a>

## Поиск в поставляемом cookbook — ref.core_recipes

Файл: `core_recipes.py`. Символы: `Maturity`, `VerificationLevel`, `Recipe`, `RecipeCatalog`

Границы: Чтение не исполняет recipe code. Maturity отдельно от verification; SDK/mock не доказывают live/device. Preview — независимая копия. Этот пример ищет существующий cookbook recipe two-columns; ref.* — имена справочника API.

```python
"""Только поиск и чтение; найденный код здесь не исполняется."""
import json
from telegram_patterns import Maturity, VerificationLevel, Recipe, RecipeCatalog

maturity: Maturity = 'experimental'
verification: VerificationLevel = 'sdk'
catalog = RecipeCatalog()
recipe: Recipe = catalog.search('две кнопки', maturity=maturity, verification=verification,
                               task='keyboards', context='private', sdk='aiogram', sdk_version='3.31.0', api_version='bot:10.3')[0]
assert recipe.id == 'two-columns' and catalog.get(recipe.id) == recipe
assert len(catalog.recipes) == 340 and catalog.library_version
assert recipe.source_files and recipe.check_files and 'keyboards' in recipe.tasks
lost = catalog.search('потерянный ответ', task='recovery', context='backend')[0]
assert lost.id == 'demo-recovery' and lost.sdk == 'python-core' and lost.api_version == 'none'
preview = recipe.preview
assert preview is not None and [len(row) for row in preview['inline_keyboard']] == [2, 2]
preview['inline_keyboard'][0][0]['text'] = 'local-copy'
assert catalog.get(recipe.id).preview != preview
# SDK evidence не делает API stable и не доказывает appearance в Telegram.
print(json.dumps({'passed': True, 'case': 'core_recipes', 'network': False}))
```

<a id="ref-core_execution"></a>

## Требования и явная offline проверка — ref.core_execution

Файл: `core_execution.py`. Символы: `RecipeRunPlan`, `RecipeRunResult`, `plan_recipe`, `run_recipe_offline`

Границы: Только установленный доверенный wheel и закрытые fixtures. Plan не читает secret values. Runner не исполняет recipe.code/приложение; native references отказывает до child. Python -I/-B, системный env allowlist, временный cwd; это не OS sandbox. Нет live rights/auth/device acceptance.

```python
"""План перед запуском; установленный core wheel, без SDK и Telegram."""
import json
from telegram_patterns import RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline

plan: RecipeRunPlan = plan_recipe('demo-recovery')
assert plan.offline_ready and plan.kind == 'sqlite'
assert not plan.offline_environment and not plan.offline_permissions
assert plan.live_data and plan.live_permissions and plan.sources
result: RecipeRunResult = run_recipe_offline(plan.recipe_id)
assert result.passed and not result.telegram_requests
assert result.checks == ('sqlite-one-effect', 'same-key-replay')
reference = plan_recipe('native.requestContact')
assert not reference.offline_ready and reference.live_permissions
print(json.dumps({'passed': True, 'case': 'core_execution', 'network': False}))
```

<a id="ref-core_starter"></a>

## Новый проект из предоставленного wheel — ref.core_starter

Файл: `core_starter.py`. Символы: `StarterPlan`, `StarterComponent`, `StarterConflict`, `starter_components`, `create_starter`

Границы: Дополнительный аргумент — путь к предоставленному wheel, не имя в registry. Только новый target и существующий parent; dry-run без записи, repeat сохраняет код. Closed starter registry не заменяет host backend/auth; I/O failure может оставить partial new files.

```python
"""Предоставленный wheel передается явно; генерируем только новый temp target."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from telegram_patterns import StarterPlan, StarterComponent, StarterConflict, starter_components, create_starter

wheel = Path(sys.argv[1]).resolve(strict=True)
component: StarterComponent = next(c for c in starter_components('bot') if c.id == 'text-form')
assert component.min_library_version == '0.8.0'
with TemporaryDirectory() as folder:
    target = Path(folder) / 'new bot'
    plan: StarterPlan = create_starter(target, library=wheel, components=['text-form'], dry_run=True)
    assert not target.exists() and not plan.created and 'starter_form.py' in plan.files
    created = create_starter(target, library=wheel, components=['text-form'])
    assert created.created and created.files == plan.files and component.id in created.components
    before = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    try: create_starter(target, library=wheel)
    except FileExistsError: pass
    else: raise AssertionError('Existing project overwritten')
    assert before == {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    try: create_starter(Path(folder) / 'invalid', library=wheel, components=['api-client'])
    except StarterConflict as error: assert error.reason == 'component-template'
    else: raise AssertionError('Incompatible selection accepted')
print(json.dumps({'passed': True, 'case': 'core_starter', 'network': False}))
```

<a id="ref-core_doctor"></a>

## Read-only diagnosis в SDK-free окружении — ref.core_doctor

Файл: `core_doctor.py`. Символы: `doctor`

Границы: Пример намеренно запускается без aiogram: readiness fail содержит команды следующего явного действия. Без webhook=True doctor не читает .env, не обращается к сети и не подтверждает live identity; webhook=True делает один read-only getWebhookInfo с BOT_TOKEN из окружения или .env проекта. Предлагаемые repairs не выполняются, token не попадает в отчет. SDK probe установленного extra изолирован от проекта.

```python
"""Doctor запускается SDK-free: диагностика readiness, не автоматический install."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from telegram_patterns.cli import doctor

with TemporaryDirectory() as folder:
    project = Path(folder)
    (project / 'pyproject.toml').write_text('[project]\nname="fixture"\n', encoding='utf-8')
    (project / '.env').write_text('BOT_TOKEN=PRIVATE_FIXTURE', encoding='utf-8')
    before = {p.name: p.read_bytes() for p in project.iterdir()}
    report = doctor(project)
    checks = {check['name']: check for check in report['checks']}
    assert checks['aiogram']['reason'] == 'sdk-missing'
    assert not report['passed'] and not report['network'] and not report['suggestions_executed']
    assert checks['aiogram']['remediation']['commands'] and 'PRIVATE_FIXTURE' not in json.dumps(report)
    assert before == {p.name: p.read_bytes() for p in project.iterdir()}
print(json.dumps({'passed': True, 'case': 'core_doctor', 'network': False}))
```

<a id="ref-core_selection"></a>

## Серверные значения и подтверждение выбора — ref.core_selection

Файл: `core_selection.py`. Символы: `SelectionOption`, `SelectionSpec`, `SelectionContext`, `SelectionState`, `SelectionResult`, `SelectionMenu`

Границы: Черновик на сервере в одном процессе; точные проверки владельца, контекста, ревизии и токена подтверждения. Бизнес-операция, долговременное хранение и работа нескольких процессов не гарантируются. Текущие права, `resource_version` и идемпотентная транзакция принадлежат приложению; синтетический транспорт не доказывает доставку и отображение в Telegram.

```python
"""SDK-free server draft: configured values, revisions and bound confirmation."""
from dataclasses import replace
import json
from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionResult, SelectionSpec, SelectionState

context = SelectionContext(100, 42, 42, 100)
rules = SelectionSpec([SelectionOption('a', 'Alpha', ['basic']), SelectionOption('b', 'Beta')],
                      toggles={'notify':'Уведомлять'}, filters={'all':'Все','basic':'Основные'},
                      quantity_min=1, quantity_max=3, min_selected=1, max_selected=2)
menu = SelectionMenu(rules, context)
initial: SelectionState = menu.state
denied: SelectionResult = menu.apply(initial.callback('s:a'), replace(context, owner_id=43))
assert denied.status == 'denied' and denied.state is None and menu.state is initial
assert menu.apply(initial.callback('s:a'), context).status == 'accepted'
assert menu.apply(initial.callback('s:a'), context).status == 'stale'
for action in ('s:b','t:notify','q:inc','f:basic','ask'):
    assert menu.apply(menu.state.callback(action), context).status in {'accepted','confirming'}
pending = menu.state
assert pending.confirmation_id is not None
old_confirmation = pending.callback('y:' + pending.confirmation_id)
menu.replace_spec(replace(rules, resource_version='2'))
assert menu.apply(old_confirmation, context).status == 'stale'
assert menu.state.selected == ('a','b')
assert menu.apply(menu.state.callback('ask'), context).status == 'confirming'
pending = menu.state
assert pending.confirmation_id is not None
data = pending.callback('y:' + pending.confirmation_id)
result = menu.apply(data, context)
assert result.status == 'confirmed' and result.state is not None and result.state.operation_id is not None
assert result.state.spec.resource_version == '2'
assert menu.apply(data, context).status == 'stale'
print(json.dumps({'passed':True,'case':'core_selection','network':False,'business_effects':0}))
```

<a id="ref-core_calendar"></a>

## Календарь, время и транзакционная запись — ref.core_calendar

Файл: `core_calendar.py`. Символы: `CalendarMonth`, `TimeSlot`, `resolve_local_time`, `SlotSchedule`, `SlotBooking`, `SQLiteSlotStore`

Границы: Без SDK; для Europe/Warsaw нужна база IANA приложения или необязательный extra calendar (проверено с tzdata 2026.5). Текущие права приложения проверяются синхронно внутри транзакции файловой SQLite до эффекта или повтора. Публикация расписания — доверенное приложению сравнение с заменой (CAS); неизменяемая квитанция отличается от текущей записи; внешних побочных эффектов нет. Файл, миграции, срок хранения и асинхронное завершение работы принадлежат приложению.

```python
"""SDK-free calendar, explicit DST choice, transaction and current booking."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from telegram_patterns import CalendarMonth, TimeSlot, resolve_local_time, SlotSchedule, SlotBooking, SQLiteSlotStore

month = CalendarMonth(2026, 10, 'Europe/Warsaw', [date(2026, 10, 25)])
assert month.allows(date(2026, 10, 25))
early = resolve_local_time(datetime(2026, 10, 25, 2, 30), 'Europe/Warsaw', fold=0)
late = resolve_local_time(datetime(2026, 10, 25, 2, 30), 'Europe/Warsaw', fold=1)
assert late - early == timedelta(hours=1)
slot = TimeSlot('early', early, early + timedelta(minutes=15))
with TemporaryDirectory(prefix='calendar public api ') as temporary:
    store = SQLiteSlotStore(Path(temporary) / 'slots.sqlite3',
                            authorize=lambda connection, actor, resource: actor == 42 and resource == 'room')
    store.initialize()
    schedule = store.publish('room', [slot], expected_revision=0)
    assert isinstance(schedule, SlotSchedule)
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    receipt = store.reserve('room', 'early', actor_id=42, expected_revision=schedule.revision, operation_id='public-example', now=now)
    replay = store.reserve('room', 'early', actor_id=42, expected_revision=schedule.revision, operation_id='public-example', now=now)
    assert replay.replayed and replay.value == receipt.value
    booking = store.booking('room', receipt.value['booking_id'], actor_id=42)
    assert isinstance(booking, SlotBooking) and booking.status == 'active'
print(json.dumps({'passed': True, 'case': 'core_calendar', 'network': False,
                  'business_effects': 1, 'replayed': replay.replayed}))
```

<a id="ref-core_outbox"></a>

## Транзакционная очередь отправки и сверка — ref.core_outbox

Файл: `core_outbox.py`. Символы: `SQLiteOutbox`, `OutboxState`, `OutboxResolution`, `OutboxReceipt`, `OutboxClaim`, `OutboxRecord`, `OutboxConflict`, `OutboxLeaseLost`

Границы: `enqueue` требует активную транзакцию переданного соединения той же основной БД SQLite и сам ее не завершает. Перед внешним вызовом фиксируется `sending`; истекшая попытка становится `unknown` без автоматического повтора. Решение `absent` требует доказательства отсутствия эффекта и позднего результата, проверки ревизии и `evidence_ref`. Отправка, права, запрос статуса провайдера и хранение истории принадлежат приложению.

```python
"""Business + intent commit together; an expired sending lease never authorizes a new send."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from telegram_patterns import (
    OutboxClaim, OutboxConflict, OutboxLeaseLost, OutboxReceipt, OutboxRecord,
    OutboxResolution, OutboxState, SQLiteOutbox,
)

with TemporaryDirectory() as directory:
    path = Path(directory) / 'business.sqlite'
    outbox = SQLiteOutbox(path)
    outbox.initialize()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE orders(id TEXT PRIMARY KEY)')
        db.execute('INSERT INTO orders VALUES (?)', ('server-intent',))
        receipt: OutboxReceipt = outbox.enqueue(db, 'bot:100', 'server-intent', {'order': 'server-intent'}, now=10)
    assert not receipt.duplicate and receipt.state == 'pending'
    claimed = outbox.claim('bot:100', 'worker', lease_seconds=1, now=10)
    assert isinstance(claimed, OutboxClaim)
    # A crashed sender may have already delivered. Simulate lease expiry, not proof of absence.
    assert outbox.recover_expired('bot:100', now=11) == 1
    assert outbox.claim('bot:100', 'new-worker', now=11) is None
    try:
        outbox.confirm(claimed, {'message_id': 1}, now=11)
    except OutboxLeaseLost:
        pass
    else:
        raise AssertionError('Expired sender confirmed a receipt')
    observed = outbox.get('bot:100', 'server-intent')
    assert isinstance(observed, OutboxRecord)
    state: OutboxState = observed.state
    assert state == 'unknown'
    resolution: OutboxResolution = 'sent'
    # Host has independently verified this fake provider receipt before reconciliation.
    final = outbox.reconcile('bot:100', 'server-intent', expected_revision=observed.revision,
                             outcome=resolution, evidence_ref='verified-fake-receipt', result={'message_id': 1}, now=11)
    assert final.state == 'sent'
    try:
        outbox.reconcile('bot:100', 'server-intent', expected_revision=observed.revision,
                         outcome='absent', evidence_ref='stale-review', now=11)
    except OutboxConflict:
        pass
    else:
        raise AssertionError('Stale reconciliation changed the completed send')
print(json.dumps({'passed': True, 'case': 'core_outbox', 'network': False}))
```

<a id="ref-core_jobs"></a>

## Сохраненные задания и управляемые уведомления — ref.core_jobs

Файл: `core_jobs.py`. Символы: `SQLiteJobQueue`, `JobState`, `JobOutcome`, `JobReason`, `JobClaim`, `JobRecord`, `JobConflict`, `JobLeaseLost`, `JobQueueFull`

Границы: `schedule` и бизнес-запись выполняются в разных транзакциях; для общей записи нужен outbox. Без настроек получателя доставка запрещена. Только переход `start` в `sending` разрешает внешний вызов после повторной проверки согласия, срока, владения и ограничений частоты. Сбой после начала оставляет `unknown`; отмена не отзывает удаленный запрос. Повтор после HTTP 429 допустим только при подтвержденном отказе без эффекта. Настройки, задержки и попытки сохраняются; отправка, права и хранение истории принадлежат приложению.

```python
"""Persisted recipient consent, pacing, cancellation and no automatic retry of unknown delivery."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_patterns import (
    JobClaim, JobConflict, JobLeaseLost, JobOutcome, JobQueueFull, JobReason,
    JobRecord, JobState, SQLiteJobQueue,
)

with TemporaryDirectory() as directory:
    queue = SQLiteJobQueue(Path(directory) / 'jobs.sqlite', max_active_jobs=1)
    queue.initialize()
    queue.set_recipient(100, 42, subscribed=True, reachable=True)
    queued: JobRecord = queue.schedule(100, 'reminder-one', 42, {'order': 'one'}, due_at=10, deadline_at=100, now=10)
    state: JobState = queued.state
    assert state == 'scheduled'
    try:
        queue.schedule(100, 'reminder-two', 42, {}, due_at=10, deadline_at=100, now=10)
    except JobQueueFull:
        pass
    else:
        raise AssertionError('Queue capacity was ignored')
    claimed = queue.claim(100, 'worker', now=10)
    assert isinstance(claimed, JobClaim)
    sending = queue.start(claimed, now=10)
    assert sending.state == 'sending'  # Only this state authorizes host transport.
    outcome: JobOutcome = 'unknown'
    unknown = queue.finish(claimed, outcome=outcome, now=11)
    reason: JobReason | None = unknown.reason
    assert unknown.state == 'unknown' and reason == 'send-outcome-unknown'
    assert queue.claim(100, 'other-worker', now=20) is None
    try:
        queue.finish(claimed, outcome='sent', message_id=1, now=12)
    except JobLeaseLost:
        pass
    else:
        raise AssertionError('Old sender changed unknown delivery')
    final = queue.reconcile(100, 'reminder-one', expected_revision=unknown.revision,
                             evidence_ref='verified-fake-receipt', outcome='sent', message_id=1)
    assert final.state == 'sent'
    try:
        queue.reconcile(100, 'reminder-one', expected_revision=unknown.revision,
                         evidence_ref='stale-review', outcome='failed')
    except JobConflict:
        pass
    else:
        raise AssertionError('Stale reconciliation changed delivery')
print(json.dumps({'passed': True, 'case': 'core_jobs', 'network': False}))
```

<a id="ref-core_worker"></a>

## Остановка обработчика и безопасная корреляция — ref.core_worker

Файл: `core_worker.py`. Символы: `InboxWorker`, `WorkerOutcome`, `settled_to_thread`, `Telemetry`, `TelemetryContext`, `TelemetryMetric`, `TelemetrySnapshot`, `TelemetryStage`, `TelemetryOutcome`

Границы: Композиция сохраненных входящих событий без обязательного SDK. Приложение декодирует данные, обрабатывает событие, задает устойчивые идентификаторы операций и закрывает сессию после завершения работы. Только `True` подтверждает сохраненный бизнес-результат. Отмена не останавливает поток SQLite: `settled_to_thread` дожидается его завершения. Ошибки обработки сохраняются в карантине; потеря владения требует сверки. Метрики используют фиксированные поля и метки, без сообщений, токенов, `initData` и текста исключений. HMAC-ссылки не авторизуют и не анонимизируют. Быстрый синхронный приемник событий принадлежит приложению; скрытой очереди нет.

```python
"""Owned worker drain and safe correlation; no Telegram, external sender or background service."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from telegram_patterns import (
    InboxWorker, WorkerOutcome, settled_to_thread, SQLiteInbox,
    Telemetry, TelemetryContext, TelemetryMetric, TelemetryOutcome, TelemetrySnapshot, TelemetryStage,
)


async def main() -> None:
    events: list[str] = []
    telemetry = Telemetry(b'local-fixture-key-with-32-bytes!!x', events.append)
    stage: TelemetryStage = 'operation'
    outcome: TelemetryOutcome = 'replayed'
    with telemetry.bind(bot_id=100, update_id=1, operation_id='server-intent') as context:
        observed: TelemetryContext = context
        assert observed.update_ref is not None and observed.operation_ref is not None
        telemetry.emit(stage, outcome, duration_ms=1, attempt=2)
    assert telemetry.current() is None and 'server-intent' not in events[0]
    snapshot: TelemetrySnapshot = telemetry.snapshot()
    metric: TelemetryMetric = snapshot.metrics[0]
    assert metric.count == 1 and metric.retries == 1
    with TemporaryDirectory() as directory:
        inbox = SQLiteInbox(Path(directory) / 'worker.sqlite')
        inbox.initialize()
        inbox.receive(100, 1, {'update_id': 1, 'message': {}})
        handled: list[int] = []
        def decode(payload: dict[str, Any]) -> int:
            return int(payload['update_id'])
        async def handle(update_id: int, claim: Any) -> bool:
            # Host normally commits an idempotent operation/outbox before returning exactly True.
            handled.append(update_id)
            return True
        worker = InboxWorker(inbox, 100, 'fixture-worker', decode, handle, telemetry=telemetry)
        result: WorkerOutcome = await worker.run_one()
        assert result == 'done' and handled == [1]
        stored = await settled_to_thread(inbox.get, 100, 1)
        assert stored is not None and stored.state == 'done'
        stop = asyncio.Event()
        stop.set()
        await worker.serve(stop)  # An already stopped owner does not admit work.
    print(json.dumps({'passed': True, 'case': 'core_worker', 'network': False}))


if __name__ == '__main__':
    asyncio.run(main())
```

<a id="ref-core_payments"></a>

## Точные суммы и доверенные платежные наблюдения — ref.core_payments

Файл: `core_payments.py`. Символы: `Money`, `MAX_MINOR_UNITS`, `SQLitePaymentLedger`, `PaymentRoute`, `PaymentKind`, `PaymentState`, `ProviderEventKind`, `PaymentBinding`, `ProviderEvent`, `PaymentOperation`, `PaymentClaim`, `PaymentReceipt`, `PaymentOrder`, `AccessDecision`, `PaymentCheck`, `PaymentVerifier`, `PaymentConflict`, `PaymentLeaseLost`

Границы: Только локальная SQLite и точные суммы. Verifier вызывается каждый раз вне DB и должен проверять настоящий протокол/статус провайдера; DTO и callback клиента не подтверждают оплату. Полная привязка продавца, бота, пользователя, заказа, провайдера, валюты и разрядности сверяется до финансового изменения. Возврат требует текущего ACL при резервировании и отправке, unknown сохраняет резерв. Paid/period/refund и доступ изменяются одной транзакцией с аудитом. Stars только целые XTR и полный возврат, сроки подписки задает подтвержденный charge. Host владеет транспортом, секретами, допустимостью платежного маршрута и retention. Фикстура не является live/sandbox приемкой. Схема 1 обновляется до 2 атомарно с сохранением старых receipt. Нативное продление упорядочивается в зарегистрированной эпохе; unknown RPC разрешается с проверкой ревизий операции и контроллера, без выдуманного GET настройки.

```python
"""Exact money and trusted local receipt fixture; not a real provider authentication protocol."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from telegram_patterns import (
    MAX_MINOR_UNITS, AccessDecision, Money, PaymentBinding, PaymentCheck, PaymentClaim,
    PaymentConflict, PaymentKind, PaymentLeaseLost, PaymentOperation, PaymentOrder,
    PaymentReceipt, PaymentRoute, PaymentState, PaymentVerifier, ProviderEvent,
    ProviderEventKind, SQLitePaymentLedger,
)

assert Money(MAX_MINOR_UNITS, 'USD', 2).minor_units == MAX_MINOR_UNITS
price = Money.from_decimal('10.00', 'USD', 2)
assert price.to_decimal() == '10.00' and (price - Money(1, 'USD', 2)).minor_units == 999
route: PaymentRoute = 'external'
binding = PaymentBinding('fixture-merchant', 100, 200, 'order-one', 'fictional-provider', price, route=route)
with TemporaryDirectory() as directory:
    ledger = SQLitePaymentLedger(Path(directory) / 'payments.sqlite')
    ledger.initialize()
    operation: PaymentOperation = ledger.create_order(binding, 'invoice-one', now=100)
    kind: PaymentKind = operation.kind
    state: PaymentState = operation.state
    assert kind == 'invoice' and state == 'pending'

    def current_access(db: Any, current: PaymentOperation, replayed: bool) -> bool:
        # A production check reads current operator/object ACL in this writer transaction.
        assert db.in_transaction and type(replayed) is bool
        return current.binding == binding and current.actor_id == (200 if current.kind == 'invoice' else 900)

    check: PaymentCheck = current_access
    claim: PaymentClaim = ledger.start_operation(binding, 'invoice-one', 'worker', check=check, now=100)
    assert claim.operation_id == 'invoice-one'
    events = {
        'invoice': ProviderEvent(binding, 'invoice-event', 'invoice-created', 'created', 'fixture-invoice-proof',
                                 operation_id='invoice-one', provider_ref='invoice-native'),
        'paid': ProviderEvent(binding, 'paid-event', 'paid', 'captured', 'fixture-paid-proof',
                              charge_id='charge-native', amount=price, paid_at=102),
        'refund': ProviderEvent(binding, 'refund-event', 'refunded', 'refunded', 'fixture-refund-proof',
                                operation_id='refund-one', charge_id='charge-native',
                                refund_id='refund-native', amount=price),
    }

    def trusted_fixture(raw: Any) -> ProviderEvent:
        # Only this closed local fixture maps labels to receipts. Production must verify provider auth/status.
        if not isinstance(raw, str) or raw not in events:
            raise ValueError('Unknown local fixture')
        return events[raw]

    verify: PaymentVerifier = trusted_fixture
    invoice: PaymentReceipt = ledger.apply_event('invoice', verify=verify, now=101)
    assert invoice.kind == 'invoice-created' and not ledger.has_access(binding, now=101).active
    receipt: PaymentReceipt = ledger.apply_event('paid', verify=verify, now=102)
    event_kind: ProviderEventKind = receipt.kind
    assert event_kind == 'paid'
    assert ledger.apply_event('paid', verify=verify, now=102).duplicate
    order: PaymentOrder = ledger.get_order(binding)
    access: AccessDecision = ledger.has_access(binding, now=102)
    assert order.confirmed_charges == 1 and access.active
    try:
        ledger.create_order(replace(binding, amount=Money(1001, 'USD', 2)), 'invoice-one', now=102)
    except PaymentConflict:
        pass
    else:
        raise AssertionError('Changed server binding accepted')
    ledger.request_refund(binding, 'charge-native', 'refund-one', price, 900, check=check, now=103)
    ledger.start_operation(binding, 'refund-one', 'worker', check=check, lease_seconds=1, now=103)
    # A lost sender may already have refunded remotely. Expiry alone never permits another refund.
    ledger.recover_expired(binding, now=104)
    unknown = ledger.get_operation(binding, 'refund-one')
    assert unknown.state == 'unknown'
    try:
        ledger.start_operation(binding, 'refund-one', 'other-worker', check=check, now=104)
    except PaymentLeaseLost:
        pass
    else:
        raise AssertionError('Unknown refund sent again')
    ledger.reconcile_operation('refund', verify=verify, expected_revision=unknown.revision, now=104)
    assert not ledger.has_access(binding, now=104).active
    assert ledger.get_order(binding).fully_refunded_charges == 1
print(json.dumps({'passed': True, 'case': 'core_payments', 'network': False}))
```

<a id="ref-core_providers"></a>

## Платежные адаптеры с независимой сверкой — ref.core_providers

Файл: `core_providers.py`. Символы: `CryptoPayAdapter`, `InvoiceRequest`, `PlategaAdapter`, `PlategaRefundSupport`, `ProviderHttpRequest`, `ProviderHttpResponse`, `ProviderInvoice`, `ProviderNotification`, `ProviderRateLimited`, `ProviderReadFailure`, `ProviderRefund`, `ProviderWriteUnknown`, `RefundRequest`, `YooKassaAdapter`, `YooKassaCreateOptions`, `YooKassaPeerPolicy`, `binding_reference`

Границы: SDK не требуется; внедренный HTTP-транспорт приложения отвечает за TLS, ограничения потока и секреты. Уведомление ведет к независимому запросу статуса и проверке получателя, окружения, заказа и точной суммы; DTO не подтверждает оплату. Неопределенная запись не повторяется автоматически. Host заранее сохраняет параметры, ключи и нативные ID. Crypto Pay без ID после потерянного создания требует операторской сверки; нативный возврат не выдуман. Platega не дает доверенного paid_at в проверенном контракте, поэтому событие выдачи доступа не создается. ЮKassa поддерживает только полное подтверждение. Реальные кабинеты и sandbox не проверены; цифровые товары внутри Telegram оплачиваются Stars.

```python
"""Локальные HTTP-фикстуры провайдеров: DTO и уведомление не выдают доступ."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

from telegram_patterns import (
    AsyncTransport,
    CryptoPayAdapter,
    InvoiceRequest,
    Money,
    PaymentBinding,
    PlategaAdapter,
    PlategaRefundSupport,
    ProviderHttpRequest,
    ProviderHttpResponse,
    ProviderInvoice,
    ProviderNotification,
    ProviderRateLimited,
    ProviderReadFailure,
    ProviderRefund,
    ProviderWriteUnknown,
    RefundRequest,
    YooKassaAdapter,
    YooKassaCreateOptions,
    YooKassaPeerPolicy,
    binding_reference,
)


def response(value: object, status: int = 200) -> ProviderHttpResponse:
    return ProviderHttpResponse(status, json.dumps(value).encode('utf-8'))


class FixtureHTTP:
    """Очередь ответов в памяти; каждый запрос использует публичный контракт, без сети."""

    def __init__(self, *replies: ProviderHttpResponse) -> None:
        self.replies = list(replies)
        self.requests: list[ProviderHttpRequest] = []

    async def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        assert request.url.startswith(('https://api.yookassa.ru/', 'https://testnet-pay.crypt.bot/',
                                       'https://app.platega.io/'))
        assert request.timeout_seconds <= 60 and request.max_response_bytes <= 1048576
        self.requests.append(request)
        if not self.replies:
            raise AssertionError('Unexpected local HTTP request')
        return self.replies.pop(0)


def order(provider: str) -> PaymentBinding:
    return PaymentBinding('merchant:fixture', 100, 42, 'order:fixture', provider,
                          Money(1000, 'RUB', 2), allow_partial_refunds=True)


def payment(binding: PaymentBinding, state: str) -> dict[str, Any]:
    native: dict[str, Any] = {
        'id': 'payment-fixture', 'status': state, 'paid': state != 'pending', 'test': True,
        'amount': {'value': binding.amount.to_decimal(), 'currency': binding.amount.currency},
        'recipient': {'account_id': 'shop-fixture'},
        'metadata': {'telegram_binding': binding_reference(binding, 'invoice:1'),
                     'telegram_operation': 'invoice:1'},
    }
    if state == 'succeeded':
        native['captured_at'] = '2026-11-05T12:00:00Z'
    return native


def yookassa(transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse]) -> YooKassaAdapter:
    return YooKassaAdapter(transport, merchant_id='merchant:fixture', shop_id='shop-fixture',
                          secret_key='fixture-only-not-a-secret', test=True)


async def main() -> None:
    binding = order('yookassa')
    held = payment(binding, 'waiting_for_capture')
    paid = payment(binding, 'succeeded')
    refund = {'id': 'refund-fixture', 'payment_id': 'payment-fixture', 'status': 'pending',
              'amount': {'value': '2.00', 'currency': 'RUB'}}
    local = FixtureHTTP(response(held), response(held), response(paid), response(paid),
                        response(paid), response(paid), response(refund))
    transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse] = local
    adapter = yookassa(transport)
    created: ProviderInvoice = await adapter.create(
        InvoiceRequest(binding, 'Fixture order', 'https://example.com/return'),
        operation_id='invoice:1', options=YooKassaCreateOptions(capture=False))
    assert created.native_state == 'waiting_for_capture' and created.paid_at is None
    capture_key = adapter.capture_key(binding, created.provider_id, invoice_operation_id='invoice:1',
                                      operation_id='capture:1')
    captured = await adapter.capture(binding, created.provider_id, invoice_operation_id='invoice:1',
                                     operation_id='capture:1')
    assert captured.native_state == 'succeeded' and captured.paid_at == 1793880000
    assert local.requests[2].headers['idempotence-key'] == capture_key
    trusted_observation = await adapter.payment_event(binding, created.provider_id,
                                                      invoice_operation_id='invoice:1',
                                                      evidence_ref='fixture:get-payment')
    assert trusted_observation.kind == 'paid' and trusted_observation.amount == binding.amount
    pending: ProviderRefund = await adapter.refund(
        RefundRequest(binding, created.provider_id, Money(200, 'RUB', 2), 'invoice:1'),
        operation_id='refund:1')
    assert pending.native_state == 'pending'  # Receipt acceptance is not a completed refund.
    policy = YooKassaPeerPolicy()
    assert policy.allows('185.71.76.1') and not policy.allows('127.0.0.1')
    body = json.dumps({'type': 'notification', 'event': 'payment.succeeded',
                       'object': {'id': created.provider_id, 'status': 'succeeded'}}).encode()
    hint: ProviderNotification | None = adapter.verify_notification(body, peer_ip='185.71.76.1')
    assert hint is not None and hint.provider_id == created.provider_id
    assert adapter.verify_notification(body, peer_ip='127.0.0.1') is None

    crypto_order = order('cryptopay')
    invoice = {'invoice_id': 123, 'status': 'paid', 'currency_type': 'fiat', 'fiat': 'RUB',
               'amount': '10.00', 'payload': binding_reference(crypto_order, 'invoice:1'),
               'paid_at': '2026-11-05T12:00:00Z'}
    crypto_http = FixtureHTTP(response({'ok': True, 'result': [invoice]}))
    crypto = CryptoPayAdapter(crypto_http, merchant_id=crypto_order.merchant_id, token='fixture-only-token')
    crypto_paid = await crypto.payment_event(crypto_order, '123', invoice_operation_id='invoice:1',
                                             evidence_ref='fixture:crypto-get')
    assert crypto_paid.charge_id == '123' and crypto_paid.amount == crypto_order.amount
    # Synthetic local HMAC demonstrates the wire contract, not a real provider identity.
    raw = json.dumps({'update_id': 7, 'request_date': '2026-11-05T12:00:00Z',
                      'update_type': 'invoice_paid', 'payload': invoice}).encode()
    signature = hmac.new(hashlib.sha256(b'fixture-only-token').digest(), raw, hashlib.sha256).hexdigest()
    crypto_hint = crypto.verify_event(raw, {'crypto-pay-api-signature': signature})
    assert crypto_hint is not None and crypto_hint.provider_id == '123'
    assert crypto.verify_event(raw + b' ', {'crypto-pay-api-signature': signature}) is None

    platega_order = order('platega')
    transaction = {'id': 'transaction-fixture', 'status': 'CONFIRMED', 'mechantId': 'native-merchant',
                   'paymentDetails': {'amount': 10, 'currency': 'RUB'},
                   'payload': binding_reference(platega_order, 'invoice:1')}
    platega_http = FixtureHTTP(response(transaction), response({'supported': True, 'partialSupported': True,
                                                               'totalDeductUsdt': 1, 'penaltyUsdt': 0}))
    platega = PlategaAdapter(platega_http, merchant_id=platega_order.merchant_id,
                            native_merchant_id='native-merchant', secret='fixture-only-secret', payment_method=2)
    support: PlategaRefundSupport = await platega.refund_support(
        RefundRequest(platega_order, 'transaction-fixture', Money(200, 'RUB', 2), 'invoice:1'))
    assert support.supported and support.partial_supported and support.total_deduct_usdt == 1
    # No native paid timestamp is invented to grant access from this Platega snapshot.

    limited_http = FixtureHTTP(ProviderHttpResponse(429, b'{}', {'Retry-After': '7'}))
    try:
        await yookassa(limited_http).get(created.provider_id, binding=binding, invoice_operation_id='invoice:1')
    except ProviderRateLimited as limited:
        assert limited.retry_after == 7 and len(limited_http.requests) == 1
    else:
        raise AssertionError('Read rate limit was ignored')
    missing_http = FixtureHTTP(response({}, 404))
    try:
        await yookassa(missing_http).get(created.provider_id, binding=binding, invoice_operation_id='invoice:1')
    except ProviderReadFailure:
        assert len(missing_http.requests) == 1  # Absence is not permission to create again.
    else:
        raise AssertionError('Missing lookup was accepted')
    unknown_http = FixtureHTTP(response({}, 502))
    try:
        await yookassa(unknown_http).create(InvoiceRequest(binding, 'Fixture', 'https://example.com/return'),
                                           operation_id='invoice:unknown')
    except ProviderWriteUnknown:
        assert len(unknown_http.requests) == 1  # Host preserves its operation and reconciles; no retry here.
    else:
        raise AssertionError('Uncertain write was accepted')
    assert not local.replies and not crypto_http.replies and not platega_http.replies
    print(json.dumps({'passed': True, 'case': 'core_providers', 'network': False,
                      'live_provider_verified': False}))


asyncio.run(main())
```
