# Выбрать компоненты нового проекта — 0.17.0

CLI устанавливается из предоставленного локального wheel. Он создает новый проект и подключает выбранные публичные API, сохраняя Python/aiogram и TypeScript starter. Он не устанавливает зависимости, не запускает polling и не настраивает серверную авторизацию. Для существующего проекта используйте точечные импорты: `init` принимает только новый target с существующим обычным родителем, без symlink/junction ancestors.

Список доступен в core без aiogram и артефактов:

```powershell
python -m telegram_patterns init --list-components
```

В каждом record указаны intent, templates, requires, дополнительные files, commands, callback_prefixes и min_library_version. Это закрытый набор из **15 групп starter**, входящих в общий каталог компонентов. Список не обещает генерацию всех прикладных workflows библиотеки: backend auth, БД проекта, денежный ledger и расширенные provider adapters подключаются через публичный API с контрактами проекта.

## Что создается

| Выбор | Подключение и проверяемое поведение |
| --- | --- |
| База Python: bot-settings, command-replies, action-menu, callback-router, bot-polling, bot-test-transport | /start, /help, кнопка с ACK, explicit live lifecycle и offline.py. Эти группы всегда нужны текущему шаблону |
| База bot-mini-app: mini-app-bridge, responsive-shell | Форма, тема/lifecycle, compiled ESM; backend еще не подключен |
| native-keyboards | /keyboard, две/три кнопки в рядах, стили primary/success, разрешенный публичный выбор и stale fallback |
| paginated-menu | /catalog, страницы 1–3, редактирование сообщения и отдельные namespaces выбора/страницы |
| text-form | /apply, проверка Python/TypeScript, review, /back, /cancel, явное подтверждение. SimpleEventIsolation включается; MemoryStorage временный. Service проверяет собственный private scope и только валидирует ввод |
| update-events | Outer middleware с bounded kind/phase counters; raw Update и IDs не сохраняются; не durable audit |
| mini-app-native-api | HapticFeedback на user click; отсутствие capability дает локальный fallback, disposal удаляет handler |
| selection-draft | Только публичный demo-service ID и TTL. Anonymous scope — для публичного preview; реальный account scope должен прийти с backend. Имя формы/token не сохраняются; неизвестный ID очищается |
| api-client | createClient factory с endpoint/headers/transport host; UI проверяет локальный fixture без HTTP. Настоящий backend/session не подставляются автоматически |

Все семь дополнительных групп можно сочетать: команды, callback prefixes и файлы не пересекаются. Выбор не уменьшает содержимое wheel/tarball — он определяет подключение модулей в созданном проекте. IDs регистрозависимы; передается не более 60 элементов (лимит CLI blueprint, не Telegram). Повторяющиеся IDs нормализуются; порядок результата фиксирован реестром. Не выбранные дополнительные модули не создаются и не импортируются. Dependency closure и обязательные группы показаны в `components`, исходный выбор — в `requested_components`.

## Создать бот с формой и событиями

Установите wheel 0.17.0 в отдельное tools окружение или используйте уже установленный CLI этой версии. Пути ниже заменяются на предоставленные артефакты; пакетов с нашим именем в registry не предполагается.

```powershell
$tgWheel = 'C:\path\awesome_telegram_patterns-0.17.0-py3-none-any.whl'
python -m telegram_patterns init .\new-bot --library $tgWheel --component text-form --component update-events --dry-run
python -m telegram_patterns init .\new-bot --library $tgWheel --component text-form --component update-events
```

Dry-run возвращает `created: false`, все относительные `files`, `components`, `requested_components`, версию и target; никакие файлы/каталоги не записываются. Та же команда без dry-run создает ровно перечисленные файлы. После явной установки generated project выполните `offline.py` и `offline_components.py` из его каталога. Последний прогон проверяет выбранные Python routes, foreign/stale input, ACK и закрытие FSM/session. Ни один из них не обращается к Telegram. Установщики зависимостей могут использовать интернет.

## Добавить Mini App

```powershell
$tgTS = 'C:\path\awesome-telegram-patterns-0.17.0.tgz'
python -m telegram_patterns init .\new-mini --library $tgWheel --template bot-mini-app --typescript $tgTS --component native-keyboards --component paginated-menu --component api-client --component selection-draft --component mini-app-native-api --dry-run
```

После просмотра выполните ту же команду без dry-run. Дополнительные `.ts` файлы импортируются и монтируются в `mini-app/src/main.ts`; `disposeApp()` освобождает их handlers/UI. Generated project включает все выбранные Python modules в setuptools py-modules, поэтому установленный `app` работает вне дерева созданного проекта. Нужны matching wheel/tarball; npm получает file filesystem path с буквальными пробелами, Python — file URI. После переноса обновите пути.

## Конфликты и совместимость

Frontend component + template bot, несовпадающие версии артефактов, недостающий tarball, неизвестный ID, слишком старый API компонента и коллизии файлов/команд/prefix отклоняются до создания target. `StarterConflict`/CLI JSON содержат фиксированный `reason`, explanation и supported IDs; исходный неизвестный input не отражается. Причины component-template/artifact-version/component-version подсказывают выбрать template, matching artifacts или сверить минимальную версию. `init --list-components` не принимает параметры создания.

Existing target отклоняется даже если это пустой каталог. Повторная команда не обновляет проект и не перезаписывает пользовательский код. При ошибке ввода target не создается; при FS ошибке во время уже начатой записи может остаться частичный новый каталог. Он не удаляется автоматически. Это новая композиция проекта, а не мигратор существующих приложений.

`create_starter(..., components=None)` сохраняет прежний набор по умолчанию. Новый keyword принимает Sequence[str]; строка целиком/нестроковые IDs не подходят. Пять прежних positional fields StarterPlan сохранены; новые components/requested_components имеют пустые tuple defaults. Никакой обязательной новой инфраструктуры нет.

Сверено 2026-10-04: [официальный HapticFeedback](https://core.telegram.org/bots/webapps#hapticfeedback), impactOccurred('light') и gate 6.1. Метод не удостоверяет пользователя и не гарантирует физическую вибрацию. Новая композиция проверяется installed CLI/wheel/tarball, настоящим synthetic Dispatcher и Chrome viewport/theme cases; native SDK для haptics — fixture. Live Telegram, backend auth, durable FSM и реальные устройства требуют собственных сценариев.
