# Миграция с 0.5.0 на проверенные артефакты 0.28.0

Этот guide относится к переходу с frozen 0.5.0 на **точные development artifacts 0.28.0**. Рабочие before/after consumers находятся в [examples/migration](../examples/migration/README.md). Это проверка локальной миграции, не объявление 1.0 RC или production-ready статуса. Применимость к другим bytes и версиям нужно проверять новым прогоном.

## Версии и границы доказательства

| Роль | Source commit | Артефакт | SHA256 |
| --- | --- | --- | --- |
| До, `v0.5.0` | `73963b2e4add8ee6922bc07a6b7baa4104fdd00e` | `awesome_telegram_patterns-0.5.0-py3-none-any.whl` | `8996afaac89555c4796f4a5cd064cd31ae41eb692d01de6672f53316099236a6` |
| До | тот же | `awesome-telegram-patterns-0.5.0.tgz` | `7ee13e86b343665807a57ccffda8900ce538f72f2e9a659fb3a441bd32b163a3` |
| После, 0.28.0 | `92a9d151dc57d85cc5f1eb614f9980e808b36b59` | `awesome_telegram_patterns-0.28.0-py3-none-any.whl` | `e0b42b53f1228fc804ab37b73675641fada1c148aa9eebffd11b05af1859fb7d` |
| После | тот же | `awesome-telegram-patterns-0.28.0.tgz` | `dd24c7db27d9f1dd1f2dcc36a49bd67d14577eec1c7a15216632f92615ca3931` |

Исторические пакеты собраны без патчей из `git archive` указанного commit; `SOURCE_DATE_EPOCH=1791122697`, SHA архива `2e4d02550c81225331765228418951a5dc0632f4d97b8907c98685a84ab2d0f8`. Команды frozen-ref сборки и canonical runner — в README примера. Установка скилла не устанавливает runtime package; не заменяйте локальные artifacts одноимёнными registry packages. Сохраняйте стек существующего проекта и лицензии/third-party notices пакетов.

В проверенной исторической поверхности сохранены 47 Python имён и 23 TypeScript root declarations; удалений нет. В 0.28.0 обнаружено 107 TS exports. Все 99 прежних native metadata records совпали; Serverless добавлен отдельно. Inventory Python охватывает явно публичные root/aiogram/testing/cli exports; случайные SDK reexports и private modules не включены. Это не утверждение, что у новой библиотеки всего 47 Python exports.

Статический inventory дополняют реальные installed consumers, SQLite, сохранённый FSM snapshot, runtime transport и девять compiler witnesses. Compiler — TypeScript 7.0.2; отдельный classic declaration parser — 5.9.3. Parser не заменяет compiler и runtime. DOM, реальные устройства, Telegram delivery, provider accounts и платежи этим сценарием не проверяются. Сводка приёмки: [migration-098-acceptance.json](internal/migration-098-acceptance.json).

## Контракты, требующие изменения consumer

В таблице пути сокращены относительно `examples/migration/`. В каждом runtime consumer `before` выполняется со старым установленным пакетом, `after` — с новым; runner сохраняет исходное состояние между ними.

