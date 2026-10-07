# Выпуск версий

Каждая версия библиотеки отмечена аннотированным git-тегом `vX.Y.Z` на коммите, который ее ввел. По тегу [workflow Release](../.github/workflows/release.yml) собирает Python wheel, npm tarball и `SHA256SUMS` и публикует их в GitHub Release. Пока пакеты не опубликованы в PyPI и npm, релиз — основной источник установки.

## Как собирается релиз

[`scripts/build_release.py`](../scripts/build_release.py) экспортирует дерево тега через `git archive`, поэтому незакоммиченные файлы рабочей копии в релиз не попадают. `SOURCE_DATE_EPOCH` равен времени коммита, поэтому две сборки одного тега с одинаковыми версиями инструментов дают побайтно одинаковые файлы. Версии зависимостей сборки заданы `package-lock.json` тега и диапазоном setuptools в `pyproject.toml`; `build` закреплен в workflow.

```bash
python -m pip install 'build==1.3.0'
python scripts/build_release.py --ref v0.24.0 --output dist/v0.24.0
python scripts/build_release.py --ref v0.24.0 --notes
```

Вместе с пакетами создается `awesome-telegram-patterns-X.Y.Z.cdx.json` — CycloneDX 1.6 SBOM: оба артефакта с SHA-256, лицензией из `pyproject.toml` тега и необязательные зависимости extras (aiogram, tzdata). Он детерминирован и входит в `SHA256SUMS`. Workflow создает для всех трех файлов подписанную attestation происхождения сборки (`actions/attest`, Sigstore).

Заметки к релизу берутся из текущего `CHANGELOG.md`: раздел `## X.Y.Z` либо пункты вида `Пункт NNN, X.Y.Z: …`. Все релизы 0.x помечаются как prerelease.

## Выпустить новую версию

1. Обновите версию в `packages/python/pyproject.toml`, `__version__` в `packages/python/src/telegram_patterns/__init__.py`, `packages/typescript/package.json`, `components.json`, `resources/recipes.json`, `metadata.version` во frontmatter всех скиллов и раздел CHANGELOG. `validate_skills.py` не пропустит скилл с другой версией.
2. Проверьте демо Mini App на устройствах по [чек-листу](device-qa-checklist.md): iOS, Android, Desktop и Web в тестовом окружении Telegram. Отчет и скриншоты положите в `docs/device-checks/X.Y.Z/`, проверьте `python scripts/device_report.py check docs/device-checks/X.Y.Z --version X.Y.Z` и закоммитьте. Начиная с 0.25.0 workflow Release без корректного отчета в теге завершается ошибкой; с отчетом прикладывает к релизу `device-report-X.Y.Z.zip` и добавляет таблицу результатов в описание.
3. После слияния в `main` поставьте тег на этот коммит и отправьте его:

   ```bash
   git tag -a v0.25.0 -m "awesome-telegram-patterns 0.25.0"
   git push origin v0.25.0
   ```

4. Workflow Release соберет артефакты из тега и опубликует релиз. Тот же тег запускает workflow [Full acceptance](../.github/workflows/full-acceptance.yml): полный `verify_pattern_packages.py` на Ubuntu и macOS с отчетами в артефактах запуска.

## Релизы для существующих тегов

Версии 0.5.0–0.24.0 и коммиты, которые их ввели, перечислены в [`.github/release-tags.json`](../.github/release-tags.json). После слияния workflow в `main` запустите **Actions → Release → Run workflow** с пустым полем `tags`: ручной запуск создаст недостающие аннотированные теги из этого списка (проверив версию в `pyproject.toml` коммита) и опубликует все теги без релиза. Чтобы пересобрать конкретные версии, перечислите их через пробел. Теги, созданные через `GITHUB_TOKEN`, не запускают другие workflow — публикация идет в том же запуске.

## Публикация в PyPI и npm

[Workflow Publish](../.github/workflows/publish.yml) загружает файлы опубликованного GitHub Release в PyPI и npm через trusted publishing (OIDC): долгоживущие токены в репозитории не хранятся, npm автоматически добавляет provenance. Перед загрузкой он сверяет `SHA256SUMS`. Пока репозиторная переменная `PUBLISH_TO_REGISTRIES` не равна `true`, workflow ничего не публикует.

Включить публикацию может только владелец:

1. Занять имена. `python scripts/check_registry_names.py` показывает, свободны ли они. На 7 октября 2026 проект `awesome-telegram-patterns` на PyPI и пакет `@awesome-telegram/patterns` на npm не существуют, scope `@awesome-telegram` не найден. На npm создайте организацию `awesome-telegram` (бесплатно для публичных пакетов). На PyPI pending publisher не резервирует имя: оно закрепляется первой загрузкой, поэтому выпустите первую версию вскоре после настройки. Если имя занято другим автором, выберите новое и замените его в `pyproject.toml`, `package.json`, README, документации и workflow.
2. В GitHub создать environments `pypi` и `npm` (Settings → Environments), при желании с обязательным подтверждением.
3. PyPI: в аккаунте **Publishing → Add a new pending publisher** указать проект `awesome-telegram-patterns`, владельца `Zulut30`, репозиторий `awesome-telegram-skills`, workflow `publish.yml`, environment `pypi`. Pending publisher создает проект при первой загрузке.
4. npm: в настройках пакета `@awesome-telegram/patterns` → **Trusted publishing** указать GitHub Actions, `Zulut30/awesome-telegram-skills`, workflow `publish.yml`, environment `npm`. Если npm не позволяет настроить trusted publisher для еще не существующего пакета, первую версию опубликуйте вручную с 2FA. Trusted publishing требует npm ≥ 11.5.1 — workflow ставит npm 11.
5. Задать переменную `PUBLISH_TO_REGISTRIES=true` (Settings → Secrets and variables → Actions → Variables) и запустить **Publish** для нужного тега или опубликовать следующий релиз.

## Проверить скачанный релиз

```bash
sha256sum -c SHA256SUMS
gh attestation verify awesome_telegram_patterns-0.24.0-py3-none-any.whl --repo Zulut30/awesome-telegram-skills
python -m pip install ./awesome_telegram_patterns-0.24.0-py3-none-any.whl
npm install ./awesome-telegram-patterns-0.24.0.tgz
```
