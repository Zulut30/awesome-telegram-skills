# Групповой бот: темы, права, заявки и модерация

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Самостоятельное приложение `examples/group-bot`, distribution `awesome-telegram-group-example` 0.1.0, использует предоставленный Python wheel библиотеки 0.24.0 и aiogram; CI проверяет пример на текущей версии библиотеки. Это пример композиции `BotSettings`, `build_request`, `event_router`, `ActionButton` и `action_menu`. Его `Application`, `Store`, `ProcessLock` и `Context` принадлежат приложению, не являются новыми публичными exports библиотеки и не требуют сервисного/магазинного примера.

## Что попробовать

| Команда | Результат |
| --- | --- |
| `/group_help` | Меню и правила подтверждения |
| `/rights` | Проверка bot/actor admin; нужное право проверяется для каждого действия отдельно |
| `/topic_info` | ID текущей группы и темы без изменения состояния |
| `/topic_create Название` | Предпросмотр создания темы; название 1–128 символов |
| `/topic_close`, `/topic_reopen` | Предпросмотр изменения конкретной текущей темы; General не поддержан |
| `/joins` | До 30 последних наблюдаемых заявок этой группы, не полный Telegram backlog |
| `/approve ID`, `/decline ID` | Предпросмотр конкретной наблюдаемой заявки из `/joins` |
| `/mute` в ответ на сообщение | Предпросмотр ограничения прав обычного участника на 10 минут |

Область примера — явно настроенные supergroup. Forum-команды требуют `is_forum`; автор действует от личного аккаунта. Анонимный `sender_chat`, бот, Business, чужая группа/тема/кнопка и callback без доступного сообщения не получают прав. Ограничение supergroup — выбор этого приложения: актуальный createForumTopic также имеет private context; этот пример его не реализует.

`/mute` временно выключает все перечисленные member permissions, а не только текст. Уже restricted, вышедшие, администраторы, боты и сам инициатор не принимаются как цель. Пример не удаляет сообщения, не банит и не делает массовых действий. Ответ другой темы не может стать целью текущей команды.

## Проверка без аккаунта Telegram

Из предоставленного checkout:

```bash
python scripts/build_release.py --ref HEAD --output output/release
```

```bash
python scripts/verify_group_bot.py --wheel output/release/awesome_telegram_patterns-0.24.0-py3-none-any.whl --output output/group-bot-check
```

Output должен быть новым каталогом, существующие каталоги и известные links отклоняются до build/install. Helper собирает отдельный app wheel и проверяет его source bytes, RECORD и entrypoint. В новом consumer вне репозитория устанавливает предоставленную библиотеку и приложение, проверяет installed origins, console `--help`, Mypy, 19 тестов с SDK Dispatcher и настоящей file SQLite, четыре отдельные процессные фазы и OS lock. Фазы: сохранение предпросмотра → подтверждение после рестарта → реальный `os._exit(77)` после synthetic createForumTopic до сохранения результата → восстановление unknown без повторной отправки. Shadow modules/.env текущего проекта не читаются и не исполняются.

Используется `StubSession` с обязательными зарегистрированными ответами; fixture не может переключиться на HTTP. В процессных фазах реальный SDK HTTP и Python DNS/connect запрещены. Fixtures искусственные: нет live модерации, Telegram permission/delivery acceptance или проверки privacy mode. Это не OS sandbox для чужого кода.

## Локальная поставка и live запуск

