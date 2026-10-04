# Рецепты и API каталог 0.4.0

4 октября 2026. Два независимых локальных пакета, двадцать одна группа компонентов. Цель выпуска — готовые раскладки клавиатур и ввод, обработка Bot API событий, поиск и построение запросов всех SDK методов, native Mini App API с явными capability gates. [Начать с рецептов](../recipes/README.md).

## Что реализовано

| Область | Исполняемый код / примеры | Граница |
| --- | --- | --- |
| Inline/reply/input | inline_keyboard, reply_keyboard, input_prompt, remove_keyboard; two/three/mixed/colors в keyboards_bot.py | Snapshot native models, style/emoji fallback/часть context checks; права, реальные ID и пользовательский ответ проверяет host |
| События и меню | UpdateObserver, event_router; demo ACK → owner-bound edit, request data и reply_to binding | Best-effort metadata, не durable inbox/audit; SDK handled не означает успешный business effect |
| Bot API 10.3 | method_catalog/build_request, 185 отдельных request-рецептов; 400 native SDK типов сопоставлены с источником | Request construction/serialization без HTTP, не все semantic constraints и бизнес-сценарии Telegram |
| Mini App | 99 native функций, 44 события, каталог properties; TelegramNativeAPI; popup/location compositions | Literal пути/события типизированы, параметры/результаты unknown; native init/permissions/order/SDK callback semantics остаются явными |
| Остальной проект | Формы, HMAC, SQLite, commands/catalog, bridge/network/draft/responsive shell предыдущих версий | Сохраняются опубликованные контракты; external providers и MTProto — отдельные задачи |

Для Mini App facade проверяет версию и существующий function/owner, сохраняет receiver и callback identity. Подписки получают отдельный wrapper, принадлежат adapter, выключаются при unsubscribe/dispose; неуспешный native cleanup можно повторить, поздние callbacks подавлены. Прямые вызовы onClick/onEvent через call требуют caller-owned off. Адаптер не аутентифицирует пользователя и не подтверждает разрешение capability.

Демо бота предназначено для тестового token, явно устанавливает default command menu и не удаляет webhook. Меню/ожидания хранятся в памяти одного процесса и сбрасываются при рестарте; edit lock не является multi-worker гарантией. Частные business actions/durable operations требуют собственного сервиса. Контакты/геопозиция не сохраняются в демо и не копируются в observer. Bots не получают произвольные user typing/read receipts/URL/copy clicks и историю аккаунта.

## Воспроизведение

```powershell
npm.cmd ci
python scripts/verify_pattern_packages.py
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests -v
```

verify строит wheel/tarball и использует отдельные core/SDK/TypeScript consumer-проекты вне checkout: installed imports/declarations/CSS, пакетные тесты, offline catalog/form/keyboards Dispatcher, generated-catalog check, самостоятельно скопированный code-patterns skill, strict typecheck и исполнение popup/location рецептов. Generator проверен на реальной записи/check/drift во временном repository. Browser matrix охватывает 7 размеров и две темы; это browser UI proof, не физический Telegram-клиент.

Проверка прошла: **70 Python тестов**, **21 TypeScript тест**, 185 executable request-рецептов построены и сериализованы SDK, 400 типов сопоставлены с официальным индексом, 99 native paths и 44 события проверены mock-контрактами. Keyboard Dispatcher получил 16 synthetic updates / 32 metadata traces; проверены ACK → edit, duplicate no-op, чужой actor, reply text, contact/users_shared, bound ForceReply, copy/disabled/remove. Popup/location consumer проверил unavailable/denied/cancelled/error/success, повтор init/callback и подавление позднего callback после dispose. Copied skill: 5 Markdown-файлов со всеми локальными references, 2 Python блока исполнены через установленный wheel.

Chrome 154.0.8037.97: **141 browser check**, 14 viewport/theme cases (7 размеров × 2 темы), без горизонтального переполнения, с labels/focus/error и сохранением полей при theme/resize; отдельно потерянный HTTP ответ не удвоил business effect mock backend. Core установлен без aiogram; SDK consumer имеет aiogram 3.31.0. Дополнительно прошли 16 root unittest и структурная проверка 41 навыка.

Доказательства: [distribution-report.json](../output/pattern-library-0.4.0/distribution-report.json), [Python tests](../output/pattern-library-0.4.0/python-tests.log), [keyboard scenario](../output/pattern-library-0.4.0/offline-keyboards.log), [native consumer](../output/pattern-library-0.4.0/native-example-test.log), [copied recipe](../output/pattern-library-0.4.0/portable-keyboard-recipe.log), [browser report](../output/pattern-library-0.4.0/browser/report.json). Артефакты wheel/tarball и их SHA256 перечислены в distribution report; временные installed consumer-проекты сохранены по указанному там пути. Registry publication не выполнялась.

Source/SDK checks и выполнение copied reference — практическая проверка инструкций/кода, а не независимый полный аудит решений AI-агента. Telegram delivery, конкретные emoji entitlement, permissions всех методов, real device/network/keyboard behavior, provider sandbox и пользовательский MTProto не проверялись этим выпуском. Уровни покрытия перечислены в catalog, а не заменены общим ярлыком «все работает».

## Поддержание каталога

Официальные HTML сохранены в output/telegram-source-2026-10-04, source SHA256 содержатся в catalog. Обновление без Telegram вызовов:

```powershell
python .agents/skills/telegram-bot-api/scripts/update_api_index.py --html-file output/telegram-source-2026-10-04/bot-api.html
uv run --with-editable "./packages/python[aiogram]" python scripts/build_telegram_catalog.py --mini-app-html output/telegram-source-2026-10-04/mini-app.html
uv run --with-editable "./packages/python[aiogram]" python scripts/build_telegram_catalog.py --check
```

Для нового снимка сохраняйте официальный HTML, меняйте его path и дату фактической сверки в generator/source metadata. `--check` использует сохраненный metadata index без сети. Расхождение официальных methods/fields с SDK или новый неизвестный native module останавливает генерацию. Искусственные request data в recipes/fixtures — файлы/ID-заглушки; сборка recipe не делает их пригодными для отправки.

Источники: [Bot API](https://core.telegram.org/bots/api), [Mini Apps native API](https://core.telegram.org/bots/webapps#initializing-mini-apps), [события](https://core.telegram.org/bots/webapps#events-available-for-mini-apps), установленный aiogram 3.31.0.
