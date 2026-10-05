# Требования и offline запуск рецептов — 0.18.0

У всех 305 cookbook-рецептов есть план зависимостей, данных, окружения и прав. 206 Python-рецепта имеют локальный исполнитель: 185 SDK requests, 11 markup builders, девять Dispatcher-композиций и один SQLite lost-response сценарий. 99 native-фрагментов остаются reference: без Telegram host и аргументов запуск отклоняется до создания процесса. Это не меняет maturity и не добавляет live evidence.

## Сначала требования

После установки предоставленного wheel:

```powershell
telegram-patterns run-recipe two-columns
telegram-patterns run-recipe two-columns --offline
telegram-patterns run-recipe api.sendPhoto --offline
telegram-patterns run-recipe demo-recovery --offline
telegram-patterns run-recipe native.requestContact
```

Первая команда только печатает план. `--offline` сначала печатает и flush-ит JSONL запись `stage=plan`, затем запускает известный fixture и печатает `stage=result`. Controlled ошибка выводится безопасным JSON в stderr, exit code 2. Для native reference план доступен, `--offline` дает отказ. Live режима нет.

JSON использует ASCII escapes для Unicode: значения полностью восстанавливаются JSON parser, включая кириллицу. Так вывод читается при Windows redirection даже с `-I`, который игнорирует PYTHONUTF8.

SDK-free план и SQLite-сценарий не требуют aiogram. SDK fixtures требуют установленный aiogram 3.31.0, с которым проверен snapshot. При отсутствии extra или другой версии план возвращает `blocked_reasons`; библиотека не устанавливает зависимости и не заменяет SDK проекта. `offline_ready` означает только готовность данного fixture.

```python
from telegram_patterns import RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline

plan: RecipeRunPlan = plan_recipe('demo-recovery')
assert plan.offline_ready
assert plan.offline_environment == plan.offline_permissions == ()
result: RecipeRunResult = run_recipe_offline('demo-recovery', timeout=60)
assert result.passed and not result.telegram_requests
assert result.checks == ('sqlite-one-effect', 'same-key-replay')
```

DTO frozen, collection fields — tuples. `Recipe.execution` возвращает независимую JSON-копию метаданных. Пользовательский `RecipeCatalog(data=...)` не становится источником исполнения; runner использует только каталог установленного пакета. Legacy schema 1 без execution читается, но такого executor у записи нет.

## Что именно выполняется

Нужен установленный пакет в текущем interpreter. Runner запускает закрытый bundled worker через Python `-I -B`: игнорируются project cwd, `PYTHONPATH` и user-site. Создается принадлежащий runner временный каталог; он удаляется при завершении. В child передаются только системные PATH/PATHEXT/SYSTEMROOT/WINDIR/TEMP/TMP/COMSPEC и PYTHONUTF8. BOT_TOKEN, payment secrets, `.env` и код приложения не читаются и не передаются.

Worker собирает настоящий SDK request/markup из синтетических fixtures либо выполняет один из четырех фиксированных bundled сценариев. Он не выполняет `recipe.code`, произвольные пути или пользовательский код. Dispatcher использует StubSession без HTTP fallback. SQLite effect и replay происходят в временной БД. Сессия и FSM композиции закрываются явно.

Перед SDK fixture запрещается настоящий aiogram HTTP transport; Python audit guard отклоняет внешний DNS/connect. Локальный socketpair/loopback нужен asyncio и разрешен. Это средство для доверенного установленного пакета, не OS sandbox для произвольного кода или зависимостей. `telegram_requests=false` и проверки fixture не доказывают отсутствие всех возможных каналов у недоверенного native extension.

Timeout 1..120 секунд, default 60; bool/NaN/inf отклоняются до создания каталога. Автоматического retry нет. Worker feedback проверяется по ID, версии, kind, результату и whitelist имен checks; ответ больше 256 KiB отклоняется. Raw child stdout/stderr не отражается в ошибках публичного runner. Timeout дает TimeoutFailure, неправильное завершение — InvalidCompletion, невыполненные prerequisites — UnsupportedCapability; неизвестный ID — KeyError.

## Права live сценария

Галерея раскрывает offline и live requirements отдельно и показывает команду копирования, без исполнения Python в браузере. План перечисляет токен/host, заменяемые fixture данные, actor/object correlation и известные ограничения. Поле `live_review` явно требует проверки официальных условий конкретного метода и ACL проекта до отправки.

Некоторые права описаны вручную, например supergroup topic/restriction и Business gift. Остальные `can_*` из SDK docstrings — подсказки, не полный permission engine. Неизвестное условие требует review; наличие метода или `offline_ready` не подтверждает реальные права, entitlement, пользовательское согласие и server auth. Native contact/write access требует согласия; clipboard имеет ограничения launch и gesture. Примеры не отправляют Telegram updates и не создают session пользовательского аккаунта.

## Источники и доказательства

5 октября 2026 частично сверены [Bot API](https://core.telegram.org/bots/api), условия topic/restrict/Business gift; [Mini Apps](https://core.telegram.org/bots/webapps), contact/write access/clipboard; [Python isolated mode](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I). Aiogram 3.31.0 проверяется установленным wheel consumer. Эта дата относится к перечисленным условиям, не обновляет весь Telegram/payment каталог.

`scripts/verify_recipe_execution.py` проверяет установленный core без SDK, все 206 Python fixtures в SDK consumer, отказ native/missing SDK, безопасные ошибки, сохранение файлов и два guard отказа. Browser tests проверяют requirements panel на phone/tablet/desktop и темах. Это executable fixtures; human/blind agent usability и реальные Telegram-клиенты остаются отдельными проверками.

`demo-calendar` — sixth Dispatcher fixture: temporary file SQLite booking/receipt, unavailable dates и DST offsets. Requires aiogram 3.31.0 и pinned tzdata 2026.5; plan сообщает calendar-extra-required или calendar-data-differs-from-checked-fixture до запуска worker.
