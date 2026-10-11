# CI и приемка локальной поставки

Обновлено 11 октября 2026 года. `.github/workflows/repository-checks.yml` выполняет четыре независимые группы проверки:

- Навыки и тесты репозитория: metadata, самостоятельные references, синтаксис, installer и реальные операции проверочных helpers.
- Python: установленный пакет, Mypy и весь `packages/python/tests` на Windows/Linux с Python 3.11 и 3.13; aiogram 3.31.0 и tzdata 2026.5 закреплены для воспроизводимой проверки.
- TypeScript: 26 поведенческих тестов и сборка библиотеки/Mini App с Node 20 и 24. Node 20 проверяет заявленную нижнюю границу manifest, а не рекомендацию для нового deployment; используйте поддерживаемый LTS.
- Поставка: после успешных предыдущих групп новый wheel/tarball устанавливаются в отдельные consumer environments на Windows/Linux. Проверяются public imports/types, CLI, offline recipes, copied guides, standalone export, browser UI и generated starters. На Windows дополнительно исполняются точные команды первого запуска с теми же артефактами.

Chrome устанавливается через Playwright; `--skip-browser` в CI не используется. Отчеты, журналы и screenshots сохраняются как GitHub artifact даже при ошибке. Вложенные consumer reports/logs/screenshots копируются в `consumer-diagnostics`, без virtual environments, node_modules и файлов приложения. Наличие workflow не является подтверждением успешного запуска на GitHub: результаты конкретного run и ОС учитываются отдельно от локальной Windows-приемки.

## Локальный повтор

Требуются Python 3.11+, uv, Node/npm и Chrome либо `CHROME_PATH`. Из корня репозитория в PowerShell:

```powershell
npm.cmd ci
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
uv run --with "PyYAML>=6,<7" python -m unittest discover -s tests -v
python scripts/verify_pattern_packages.py --output output/my-new-acceptance
```

Именованный каталог `--output` должен быть новым: предыдущие отчеты и заметки не перезаписываются. Без параметра сохраняется прежний путь `output/pattern-library-<version>`. Все browser subreports следуют за именованным каталогом. Проверочные подпроцессы имеют отдельные deadlines; при timeout останавливается их дерево, сохраняются обе строки вывода и этап с `exit_code=124`. Длительность каждого этапа включена в отчет, а progress report записывается после каждого завершенного этапа.

Тест export/check/drift выполняет реальные SDK/offline recipes один раз и использует этот снимок для трех файловых операций. Отдельная полная приемка экспортной галереи заново генерирует данные и повторяет read-only check независимо; полнота проверки исполнения не сокращена.

После успешной поставки выполните Windows quickstart с ее wheel/tarball:

```powershell
$tgWheel = (Get-ChildItem -LiteralPath output/my-new-acceptance/dist -Filter '*.whl').FullName
$tgTarball = (Get-ChildItem -LiteralPath output/my-new-acceptance/dist -Filter '*.tgz').FullName
python scripts/verify_quickstart.py --wheel $tgWheel --tarball $tgTarball --output output/my-new-quickstart
```

Фактическая приемка версии фиксируется в `docs/v1-checks`; только после этого обновляются публичные счетчики и запускаются тесты/сборка документации. SDK/mock/browser evidence не подтверждает live Telegram, реальные устройства, платежные провайдеры или независимую usability.

## Проверенные источники

11 октября 2026 сверены только перечисленные правила CI:

- [GitHub Actions: матрицы jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations).
- [uv: интеграция с GitHub Actions и закрепление версии](https://docs.astral.sh/uv/guides/integration/github/).
- [Playwright: установка браузеров, зависимости и ограничение времени CI](https://playwright.dev/docs/ci).
- [actions/upload-artifact](https://github.com/actions/upload-artifact): tag v5 закреплен на commit `330a01c490aca151604b8cf639adc76d48f6c5d4`.
