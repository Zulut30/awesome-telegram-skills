# Матрица поддержки 0.10.0

Пункт 005. Машиночитаемый снимок — [support-matrix.json](../catalog/support-matrix.json). «Заявлено» означает dependency/runtime constraint; «проверено» — конкретный прошедший сценарий. Весь declared range не считается проверенным одной комбинацией. API пока experimental.

| Область | Заявлено / формат | Проверено 4 октября 2026 | Непроверенные границы |
| --- | --- | --- | --- |
| Python core | Python >=3.11, stdlib, без SDK | 3.13.12, Windows 11 AMD64, установленный wheel без aiogram; CLI/core/SQLite consumers | Остальные Python versions и Linux/macOS требуют отдельной матрицы |
| Python bot adapters | Optional aiogram >=3.31,<4 | aiogram 3.31.0, тот же Python/OS, native SDK construction и synthetic Dispatcher | Другие SDK versions, PTB/TeleBot adapters и live Telegram не подтверждены |
| TypeScript tooling | Node >=20, ESM; no runtime dependencies | Node 24.19.0, npm 12.0.2, TypeScript 7.0.2, tarball imports/types/build и 26 тест | Другие версии Node/TS и bundlers не объявлены проверенными; CommonJS export отсутствует |
| Browser UI | DOM/fetch/ESM; Chrome или CHROME_PATH для verification | Chrome 154.0.8037.97, Playwright 1.63.0; 141 example + 245 gallery + 66 starter + 76 selected starter checks | Другие engines, screen readers и физические устройства отдельно |
| Viewports/themes | Responsive composition | Browser cases: 320–1920 px по ширине, portrait/landscape/tablet/desktop; light/dark | Viewport emulation не настоящие iOS/Android/tablet Telegram clients |
| Telegram Bot API | Runtime возможности установленного SDK | Snapshot Bot API 10.3: 185 request methods / 400 indexed types, construction | Server permissions, real delivery, payment workflows и все SDK versions не доказаны |
| Mini App native API | 99 paths / 44 events snapshot, version/platform/presence gates | Types/build, mock native callbacks/listeners и browser compositions | Нет live matrix версий Telegram iOS/Android/Desktop; method availability не permission/auth |
| Storage | SQLiteOnce только file SQLite; host FSM | Local file SQLite/replay; MemoryStorage form example | Durable FSM/restart/multiworker, production storage adapters — последующие пункты |
| Windows symlink case | Directory symlink проверяется при возможности | 103 Python passed; 1 из 104 skipped из-за недоступных directory symlinks | Пропуск не PASS этого filesystem случая |

Node >=20 — текущий технический минимум manifests, а не рекомендация выбирать Node 20 для production. По [официальной таблице Node.js](https://nodejs.org/en/about/previous-releases) ветка 20 уже EOL; использовать поддерживаемую LTS и затем проверять точную версию приложения. Наш снимок проверен на 24.19.0, что не означает «самая свежая версия».

Evidence: [012.json](v1-checks/012.json), `output/pattern-library-0.10.0/distribution-report.json` и соответствующие logs, привязанные к hashes wheel/tarball. Telegram/live/sandbox evidence сейчас отсутствует, версии клиентов поэтому не выдумываются. Расширение исполняемой OS/runtime matrix относится к 081, device acceptance — к 067; публикация таблицы не закрывает эти пункты.

Для другого SDK/runtime сохраняйте выбранный стек и выполните relevant consumer/tests перед обещанием совместимости. `doctor` предупреждает об aiogram, отличном от проверенного 3.31.0; проверка формата token не проверяет Telegram identity. Обновление support matrix следует за новым evidence, а не только за изменением диапазона зависимости.

Дополнительно в 0.9.0: Mypy 2.4.0 по 17 исходным файлам и consumer wheel; TypeScript consumer включает named field type и негативные assertions.

В 0.8.0 дополнительно проверены категории/recovery, unknown outcome после HTTP/отмены/некорректного feedback, сверка SQLite effect и переносимый error reference.

В 0.9.0 дополнительно: structural protocols, copied custom adapter type/runtime consumer и собственные TS storage/transport. Provider fixture не подтверждает работу реальной платежки.

В 0.9.1 дополнительно: source/resources/RECORD и полный JS/declarations/CSS archive contract; 7 negative archive cases. Из 452 browser checks 386 workspace/example/gallery и 66 installed starter; эти scope не смешиваются.

В 0.9.2 дополнительно исправлен npm file path starter: после percent-encoded URI регрессии проведен полный rebuild/install. [Первый запуск](quickstart.md) проверен по его PowerShell-командам в новом consumer с пробелами в путях: installed wheel/origin, offline бот, doctor, сборка из tarball и 60 отдельных Chrome checks (320/768/1440 px, light/dark). Существующий каталог сохранен. Эти 60 checks дополняют 452 проверки общей поставки; ни один из них не подтверждает физическое Telegram-устройство, backend auth или человеческое удобство.

В 0.10.0 проверен выбор 15 групп starter-компонентов: точный dry-run, сохранность при повторном init, отклонение несовместимых версий, команд, callback prefixes и путей до записи. Mypy проверяет 18 исходных файлов и installed consumers. Полная поставка проходит 52 этапа; из 528 browser checks 386 относятся к workspace, 142 — к двум установленным starters. Документированный первый запуск повторен на артефактах 0.10.0 и дает еще 60 checks. Готовая форма использует временный MemoryStorage; ее validation fixture не сохраняет заявку и не заменяет сервис приложения.
