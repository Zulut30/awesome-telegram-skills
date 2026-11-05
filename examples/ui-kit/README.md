# Локальная галерея UI

Framework-neutral компоненты и шесть композиций: каталог, товар, корзина, профиль,
настройки и запись. `screens.ts` принимает сервисы с load/verified scope; сервис
настроек получает save. Бизнес-правила, DTO validation и unknown/reconciliation
остаются у проекта. `main.ts` — явно учебный источник данных, без auth/платежей.

После установки зависимостей checkout:

```sh
npm run build -w @awesome-telegram/patterns
node node_modules/typescript/bin/tsc -p examples/ui-kit/tsconfig.json
node examples/ui-kit/server.mjs
```

Откройте адрес, напечатанный сервером. Импортируйте styles.css, затем tokens.css.
Никаких внешних шрифтов, CDN, изображений, Telegram token или платных сервисов.
Server предназначен только для loopback разработки и завершается Ctrl+C.

```sh
node node_modules/typescript/bin/tsc --strict --target ES2022 --module NodeNext --moduleResolution NodeNext --outDir examples/ui-kit/dist/reference --rootDir examples/api-reference/typescript examples/api-reference/typescript/ui.ts
node packages/typescript/tests/ui-browser.mjs
```

Browser runner сохраняет отчёт и synthetic screenshots в ignored output.
Это не утверждённые visual baselines, не device/keyboard/screen-reader приёмка.


Проверка установленного tarball выполняется отдельно от checkout-сборки:

```sh
python scripts/verify_ui_example.py --tarball output/pattern-library-0.28.0/dist/awesome-telegram-patterns-0.28.0.tgz --output output/ui-installed
```

Нужны Node/npm, зависимости checkout (`npm ci`) и Chrome либо `CHROME_PATH`.
Помощник устанавливает переданный пакет, закрепленные TypeScript и axe в новый
временный consumer за пределами репозитория. Он копирует `main.ts`, `screens.ts`
и пример публичного API, проверяет строгие типы и использует `index.js`,
`styles.css`, `tokens.css`, разрешённые через exports установленного пакета.
Входной архив и публичные файлы связаны SHA-256; существующий output сохраняется.
Отчёт содержит 35 проверок взаимодействий, 96 проверок компоновки и 24 axe-состояния,
включая неполные результаты axe. Утверждённых визуальных эталонов, физических
устройств, системных клавиатур и screen reader эта проверка не заменяет.
