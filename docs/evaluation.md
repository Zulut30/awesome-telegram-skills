# Проверка качества навыков

Для пункта 010 дополнительно: «прочитай историю моих групп» → отдельная явно поставленная user-client задача; «наблюдай typing/read/copy» → обычный Update не выдумывается; «direct-link Mini App отправляет результат» → backend/auth и launch-specific channel вместо универсального sendData. Business read-mark отличается от history, revoked connection не разрешается одним can_reply; guest/bot-to-bot требуют специальных настроек и защиты от циклов. SDK/native probes подтверждают модели и presence boundary; независимая оценка решения агента и live permission acceptance считаются отдельно.

Для cookbook 0.4.0 дополнительно: «сделай две/три кнопки в ряд», «раскрась и добавь custom emoji», «запроси контакт / выбери users/chat», «измени поле ввода», «отслеживай реакции» и «подключи native location на старом клиенте». Агент сохраняет Dispatcher/SDK, выбирает нужный recipe, проверяет context/entitlement, ACK перед edit/effect, reply_to binding и request_id; не объявляет shared IDs правами, typing/read receipts/copy clicks доступными бот API. Unknown top-level parameters отклоняются; generated fixtures не отправляются. Native denied/unavailable/cancel/late callback не становятся accepted. Пробы через installed wheel/tarball, copied skill references и synthetic Dispatcher исполняются отдельно от независимой оценки решений агента и live/device испытаний; отчет — [telegram-cookbook-review.md](telegram-cookbook-review.md).

Структурная проверка файлов не измеряет поведение агента. Следующие сценарии задают полную матрицу испытаний при развитии набора. Выполненная выборка с независимыми приложениями, routing и Python probe описана в [quality-review.md](quality-review.md) и [skill-extension-review.md](skill-extension-review.md). Повторный аудит содержания прежних 33 навыков описан в [skill-quality-audit.md](skill-quality-audit.md), расширение до 40 — в [skill-product-extension-review.md](skill-product-extension-review.md). Каждый отчет отдельно обозначает фактические пробы и их ограничения; остальные сценарии пока являются планом.

Последующий [полный проход 40 навыков](skill-full-check.md) содержит по одному конкретному сценарию на каждый навык и 56 слепых запросов выбора по descriptions. Он расширяет выполненную выборку, но не превращает все строки ниже в пройденные live-интеграции.

Для каждого испытания дай агенту запрос, нужный навык и минимальные исходные файлы. Не подсказывай ожидаемое решение. Используй временный проект, fake integrations или отдельный тестовый бот согласно сценарию. Сохраняй запрос, результат, дифф и фактические проверки; исправляй навык по наблюдаемой ошибке.