| Контракт | Что изменилось | Работающий путь |
| --- | --- | --- |
| `SQLiteOnce.run` payload | Старый JSON encoder принимал tuple и integer dict keys. Новый требует строгие JSON values. | `python_consumer.py`: известный tuple явно преобразуется в array с прежними scope/key/hash; replay возвращает старый receipt без effect. Неоднозначные keys отклонены, не нормализованы молча. |
| `VerifiedLaunch.user` | Раньше readonly был только верхний mapping; теперь вложенные dict/list тоже readonly. `json.dumps(dict(launch.user))` больше не подходит для вложенных данных. | `python_consumer.py`: `launch.as_dict()` создаёт отделённую копию. Авторизация использует проверенный `launch.user_id`, не редактируемую копию. Tamper, duplicate hash и expired launch отклонены на обеих версиях. |
| `doctor()` JSON | `checks[*].detail` заменён на `reason` и `remediation`. | `python_consumer.py` проверяет обе schema и отсутствие synthetic token; обновите свои JSON consumers. Старый CLI не имеет `--version` (код 2); `importlib.metadata.version` работает на обеих версиях. |
| `BotSettings.from_env` placeholder | Старый from_env принимал token-shaped placeholder `100:REPLACE_WITH_TOKEN`; новый отказывает. Прямая проверка пустого token существовала уже в 0.5.0. | `python_consumer.py`: negative inputs проверены отдельно; валидный synthetic token-shaped input работает на обеих версиях. В настоящей конфигурации замените placeholder выданным token; не обходите preflight. |
| `ApiClient` URL | Раньше base `https://host/api/v1` + `/orders` давал `/orders`; теперь сохраняется `/api/v1/orders`. Same-origin absolute URL вне base prefix отклоняется. | `typescript_consumer.mjs`: переносимая конфигурация обеих версий — base `https://host/api/v1/`, relative route `orders`. Сверьте фактические маршруты backend. |
| `ApiError.outcome` | Union расширен значением `rejected`; прежний exhaustive switch больше не компилируется. | `types/legacy-error-exhaustive.ts` проходит до обновления, отклоняется после. `types/after-adapted.ts` обрабатывает rejected отдельно; unknown запись сверяется по исходному ID. |
| `TelegramNativeAPI.call` | Аргументы теперь типизированы по методу; неверный haptic style `loud` отклоняется compiler. | `types/legacy-native-invalid.ts` и `types/after-adapted.ts`: валидировать входные значения; `light` компилируется и реально вызывается в runtime consumer. |
| Native metadata minimum | Добавленный Serverless имеет неизвестный minimum; `minVersion` стал nullable. Прежние records не изменились. | `types/legacy-minimum.ts` отклоняется после обновления; `after-adapted.ts` проверяет null. Тип берётся из `typeof TELEGRAM_NATIVE_METHODS[keyof typeof TELEGRAM_NATIVE_METHODS]`; экспортированного `NativeMethodSpec` нет. |
| Bridge platform | SDK object без platform раньше мог считаться Telegram. Теперь нужен наблюдаемый platform. | `typescript_consumer.mjs`: outside fallback для отсутствующего platform, inside для tdesktop. Это UI detection, не auth. |
| Bridge listener errors | Ошибка первого listener раньше останавливала fanout; теперь другие получают snapshot до передачи ошибки host. | `typescript_consumer.mjs`: оба варианта исполнены; изолируйте ошибки собственных listeners и не используйте их порядок как business transaction. Dispose снимает subscriptions. |
| `run_bot` boot order | Default preflight вызывает GetMe до установки menu/polling. | `sdk_consumer.py`: fake transport старой версии наблюдает SetMyCommands, новой — GetMe → SetMyCommands. В offline fixtures нужен GetMe responder; production preflight не отключается. Публичный host Dispatcher subclass изолирует polling, реальный token не проверяется. |
| `ApiClient.timeoutMs` | Старый таймер принимал >2147483647ms и переполнялся; новый отказывает до transport. | `api_contract_consumer.mjs`: старый overflow и новый отказ наблюдаются; конечный положительный 1000ms работает на обеих версиях. |
| `ApiClient` JSON body | Старый POST с function body мог уйти без JSON, потому что JSON.stringify возвращает undefined. | `api_contract_consumer.mjs`: новый отказ до transport; явный JSON object с прежним original ID работает. |
| `headers()` callback error | Старый consumer получал исходный текст исключения; новый — контролируемый PatternError с outcome rejected. | `api_contract_consumer.mjs`: transport не вызывается, private текст скрыт после обновления. Это не unknown отправка; blind retry не нужен. |
| Frozen starter | В wheel 0.5.0 нет `.env.example.txt`; create_starter отказывает до создания папки. | `python_consumer.py` сохраняет исторический дефект; 0.28 создаёт свежий target и отказывается от существующего, сохраняя host marker. Старый проект не переписывается starter ради успешной проверки. |

