# Проверяемое evidence рецептов

`scripts/recipe_evidence.py` создаёт реестр из фактического `distribution-report.json`, точных wheel/tarball и исходников проверенного выпуска. Дата `docs/sources.md`, поле `source_snapshot` и свежая дата страницы не являются результатом исполнения. Helper не меняет каталоги, зрелость, exports или существующие файлы и сам не запускает рецепты.

В 0.28.0 уже есть полезные данные: `code_sha256`, `source_files`, `check_files`, `scope` у карточек и 241 индивидуальный результат в `recipe_execution.recipes`. Не хватало общей проверяемой привязки каждой записи к полному отчёту, точным артефактам, исходникам и происхождению команды. Новый реестр соединяет эти данные и явно сохраняет пробелы.

## Что действительно проверено в 0.28.0

Канонический отчёт: `output/pattern-library-0.28.0/distribution-report.json`, 92 успешных этапа, 879 Python и 89 TypeScript тестов. Это общие числа выпуска, не число поведенческих тестов каждого рецепта.

| Scope | Результат и граница |
| --- | --- |
| 185 Python `sdk-request` | Отдельные результаты: построение SDK request из synthetic fixtures и проверка имени метода. Запросы не отправлены; права Telegram не проверены |
| 11 Python `sdk-markup` | Восстановление native markup и сравнение wire JSON с preview |
| 11 Python `ptb-markup` | Проверка core JSON и преобразования через python-telegram-bot |
| 24 Python `dispatcher`, 9 `application`, 1 `sqlite` | Исполняются поставляемые доверенные fixtures/compositions, включая конкретные checks из отчёта; это не произвольный запуск `recipe.code` |
| 100 TypeScript `reference` | Индивидуального runtime result нет: `not_run`. Они остаются справочными фрагментами |
| `recipe_gallery` | 341 карточка, regeneration/check: 207 sdk, 34 mock, 100 reference, 0 live. Поле sdk не равнозначно live-проверке |
| `gallery_export`, `gallery_browser` | Точные копии, read-only export/check, CLI, локальный UI, фильтры/preview/clipboard/размеры. Галерея не исполняет все 341 фрагмента |
| `native_recipes` | Отдельный `tests/native-recipes-consumer.mjs` проверяет два готовых примера из `examples/mini-app/src/native-recipes.ts`: location и popup, включая отказ, late callback и cleanup. Это не результаты для 100 `native.*` карточек |

Все 341 карточки получают запись реестра: 241 `offline_pass`, 100 `not_run`; зрелость сохраняется: 56 experimental, 285 reference, 0 stable. `offline_pass` обозначает только указанный synthetic fixture/SDK уровень. Нет live Telegram, платёжных кабинетов, физических устройств, независимой слепой оценки навыков или исследования удобства.

## Создать и перепроверить реестр

Нужны Python 3.11+ и локальные файлы поставки. Для необязательной проверки исходного commit нужен локальный Git с уже имеющимся объектом; helper ничего не коммитит, не меняет refs/index и не загружает из сети.

Замороженные исходники 0.28.0 доступны отдельным snapshot, поскольку основной checkout может уже разрабатываться дальше. Пример PowerShell из корня репозитория:

```powershell
$releaseSource = 'C:/provided/awesome-telegram-skills-0.28.0-source'
$releaseReport = 'output/pattern-library-0.28.0/distribution-report.json'
$releaseWheel = 'output/pattern-library-0.28.0/dist/awesome_telegram_patterns-0.28.0-py3-none-any.whl'
$releaseTarball = 'output/pattern-library-0.28.0/dist/awesome-telegram-patterns-0.28.0.tgz'
$newRegistry = 'output/recipe-evidence-0.28.0.json'
python scripts/recipe_evidence.py create --report $releaseReport --wheel $releaseWheel --tarball $releaseTarball --source $releaseSource --source-ref 92a9d151 --git-repository . --registry $newRegistry
python scripts/recipe_evidence.py check --report $releaseReport --wheel $releaseWheel --tarball $releaseTarball --source $releaseSource --registry $newRegistry
```

