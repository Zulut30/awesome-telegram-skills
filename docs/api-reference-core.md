# Python core — 0.11.1

[Индекс всех символов](api-reference.md). Образцы ниже воспроизводятся через установленный wheel/tarball вне исходного дерева. Assert — проверка fixture, не бизнес-правило production приложения.

Установите предоставленный локальный wheel без aiogram. Для core_starter.py передайте путь к нему как первый аргумент: `python core_starter.py "<PROVIDED_WHEEL>"`. Остальные файлы запускаются `python <FILE.py>`. core_doctor намеренно проверяет SDK-free окружение.

<a id="ref-core_identity"></a>

## Конфигурация и проверенный запуск — ref.core_identity

Файл: `core_identity.py`. Символы: `BotSettings`, `InvalidInitData`, `VerifiedLaunch`, `validate_init_data`

Границы: HMAC fixture без Telegram; token только на backend, raw initData проверяется до session/ACL. BotSettings repr скрывает token, сериализация не становится безопасной. VerifiedLaunch — результат проверки, ручной DTO не подтверждает identity.

```python
"""Искусственная HMAC-подпись для локального примера, без Telegram и login."""
import hmac
import json
from urllib.parse import urlencode
from telegram_patterns import BotSettings, InvalidInitData, VerifiedLaunch, validate_init_data

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
# Настоящие initData приходят от Telegram; ACL/session/replay проверяет backend.
print(json.dumps({'passed': True, 'case': 'core_identity', 'network': False}))
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
recipe: Recipe = catalog.search('две кнопки', maturity=maturity, verification=verification)[0]
assert recipe.id == 'two-columns' and catalog.get(recipe.id) == recipe
assert len(catalog.recipes) == 298 and catalog.library_version
preview = recipe.preview
assert preview is not None and [len(row) for row in preview['inline_keyboard']] == [2, 2]
preview['inline_keyboard'][0][0]['text'] = 'local-copy'
assert catalog.get(recipe.id).preview != preview
# SDK evidence не делает API stable и не доказывает appearance в Telegram.
print(json.dumps({'passed': True, 'case': 'core_recipes', 'network': False}))
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

Границы: Пример намеренно запускается без aiogram: readiness fail содержит команды следующего явного действия. Doctor не читает .env/не отправляет token, не выполняет предлагаемые repairs и не подтверждает live identity. SDK probe установленного extra изолирован от проекта.

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