| Запрос | Ожидаемый выбор | Критерий результата |
| --- | --- | --- |
| «Спроектируй запись к мастеру: бот + календарь» | project-planner | MVP, границы компонентов, первый проверяемый сценарий |
| «Добавь фото с подписью и кнопкой» | bot-api + навык языка | Корректный запрос SDK и форматирование вставок |
| «Добавь /start в существующий aiogram 3 проект» | bot-python | Framework сохраняется, нет примеров aiogram 2 |
| «Подключи TypeScript Mini App к Python API» | mini-app-typescript | Корректный bridge/SDK, типы и сборка; секреты остаются на сервере |
| «Старая кнопка подтверждения создает второй заказ» | dialogs | Проверка перехода и один прикладной эффект при гонке |
| «Сделай @bot поиск личных заметок» | inline-mode | Результаты разных пользователей не смешиваются в кеше |
| «Бот-модератор управляет двумя темами группы» | groups | Проверяются полномочия и изоляция контекста |
| «В Mini App клавиатура перекрывает кнопку» | mini-app-ui | Исправление подтверждено в соответствующем клиенте |
| «Mini App должна быть удобной на телефоне, планшете и ПК» | mini-app-architecture + mini-app-ui | Компактная/широкая компоновка, общий источник состояния, измерения и screenshots |
| «После back/forward Mini App перестает реагировать на resize» | mini-app-typescript + debugging | Восстановление lifecycle подписок после pageshow; повтор исходного сценария |
| «Добавь вход через initData в backend» | mini-app-auth | Подмена и истечение отклонены; проверка не отключена |
| «Заверши заказ в Mini App, покажи его в боте» | mini-app-integration | Канал соответствует запуску; повтор не создает второй заказ |
| «Продай цифровой доступ внутри Telegram» | payments | Проверены текущие правила; выдача зависит от серверной оплаты |
| «Добавь тест повторной доставки платежа» | testing | Проверяется единственная выдача, а не wording реализации |
| «Задеплой webhook на выбранный хостинг» | deploy | Нет потери после ACK; реальный update обработан |
| «Рабочий бот перестал отвечать после релиза» | debugging | Сначала факты; нет сброса webhook/updates ради пробы |
| «Проверь доступ к заказам Mini App» | security-review | Чужой order_id не дает доступ; есть конкретные доказательства |
| «Добавь зеленую кнопку с premium emoji» | buttons | Проверены style, custom emoji entitlement и payload SDK |
| «Покажи данные профиля и Premium» | profiles | Правильный API; неизвестное поле не выдается за доказанный факт |
| «Поменяй фото и описание бота» | profiles + bot-api | Используются методы собственного бота, сохраняется локализация; пропуск поля не очищает его |
| «Бот должен читать мои выбранные группы и историю» | user-client | Используется авторизованная user session; Business connection не дает историю групп |
| «Бот отвечает в разрешенных личных чатах подключенного аккаунта» | business-bots | Отдельные connection/rights и доступные updates; это не полный пользовательский клиент |
| «Выбери библиотеку для новой функции» | library-selection | Поддержка установлена по актуальному SDK, не по названию пакета |
| «Подключи CryptoBot к заказам» | cryptopay | Проверена raw-body подпись; non-unique update_id не удваивает выдачу |
| «Добавь Platega checkout» | platega | Секрет заголовка и статус транзакции проверены; нет выдуманного idempotency header |
| «Добавь ЮKassa и capture» | yookassa | waiting_for_capture отличается от succeeded; подлинность проверена способом ЮKassa |
| «Добавь другую платежку» | payment-provider | Adapter отражает реальные capabilities и callback protocol провайдера |
| «Проверь Mini App на iPhone, Android, планшете и ПК» | mini-app-device-qa | Есть версии клиентов, launch mode и доказательства; недоступные устройства не получают passed |
| «Mini App тормозит на слабом Android» | mini-app-performance | Baseline, подтвержденная причина, сопоставимое до/после; simulator не объявлен реальным телефоном |
| «Сделай общие поля, карточки и dialog для нескольких экранов» | mini-app-design-system | Контракт компонентов, темы, focus/label/error и подключение к реальному экрану |
| «Добавь Python API заказа, БД и миграцию» | python-backend | Серверная личность и права, транзакция, конкурентность, replay и реальный storage в проверке |
| «Добавь native геолокацию с ручным выбором» | mini-app-native-capabilities | Version gate, init, отказ/unsupported/late callback и полезный fallback |
| «Добавь напоминание за сутки с отпиской» | notifications | Eligibility перед dispatch, durable job, 429, restart и честная политика unknown outcome |
| «Свяжи frontend, API и worker в безопасных логах» | observability | Корреляция при конкурентности, bounded labels, canaries отсутствуют в финальном output |
| «Добавь русский/английский с датами и ценами» | localization | Locale, plural/fallback, timezone отдельно от языка, сохранение формы |
| «Только спроектируй архитектуру Mini App» | mini-app-architecture | Границы, контракты и план приемки; реализация не начинается без запроса |
| «Локализуй Python-бота без Mini App» | localization | Проверки ответов/форматирования и проекта; frontend build не требуется |
| «ЮKassa: запрос потерял ответ 25 часов назад» | yookassa | Сверка сохраненного объекта и политика unknown; старый key не считается бессрочной защитой от второго списания |
| «Добавь Platega подписку и два оплаченных периода» | platega | Subscription и charge IDs различаются; duplicate callback не продлевает доступ, отмена останавливает будущие списания |
| «Пользователь отписался между claim и отправкой напоминания» | notifications | Атомарная eligibility/dispatch граница, проверяемый порядок событий; текущая отправка не обещана отмененной |
| «Polling подтвердил update до завершения заказа» | bot-python + deploy | Измерен момент offset/commit; выбран надежный прием, последовательность handlers не выдается за гарантию |
| «Старая кнопка вызывает отказ, но spinner продолжает крутиться» | dialogs | Callback ACK выполняется и при отказе; подтверждение не объявлено успешной операцией |
| «Business-бот меняет bio подключенного аккаунта» | profiles + business-bots | Используется фактическое can_edit_bio из BusinessBotRights, права и connection проверяются отдельно |
| «Покупка Stars без доступных условий» | payments | Условия доступны, согласие получено до покупки; остальные шаги выдачи остаются серверными |
| «Первый пользователь не понимает, как записаться и исправить контакты» | mini-app-ux | Понятный путь и ошибки, возврат без потери ввода; walkthrough не объявляется исследованием с участниками |
| «После релиза у кнопки обрезалась надпись в темной теме» | mini-app-visual-regression | Воспроизводимые expected/actual/diff, обнаружение дефекта; эталон не перезаписывается для сокрытия ошибки |
| «Mini App теряет черновик и повторяет заказ после timeout» | mini-app-network-recovery | Scoped storage/operation ID, сверка неизвестного результата и один эффект; смена аккаунта не отправляет чужой черновик |
| «После потерянного ответа TTL контактов истек, пользователь заполнил форму заново» | mini-app-network-recovery | Личные поля удалены по сроку, recovery identity не потеряна; новая запись того же намерения не создается до сверки |
| «Вход через Telegram на сайте и привязка к текущему аккаунту» | web-login | Проверенный OIDC ID token/state/nonce, уникальная привязка, sub не заменяет Bot API id |
| «JWT verifier принимает дополнительную недоверенную aud или чужую azp» | web-login | Проверен полный OIDC-контракт audience/authorized party; наличие Client ID в массиве не разрешает другие аудитории |
| «Оператор магазина должен найти заказ и отменить его» | admin-panel | Серверные capability/object scope, revision, однократная операция и согласованный журнал |
| «Бот обрабатывает аудио и возвращает результат владельцу» | media-processing | Настоящий parser/output, лимиты и очистка, авторизация выдачи; file_unique_id не используется для отправки |
| «Продление оплаченного доступа, отмена и refund старого периода» | subscription-access | Charge ledger/периоды, duplicate/out-of-order, корректные границы и независимость нового периода |
| «Dialog дергается, а screen reader теряет контекст» | mini-app-ui + mini-app-design-system | Reduced motion, cleanup вне animationend, focus/объявления; реальный reader имеет собственный результат проверки |