`create` требует новое имя файла и существующий родительский каталог. Существующий файл не обрезается и не заменяется. `check` ничего не пишет. Успешный exit 0 означает `binding_verified=true`, а `quality_or_production_approved` всегда false. Без `--source-ref` и `--git-repository` остаётся проверяемая привязка source bytes, но `git_source=null`: проверка принадлежности commit не утверждается. При их указании допустим только SHA commit; содержимое source/check files сравнивается с blob-объектами этого commit. Built JS/declarations обычно не хранятся в Git: их точные bytes сверяются с tarball, source TypeScript — с commit.

Helper проверяет:

- SHA256 и размер обоих артефактов по отчёту, версии, wheel RECORD и точное содержимое distributions через существующий `verify_distribution_contract`;
- byte equality каталога карточек с `recipes.json` внутри wheel и SHA256 кода каждой карточки;
- version/kind/ID/непустые checks, отсутствие Telegram/network у каждого индивидуального Python result; неизвестные/повторные IDs и неполные результаты отклоняются;
- hashes всех упомянутых source/check files, package source/resources и TypeScript source/dist, а также runner scripts;
- при повторном `check` — SHA исходного отчёта, hashes исходников и полное совпадение заново вычисленного реестра. Изменение рецепта или runner без новой проверки не скрывается прежней версией/датой.

В исходном distribution-report полные argv не были записаны. Поэтому `producer_command` для Python честно восстановлен из AST привязанного `verify_recipe_execution.py` и фактического SDK interpreter origin; `command_provenance` прямо указывает это ограничение. Сохраняется batch-команда `--all-python` и pointer на индивидуальный result, а не выдуманный отдельный CLI-запуск каждого ID. `reproduction_command` — публичная команда для будущего повторного исполнения одного рецепта; наличие поля не означает, что она была исполнена отдельно в историческом выпуске. Неизвестная структура producer требует обновить parser и проверить контракт; helper не угадывает будущие команды.

Схема реестра: [catalog/recipe-evidence.schema.json](../catalog/recipe-evidence.schema.json). Дополнительно к JSON-структуре helper заново вычисляет записи из bound inputs. Время создания реестра не обновляет дату runtime evidence. Полный повтор поставки выполняется отдельно через `python scripts/verify_pattern_packages.py`; `check` этого не заменяет.

## Stable и будущие рецепты

Реестр всегда хранит все текущие карточки и сохраняет `maturity` без повышения. Новый рецепт без индивидуального результата получает `not_run`, даже если весь каталог был перечислен/экспортирован и общий отчёт passed. Наличие aggregate native/browser suite не заполняет этот пробел.

`--require-stable` дополнительно требует непустой stable scope и индивидуальное bound offline evidence для каждого stable ID. На 0.28.0 эта команда намеренно завершается с exit 1: `no_stable_scope`, `evidence_complete=false`. При `create --require-stable` файл вообще не создаётся. Нельзя предъявлять «0 из 0 stable прошли» как качество.

Даже `bound_offline_evidence` в будущем означает только полноту связанного offline evidence. Решение о stable API, достаточности сценариев, live/device/production остаётся отдельной проверкой; `quality_or_production_approved=false` сохраняется. Для нового результата нужны новая реальная проверка, её отчёт, точные артефакты и соответствующие исходники. Изменение каталожной зрелости или даты без такого результата ничего не доказывает.

Локальный JSON-отчёт является доверенным входом владельца, а не криптографически подписанной аттестацией CI. Hash binding обнаруживает подмену после связывания и несогласованность входов, но не доказывает правдивость произвольно переписанного отчёта. Пути interpreter origin исторические: для перепроверки hashes старое окружение не нужно. Consumer proof дополнительно устанавливает точный wheel и проверяет его происхождение отдельно; он не создаёт новые результаты для остальных рецептов.

Проверки helper:

```powershell
python -m unittest tests.test_recipe_evidence tests.test_distribution_contract -v
```

Первый suite проверяет атрибуцию, отсутствие автоматического stable/native PASS, stale artifact/report/source refusal и сохранность caller files. Archive verifier в этих unit fixtures заменён тестовой границей; второй suite и фактический consumer-прогон проверяют реальные архивные операции.