Нужны предоставленные wheel библиотеки и wheel приложения из собственного отчёта проверки. Пакеты не объявлены опубликованными в PyPI. Пример установки в новый venv (подставьте реальные локальные пути):

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe '<PATTERN_WHEEL>[aiogram]' '<GROUP_EXAMPLE_WHEEL>'
& .\.venv\Scripts\telegram-group-example.exe --help
```

```bash
uv venv .venv
uv pip install --python .venv/bin/python '<PATTERN_WHEEL>[aiogram]' '<GROUP_EXAMPLE_WHEEL>'
.venv/bin/telegram-group-example --help
```

Для существующего проекта сохраняйте его SDK/Dispatcher/storage: переносите нужную композицию, не создавайте второй polling consumer ради helper. Диапазон Python — >=3.11 по metadata; реально проверенная версия и SDK указаны в отчёте, не весь диапазон.

Live запуск выполняется отдельно владельцем в тестовой группе после настройки `BOT_TOKEN` в окружении, проверки действующего webhook/getUpdates consumer, минимальных прав и постоянной локальной БД. Parent каталога БД должен существовать. Например, для выбранного владельцем ID:

```powershell
& .\.venv\Scripts\telegram-group-example.exe --database 'C:\group-data\group.sqlite' --chat -1001234567890
```

```bash
.venv/bin/telegram-group-example --database ~/group-data/group.sqlite --chat -1001234567890
```

Повторяйте `--chat` для каждой разрешённой группы. Пример запускает polling; webhook и pending updates автоматически не удаляются. `resolve_used_update_types()` включает message, callback_query, chat_join_request, chat_member и my_chat_member. Доставка membership/join updates требует настроек и прав Telegram; отсутствие события не считается отсутствием пользователя/заявки. При миграции group → supergroup приложение сохраняет старый/новый 64-bit ID и блокирует старые предпросмотры. Новый ID нужно явно добавить в `--chat`; сохранённое подтверждение на него не переносится. Mapping остаётся в БД для сверки старых ссылок.

Один процесс на одну SQLite-базу и локальный диск; второй владелец отклоняется OS lock. Дополнительные workers/сетевой storage не приняты. Отмена coroutine дожидается owned SQLite work. Shutdown запрещает новые updates, отменяет и дожидается уже запущенных обработчиков перед закрытием SDK session и освобождением OS lock. Другой bot ID/schema не может переиспользовать базу. БД содержит IDs, названия созданных тем и результаты операций; защищайте её как прикладные данные. Invite links, bio, временный user_chat_id и query_id в таблицы не записываются. Срок подтверждения 5 минут и окно `/joins` 2 часа не удаляют journal и неизвестные результаты; retention/backup/restore настраивает владелец приложения.

## Права и повтор

Перед предпросмотром и перед эффектом приложение сначала запрашивает bot membership, затем actor membership. Нужны admin/creator и соответствующее право: can_manage_topics, can_invite_users или can_restrict_members. Timeout/ошибка чтения/несовпадение identity запрещают действие. Для mute заново проверяется обычный target member. Дополнительная проверка автора — правило приложения; сервер Telegram проверяет права самого бота. Между чтением и запросом возможна гонка изменения прав, которую локальный код полностью не устраняет.

Предпросмотр принадлежит bot/chat/thread/actor и ID конкретного сообщения этого бота. Callback data содержит только случайный ключ, не user-provided API параметры. ACK снимает индикатор кнопки и не означает успех. Cancel не отменяет уже отправленный запрос. Повтор команды определяется chat/message ID: update_id может сбрасываться после простоя и не используется как бессрочный ID операции.

Journal проходит `draft → ready → sending → done/rejected/unknown`. Claim хранится до SDK-запроса. Одна подтверждённая операция имеет одну попытку записи в Telegram; concurrent confirm и replay её не дублируют. Явные BadRequest/Forbidden/flood rejection сохраняются rejected без автоматических повторов. Timeout, cancellation, некорректный ответ или crash после отправки оставляют unknown; pending SDK-запрос может иметь внешний эффект. Сбой записи результата оставляет sending и управляемое объяснение, после рестарта sending станет unknown. Draft без надёжно сохранённого prompt становится stale; ready сохраняется до проверки срока. ACL и свежие права проверяются и перед возвратом сохранённого результата.

При unknown сначала сверьте тему/права/заявку в Telegram и сохранённые key/status/result в собственной БД. Не удаляйте строки и не нажимайте новую команду как автоматический retry: это отдельная операция с возможным повторным эффектом. Только владелец после сверки решает, нужен ли новый предпросмотр. SQLite обеспечивает локальные транзакции; exactly-once внешнего Telegram API не обещается.

## Заявки и membership

Обычный chat_join_request сохраняется с version `(date, update_id)`. Дубликат или более старое событие не переоткрывает его. Новая заявка, наблюдаемая до claim, делает старое подтверждение stale; действие другой группы её не меняет. Membership update завершает старую наблюдаемую заявку; изменение membership инициатора также инвалидирует его готовые предпросмотры.

Запрос на вступление, назначенный боту (`query_id`), отдельно проходит durable `queueing → pending/unknown`: приложение отвечает `queue`, оставляя решение администраторам. Timeout/cancellation/crash не превращают неизвестный ответ в доступную для approve заявку и не пересылают query автоматически. Это минимальная очередь, не автоматическая проверка пользователя и не Mini App verification. Urgent query queue не ждёт mutex команд/модерации этой группы; SQLite receipts сравнивают version, не затирая новую заявку. Если возраст события уже >=7 секунд или часы не согласованы, запрос не отправляется, состояние unknown. SDK queue ограничен тремя секундами. Реальную доставку в пределах срока Telegram и поведение под нагрузкой нужно отдельно проверить live. `user_chat_id` для личной переписки здесь не используется. Approve/decline API адресует user_id, без request version: если новая серверная заявка возникает после локальной проверки/claim или update задержан, локальное versioning не устраняет эту гонку. Неизвестные результаты требуют сверки, не автоматического retry.

## Источники и границы

Частично проверено 2026-10-05: [Bot API getChatMember](https://core.telegram.org/bots/api#getchatmember), [forum topics](https://core.telegram.org/bots/api#createforumtopic), [close/reopen](https://core.telegram.org/bots/api#closeforumtopic), [restrictChatMember](https://core.telegram.org/bots/api#restrictchatmember), [join requests](https://core.telegram.org/bots/api#chatjoinrequest), [query queue](https://core.telegram.org/bots/api#answerchatjoinrequestquery), [Update delivery](https://core.telegram.org/bots/api#update), [migrations](https://core.telegram.org/bots/api#message), [privacy mode](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get). Установленный aiogram 3.31.0 подтверждён настоящим импортом методов/types и Dispatcher event_update. Дата относится к перечисленным правилам этого примера; остальные источники проекта не обновлены.

Реальные права, delivery, бот/actor revoke, две группы/темы и migration проверяются отдельно в выбранных владельцем тестовых группах. Offline результат не делает библиотеку stable 1.0 и не подтверждает эксплуатационные лимиты.