## Негативные сценарии выбора

Для doctor 0.11.0: SDK-free окружение получает понятный план установки предоставленного wheel с extra; отсутствие pip дает ensurepip. Установщик исполняется отдельно от read-only diagnosis в новом consumer. Поврежденный TOML, JSON со строкой/null вместо dependencies, неверный token, недоступный target и отсутствие Node/npm имеют причины и следующие действия без raw data. Старый SDK отличается от совместимого непроверенного; read-only snapshot сохраняется, NODE_OPTIONS/BOT_TOKEN/payment secret не проходят в Node probe. Исправленный manifest и окружение дают успешный повторный doctor. Эти runnable cases не подменяют слепую оценку решения агента или исследование удобства человеком.

Отдельный doctor regression: проектные aiogram.py и aiohttp.py имеют намеренный файловый эффект при import. Diagnostic CLI не создает marker: SDK shadow дает adapter-origin-unverified, dependency shadow не попадает в isolated Python -I -B probe. До исправления прямой adapter import исполнял aiogram.py; успешная узкая проверка отсутствия raw token не доказывала read-only поведения.

Для библиотеки готовых компонентов дополнительно проверяются: подключение Router к существующему Dispatcher; импорт core без aiogram; установка wheel/tarball в отдельный проект; API decoder и unknown POST с transport retry; серверная дедупликация и GET сверка; сохранение формы при theme/resize; scoped черновик без контактов и storage failure. Выполненные результаты новой библиотеки описываются отдельно от исторического аудита 40 навыков.

Для 0.1.1 добавлены сценарии: случайный commit/executescript callback не оставляет эффект без ledger; savepoint работает внутри общей транзакции; невалидная кодировка запуска обрабатывается как auth failure; HTTP 204/205 проходит через null decoder, оборванное тело отличается от некорректного JSON; неуспешная регистрация bridge допускает повторный start без утечек; изменение options не меняет scope черновика; поле/hint/error не конфликтуют с существующими ID даже без window/randomUUID; семантические цвета Telegram применяются к секциям, подсказкам и ошибкам. Это выполняемые контрактные сценарии библиотеки, без отдельного нового испытания автоматического выбора навыков.

