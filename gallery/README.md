# Локальная галерея

Открой [index.html](index.html) в браузере: поиск, категории, уровни проверки, код и клавиатурное превью. Статические CSS/JS расположены рядом; токены, npm install и сервер для просмотра не нужны. При желании из этого каталога можно запустить `python -m http.server 4174 --bind 127.0.0.1` и открыть http://127.0.0.1:4174.

В снимке 0.5.0: 298 записей, из них 196 SDK-построений, три mock-сценария, 99 справочных фрагментов и ноль live проверок. Native Mini App fragments требуют аргументов и собственного приложения. Превью показывает пример раскладки; не подтверждает доставку или внешний вид настоящего Telegram.

Генерация из корня репозитория с установленным локальным пакетом и aiogram extra:

```powershell
uv run --with-editable "./packages/python[aiogram]" python scripts/build_recipe_gallery.py
uv run --with-editable "./packages/python[aiogram]" python scripts/build_recipe_gallery.py --check
```

Генератор выполняет только собственные known fixtures и три offline сценария, не Markdown-код из API каталога и не Telegram HTTP. Сохраняет `catalog/recipe-gallery.json`, wheel resource и HTML с одним снимком. `--output-dir` пишет отдельную галерею в указанный каталог; `--check` проверяет совпадение и не перезаписывает файлы. [CLI и полная проверка](../docs/developer-tools-review.md).
