# Версии, совместимость и deprecation

Политика пункта 004. Канонические контракты — [публичный API](public-api.md), [maturity](v1-maturity.md) и support matrix выпуска. Сейчас 0.6.0 в разработке, API experimental; эта политика не объявляет текущую библиотеку stable.

## Теги и релизы

Каждая выпущенная версия отмечена аннотированным тегом `vX.Y.Z` на коммите, который ее ввел, начиная с 0.5.0. Артефакты релиза воспроизводимо собираются из тега; порядок описан в [releasing.md](releasing.md).

## Политика поддержки

Сроки окружений сверены 7 октября 2026 года с [Python Developer's Guide](https://devguide.python.org/versions/) и [расписанием Node.js](https://github.com/nodejs/Release). Мы поддерживаем окружение, пока его поддерживает upstream, и объявляем прекращение поддержки в CHANGELOG не позже чем за одну минорную версию.

| Компонент | Поддерживается | Срок | Примечание |
| --- | --- | --- | --- |
| Библиотека 0.x | последняя минорная версия | до выхода следующей минорной | исправления, в том числе безопасности, только для нее ([SECURITY.md](../SECURITY.md)) |
| Библиотека ≥1.0 | последняя и предыдущая минорные | предыдущая — 6 месяцев после выхода новой | исправления безопасности для обеих |
| Python 3.11 | да | до октября 2027 | минимальная версия (`requires-python >=3.11`) |
| Python 3.12, 3.13 | да | до октября 2028 и 2029 | |
| Python 3.14 | да | до октября 2030 | |
| Python 3.15 | после финального выпуска | — | сейчас prerelease |
| Node.js 20 | объявлен минимальным в `engines`, upstream EOL 30.04.2026 | до следующей минорной версии после объявления | обновитесь до 22 или 24 |
| Node.js 22 | да | до 30.04.2027 | Maintenance LTS |
| Node.js 24 | да | до 30.04.2028 | Active LTS, основная версия CI |
| Node.js 26 | после перехода в LTS | до 30.04.2029 | сейчас Current |
| aiogram | `>=3.31,<4` | пока выходит 3.x | проверяется на 3.31.0; aiogram 4 — отдельное решение |
| Telegram Bot API | 10.3 | до следующей версии | каталог отслеживает новые версии (пункт 51 плана) |

## Автоматическая проверка

`scripts/check_api_compatibility.py` сравнивает сигнатуры публичных символов Python (функции, конструкторы, публичные методы, значения `Literal`) и декларации экспортов TypeScript с предыдущим тегом или базовой веткой pull request. Удаленный или измененный символ без упоминания в верхнем разделе CHANGELOG валит CI. Проверка не решает, совместимо ли изменение: это по-прежнему определяют правила ниже.

## Что входит в обещание совместимости

Документированные import paths/exports, constructors/functions и обязательные/optional параметры, return types и shapes, exception classes/kinds/outcome, side effects, ресурсное владение, CLI commands/exit codes/JSON fields, CSS subpath и публичные style tokens. Для сохраняемого состояния также важны schema version, scope и восстановление operation identity. Текст diagnostics, сгенерированные DOM IDs, приватные helpers и случайные SDK reexports не являются стабильным контрактом. Нельзя полагаться на приватное имя вместо публичного API.

Совместимость определяется зрелостью отдельного компонента, а не только номером всего пакета. Reference не обещает готовый workflow; experimental требует учета возможных изменений. Стабильный узкий request builder не обещает целый backend/payment flow.

## Правила изменения версии

| Изменение | До 1.0 | Для stable API начиная с 1.0 |
| --- | --- | --- |
| Исправление без нарушения контракта | PATCH | PATCH |
| Новый API или optional возможность с совместимым default | MINOR | MINOR |
| Deprecation существующего public API | MINOR с replacement и migration | MINOR с предупреждением и сроком удаления |
| Удаление/переименование, required параметр, несовместимый return/error/side effect | MINOR и явная migration, без скрытого breaking PATCH | MAJOR после deprecation window |
| Только документация/внутренний refactor без изменения поведения | Commit; для поставки новый PATCH при изменившихся байтах | Commit; для поставки новый PATCH при изменившихся байтах |

Python и TypeScript независимы при выполнении; для совместной поставки/starter используется один release identity. Сейчас numeric X.Y.Z совпадает в manifests/catalog/example. Release candidate отображается в допустимом формате каждого registry: Python `1.0.0rc1`, npm `1.0.0-rc.1`, identity `1.0.0-rc.1`. Текущий starter/verifier пока принимает только numeric releases; фактическая RC-поставка требует соответствующей реализации и consumer-проверки в пункте 099, а не смены строки версии вручную.

Development commit/локальный build не равен опубликованному релизу. Отчет и consumer evidence относятся к конкретным artifact hashes. После выпуска содержимое номера неизменно, в том числе при локальном распространении принятого релиза: новые байты — новая версия. Wheel/tarball собираются из принятого source commit, проверяются и сохраняются с checksum; registry publication не подразумевается автоматически.

## Период deprecation stable API

Удаление возможно в следующем major после **как минимум двух minor выпусков и 90 календарных дней** с первого предупреждения — должны пройти оба условия. Release notes указывают `deprecated_in`, replacement, migration и `removal_not_before`; объявлять точную дату без будущего major не требуется. До 1.0 этот период не обещается, но breaking изменение все равно требует notes и before/after example.

Python использует адресный `DeprecationWarning` с корректным stacklevel в точке использования, когда поведение действительно deprecated. TypeScript — `@deprecated` в declarations/documentation и migration; runtime warning, если нужен, не повторяется бесконечно. Сейчас deprecated APIs нет, поэтому пустые warning wrappers не добавляются. Aliases сохраняют старые допустимые аргументы/результат до удаления.

При изменении storage старое состояние либо мигрируется явно, либо возвращается различимый отказ с инструкцией сверки. Нельзя очистить pending operation ID и создать новую опасную операцию под видом исправления schema. Для security hotfix не скрывают breaking change внутри PATCH: если новый контракт действительно несовместим, выбирается соответствующая версия и предлагается migration/ограничение функции.

## Приемка изменения

Автор описывает affected public contract и класс совместимости, проверяет старый consumer для совместимого изменения либо before/after для breaking, синхронизирует exports/types/catalog/changelog/examples/инструкции. Release review сверяет support matrix, artifact hashes и обязательные сценарии. Evidence старой версии не переносится без проверки новой поставки.

Проверенные источники 4 октября 2026: [SemVer 2.0.0](https://semver.org/) — публичный API, major/minor/patch и неизменность релиза; [PyPA versioning](https://packaging.python.org/en/latest/discussions/versioning/) — правила Python versions. Срок 90 дней/два minor и процедура удаления — собственная политика проекта.