Для bot tools 0.2.0: текущие /ping/router сохраняются при добавлении static commands; чужой bot mention не получает ответ; разные commands имеют собственный текст; menu keys уникальны, навигация и action prefixes различимы; старая page после уменьшения каталога не открывает пустой объект; реальные SDK polling/cancel не оставляют GetUpdates child активным; session закрывается при setup error/cancel и остается caller при preflight failure; StubSession отклоняет незаданный метод/невалидный SDK response и не использует HTTP fallback. Один create_app проходит command → page → selection через настоящий Dispatcher с synthetic updates.

- Обычная inline-кнопка не должна активировать inline-mode только из-за слова «inline».
- Одиночная команда без состояния не требует dialogs/FSM.
- Обычная верстка сайта вне Telegram не требует mini-app-ui.
- Узкое исправление не должно запускать полное проектирование и внедрение инфраструктуры.
- MTProto-клиент или userbot не должен автоматически считаться обычным Bot API ботом.
- Personal chat, прикрепленный к профилю, не должен интерпретироваться как вся личная переписка пользователя.
- Shared-secret callback Platega не должен проверяться придуманной схемой подписи Crypto Pay.
- Одно изменение отступа не требует создания библиотеки компонентов.
- Одиночный ответ handler не должен создавать campaign/worker очередь.
- Общий TypeScript bridge не требует подключения всех native capabilities.
- Перевод отдельного абзаца не активирует проектную локализацию.
- Конкретная ошибка webhook относится к debugging; внедрение instrumentation — к observability.
- Отсутствие реального устройства оставляет native/device QA не выполненным; браузерная симуляция сохраняет свой scope.
- Обычная отправка готового файла не требует media-processing pipeline.
- Изменение цвета кнопки не требует UX-исследования и новой snapshot инфраструктуры.
- Ошибка одного GET не требует offline outbox или Service Worker.
- Mini App initData не проверяется OIDC verifier; вход на сайте не создает MTProto session.
- Авторизация endpoint не требует полной админки, а invoice не требует новой модели тарифов без запроса.
- Изменение baseline без просмотра diff не является подтверждением исправления дизайна.

## Граница проверки

Для инструментов библиотеки 0.5.0: агент на запрос «две кнопки в ряд» находит two-columns и использует native markup с нужным handler, не выдает SDK-construction за live проверку. При запросе sendPhoto различает request fixture и реальные media/IDs. Native reference требует параметров и capability/permission checks. Запрос создать новый проект: сначала local artifact/exports и dry-run; существующий даже пустой каталог не перезаписывается, текущий PTB/React не мигрирует. Bot-mini-app starter описывается как frontend companion без backend auth. Doctor без token сообщает warn, с require-token — fail, но формат не объявляется проверкой Telegram token; .env/секреты не выводятся. Отдельно испытываются core catalog без SDK, установленная console entrypoint, actual template files, offline Dispatcher, wheel/tarball dependencies, strict TS build и браузерные действия. Это контрактные испытания; независимый прогон поведения агента остается отдельным scope.

Для формы библиотеки 0.3.0: агент подключает Router к текущему aiogram Dispatcher с сохранением его FSM/storage/isolation; service принимает стабильный operation_id и делает durable effect/replay. Последнее поле не отправляет заявку без подтверждения; /back исправляет ответ, /help остается доступной, старая/чужая кнопка ACK без effect. Проверяются конкурентные подтверждения, дубли текста, isolation двух пользователей, отмена до отправки, commit + потеря ответа и повтор с прежним ID, cancellation и ошибка feedback. Pending identity не очищается по TTL обычного draft. Несовместимая FSM schema не сбрасывается молча. Исполняемые contract/consumer сценарии записываются отдельно от независимого испытания решений агента.

В наборе проверяются frontmatter, уникальность имен, UI-метаданные, локальные ссылки, переносимость отдельных каталогов, поведение установщика и парсер индекса API. Реальные Telegram-клиенты, боты, платежи и независимое поведение агента требуют отдельного испытания; они не подтверждаются тестами этого репозитория.
# Сценарии переиспользования библиотеки: telegram-code-patterns

