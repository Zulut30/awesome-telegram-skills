# Python core — 0.24.0

Термины: **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **entitlement** — право на возможность (custom emoji, оплаченный доступ), которое проверяется отдельно от самого запроса.

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

<a id="ref-core_storage"></a>

## SQLite effect и повтор — ref.core_storage

Файл: `core_storage.py`. Символы: `OnceResult`, `OperationConflict`, `SQLiteOnce`, `OnceStore`

Границы: Scope/ACL определяет сервер до effect и replay. Atomicity касается только переданного SQLite connection: без HTTP, другого storage, commit/rollback. Файл/миграции/retention принадлежат host.

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
    store: OnceStore[sqlite3.Connection] = SQLiteOnce(path)
    store.initialize()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE entries(label TEXT)')
    def apply(transaction: sqlite3.Connection) -> dict[str, str]:
        transaction.execute('INSERT INTO entries VALUES (?)', ('public-fixture',))
        return {'status': 'recorded'}
    result: OnceResult = store.run('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply)
    replay = store.run('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply)
    assert result.value == replay.value and not result.replayed and replay.replayed
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
assert len(catalog.recipes) == 315 and catalog.library_version
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
