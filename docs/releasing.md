# Выпуск версий

Каждая версия библиотеки отмечена аннотированным git-тегом `vX.Y.Z` на коммите, который ее ввел. По тегу [workflow Release](../.github/workflows/release.yml) собирает Python wheel, npm tarball и `SHA256SUMS` и публикует их в GitHub Release. Пока пакеты не опубликованы в PyPI и npm, релиз — основной источник установки.

## Как собирается релиз

[`scripts/build_release.py`](../scripts/build_release.py) экспортирует дерево тега через `git archive`, поэтому незакоммиченные файлы рабочей копии в релиз не попадают. `SOURCE_DATE_EPOCH` равен времени коммита, поэтому две сборки одного тега с одинаковыми версиями инструментов дают побайтно одинаковые файлы. Версии зависимостей сборки заданы `package-lock.json` тега и диапазоном setuptools в `pyproject.toml`; `build` закреплен в workflow.

```bash
python -m pip install 'build==1.3.0'
python scripts/build_release.py --ref v0.24.0 --output dist/v0.24.0
python scripts/build_release.py --ref v0.24.0 --notes
```

Заметки к релизу берутся из текущего `CHANGELOG.md`: раздел `## X.Y.Z` либо пункты вида `Пункт NNN, X.Y.Z: …`. Все релизы 0.x помечаются как prerelease.

## Выпустить новую версию

1. Обновите версию в `packages/python/pyproject.toml`, `packages/typescript/package.json`, `components.json`, `resources/recipes.json` и раздел CHANGELOG.
2. После слияния в `main` поставьте тег на этот коммит и отправьте его:

   ```bash
   git tag -a v0.25.0 -m "awesome-telegram-patterns 0.25.0"
   git push origin v0.25.0
   ```

3. Workflow Release соберет артефакты из тега и опубликует релиз.

## Релизы для существующих тегов

Версии 0.5.0–0.24.0 и коммиты, которые их ввели, перечислены в [`.github/release-tags.json`](../.github/release-tags.json). После слияния workflow в `main` запустите **Actions → Release → Run workflow** с пустым полем `tags`: ручной запуск создаст недостающие аннотированные теги из этого списка (проверив версию в `pyproject.toml` коммита) и опубликует все теги без релиза. Чтобы пересобрать конкретные версии, перечислите их через пробел. Теги, созданные через `GITHUB_TOKEN`, не запускают другие workflow — публикация идет в том же запуске.

## Проверить скачанный релиз

```bash
sha256sum -c SHA256SUMS
python -m pip install ./awesome_telegram_patterns-0.24.0-py3-none-any.whl
npm install ./awesome-telegram-patterns-0.24.0.tgz
```