Дополнение для 0.6.0 и пункта 002 roadmap. Это набор задач для оценки решений, отдельно от статической проверки навыка и запуска примеров.

| Запрос | Ожидаемое решение | Ошибка приемки |
| --- | --- | --- |
| «Подключи готовые две кнопки в ряд из локального wheel 0.6.0» | Выбрать RecipeCatalog/inline_keyboard через публичный API; увидеть experimental + sdk, проверить handler/context | Объявить production/live готовность на основании разметки |
| «В каталоге есть sendInvoice, значит готова выдача платного доступа?» | Указать reference request-only scope; реализовать подтверждение оплаты и серверные права отдельным workflow | Выдать доступ по созданию invoice или invoiceClosed |
| «Найди только стабильные рецепты» | Поиск maturity=stable дает пустой результат текущего snapshot; отсутствие не подменять SDK/mock фильтром | Назвать sdk/mock рецепты stable автоматически |
| «У меня React и PostgreSQL; подключи библиотеку для Mini App» | Сохранить стек; использовать подходящие bridge/API adapters и host lifecycle/storage | Переписать UI на plain DOM или заменить PostgreSQL ради SQLiteOnce |
| «Исправь отступ у существующей кнопки» | Узкое исправление в текущем UI; библиотека не внедряется без необходимости | Загрузить весь набор и создать новый проект |

Проверка переносимых Python-примеров выполняется `scripts/verify_developer_recipe.py` по скопированному навыку через установленный core wheel: catalog и maturity блоки. Она доказывает работоспособность этих примеров; независимые слепые решения по таблице проверяются отдельно в пункте 088.

## Первый запуск — пункт 011

| Запрос | Ожидаемое решение | Ошибка приемки |
| --- | --- | --- |
| «Дали wheel и tarball 0.9.2; покажи первый запуск без токена» | Установить локальный wheel; dry-run/new init; install и offline.py; собрать локальный frontend и проверить его ввод | Registry install по одному имени; live app.py вместо offline; выдача preview за авторизацию |
| «Повтори первый запуск в моем существующем каталоге» | Предложить новый каталог или точечные импорты; guard сохраняет прежние файлы | Удаление каталога или принудительная перезапись |
| «Пути к файлам содержат пробелы» | LiteralPath/вызов через PowerShell & с переменными; direct file URI установленного пакета | Source import вместо установленного wheel/tarball |

`scripts/verify_quickstart.py --wheel <WHEEL> --tarball <TARBALL> --output <NEW_PROOF_DIR>` выполняет блоки из руководства в новом временном consumer вне репозитория, проверяет origins, offline Dispatcher, doctor, неизменность существующего каталога и Chrome на шести размерах/темах. Проверяется Windows PowerShell, зависимости могут устанавливаться из registry; настоящий токен не передается. Установку и поведение примера эта проверка подтверждает; независимое слепое решение агента и человеческое удобство измеряются в отдельных пунктах 020/088.

## Создание проекта из компонентов — пункт 012

| Запрос | Ожидаемое решение | Ошибка приемки |
| --- | --- | --- |
| «Новый бот: клавиатура, страницы и форма» | Выбрать IDs, показать dry-run closure/files, создать только новый каталог и выполнить выбранные routes через installed wheel | Imports/metadata без реально подключенных modules; коллизия команд или пропуск isolation формы |
| «Добавь api-client в bot template» | component-template до записи; предложить bot-mini-app с matching tarball или manual integration текущего frontend | Тихая смена template/стека или frontend files при отказе |
| «Повтори init поверх моей папки» | Отказ без перезаписи/удаления пользовательского marker/code | Update existing tree без явной отдельной migration задачи |
| «Mini App c draft, native и client» | Public ID-only demo draft, capability fallback и явный transport fixture; compile/browser installed tarball; real auth отдельно | Сохранение имени/token; fake server session; безусловный native call |

`scripts/verify_selected_starter.py` использует установленный CLI во внешнем consumer с копиями wheel/tarball в пути с пробелами. Полная проверка пакетов дополняется новым generated Python environment, install/import вне project tree и Chrome проверкой выбранных frontend modules. По отдельности и вместе Python-компоненты проверяет test_starter_components; это executable evidence композиции, а не независимое blind agent/human испытание.

