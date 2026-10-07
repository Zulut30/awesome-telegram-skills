# Локальная галерея

Опубликованная версия с тем же содержимым: [https://zulut30.github.io/awesome-telegram-skills/recipes/](https://zulut30.github.io/awesome-telegram-skills/recipes/). Этот каталог нужен для просмотра без интернета и для экспорта.

Открой [index.html](index.html) в браузере: поиск, фильтры по задаче, контексту чата, SDK/версии, зрелости и проверке, код и клавиатурное превью. [Описание навигации](../docs/gallery-navigation.md) объясняет поиск «две кнопки», «назад» и «потерянный ответ», ограничения фильтров и ссылки на исходники. Статические CSS/JS расположены рядом; токены, npm install и сервер для просмотра не нужны. При желании из этого каталога можно запустить `python -m http.server 4174 --bind 127.0.0.1` и открыть http://127.0.0.1:4174.

В снимке 0.12.0: 299 записей, из них 196 SDK-построений, четыре mock-сценария, 99 справочных фрагментов и ноль live проверок. Native Mini App fragments требуют аргументов и собственного приложения. Превью показывает пример раскладки; не подтверждает доставку или внешний вид настоящего Telegram.

Генерация из корня репозитория с установленным локальным пакетом и aiogram extra:

```powershell
uv run --with-editable "./packages/python[aiogram]" python scripts/build_recipe_gallery.py
uv run --with-editable "./packages/python[aiogram]" python scripts/build_recipe_gallery.py --check
```

Генератор выполняет только собственные known fixtures и четыре offline сценария, не Markdown-код из API каталога и не Telegram HTTP. Сохраняет `catalog/recipe-gallery.json`, wheel resource и HTML с одним снимком. `--output-dir` пишет отдельную галерею и копирует связанные исходники и код проверки в `files/`, поэтому ссылки работают после переноса экспорта. `--check` проверяет совпадение и не перезаписывает файлы. [CLI и полная проверка](../docs/internal/developer-tools-review.md).
