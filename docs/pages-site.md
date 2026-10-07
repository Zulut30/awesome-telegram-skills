# Документация на GitHub Pages

Сайт: **https://zulut30.github.io/awesome-telegram-skills/**. Он собирается из канонических Markdown-файлов, YAML-метаданных скиллов и каталогов библиотеки; отдельные вручную поддерживаемые копии инструкций не нужны.

## Состав

- Отдельная страница каждого скилла: назначение, пример вызова, инструкции и локальные references.
- Руководства Python/TypeScript, группы компонентов, полный публичный API и исполняемые примеры.
- Галерея рецептов с кодом и связанными исходными файлами.
- Поиск по документации/API, мобильное меню, светлая/темная тема и копирование кода.
- `llms.txt`, `llms-full.txt`, `components.json` и `api-reference-index.json` для чтения агентом. Полный текст загружается по необходимости, а не для каждой узкой задачи.

## Локальная сборка

```powershell
python -m pip install -r requirements-docs.txt
python scripts/build_docs_site.py --source . --output output/docs-preview
python scripts/verify_docs_site.py --site output/docs-preview
python -m unittest discover -s site/tests -v
python -m http.server 4180 --bind 127.0.0.1 --directory output/docs-preview
```

Откройте http://127.0.0.1:4180. Для повторной сборки выберите новый каталог; builder сохраняет существующий output. `--check` пересобирает во временный каталог и сравнивает результат, не меняя прежние файлы. Тесты помощников действительно собирают сайт в временном каталоге, проверяют отказ перезаписи, обнаружение измененного artifact и запрет публикации непринятой версии. Для тестов из отдельного принятого snapshot задайте `DOCS_SOURCE` его абсолютным путем.

Источник должен соответствовать принятой версии с `passed: true` в сохраненной приемке. Если рабочий checkout содержит незавершенную следующую версию, собирайте документацию из чистого принятого Git-снимка. Локальные логи `output/` и credentials не входят в сайт.

## Публикация

Сборку и проверки сайта (тесты `site/tests`, `build_docs_site.py`, `verify_docs_site.py`, браузерные сценарии в Chromium) выполняет один reusable workflow `.github/workflows/docs-site.yml`. Его вызывают задача `docs-site` в `Repository checks` для каждого pull request и push (она входит в обязательную `required`) и workflow `.github/workflows/docs-pages.yml`, который запускается только из `main` или вручную: он собирает сайт тем же workflow, загружает Pages-artifact и публикует его в environment `github-pages`. Публикации идут по одной в группе `pages` с `cancel-in-progress: false`: начатый deploy не прерывается, новый push ждет его завершения (из нескольких ожидающих остается последний). Изменение документации не публикует Python/npm-пакеты.

Проверка HTML/поиска и браузерных размеров относится к сайту документации; она не является приемкой настоящего Mini App на физических устройствах Telegram.

## Проверенные источники

6 октября 2026 года сверены [custom workflows GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), 7 октября 2026 года — [reusable workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations) (вызов `./.github/workflows/...` из того же коммита, права токена только понижаются) и группа concurrency `pages` из [официального шаблона Pages](https://github.com/actions/starter-workflows/blob/main/pages/static.yml), [Pages API](https://docs.github.com/en/rest/pages/pages#create-a-github-pages-site) и [расширения Python-Markdown](https://python-markdown.github.io/extensions/). Actions в workflow закреплены по commit SHA официальных release tags. Дата относится к сборке/публикации этого сайта, а не ко всем Telegram-источникам репозитория.