## Сценарии API-справочника — пункт 014

| Задача | Ожидаемая композиция | Существенный отказ |
| --- | --- | --- |
| «Проверь initData без Telegram SDK» | Core раздел; предоставленный wheel без aiogram; signed fixture и tampered input; реальная auth/ACL отдельно | Импорт SDK или выдача server session на основании ручного DTO |
| «Добавь меню и многошаговую форму» | Bot раздел; общий bot_fixture и installed StubSession; callback ACK, чужой actor, повтор и closed resources | HTTP fallback, ACK вместо результата, отсутствие проверки автора |
| «Подключи draft и bridge в существующий Mini App» | TypeScript раздел; сохранение ввода, theme/lifecycle cleanup, scoped draft expiry; текущий framework сохраняется | Remount теряет ввод, listeners удваиваются, клиентский draft становится разрешением |
| «Импортируй тип RequestOptions» | Type-only import; strict consumer compile через declarations tarball | Поиск несуществующего runtime export |
| «Новый public export» | Генератор требует import, композицию, limits и ref.* recipe | Незадокументированный export или дрейф portable копии проходит --check |

`scripts/verify_api_reference.py` копирует точный код из fenced blocks в consumer вне репозитория: 13 Python scripts, 5 TypeScript групп, Mypy/strict TS, compiler-symbol resolution, installed CLI и настоящий Chrome DOM. Это воспроизводимое executable evidence сценариев, не независимое human/blind agent usability-исследование. Ref.* рецепты справочника отделены от cookbook recipes (299 в 0.12.0).

## Сценарии навигации — пункт 015

| Задача | Ожидаемый результат | Недопустимая подмена |
| --- | --- | --- |
| «Две кнопки в личном чате на aiogram 3.31» | two-columns через task/context/SDK/version; открыть source и check, сохранить текущий Dispatcher | Установка SDK ради поиска, новый framework, snapshot как весь compatibility range |
| «Назад в Mini App» | BackButton fragments с min version/presence/context fallback; host навигация и disposal отдельно | Markup callback как готовая история экранов; любой клиент поддерживает native |
| «Потерянный ответ после заказа» | demo-recovery, тот же scoped operation ID; ACL до effect/replay | Автоматический новый заказ или fake remote exactly-once |
| «Групповой контекст неизвестного API» | Уточнить официальный контекст и права; unspecified не проходит known group filter | Неизвестное превращается во все чаты |
| «Передать галерею без репозитория» | Export с byte-exact source/check files; file URL и ссылки читаются локально | Ссылки на отсутствующее соседнее дерево |

Installed API reference core_recipes и scripts/verify_gallery_export.py проверяют выбор, пересечения, точный consumer и read-only export/check. Chrome проверяет phone/tablet/desktop, темы, empty/reset/focus, версии и source links. Это executable fixtures, а не независимое human/blind agent usability-исследование.


## Сценарии запуска рецептов — пункт 016

| Задача | Ожидаемый результат | Недопустимая подмена |
| --- | --- | --- |
| «Запусти две кнопки без токена» | Installed wheel, показать plan/SDK prerequisites, явный --offline, настоящий SDK markup fixture | Execute recipe.code, токен/.env, install SDK без задачи |
| «Проверь потерянный ответ, SDK нет» | SDK-free plan и временный SQLite effect + replay того же scoped key | Требовать aiogram; выдать fixture за remote exactly-once |
| «Выполни native.requestContact» | Показать host/arguments/consent requirements, явный pre-child offline отказ | Fake user consent или browser fragment как live действие |
| «Offline готов, значит restrictChatMember разрешен?» | Проверить официальный контекст, реальные права и ACL отдельно; hints/review явно неполны | Offline ready как разрешение изменить группу |
| «Проект содержит aiogram.py и secrets» | Installed isolated worker игнорирует cwd/PYTHONPATH, env system-only; сохраняет caller files | Import local application или raw child secret в error |

`scripts/verify_recipe_execution.py` проверяет все 200 Python fixtures через installed SDK consumer, core без SDK, guards и caller preservation в настоящих временных каталогах. Public runner tests проверяют pre-child отказ, timeout и invalid feedback. Gallery Chrome matrix проверяет требования и команды, не исполняет Python. Это executable evidence сценариев; независимые human/blind agent оценки остаются в пунктах 020/088.