## Классификация всех изменившихся descriptors

Полный machine-readable список — [contract-map.json](../examples/migration/contract-map.json). Ниже перечислены все 19 Python и 8 TS descriptors, изменившиеся относительно исторической поверхности. Optional добавления не являются удалением старого API.

| Python public name | Класс изменения / before-after |
| --- | --- |
| `telegram_patterns.BotSettings` | Optional test_environment/env_file, сохранённая прямая валидация; прежний валидный token/from_env и redacted repr проверены core consumer. Новый placeholder guard требует пути выше. |
| `telegram_patterns.aiogram.BotSettings` | Тот же совместимый reexport; прежний runner composition работает в SDK consumer. |
| `telegram_patterns.InvalidInitData` | Добавлены taxonomy/code; ValueError catch сохранён и проверен invalid initData. |
| `telegram_patterns.OperationConflict` | Taxonomy дополнена, ValueError сохранён; changed payload с прежним ключом реально отклонён. |
| `telegram_patterns.Recipe` | Optional metadata с defaults; старый positional constructor выполнен. Verification annotation получила имя/ограниченный набор значений. |
| `telegram_patterns.RecipeCatalog` | Optional фильтры; прежний `.get('two-columns')` и packaged catalogue читаются. Verification annotation уточнена. |
| `telegram_patterns.SQLiteOnce` | Добавлен run_guarded; run сохранён. Реальный replay и current ACL deny/allow проверены. Strict JSON change описан выше. |
| `telegram_patterns.StarterPlan` | Optional components/requested_components; старый positional constructor выполнен. |
| `telegram_patterns.VerifiedLaunch` | Optional launch fields и as_dict; deep-readonly требует пути выше. |
| `telegram_patterns.aiogram.InvalidAPIRequest` | Новый taxonomy parent, прежний ValueError остаётся в MRO. Constructor/import сохранены, inventory сравнивает bases. |
| `telegram_patterns.aiogram.InvalidField` | Optional localization kwargs; прежний explicit message и ValueError работают в SDK consumer. |
| `telegram_patterns.aiogram.UpdateTrace` | Literal вынесен в именованный UpdatePhase; прежний positional constructor выполнен. |
| `telegram_patterns.aiogram.callback_router` | Optional texts; прежний callback реально исполнен. |
| `telegram_patterns.aiogram.paginated_menu` | Optional texts; прежняя pagination реально построена и проверена. |
| `telegram_patterns.aiogram.run_bot` | Optional verify_token=True меняет preflight side effect; работающий путь выше. |
| `telegram_patterns.aiogram.text_form_router` | Optional schema_version/lifetime/texts. Default schema1 принимает старый unknown snapshot; explicit schema2 отказывает без сброса ID. |
| `telegram_patterns.cli.doctor` | Optional flags совместимы; JSON shape требует изменения consumer, см. выше. |
| `telegram_patterns.create_starter` | Optional components; historical packaging gap и новый no-overwrite путь проверены. |
| `telegram_patterns.testing.StubSession` | Optional API server configuration; прежняя `.respond()` композиция действительно работает. |

| TypeScript public name | Класс изменения / before-after |
| --- | --- |
| `ApiError` | Новый PatternError parent и optional retryAfterMs; Error catch сохранён. Outcome union расширен, exhaustive switch обновляется. |
| `ClientOptions` | Optional rejectedBeforeEffect/transport contract additions; URL prefix semantics и error redaction требуют учёта, проверены runtime. |
| `RequestOptions` | Optional rejectedBeforeEffect; runtime limits/JSON validation описаны выше. |
| `DraftOptions` | Optional schemaVersion/migrateFrom; default schema1 совместима, явный mapper проверен. |
| `SelectionDraftStore` | Default read/write и scope сохранены; opt-in v1→v2 ограничивает TTL и удаляет старый scoped key только после успешного чтения/сохранения нового. |
| `TelegramNativeAPI` | Типизированные method arguments/results; валидный call сохранён, небезопасный старый аргумент отклоняется compiler. |
| `UnsupportedTelegramCapability` | Constructor без аргументов сохранён; Error parent расширен через UnsupportedCapability/PatternError. Descriptor MRO/extends изменён, это совместимое расширение taxonomy. |
| `createTextField` | Структурный return получил имя TextFieldControl; статический descriptor изменён, DOM behavior этой миграцией не проверен. |

