# Источники и актуальность

Страница из двух частей. Таблица «Скиллы» показывает, что, когда и на какой версии проверено в каждом скилле; ее строит `python scripts/check_skill_sources.py --table docs/sources.md` из раздела «Источники» каждого `SKILL.md`, а `tests/test_skill_sources.py` сверяет ее с файлами. «Журнал проверок» перечисляет сверки при изменениях набора и библиотеки, от новых к старым. Дата относится только к перечисленному содержимому и не обещает совместимость с любой установленной версией.

## Скиллы

<!-- skills-table:start -->
| Скилл | Проверено | Что сверено | Первичные источники |
| --- | --- | --- | --- |
| `telegram-admin-panel` | 2026-10-07 | не зависит от версии Bot API | [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Telegram Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app) |
| `telegram-ai-bot` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [sendMessageDraft](https://core.telegram.org/bots/api#sendmessagedraft), [MessageGenerationStopped](https://core.telegram.org/bots/api#messagegenerationstopped), [Bot API changelog](https://core.telegram.org/bots/api-changelog) |
| `telegram-bot-api` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Telegram Bot API](https://core.telegram.org/bots/api), [FAQ](https://core.telegram.org/bots/faq) |
| `telegram-bot-python` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [aiogram](https://docs.aiogram.dev/en/latest/), [python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/), [pyTelegramBotAPI](https://pytba.readthedocs.io/en/latest/), [Bot API](https://core.telegram.org/bots/api) |
| `telegram-business-bots` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Business-боты](https://core.telegram.org/bots/features#business-bots), [BusinessConnection](https://core.telegram.org/bots/api#businessconnection), [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights) |
| `telegram-buttons` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [DisabledButton](https://core.telegram.org/bots/api#disabledbutton), [answerCallbackQuery](https://core.telegram.org/bots/api#answercallbackquery), [getCustomEmojiStickers](https://core.telegram.org/bots/api#getcustomemojistickers) |
| `telegram-code-patterns` | 2026-10-07 | awesome-telegram-patterns 0.24.0, Bot API 10.3, aiogram 3.31.0 | [Bot API](https://core.telegram.org/bots/api) |
| `telegram-cryptopay` | 2026-10-02 | Crypto Pay API; 7 октября 2026 года официальная страница отвечает 403 на автоматические запросы, повторная сверка не выполнена | [Crypto Pay API](https://help.send.tg/en/articles/10279948-crypto-pay-api), [Telegram Stars и внешние платежи](https://core.telegram.org/bots/payments-stars) |
| `telegram-debugging` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Bot FAQ](https://core.telegram.org/bots/faq), [webhook guide](https://core.telegram.org/bots/webhooks), [Mini Apps](https://core.telegram.org/bots/webapps), [Bot API](https://core.telegram.org/bots/api) |
| `telegram-deploy` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Telegram webhook guide](https://core.telegram.org/bots/webhooks), [Bot API](https://core.telegram.org/bots/api), [Mini Apps](https://core.telegram.org/bots/webapps) |
| `telegram-dialogs` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [aiogram FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/), [CallbackQuery](https://core.telegram.org/bots/api#callbackquery) |
| `telegram-groups` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Bot FAQ: группы и privacy mode](https://core.telegram.org/bots/faq), [возможности ботов](https://core.telegram.org/bots/features), [Bot API](https://core.telegram.org/bots/api) |
| `telegram-inline-mode` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Inline bots](https://core.telegram.org/bots/inline), [answerInlineQuery](https://core.telegram.org/bots/api#answerinlinequery) |
| `telegram-library-selection` | 2026-10-07 | aiogram 3.31.0, python-telegram-bot 22.8, pyTelegramBotAPI 4.37.0, Telethon 1.45.0 (PyPI) | [aiogram](https://pypi.org/project/aiogram/), [python-telegram-bot](https://pypi.org/project/python-telegram-bot/), [pyTelegramBotAPI](https://pypi.org/project/pyTelegramBotAPI/), [Telethon](https://pypi.org/project/Telethon/), [Bot API changelog](https://core.telegram.org/bots/api-changelog) |
| `telegram-localization` | 2026-10-07 | Bot API 10.3 | [Telegram User](https://core.telegram.org/bots/api#user), [Intl](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl), [Bot formatting](https://core.telegram.org/bots/api#formatting-options) |
| `telegram-media-processing` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Telegram Bot API](https://core.telegram.org/bots/api), [FFmpeg documentation](https://ffmpeg.org/documentation.html), [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) |
| `telegram-mini-app-architecture` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram Mini Apps](https://core.telegram.org/bots/webapps), [Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines) |
| `telegram-mini-app-auth` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Проверка данных Mini App](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), [WebAppInitData](https://core.telegram.org/bots/webapps#webappinitdata) |
| `telegram-mini-app-design-system` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines), [WAI-ARIA patterns](https://www.w3.org/WAI/ARIA/apg/patterns/), [WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) |
| `telegram-mini-app-device-qa` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram Mini Apps](https://core.telegram.org/bots/webapps), [тестовая среда](https://core.telegram.org/bots/webapps#using-bots-in-the-test-environment) |
| `telegram-mini-app-integration` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Mini Apps: способы запуска](https://core.telegram.org/bots/webapps#implementing-mini-apps), [deep linking](https://core.telegram.org/bots/features#deep-linking), [Bot API](https://core.telegram.org/bots/api) |
| `telegram-mini-app-native-capabilities` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram client API](https://core.telegram.org/bots/webapps#initializing-mini-apps), [events](https://core.telegram.org/bots/webapps#events-available-for-mini-apps) |
| `telegram-mini-app-network-recovery` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [navigator.onLine](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine), [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API), [Telegram Mini Apps](https://core.telegram.org/bots/webapps) |
| `telegram-mini-app-performance` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Web Vitals](https://web.dev/articles/vitals), [Telegram Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines) |
| `telegram-mini-app-typescript` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram Mini Apps](https://core.telegram.org/bots/webapps), [TypeScript strict](https://www.typescriptlang.org/tsconfig/strict.html), [Vite env](https://vite.dev/guide/env-and-mode) |
| `telegram-mini-app-ui` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram Mini Apps](https://core.telegram.org/bots/webapps) |
| `telegram-mini-app-ux` | 2026-10-07 | Telegram Mini Apps (Bot API 10.3) | [Telegram Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines), [WAI Forms](https://www.w3.org/WAI/tutorials/forms/) |
| `telegram-mini-app-visual-regression` | 2026-10-07 | Playwright 1.63.0; не зависит от версии Bot API | [Playwright Visual comparisons](https://playwright.dev/docs/test-snapshots) |
| `telegram-notifications` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Bot FAQ: broadcasting](https://core.telegram.org/bots/faq#broadcasting-to-users), [ResponseParameters](https://core.telegram.org/bots/api#responseparameters), [Mini App requestWriteAccess](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `telegram-observability` | 2026-10-07 | не зависит от версии Bot API | [OpenTelemetry sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/), [Python contextvars](https://docs.python.org/3/library/contextvars.html), [Bot API](https://core.telegram.org/bots/api) |
| `telegram-payment-provider` | 2026-10-07 | Bot API 10.3, документация Robokassa и Stripe; поля другого провайдера сверяйте по его документации | [Bot Payments](https://core.telegram.org/bots/payments), [Telegram Stars](https://core.telegram.org/bots/payments-stars), [Stripe Webhooks](https://docs.stripe.com/webhooks), [Stripe API](https://docs.stripe.com/api), [Robokassa](https://docs.robokassa.ru/) |
| `telegram-payments` | 2026-10-07 | Bot API 10.3, Telegram Stars | [Telegram Stars](https://core.telegram.org/bots/payments-stars), [Bot Payments](https://core.telegram.org/bots/payments), [Bot API: Payments](https://core.telegram.org/bots/api#payments) |
| `telegram-platega` | 2026-10-07 | API Platega | [Документация Platega](https://docs.platega.io/), [Telegram Stars и внешние платежи](https://core.telegram.org/bots/payments-stars) |
| `telegram-profiles` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [User](https://core.telegram.org/bots/api#user), [getUserProfilePhotos](https://core.telegram.org/bots/api#getuserprofilephotos), [setMyDescription](https://core.telegram.org/bots/api#setmydescription), [Business-боты](https://core.telegram.org/bots/features#business-bots) |
| `telegram-project-planner` | 2026-10-07 | не зависит от версии Bot API | [Возможности ботов](https://core.telegram.org/bots/features), [создание первого бота](https://core.telegram.org/bots/tutorial), [Mini Apps](https://core.telegram.org/bots/webapps) |
| `telegram-python-backend` | 2026-10-07 | не зависит от версии Bot API | [FastAPI async](https://fastapi.tiangolo.com/async/), [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html), [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html) |
| `telegram-security-review` | 2026-10-07 | Bot API 10.3, Telegram Mini Apps | [Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), [Bot API webhook](https://core.telegram.org/bots/api#setwebhook), [Stars payments](https://core.telegram.org/bots/payments-stars) |
| `telegram-subscription-access` | 2026-10-07 | Bot API 10.3, Telegram Stars | [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment), [Stars payments](https://core.telegram.org/bots/payments-stars) |
| `telegram-testing` | 2026-10-07 | Bot API 10.3, aiogram 3.31.0 | [Bot API](https://core.telegram.org/bots/api), [тестовая среда Mini Apps](https://core.telegram.org/bots/webapps#using-bots-in-the-test-environment), [Testing your bot](https://core.telegram.org/bots/features#testing-your-bot), [Stars в тестовом окружении](https://core.telegram.org/bots/payments-stars) |
| `telegram-user-client` | 2026-10-07 | Telethon 1.45.0, MTProto | [Telethon](https://docs.telethon.dev/en/stable/), [MTProto API](https://core.telegram.org/api), [Business-боты](https://core.telegram.org/bots/features#business-bots) |
| `telegram-web-login` | 2026-10-07 | Telegram Login (OIDC) | [Telegram Login](https://core.telegram.org/bots/telegram-login), [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html) |
| `telegram-yookassa` | 2026-10-07 | API ЮKassa v3 | [API ЮKassa](https://yookassa.ru/developers/using-api/interaction-format), [уведомления](https://yookassa.ru/developers/using-api/webhooks), [Bot Payments](https://core.telegram.org/bots/payments) |
<!-- skills-table:end -->

## Общие первичные источники

| Область | Первичный источник |
| --- | --- |
| Методы, типы и changelog | [Telegram Bot API](https://core.telegram.org/bots/api) |
| Возможности ботов и deep links | [Bot features](https://core.telegram.org/bots/features) |
| Создание и старт бота | [Bot tutorial](https://core.telegram.org/bots/tutorial) |
| Доставка, privacy mode, ограничения | [Bot FAQ](https://core.telegram.org/bots/faq) |
| Inline mode | [Inline bots](https://core.telegram.org/bots/inline) |
| Webhook и публичный endpoint | [Webhook guide](https://core.telegram.org/bots/webhooks) |
| WebView, запуск, bridge, initData | [Telegram Mini Apps](https://core.telegram.org/bots/webapps) |
| Цифровые товары и Stars | [Stars payments](https://core.telegram.org/bots/payments-stars) |
| Физические товары и провайдеры | [Bot Payments API](https://core.telegram.org/bots/payments) |
| Python: aiogram | [aiogram](https://docs.aiogram.dev/en/latest/), [FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [WebApp utils](https://docs.aiogram.dev/en/latest/utils/web_app.html) |
| Python: python-telegram-bot | [python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/) |
| TypeScript Mini Apps | [TypeScript strict](https://www.typescriptlang.org/tsconfig/strict.html), [Vite env](https://vite.dev/guide/env-and-mode) |
| Скиллы в ChatGPT и Codex | [Build skills](https://learn.chatgpt.com/docs/build-skills); прежний адрес developers.openai.com/codex/skills перенаправляет сюда |

Индекс Bot API создается помощником внутри навыка и содержит source URL, retrieval timestamp и SHA256 HTML. Он не копирует описания API и не доказывает поддержку всех методов каждой библиотекой.

## Как обновлять

При изменении функции откройте относящийся к ней официальный источник, проверьте version gate и поддержку SDK. Обновите только затронутые инструкции и сценарии проверки. Не копируй целиком API-справочник в навыки: это быстро устаревает и увеличивает контекст.

Ссылки `latest` и `stable` меняются. Для существующего проекта используйте документацию установленной версии. При отсутствии сети сохраните полезную работу, но пометь непроверенные правила, параметры или совместимость.

Обновлять общую дату можно после повторной проверки всего указанного набора. Для частичного обновления укажите отдельно источник, дату и измененный инвариант в соответствующей reference.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.

Изменения Bot API и Mini Apps отслеживает еженедельный workflow `.github/workflows/telegram-docs-watch.yml`. Задача Bot API пересобирает индекс со страницы core.telegram.org и сравнивает `scripts/diff_api_index.py` версию, имена методов и типов и их поля с индексом в репозитории. Задача Mini Apps строит `scripts/mini_app_index.py` индекс методов и событий с их `min_version` и свойств и сравнивает его `scripts/diff_mini_app_index.py` с `catalog/mini-app-index.json`; метод нового модуля без указанной в документации версии попадает в отчет с пометкой «версия не указана». SHA-256 страниц меняется при каждой пересборке и не сравнивается. При изменении открывается issue со списком новых, удаленных и измененных элементов; одно и то же изменение не дублируется.

## Журнал проверок

### 2026-10-07 — пункт 52

Прочитана текущая [страница Mini Apps](https://core.telegram.org/bots/webapps): по сравнению с индексом от 4 октября появился объект [`WebApp.Serverless`](https://core.telegram.org/bots/webapps#serverless) с пометкой NEW и методом `call(name[, input][, callback])` — вызов серверных функций бота на Telegram Serverless; платформа сама проверяет initData перед вызовом, ошибка — объект с полями `message`, `type` (`ENDPOINT_ERROR`, `UNAUTHORIZED` и другие), `status`, `parameters`. В «Recent changes» и в описании нет версии Bot API, с которой метод доступен, поэтому в каталог библиотеки (`TELEGRAM_NATIVE_METHODS`) он не добавлен: без минимальной версии `supports()` не может его проверить. Еженедельная сверка сообщает о нем как о новом методе с неуказанной версией. Остальные методы, события и их версии совпали с индексом.

### 2026-10-07 — пункт 50

Старый адрес документации Codex `https://developers.openai.com/codex/skills/` перенаправляет на [Build skills](https://learn.chatgpt.com/docs/build-skills) (страница о скиллах в ChatGPT и Codex: прогрессивная загрузка `SKILL.md` по имени и описанию); ссылка в общих источниках заменена.

### 2026-10-07 — пункт 48

Для `telegram-buttons` по Bot API 10.3 сверены [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton) (`style`: `danger`, `success`, `primary`; `icon_custom_emoji_id`; `disabled`), [DisabledButton](https://core.telegram.org/bots/api#disabledbutton), [answerCallbackQuery](https://core.telegram.org/bots/api#answercallbackquery) и стиль `link` у `RichMessageButton` (только callback-кнопки); в установленном aiogram 3.31.0 — модели кнопок, `ButtonStyle` и итоговый JSON.

Для `telegram-library-selection` получены данные PyPI: aiogram 3.31.0, python-telegram-bot 22.8, pyTelegramBotAPI 4.37.0, Telethon 1.45.0, yookassa 3.13.0, aiocryptopay 0.4.8 — версии, даты релизов, требуемый Python, лицензии и число релизов за 12 месяцев; поддерживаемый Bot API — из `aiogram.__api_version__`, описания python-telegram-bot на PyPI и README pyTelegramBotAPI.

Для `telegram-payment-provider` прочитаны Robokassa: [интерфейс оплаты](https://docs.robokassa.ru/ru/pay-interface), [уведомления](https://docs.robokassa.ru/ru/notifications-and-redirects), [XML-интерфейсы](https://docs.robokassa.ru/ru/xml-interfaces) (`OpStateExt` и коды состояний), [API возвратов](https://docs.robokassa.ru/ru/refund-api), [холдирование](https://docs.robokassa.ru/ru/holding), [тестовый режим](https://docs.robokassa.ru/ru/testing-mode); Stripe: [webhooks](https://docs.stripe.com/webhooks) и [idempotent requests](https://docs.stripe.com/api/idempotent_requests). Пример подписи ResultURL проверен на примере из документации.

Для `telegram-user-client` сверены сигнатуры установленного Telethon 1.45.0: `iter_messages`, `flood_sleep_threshold` (60), `catch_up` (по умолчанию `False`), `FloodWaitError.seconds`, `events.MessageDeleted`.

### 2026-10-07 — пункт 41

Пункт 41, 7 октября 2026: каждый `SKILL.md` сверен с текущей документацией и получил раздел «Источники» со строкой «Проверено». Индекс Bot API пересобран с сегодняшней страницы — 185 методов и 400 типов совпали с сохраненным индексом 10.3; индекс Mini Apps совпал по 99 методам, 44 событиям и 68 свойствам, новым оказался только объект `WebApp.Serverless` (вызов серверных функций бота, initData проверяет платформа; в changelog Mini Apps его пока нет). Все 69 имен Telegram из `SKILL.md` есть в индексах, 75 ссылок и их якоря открываются. Сверены ключевые факты [Telegram Stars](https://core.telegram.org/bots/payments-stars), [Bot Payments](https://core.telegram.org/bots/payments), [FAQ](https://core.telegram.org/bots/faq) (лимиты рассылки и paid broadcasts), [webhooks](https://core.telegram.org/bots/webhooks), [inline](https://core.telegram.org/bots/inline), [Telegram Login](https://core.telegram.org/bots/telegram-login) (OIDC, JWKS, PKCE S256), [Platega](https://docs.platega.io/) (заголовки и статусы callback), [ЮKassa](https://yookassa.ru/developers/using-api/webhooks) (Idempotence-Key, события уведомлений) и [Telethon](https://docs.telethon.dev/en/stable/) (FloodWaitError); версии PyPI: aiogram 3.31.0, python-telegram-bot 22.8, pyTelegramBotAPI 4.37.0, Telethon 1.45.0. [Crypto Pay API](https://help.send.tg/en/articles/10279948-crypto-pay-api) отвечает 403 на автоматические запросы, поэтому у `telegram-cryptopay` осталась дата прошлой сверки, 2026-10-02.

### 2026-10-07 — пункт 40

Пункт 40, 7 октября 2026: для `telegram-ai-bot` и рецепта `demo-ai-stream` сверены [sendMessageDraft](https://core.telegram.org/bots/api#sendmessagedraft), [sendRichMessageDraft](https://core.telegram.org/bots/api#sendrichmessagedraft), [MessageGenerationStopped](https://core.telegram.org/bots/api#messagegenerationstopped), `allowed_updates` в [getUpdates](https://core.telegram.org/bots/api#getupdates) и [changelog](https://core.telegram.org/bots/api-changelog) Bot API 9.3, 9.5, 10.2 и 10.3; в установленном aiogram 3.31.0 проверены `SendMessageDraft`, `SendRichMessageDraft`, `MessageGenerationStopped` и `Update.stopped_message_generation`.

### 2026-10-05 — пункт 31

Пункт 031, 5 октября 2026: отдельно сверены aiogram 3.31.0 [storages/BaseStorage](https://docs.aiogram.dev/en/v3.31.0/dispatcher/finite_state_machine/storages.html), установленный шестипольный StorageKey/FSMContext и SQLite local CAS/transaction example. Scope — atomic state/data, schema/deadline/restart и nonpersistent MemoryStorage. [Dialog restart](dialog-restart.md) отделяет этот proof от distributed workers, live Telegram/device и business effects. Остальные даты источников не обновлены.

### 2026-10-05 — пункт 30

Проверены ровно 51 method-specific contract Bot API 10.3, Business/managed flow и installed aiogram 3.31.0 (native fields, nested multipart); [подробные условия и источники](platform-operations.md). Дата не обновляет остальной capability snapshot. Native SDK/mock не подтверждает live permissions, financial settlement или реальные устройства.

### 2026-10-05 — пункт 29: inline-поиск и опросы

Сверены только InlineQuery/answerInlineQuery/article/text content/feedback и sendPoll/Poll/PollAnswer/PollOptionAdded/Update/stopPoll с [Bot API](https://core.telegram.org/bots/api), [inline guide](https://core.telegram.org/bots/inline) и установленным aiogram 3.31.0. Проверка охватывает cache/offset/sharing, modern correct_option_ids/revoting/persistent IDs, расписание и ограничения событий; прежние даты других API не обновлены. Synthetic SDK/Dispatcher/SQLite не означает live/cache/client/provider acceptance.

### 2026-10-05 — пункт 28

2026-10-05 — пункт 028: только User/getMe, getChat/ChatFullInfo, getUserProfilePhotos, set/getMyName/Description/ShortDescription, set/removeMyProfilePhoto и InputProfilePhotoStatic/Animated в [Bot API](https://core.telegram.org/bots/api). Сверены installed aiogram 3.31.0 models, locale fields, nullable flags и native multipart. Scope — доступные observations, explicit own-bot patch и new JPG/MPEG4 bytes; source/time/Premium не дают app ACL. Business/MTProto, скрытые данные, profile audio/personal history, live permissions/codec и остальные API/payment sources не обновлялись.

### 2026-10-05 — пункт 27

2026-10-05 — пункт 027: повторно прочитаны sendPhoto/sendDocument/sendMediaGroup/editMessageMedia/getFile/Sending files в [Bot API](https://core.telegram.org/bots/api) и [aiogram download](https://docs.aiogram.dev/en/latest/api/download_file.html); сопоставлены installed aiogram 3.31.0 models, BaseSession.prepare_value и Bot.download_file. Проверены upload/photo dimensions, captions, album type/cardinality, inline upload restriction, bot-scoped file_id/file_unique_id, hosted download metadata/20 MB и local path boundary. Дата не обновляет весь каталог/API/device/provider evidence.

### 2026-10-05 — пункт 26

Пункт 026, 2026-10-05: только [formatting options](https://core.telegram.org/bots/api#formatting-options), [MessageEntity](https://core.telegram.org/bots/api#messageentity), [sendMessage](https://core.telegram.org/bots/api#sendmessage) Bot API 10.3: UTF-16 offsets, nesting, HTML/MarkdownV2 literal contexts, custom emoji fallback/entitlement и explicit entities/parse_mode. Actual installed aiogram 3.31.0 model + BaseSession.prepare_value проверяются fixture. Rich messages/date_time/all Bot API/live rendering/Unicode emoji registry этим источниковым проходом не приняты.

### 2026-10-05 — пункт 24

Для пункта 024 отдельно 5 октября 2026 года сверены [Python 3.13 zoneinfo](https://docs.python.org/3.13/library/zoneinfo.html), [datetime](https://docs.python.org/3/library/datetime.html), [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [tzdata](https://pypi.org/project/tzdata/), [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton) и [aiogram 3.31.0 DisabledButton](https://docs.aiogram.dev/en/v3.31.0/api/types/disabled_button.html). Scope: gap/fold, IANA data on Windows, BEGIN IMMEDIATE, native disabled versus fallback. Установлены aiogram 3.31.0 и tzdata 2026.5; детали — [calendar slots](calendar-slots.md). Это не live/device evidence; остальные даты Telegram/payment источников не обновлены.

### 2026-10-05 — пункт 21

Для пункта 021 отдельно 2026-10-05 проверены [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton) и [aiogram KeyboardBuilder](https://docs.aiogram.dev/en/dev-3.x/utils/keyboard.html): допустимые presentation поля/context и repeat/last adjust semantics. [Композиции](keyboard-layouts.md) используют явные host capability flags и native validation до fallback. Это частичная сверка; SDK/serializer/consumer не доказывают live client rendering или owner entitlement, даты остальных API не обновлены.

### 2026-10-05 — пункт 19

Для пункта 019 отдельно 2026-10-05 сверены [getChatMember](https://core.telegram.org/bots/api#getchatmember), [forum topics](https://core.telegram.org/bots/api#createforumtopic), [restrictChatMember](https://core.telegram.org/bots/api#restrictchatmember), [ChatJoinRequest](https://core.telegram.org/bots/api#chatjoinrequest), [assigned query queue](https://core.telegram.org/bots/api#answerchatjoinrequestquery), Update delivery и миграции Message. Scope — права конкретных операций, Bot API context, срок ограничения, версионирование наблюдаемой заявки и queue вместо автоматического approve. Установленный aiogram 3.31.0 подтверждает методы/types и event_update. [Групповой пример](group-bot.md) отдельно ограничен supergroup, private topic API не объявляется невозможным. SDK fixtures/file SQLite/crash не подтверждают live права или доставку; остальная дата источников не обновлена.

### 2026-10-05 — пункт 18

Для пункта 018 отдельно 2026-10-05 сверены [Stars digital flow](https://core.telegram.org/bots/payments-stars), [createInvoiceLink](https://core.telegram.org/bots/api#createinvoicelink), [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment), [Mini App signed data](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app) и [openInvoice](https://core.telegram.org/bots/webapps#initializing-mini-apps). Scope: XTR/пустой provider_token/один price, срок pre-checkout, серверное подтверждение, terms/paysupport, HMAC launch и callback/status distinction. Схема заказа, сессии/CSRF, receipt/access и неизвестная invoice-подготовка реализованы в отдельном [магазине](shop-example.md) с installed aiogram 3.31.0. Synthetic signed launch дополнительно сравнивается с aiogram parser; live Telegram Stars test environment и WebView cookies не объявлены проверенными. Остальные источники и общая дата каталога не обновлены.

### 2026-10-05 — пункт 17

Для пункта 017 отдельно 2026-10-05 сверены [aiogram BaseStorage/MemoryStorage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html), установленный aiogram 3.31.0 (StorageKey, startup/shutdown), [sendMessage](https://core.telegram.org/bots/api#sendmessage), [ResponseParameters retry_after](https://core.telegram.org/bots/api#responseparameters), [SQLite transaction control](https://docs.python.org/3.13/library/sqlite3.html#transaction-control) и [asyncio shield/to_thread](https://docs.python.org/3.13/library/asyncio-task.html#asyncio.shield). Scope — persistent application FSM, атомарный booking/replay/job, отсутствие sendMessage idempotency параметра, явный flood rejection и ожидание owned SQLite work перед unlock. Это частичная сверка сервисного примера, не обновление всех Telegram/payment источников. Код и границы — [service-bot](service-bot.md); synthetic transport не доказывает live доставку.

### 2026-10-05 — библиотека 0.18.0: смешанные поля диалога

Для mixed dialog fields библиотеки 0.18.0 отдельно 5 октября 2026 просмотрены [ForceReply](https://core.telegram.org/bots/api#forcereply), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [Document](https://core.telegram.org/bots/api#document), [Contact](https://core.telegram.org/bots/api#contact), [Location](https://core.telegram.org/bots/api#location) и [aiogram 3.31.0 FSM storage](https://docs.aiogram.dev/en/v3.31.0/dispatcher/finite_state_machine/storages.html). Scope: reply UI, private native request buttons, optional document/contact metadata, static/live location и host persistence. SDK version проверяется установленным consumer; email/phone/size limits являются политикой компонента. Сверка не обновляет весь Bot API, платежные страницы либо live/device acceptance.

### 2026-10-05 — библиотека 0.13.0

Библиотека 0.13.0: 5 октября 2026 частично сверены [Bot API](https://core.telegram.org/bots/api), create/editForumTopic, restrictChatMember и Business gift права; [Mini Apps](https://core.telegram.org/bots/webapps), contact/write access consent и clipboard launch/gesture; [Python -I](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I). SDK fixtures — installed aiogram 3.31.0. [Требования runner](recipe-execution.md) отделяют известные условия/SDK hints от полного live review; эта дата не обновляет другие Telegram/payment источники.

### 2026-10-04 — пункт 15

Для пункта 015 2026-10-04 отдельно сверены [create/editForumTopic](https://core.telegram.org/bots/api#createforumtopic), [restrictChatMember](https://core.telegram.org/bots/api#restrictchatmember), [channel subscription invite](https://core.telegram.org/bots/api#createchatsubscriptioninvitelink) и [Business gift rights](https://core.telegram.org/bots/api#getbusinessaccountgifts). Private/supergroup topics не сведены только к группам; undefined contexts не объявляются универсальными. Labels task служат поиску, не readiness/capability обещанию. Остальная дата каталога не менялась; installed SDK generation проверяет 3.31.0.

### 2026-10-04 — пункт 14

Для пункта 014 2026-10-04 проверен [официальный Compiler API guide](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API): примеры относятся к TypeScript <7. В установленном 7.0.2 по package exports и declarations проверены `typescript/unstable/sync` API/updateSnapshot/Project.checker, NodeHandle.resolve и AST node.forEachChild. Проверяющий скрипт использует этот закрепленный dev tool и закрывает snapshot/API; это не стабильный контракт TypeScript и не runtime dependency библиотеки. Telegram API в этом пункте не изменялся, даты остального набора источников не обновлялись.

### 2026-10-04 — пункт 13

Для пункта 013 отдельно 2026-10-04 проверены [pip install: interpreter/local archives](https://pip.pypa.io/en/stable/cli/pip_install/), [ensurepip: bootstrap без сети](https://docs.python.org/3.13/library/ensurepip.html) [Python -I/-B](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I) и [Node --version](https://nodejs.org/api/cli.html#--version). Это источники конкретных diagnostic repair/probe команд, не подтверждение всего pip/Node API. Установщики исполняются отдельно от read-only doctor в собственном consumer; установленный runtime и архивные hashes фиксируются evidence поставки.

### 2026-10-04 — пункт 12

Для пункта 012 2026-10-04 отдельно сверена секция [HapticFeedback](https://core.telegram.org/bots/webapps#hapticfeedback): impactOccurred light, version gate 6.1, клиент может воспроизвести отклик. Generated native module использует click + capability gate/fallback; synthetic SDK не подтверждает физическую вибрацию. Остальные даты каталога не менялись.

### 2026-10-04 — пункт 11

Для пункта 011 отдельно 2026-10-04 проверены [npm local paths](https://docs.npmjs.com/cli/v12/configuring-npm/package-json/#local-paths) и [tarball specs](https://docs.npmjs.com/cli/v12/using-npm/package-spec/#tarballs). CLI 0.9.2 записывает npm dependency как file filesystem path; URI для Python сохраняется. Путь с пробелами проверяется настоящей установкой npm 12.0.2 в новом external consumer, отдельно от общего support range.

### 2026-10-04 — пункт 10

Для пункта 010 2026-10-04 отдельно сверены Bot API Update/Business rights/profile chat, Mini App launch/auth, Bot Features guest/bot-to-bot и MTProto auth/history; конкретные положения и расхождения источников — в [API boundaries](telegram-api-boundaries.md). Это не обновляет дату всего каталога; SDK/model probes находятся в docs/v1-checks/010.json.

### 2026-10-04 — библиотека 0.5.0: CLI и стартеры

Для CLI/стартеров библиотеки 0.5.0 отдельно 4 октября 2026 просмотрены [PyPA command-line tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) — argparse/__main__/project.scripts — и [dependency specifiers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/) — direct file references. Это частичная сверка packaging; даты Telegram API/providers/device QA ей не обновляются. Фактическая установка wheel/tarball и созданных проектов фиксируется в [проверке инструментов](developer-tools-review.md).

Для system theme fallback того же starter 4 октября отдельно сверены [MediaQueryList change](https://developer.mozilla.org/en-US/docs/Web/API/MediaQueryList/change_event) и [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme): подписка на изменения media query и явный режим оформления native controls. Проверка фактического theme/background и cleanup выполнена в Chrome; это не общая гарантия всех WebView/устройств.

### 2026-10-04 — библиотека 0.4.0

Библиотека 0.4.0: 4 октября 2026 получены официальные HTML [Bot API](https://core.telegram.org/bots/api) и [Mini Apps](https://core.telegram.org/bots/webapps), сохранены в output/telegram-source-2026-10-04. Bot API 10.3: 185 методов / 400 типов сопоставлены с установленным aiogram 3.31.0, включая aliases SDK полей; обязательные request fixtures прошли native construction/serialization без HTTP. Отдельно просмотрены InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ForceReply, Update/getUpdates и native функции/events Mini Apps. Generated catalog содержит source SHA256. Это source/schema/contract проверка: live Telegram, условия каждого business flow, entitlement конкретного бота, платежные провайдеры и physical device QA ей не подтверждены. Даты остальных источников таблицы не обновлены этой сверкой.

### 2026-10-03 — полная проверка 40 навыков

Свежий HTTPS снимок [Bot API](https://core.telegram.org/bots/api) сопоставлен со всем индексом: 185 методов, 400 типов и их поля совпали. HTML SHA изменился; равенство схемы не доказывает неизменность всех текстовых ограничений. aiogram 3.31.0, PTB 22.8 и Telethon 1.45.0 проверены импортами и fake transport; не через живой Telegram.

Повторно получен опубликованный пример [callback статуса подписки Platega](https://docs.platega.io/callback-по-статусу-подписки-40030962e0): `Id = SubscriptionId`, пример `SUBSCRIPTION_ACTIVATED`. Предыдущая недоступность выше относится к прежнему проходу. В навыке обновлен только проверенный scope примера; полный enum и merchant callbacks не объявлены проверенными.

Для ручного verifier проверены [Telegram Login](https://core.telegram.org/bots/telegram-login) и [OIDC Core errata set 2, ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation): дополнительные недоверенные аудитории отклоняются; правила `azp` зависят от flow/extensions и не вводят универсальную обязательность поля. Это сверка правил и локально подписанных fixtures, без заявления о выпуске таких токенов Telegram.

Другие фактически просмотренные первичные источники и точный scope указаны в независимых отчетах, перечисленных в [skill-full-check.md](skill-full-check.md). Дата этого раздела не обновляет все исторические страницы набора. Свежесть полного протокола Crypto Pay остается ограничением: прямой текущий Help Center не был доступен.

### 2026-10-03 — семь продуктовых навыков

Для новых UX, visual regression, network recovery, web login, admin panel, media processing и subscription access сверены следующие первичные источники. Их дата не обновляет исторические проверки остальных SDK/providers.

| Область | Источники и проверенный scope |
| --- | --- |
| UX/доступность/движение | [WAI Forms](https://www.w3.org/WAI/tutorials/forms/), [multi-page](https://www.w3.org/WAI/tutorials/forms/multi-page/), [notifications](https://www.w3.org/WAI/tutorials/forms/notifications/), [APG dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [Animation from Interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html), [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) |
| Visual regression | [Playwright snapshots](https://playwright.dev/docs/test-snapshots) и [emulation](https://playwright.dev/docs/emulation): сравнение с эталоном и влияние среды; браузерная эмуляция не заменяет Telegram device QA |
| Сеть/черновики | [navigator.onLine](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine), [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API), [Telegram WebApps](https://core.telegram.org/bots/webapps): availability/storage gates; ledger/outbox являются решениями продукта |
| Вход на сайте | [Telegram Login](https://core.telegram.org/bots/telegram-login), [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html): Code Flow/PKCE, JWT/JWKS, scope и отдельные sub/id, сессия сервиса и linking; public discovery snapshot (`output/quality-product-extension/oidc-discovery.json`, локальный артефакт) получен без credentials |
| Операторские действия | [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [CSV Injection](https://community.owasp.org/attacks/CSV_Injection) |
| Медиа | [Bot API File/getFile](https://core.telegram.org/bots/api#file), [local server](https://core.telegram.org/bots/api#using-a-local-bot-api-server), [FFmpeg protocols](https://ffmpeg.org/ffmpeg-protocols.html), [File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): file IDs, границы parser/process и hosted/local различия |
| Подписка/доступ | [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment), [RefundedPayment](https://core.telegram.org/bots/api#refundedpayment), [Stars](https://core.telegram.org/bots/payments-stars): payment event/expiry; interval/ledger и частичный refund policy определяются продуктом |

### 2026-10-03 — частичная повторная сверка

При полном аудите инструкций заново проверены источники следующих инвариантов. Общая дата первоначальной проверки выше сохранена: повторное чтение 33 навыков не означает новую проверку каждой страницы документации.

| Область | Повторно проверенные факты и источник |
| --- | --- |
| Bot API 10.3 | 185 методов/400 типов; схема BusinessBotRights с can_edit_*; callback ACK и продвижение getUpdates offset. [Bot API](https://core.telegram.org/bots/api). В prose отдельных методов остаются can_change_*; SDK/schema используют can_edit_*. |
| Python SDK | PTB 22.8, aiogram 3.31.0 и Telethon 1.45.0 импортированы в офлайн-пробах. Polling concurrency/error handling сверены с [aiogram dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html). |
| Mini Apps | Подписанные поля initData, viewport/insets, lifecycle и callback semantics native API. [WebApps](https://core.telegram.org/bots/webapps); [pagehide](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event), [pageshow](https://developer.mozilla.org/en-US/docs/Web/API/Window/pageshow_event), [BFcache](https://web.dev/articles/bfcache). |
| Цифровая покупка | Доступность условий и согласие до покупки. [Stars Live Checklist](https://core.telegram.org/bots/payments-stars#live-checklist). |
| ЮKassa | 24 часа идемпотентности с первого запроса; повтор после этого окна не защищен прежним key. [Формат взаимодействия](https://yookassa.ru/developers/using-api/interaction-format#idempotence). |
| Platega СБП-подписка | Создание subscription отдельно от списания, получение и отмена, callback с ID списания и SubscriptionId. [Создание](https://docs.platega.io/создать-подписку-40029698e0), [получение](https://docs.platega.io/получить-подписку-40029717e0), [отмена](https://docs.platega.io/отменить-подписку-40029730e0), [callback списания](https://docs.platega.io/callback-по-списанию-40029713e0). |

Прямая документация Crypto Pay снова вернула HTTP 403; индексированный официальный материал не объявлен свежей полной сверкой. Тело отдельной страницы [callback статуса подписки Platega](https://docs.platega.io/callback-по-статусу-подписки-40030962e0) получить не удалось; схема этой ветки остается непроверенной. Полный объем доказательств и ограничения: [skill-quality-audit.md](skill-quality-audit.md).

### 2026-10-03 — восемь навыков

Добавлены восемь навыков для device QA, performance, design system, Python backend, native capabilities, notifications, observability и localization. Проверены следующие первичные источники; это частичная сверка, а не обновление даты всех источников набора.

| Область | Источник и проверяемый инвариант |
| --- | --- |
| Клиенты/native API | [Mini Apps](https://core.telegram.org/bots/webapps): LocationManager init/null/permissions, storage scope, version gates, callback принятия download |
| Производительность | [Web Vitals](https://web.dev/articles/vitals): лабораторные/полевые данные, LCP/INP/CLS; время automation не является INP |
| Компоненты | [WAI modal dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) |
| Python API | [FastAPI async](https://fastapi.tiangolo.com/async/), [SQLAlchemy concurrent tasks](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks): execution model и отдельная session для каждой конкурентной задачи |
| БД/миграции | [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html), [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html): constraints/atomic UPSERT и ручная проверка кандидата миграции |
| Уведомления | [Bot FAQ](https://core.telegram.org/bots/faq#broadcasting-to-users), [ResponseParameters](https://core.telegram.org/bots/api#responseparameters), [sendMessage](https://core.telegram.org/bots/api#sendmessage): throttle/retry_after, paid broadcast и отсутствие общего application idempotency key |
| Наблюдаемость | [OpenTelemetry sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/), [Python contextvars](https://docs.python.org/3/library/contextvars.html): обработка чувствительных данных и async context |
| Локализация | [Intl](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl), [DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat), [PluralRules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules), [Telegram User](https://core.telegram.org/bots/api#user) |

Источники библиотек относятся к конкретным версиям документации; skill не закрепляет FastAPI/SQLAlchemy/Alembic как обязательный стек. Числовые лимиты Telegram повторно сверяются при интеграции, а оплачиваемая отправка не включается автоматически.

### 2026-10-03 — библиотека 0.3.0

Для text-form API библиотеки 0.3.0 отдельно 3 октября 2026 сверены [aiogram FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [storage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html) и [Dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html): MemoryStorage теряет состояние после рестарта; FSMStrategy/host storage задаются Dispatcher; event isolation включается отдельно. Код установленного aiogram 3.31.0 подтвердил lock до чтения raw_state и DisabledEventIsolation по умолчанию. Остальные источники не обновлены этой частичной сверкой.

### 2026-10-03 — библиотека 0.2.0

Библиотека 0.2.0: 3 октября 2026 частично проверены [BotCommand](https://core.telegram.org/bots/api#botcommand), [setMyCommands](https://core.telegram.org/bots/api#setmycommands), [aiogram Command](https://docs.aiogram.dev/en/latest/dispatcher/filters/command.html), [polling](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html), [BaseSession](https://docs.aiogram.dev/en/latest/api/session/base.html) и [keyboard builder](https://docs.aiogram.dev/en/latest/_modules/aiogram/utils/keyboard.html). Установлена версия aiogram 3.31.0; сигнатуры start_polling/stop_polling/BaseSession и обработка token сверены с ее исходным кодом. Поведение отмены polling дополнительно воспроизведено synthetic transport. Это новые bot-tool contracts, не обновление даты всех Telegram/payment источников.

### 2026-10-03 — библиотека 0.1.1

Библиотека 0.1.1: 3 октября 2026 дополнительно сверены [Python SQLite authorizer](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.set_authorizer), [неявный commit executescript](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.executescript), [SQLite authorization](https://www.sqlite.org/c3ref/set_authorizer.html), [Response.json failures](https://developer.mozilla.org/en-US/docs/Web/API/Response/json), [HTTP 204](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/204), [HTTP 205](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/205), [ThemeParams](https://core.telegram.org/bots/webapps#themeparams), [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme) и [randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID). Официальный [WebApp SDK](https://telegram.org/js/telegram-web-app.js) получен прямым HTTPS-запросом и проверен на начальное platform=unknown. Это частичная проверка конкретных контрактов; live Telegram/device QA ей не подтвержден.

### 2026-10-03 — библиотека 0.1.0

Библиотека компонентов 0.1.0: 3 октября 2026 отдельно сверены HMAC Mini App initData, Router/кнопки/CreateInvoiceLink aiogram 3.31.0, явные SQLite транзакции и закрытие connection, fetch cancellation/redirect и pagehide lifecycle. Ссылки: [Python package README](../packages/python/README.md), [TypeScript package README](../packages/typescript/README.md). Эти источники относятся к перечисленным контрактам библиотеки, не обновляют дату всей таблицы ниже.

### 2026-10-02 — архитектура и интерфейс Mini App

При проверке архитектуры/UI 2 октября 2026 года дополнительно просмотрены [Telegram Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines), [viewport и insets](https://core.telegram.org/bots/webapps#initializing-mini-apps), [W3C contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [W3C target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion), [Web Vitals](https://web.dev/articles/vitals). Числовая матрица размеров и ориентир touch 44 px — критерии набора, а не официальное обещание поддержки устройств.

Воспроизведенный сценарий восстановления подписок сверялся с [MDN pagehide](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event) и [back/forward cache](https://web.dev/articles/bfcache).

### 2026-10-02 — расширение набора

| Область | Проверенный источник |
| --- | --- |
| Styles и emoji в кнопках, profile APIs | [Bot API](https://core.telegram.org/bots/api); получен напрямую снимок 10.3: 185 методов, 400 типов |
| Business/Secretary | [Bot features](https://core.telegram.org/bots/features#business-bots) |
| Python user client | [Telethon](https://docs.telethon.dev/en/stable/), [сессии](https://docs.telethon.dev/en/stable/concepts/sessions.html) |
| Клиентские API и данные профиля | [TDLib](https://core.telegram.org/tdlib), [users.getFullUser](https://core.telegram.org/method/users.getFullUser), [account.updateProfile](https://core.telegram.org/method/account.updateProfile) |
| Дополнительный Python Bot API SDK | [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) |
| Поддержка старого MTProto SDK | [Pyrogram](https://docs.pyrogram.org/): сообщает о прекращении поддержки |
| Crypto Pay | [текущая официальная страница](https://help.send.tg/en/articles/10279948-crypto-pay-api), [aiocryptopay upstream](https://github.com/layerqa/aiocryptopay) |
| Platega.io | [auth](https://docs.platega.io/), [SDK](https://docs.platega.io/sdk-1991993m0), страницы create/status/callback/cancel, ссылки в reference навыка |
| ЮKassa | [interaction format](https://yookassa.ru/developers/using-api/interaction-format), [webhooks](https://yookassa.ru/developers/using-api/webhooks), [SDK](https://github.com/yoomoney/yookassa-sdk-python) |
| Дополнительные провайдеры | [Stripe webhooks](https://docs.stripe.com/webhooks), [Robokassa](https://docs.robokassa.ru/ru/pay-interface) |

Crypto Pay: старая официальная страница указывает новый адрес. Прямое открытие нового адреса вернуло 403; получено индексированное содержимое официальной страницы с более ранней датой обхода. Поэтому актуальность ее полного протокола на дату расширения не подтверждена live-запросом. Перед интеграцией повторно проверить текущую документацию и testnet.

### 2026-10-02 — создание набора

Официальные источники просмотрены 2 октября 2026 года при создании набора. Это дата проверки источников, а не обещание совместимости с любой установленной версией SDK. Для реализации конкретной функции агент должен сопоставить текущую документацию с зависимостями проекта. Источники перечислены в разделе «Общие первичные источники».
