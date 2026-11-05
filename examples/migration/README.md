# Проверяемая миграция 0.5.0 → 0.28.0

Самостоятельные consumers устанавливают **переданные локальные wheel/tgz**, создают старое состояние и открывают его новой версией. Импорты идут из установленных пакетов, без исходников checkout и private API. Сценарий проверен для development artifacts 0.28.0; он не подтверждает миграцию на 1.0 RC.

Понадобятся Python 3.11–3.14 с `venv`/`pip`, Node.js и npm. Проверенный полный прогон: Python 3.13, Node 24, Windows. Runner выбирает `Scripts/python.exe` / `bin/python` и `npm.cmd` / `npm` по ОС; Linux-исполнение этой конкретной приёмкой не подтверждено. Можно скопировать весь этот каталог отдельно: runner ищет только соседние файлы и четыре явно заданных артефакта.

## Запуск

Подставьте пути к вашим артефактам и **ещё не существующему** каталогу. Имя пакета в registry не заменяет предоставленный wheel/tgz. Из корня checkout, Bash:

```bash
python examples/migration/run.py \
  --before-wheel artifacts/0.5.0/awesome_telegram_patterns-0.5.0-py3-none-any.whl \
  --before-tarball artifacts/0.5.0/awesome-telegram-patterns-0.5.0.tgz \
  --after-wheel artifacts/0.28.0/awesome_telegram_patterns-0.28.0-py3-none-any.whl \
  --after-tarball artifacts/0.28.0/awesome-telegram-patterns-0.28.0.tgz \
  --after-version 0.28.0 --output /tmp/telegram-migration-new \
  --with-sdk --with-types
```

PowerShell:

```powershell
python examples/migration/run.py `
  --before-wheel artifacts/0.5.0/awesome_telegram_patterns-0.5.0-py3-none-any.whl `
  --before-tarball artifacts/0.5.0/awesome-telegram-patterns-0.5.0.tgz `
  --after-wheel artifacts/0.28.0/awesome_telegram_patterns-0.28.0-py3-none-any.whl `
  --after-tarball artifacts/0.28.0/awesome-telegram-patterns-0.28.0.tgz `
  --after-version 0.28.0 --output (Join-Path $env:TEMP 'telegram-migration-new') `
  --with-sdk --with-types
```

Без `--with-sdk` core остаётся без Bot SDK; без `--with-types` не устанавливаются compiler/parser tools. `--with-sdk` создаёт **дополнительные отдельные** environments с aiogram==3.31.0; `--with-types` ставит TypeScript 7.0.2 и parser 5.9.3 только в output. Для этого нужен доступ к dependency registries или заранее заполненный cache. Runtime consumers используют synthetic transport и не обращаются в Telegram/платёжные API. `--python`, `--node`, `--npm` позволяют явно выбрать executables.

Runner откажется от любого существующего output, включая собственный завершённый запуск. Он не продолжает прерванную операцию и ничего не удаляет. В новом output появляются `.migration-owner.json`, `report.json`, логи команд, environments, Node projects, SQLite backup, исходный FSM snapshot и результаты. Успех — код 0 и `report.json.passed=true`; для полного доказательства также нужны `with_sdk=true`, `with_types=true`.

## Что исполняется

| Файл | До / после |
| --- | --- |
| `python_consumer.py` | SQLite receipt replay, strict JSON, backup/integrity, неизвестное финансовое состояние, initData, diagnostic JSON и fresh starter/no-overwrite |
| `typescript_consumer.mjs` | Draft v1→v2 с явным mapper, scope/TTL, API route prefix, unknown POST без retry, platform detection, listener fanout, valid native call/dispose |
| `api_contract_consumer.mjs` | Timeout overflow, body без JSON representation, исключение headers callback и переносимый valid request |
| `sdk_consumer.py` | Одинаковая aiogram-композиция, foreign actor, повтор submit, ресурсное владение, GetMe preflight; без реального polling |
| `fsm_consumer.py` | Старый router создаёт unknown submission; новый получает его через публичные FSM state/data APIs и сверяет исходный ID; schema2 отказывает без сброса |
| `types/*.ts` | Старые assumptions компилируются до обновления и отклоняются после; исправленный after компилируется |
| `python_inventory.py`, `typescript_inventory.mjs` | Исторические public names/signatures и транзитивные root declaration exports, без объявления статического diff полной семантической проверкой |

`public-api-0.5.json` содержит 47 исторических явно публичных Python имён. При запуске без SDK inventory ограничен root/cli; полный прогон проверяет все 47. `contract-map.json` классифицирует 27 изменившихся descriptors. Дополнительные поведенческие различия перечислены в [guide](../../docs/migration-from-0.5.md).

## Как получить исторические пакеты

Предпочтительный вход — сохранённые артефакты вместе с SHA256 и source identity. Если их нет, в **полном checkout** проверьте frozen ref и соберите его отдельно существующим release builder:

```bash
git rev-parse 'v0.5.0^{commit}'
python -m pip install -r requirements/build.txt
python scripts/build_release.py \
  --ref 73963b2e4add8ee6922bc07a6b7baa4104fdd00e \
  --output artifacts/0.5.0-new
```

Ожидаемый commit — `73963b2e4add8ee6922bc07a6b7baa4104fdd00e`; список исторических refs — `.github/release-tags.json`. Builder экспортирует `git archive`; не исправляйте старое дерево ради успеха consumer и не создавайте новый tag. Инструменты сборки влияют на bytes: сверьте собственные SHA с evidence в guide. Для 0.28.0 нужен именно переданный проверенный artifact; текущий WIP checkout не является его заменой.

Исторический 0.5.0 starter имеет известный packaging defect: нет `.env.example.txt`; consumer ожидает отказ **до создания target**. Существующий проект не пересоздаётся starter. Unknown/unbound финансовые записи сохраняют ID и требуют явной сверки владельца; никакого автоматического `paid`, invoice/send или нового retry ID здесь нет. Лицензии и third-party notices исходных пакетов сохраняются.
