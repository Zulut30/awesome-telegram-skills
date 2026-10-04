# Структура API и типы

Пункт 006. Python core не импортирует SDK, aiogram adapters подключаются отдельным extra, transport fixtures лежат в testing. TypeScript имеет явные value/type reexports из одного root и отдельный CSS subpath. Разделение по домену не означает обязательную установку всех adapters или переписывание frontend.

Публичные символы Python определены через __all__ root/aiogram/testing. SDK/stdlib names не попадают в wildcard импорт случайно; старые explicit SDK imports из adapter module пока остаются доступными. Новым потребителям следует импортировать native Bot/Dispatcher/models из aiogram. Названия функций и классов существующего документированного API сохранены.

## Общие правила имен

- Python: snake_case функций/параметров, PascalCase DTO/classes, именованные Literal aliases для ограниченных значений. TypeScript: camelCase функций/методов, PascalCase interfaces/classes и SCREAMING_SNAKE_CASE immutable catalogs.
- `create_*` создает owned composition, `build_request` строит SDK request без HTTP, `run_bot` владеет запуском/session, `validate_init_data` валидирует launch, не ACL. `search/get`, `read/write/clear`, `snapshot/subscribe` сохраняют различия доменов; переименования ради формальной одинаковости не вводятся.
- Status/outcome и operation identity явно отделены от пользовательского текста, UI availability и подтвержденного server effect. Optional SDK fields проверяются после выбора действия; фильтр aiogram не подменяет явный типовой guard.

## Добавленные публичные типы

| Тип | Точка импорта | Контракт |
| --- | --- | --- |
| `Maturity` | telegram_patterns | Literal stable/experimental/reference, тот же schema и runtime validation RecipeCatalog |
| `VerificationLevel` | telegram_patterns | Literal sdk/mock/browser/live/not_run, независимо от maturity |
| `ButtonStyle` | telegram_patterns.aiogram | Literal primary/success/danger, без arbitrary RGB |
| `ChatType` | telegram_patterns.aiogram | Literal private/group/supergroup/channel; реальные контекстные ограничения проверяет builder |
| `UpdatePhase` | telegram_patterns.aiogram | Literal received/handled/unhandled/failed/cancelled для UpdateTrace/observer |
| `Responder` | telegram_patterns.testing | Значение либо sync/async callable от SDK method; return validation у StubSession |
| `TextFieldControl` | @awesome-telegram/patterns | root/input/setError именует прежнюю структуру createTextField; DOM references сохраняют прежнюю assignability |

## Совместимость и миграция

Документированные imports и имена не переименованы. Старый wildcard, использовавший случайный SDK import, следует заменить:

```python
# Before: from telegram_patterns.aiogram import *; Bot/Dispatcher приходили случайно.
from aiogram import Bot, Dispatcher
from telegram_patterns.aiogram import ActionButton, action_menu, callback_router
```

Новые named types добавлены совместимо. Изменение wildcard набора явно описано; direct `from telegram_patterns.aiogram import Bot` временно сохранен, но не становится публичным library contract. Native controls/FSM не получают новых прав или автоматической persistence.

Типы `Recipe.maturity/verification` и соответствующих search filters уточнены до Literal. В typed consumer переменные следует объявлять как Maturity/VerificationLevel; внешнюю строку проверять по разрешенным значениям до cast. Это ужесточение статического контракта до 1.0, runtime schema validation и conservative чтение старых records сохранены:

```python
from telegram_patterns import Maturity, RecipeCatalog

level: Maturity = 'experimental'
recipes = RecipeCatalog().search(maturity=level)
```

## Проверки

Mypy проверяет исходники Python и статический consumer установленного wheel, включая deliberate invalid Literal assignments с warn_unused_ignores. TypeScript consumer компилируется против установленного tarball, включая invalid paths/events/shape assertions. Runtime tests проверяют работоспособность wildcard composition, отсутствие случайных SDK names и отказ ошибочной регистрации UpdateObserver на message observer до telemetry/effect. Полная distribution проверка остается обязательной.