Новые session/auth/payment APIs не конвертируют произвольные старые таблицы и не дают оснований считать legacy state оплаченным. Случайная смена source filenames при сохранённом публичном reexport сама по себе не требует переписывания consumer на private implementation.

## Сохраняемое состояние и неизвестный результат

1. Перед настоящим обновлением согласуйте snapshot с writers: остановите прежних workers или используйте согласованный online backup. Не запускайте два polling consumer для одного бота. В примере before и after исполняются последовательно.
2. After consumer сначала открывает исходную SQLite через `mode=ro`, включает `query_only`, делает настоящий SQLite backup и проверяет integrity. Только затем обращается к новой библиотеке. SHA backup записывается в report; исходные schema, receipts и business rows сравниваются целиком.
3. Таблица SQLiteOnce сохраняет scope, operation_key, payload_hash и result_json. Прежний completed receipt возвращается с исходным ID, без повторного business effect; business count остаётся 1. ACL проверяется отдельно через run_guarded даже при replay. Изменённый payload с прежним ключом даёт conflict.
4. Старый public transaction boundary создаёт host-owned финансовые fixture rows `unknown` и `legacy-unbound`. Новый consumer оставляет их статус и original IDs неизменными. Completed local transaction не подтверждает payment success. Нет paid, нового invoice, send или попытки угадать provider identity.
5. Неизвестное/непривязанное финансовое состояние остаётся readonly/quarantine до явной сверки владельцем с подтверждённым provider identity. Если доказанного mapping нет, эта часть миграции останавливается. Сохраняются backup, исходный ID и reason; доступ не выдаётся.
6. FSM consumer получает настоящий old unknown submission, сохраняет snapshot через публичные `get_state/get_data` и восстанавливает через `set_state/set_data`. Default schema1 сохраняет original operation ID, `/apply` и `/cancel` не сбрасывают unknown; чужой actor отклонён. Host callback выполняет reconciliation того же ID один раз. Это не новый внешний effect. Schema2 оставляет old state неизменным и возвращает отказ.
7. Новый durable lifetime/другая storage не подключаются автоматически. Старые snapshots без lifetime требуют отдельного host mapping/review. Не очищайте pending ID ради новой schema.
8. Selection draft содержит только allowlisted selection IDs: token/paid поля отбрасывались уже старой версией. Явный mapper v1→v2 не переносит auth/payment state, не расширяет user scope, не продлевает исходный срок; пользователь 99 не читает draft пользователя 42.
9. При сбое остановите новых writers и сначала сверьте реальные эффекты. Не восстанавливайте старый backup поверх новых подтверждённых платежей. Пример не выполняет автоматический production rollback и не удаляет предыдущий output.

## Как оценивать результат

Выполните полный [runner](../examples/migration/README.md) с `--with-sdk --with-types`, проверьте artifact SHA, exit 0 и `report.json.passed=true`. Существующий output должен быть отвергнут до запуска installers, host marker и предыдущий отчёт — сохраниться. Для новой версии/source bytes требуется новый output и отдельная приёмка.

Совместимость signatures/declarations не доказывает поведение всех приложений. Эта проверка покрывает перечисленные контракты; live Telegram, физические устройства, платежные кабинеты и 1.0 RC требуют своей приёмки. Общие правила: [versioning](versioning.md), [release process](releasing.md), [подключение библиотеки](for-agents.md).
