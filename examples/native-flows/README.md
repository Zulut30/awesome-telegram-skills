# Native flows: локальный fake SDK

Небольшой пример использует public main imports, typed native wrappers и
доступные DOM-альтернативы. Платформа/версия/launch выбираются явно для fixture;
это не проверка устройства, разрешения, Telegram auth, Serverless или оплаты.
Кнопки выполняют только fake callbacks. Внешние ссылки не запрашиваются автоматически.

```sh
npm run build -w @awesome-telegram/patterns
node examples/native-flows/server.mjs
```

Откройте напечатанный loopback URL. Contact/QR/location при отказе или недоступности
открывают ручное поле; file picker использует обычный HTML input. Значения storage,
биометрический token, initData и endpoint errors не выводятся в UI.

```sh
node --test packages/typescript/tests/native-flows.test.mjs
node node_modules/typescript/bin/tsc --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess --target ES2022 --module NodeNext --moduleResolution NodeNext --outDir output/production-run-2026-11-05/native-flows/reference --rootDir examples/api-reference/typescript examples/api-reference/typescript/flows.ts
node packages/typescript/tests/native-flows-browser.mjs
```

Вторая команда собирает public consumer fixture, который браузерный runner также
исполняет. Нужны установленные dev dependencies и Chrome или `CHROME_PATH`.
На Windows используйте `npm.cmd` вместо `npm`, если PowerShell блокирует npm.ps1.

Поздние callbacks и неизвестный исход проверяются детерминированно также в Node.
Браузерная матрица — fake SDK в локальном Chrome, device/native acceptance not run.
