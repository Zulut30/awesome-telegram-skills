# Источники и актуальность

Библиотека 0.4.0: 4 октября 2026 получены официальные HTML [Bot API](https://core.telegram.org/bots/api) и [Mini Apps](https://core.telegram.org/bots/webapps), сохранены в output/telegram-source-2026-10-04. Bot API 10.3: 185 методов / 400 типов сопоставлены с установленным aiogram 3.31.0, включая aliases SDK полей; обязательные request fixtures прошли native construction/serialization без HTTP. Отдельно просмотрены InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ForceReply, Update/getUpdates и native функции/events Mini Apps. Generated catalog содержит source SHA256. Это source/schema/contract проверка: live Telegram, условия каждого business flow, entitlement конкретного бота, платежные провайдеры и physical device QA ей не подтверждены. Даты остальных источников таблицы не обновлены этой сверкой.

Библиотека 0.2.0: 3 октября 2026 частично проверены [BotCommand](https://core.telegram.org/bots/api#botcommand), [setMyCommands](https://core.telegram.org/bots/api#setmycommands), [aiogram Command](https://docs.aiogram.dev/en/latest/dispatcher/filters/command.html), [polling](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html), [BaseSession](https://docs.aiogram.dev/en/latest/api/session/base.html) и [keyboard builder](https://docs.aiogram.dev/en/latest/_modules/aiogram/utils/keyboard.html). Установлена версия aiogram 3.31.0; сигнатуры start_polling/stop_polling/BaseSession и обработка token сверены с ее исходным кодом. Поведение отмены polling дополнительно воспроизведено synthetic transport. Это новые bot-tool contracts, не обновление даты всех Telegram/payment источников.

Библиотека компонентов 0.1.0: 3 октября 2026 отдельно сверены HMAC Mini App initData, Router/кнопки/CreateInvoiceLink aiogram 3.31.0, явные SQLite транзакции и закрытие connection, fetch cancellation/redirect и pagehide lifecycle. Ссылки: [Python package README](../packages/python/README.md), [TypeScript package README](../packages/typescript/README.md). Эти источники относятся к перечисленным контрактам библиотеки, не обновляют дату всей таблицы ниже.

Библиотека 0.1.1: 3 октября 2026 дополнительно сверены [Python SQLite authorizer](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.set_authorizer), [неявный commit executescript](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.executescript), [SQLite authorization](https://www.sqlite.org/c3ref/set_authorizer.html), [Response.json failures](https://developer.mozilla.org/en-US/docs/Web/API/Response/json), [HTTP 204](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/204), [HTTP 205](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/205), [ThemeParams](https://core.telegram.org/bots/webapps#themeparams), [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme) и [randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID). Официальный [WebApp SDK](https://telegram.org/js/telegram-web-app.js) получен прямым HTTPS-запросом и проверен на начальное platform=unknown. Это частичная проверка конкретных контрактов; live Telegram/device QA ей не подтвержден.

Официальные источники просмотрены 2 октября 2026 года при создании набора. Это дата проверки источников, а не обещание совместимости с любой установленной версией SDK. Для реализации конкретной функции агент должен сопоставить текущую документацию с зависимостями проекта.

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
| Загрузка навыков в Codex | [Codex skills](https://developers.openai.com/codex/skills/) |

## Расширение от 2 октября 2026 года

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

Индекс Bot API создается помощником внутри навыка и содержит source URL, retrieval timestamp и SHA256 HTML. Он не копирует описания API и не доказывает поддержку всех методов каждой библиотекой.

## Дополнение от 3 октября 2026 года

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

## Частичная повторная сверка 3 октября 2026 года

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

## Семь продуктовых навыков от 3 октября 2026 года

Для новых UX, visual regression, network recovery, web login, admin panel, media processing и subscription access сверены следующие первичные источники. Их дата не обновляет исторические проверки остальных SDK/providers.

| Область | Источники и проверенный scope |
| --- | --- |
| UX/доступность/движение | [WAI Forms](https://www.w3.org/WAI/tutorials/forms/), [multi-page](https://www.w3.org/WAI/tutorials/forms/multi-page/), [notifications](https://www.w3.org/WAI/tutorials/forms/notifications/), [APG dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [Animation from Interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html), [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) |
| Visual regression | [Playwright snapshots](https://playwright.dev/docs/test-snapshots) и [emulation](https://playwright.dev/docs/emulation): сравнение с эталоном и влияние среды; браузерная эмуляция не заменяет Telegram device QA |
| Сеть/черновики | [navigator.onLine](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine), [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API), [Telegram WebApps](https://core.telegram.org/bots/webapps): availability/storage gates; ledger/outbox являются решениями продукта |
| Вход на сайте | [Telegram Login](https://core.telegram.org/bots/telegram-login), [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html): Code Flow/PKCE, JWT/JWKS, scope и отдельные sub/id, сессия сервиса и linking; [public discovery snapshot](../output/quality-product-extension/oidc-discovery.json) получен без credentials |
| Операторские действия | [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [CSV Injection](https://community.owasp.org/attacks/CSV_Injection) |
| Медиа | [Bot API File/getFile](https://core.telegram.org/bots/api#file), [local server](https://core.telegram.org/bots/api#using-a-local-bot-api-server), [FFmpeg protocols](https://ffmpeg.org/ffmpeg-protocols.html), [File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): file IDs, границы parser/process и hosted/local различия |
| Подписка/доступ | [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment), [RefundedPayment](https://core.telegram.org/bots/api#refundedpayment), [Stars](https://core.telegram.org/bots/payments-stars): payment event/expiry; interval/ledger и частичный refund policy определяются продуктом |

## Полная проверка 40 навыков 3 октября 2026 года

Свежий HTTPS снимок [Bot API](https://core.telegram.org/bots/api) сопоставлен со всем индексом: 185 методов, 400 типов и их поля совпали. HTML SHA изменился; равенство схемы не доказывает неизменность всех текстовых ограничений. aiogram 3.31.0, PTB 22.8 и Telethon 1.45.0 проверены импортами и fake transport; не через живой Telegram.

Повторно получен опубликованный пример [callback статуса подписки Platega](https://docs.platega.io/callback-по-статусу-подписки-40030962e0): `Id = SubscriptionId`, пример `SUBSCRIPTION_ACTIVATED`. Предыдущая недоступность выше относится к прежнему проходу. В навыке обновлен только проверенный scope примера; полный enum и merchant callbacks не объявлены проверенными.

Для ручного verifier проверены [Telegram Login](https://core.telegram.org/bots/telegram-login) и [OIDC Core errata set 2, ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation): дополнительные недоверенные аудитории отклоняются; правила `azp` зависят от flow/extensions и не вводят универсальную обязательность поля. Это сверка правил и локально подписанных fixtures, без заявления о выпуске таких токенов Telegram.

Другие фактически просмотренные первичные источники и точный scope указаны в независимых отчетах, перечисленных в [skill-full-check.md](skill-full-check.md). Дата этого раздела не обновляет все исторические страницы набора. Свежесть полного протокола Crypto Pay остается ограничением: прямой текущий Help Center не был доступен.

## Как обновлять набор

Для CLI/стартеров библиотеки 0.5.0 отдельно 4 октября 2026 просмотрены [PyPA command-line tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) — argparse/__main__/project.scripts — и [dependency specifiers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/) — direct file references. Это частичная сверка packaging; даты Telegram API/providers/device QA ей не обновляются. Фактическая установка wheel/tarball и созданных проектов фиксируется в [проверке инструментов](developer-tools-review.md).

Для system theme fallback того же starter 4 октября отдельно сверены [MediaQueryList change](https://developer.mozilla.org/en-US/docs/Web/API/MediaQueryList/change_event) и [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme): подписка на изменения media query и явный режим оформления native controls. Проверка фактического theme/background и cleanup выполнена в Chrome; это не общая гарантия всех WebView/устройств.

Для text-form API библиотеки 0.3.0 отдельно 3 октября 2026 сверены [aiogram FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [storage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html) и [Dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html): MemoryStorage теряет состояние после рестарта; FSMStrategy/host storage задаются Dispatcher; event isolation включается отдельно. Код установленного aiogram 3.31.0 подтвердил lock до чтения raw_state и DisabledEventIsolation по умолчанию. Остальные источники не обновлены этой частичной сверкой.

При проверке архитектуры/UI 2 октября 2026 года дополнительно просмотрены [Telegram Design Guidelines](https://core.telegram.org/bots/webapps#design-guidelines), [viewport и insets](https://core.telegram.org/bots/webapps#initializing-mini-apps), [W3C contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), [W3C target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion), [Web Vitals](https://web.dev/articles/vitals). Числовая матрица размеров и ориентир touch 44 px — критерии набора, а не официальное обещание поддержки устройств.

Воспроизведенный сценарий восстановления подписок сверялся с [MDN pagehide](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event) и [back/forward cache](https://web.dev/articles/bfcache).

При изменении функции открой относящийся к ней официальный источник, проверь version gate и поддержку SDK. Обнови только затронутые инструкции и сценарии проверки. Не копируй целиком API-справочник в навыки: это быстро устаревает и увеличивает контекст.

Ссылки `latest` и `stable` меняются. Для существующего проекта используй документацию установленной версии. При отсутствии сети сохрани полезную работу, но пометь непроверенные правила, параметры или совместимость.

Обновлять общую дату можно после повторной проверки всего указанного набора. Для частичного обновления укажи отдельно источник, дату и измененный инвариант в соответствующей reference.

Для пункта 010 2026-10-04 отдельно сверены Bot API Update/Business rights/profile chat, Mini App launch/auth, Bot Features guest/bot-to-bot и MTProto auth/history; конкретные положения и расхождения источников — в [API boundaries](telegram-api-boundaries.md). Это не обновляет дату всего каталога; SDK/model probes находятся в docs/v1-checks/010.json.

Для пункта 011 отдельно 2026-10-04 проверены [npm local paths](https://docs.npmjs.com/cli/v12/configuring-npm/package-json/#local-paths) и [tarball specs](https://docs.npmjs.com/cli/v12/using-npm/package-spec/#tarballs). CLI 0.9.2 записывает npm dependency как file filesystem path; URI для Python сохраняется. Путь с пробелами проверяется настоящей установкой npm 12.0.2 в новом external consumer, отдельно от общего support range.

Для пункта 013 отдельно 2026-10-04 проверены [pip install: interpreter/local archives](https://pip.pypa.io/en/stable/cli/pip_install/), [ensurepip: bootstrap без сети](https://docs.python.org/3.13/library/ensurepip.html) [Python -I/-B](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I) и [Node --version](https://nodejs.org/api/cli.html#--version). Это источники конкретных diagnostic repair/probe команд, не подтверждение всего pip/Node API. Установщики исполняются отдельно от read-only doctor в собственном consumer; установленный runtime и архивные hashes фиксируются evidence поставки.

Для пункта 012 2026-10-04 отдельно сверена секция [HapticFeedback](https://core.telegram.org/bots/webapps#hapticfeedback): impactOccurred light, version gate 6.1, клиент может воспроизвести отклик. Generated native module использует click + capability gate/fallback; synthetic SDK не подтверждает физическую вибрацию. Остальные даты каталога не менялись.

Для пункта 014 2026-10-04 проверен [официальный Compiler API guide](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API): примеры относятся к TypeScript <7. В установленном 7.0.2 по package exports и declarations проверены `typescript/unstable/sync` API/updateSnapshot/Project.checker, NodeHandle.resolve и AST node.forEachChild. Проверяющий скрипт использует этот закрепленный dev tool и закрывает snapshot/API; это не стабильный контракт TypeScript и не runtime dependency библиотеки. Telegram API в этом пункте не изменялся, даты остального набора источников не обновлялись.
