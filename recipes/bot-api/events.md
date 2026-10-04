# Какие действия бот получает

Bot API присылает `Update`: сообщения/редактирование, callback, inline queries/results, изменения участников, реакции, polls, payment queries, Business, boosts и другие виды текущего SDK. [Полный Update](https://core.telegram.org/bots/api#update), [getUpdates](https://core.telegram.org/bots/api#getupdates), [setWebhook](https://core.telegram.org/bots/api#setwebhook). Каталог методов: [README](README.md).

```python
from aiogram import Dispatcher
from telegram_patterns.aiogram import UpdateObserver, event_router

async def record(trace):
    # Только update_id/kind/phase/detail; actor_id/chat_id по умолчанию отсутствуют.
    # Ваш metric/log sink. Не сериализуйте исходный Update.
    print(trace.kind, trace.phase, trace.detail)

async def on_reaction(event):
    # Native MessageReactionUpdated. Реакция не подтверждает платеж/права.
    pass

dispatcher = Dispatcher()
dispatcher.update.outer_middleware(UpdateObserver(record))
dispatcher.include_router(event_router({"message_reaction": on_reaction}))
# Для собственного SDK polling/webhook entrypoint:
# allowed_updates = dispatcher.resolve_used_update_types()
```

`event_router` регистрирует native handlers всех доступных в установленном SDK update kinds, сохраняет SDK payload/DI. Handler сам отвечает на callback/payment query, проверяет контекст и выполняет работу. `UpdateObserver` пассивно видит только доставленные боту Update, записывает received → handled/unhandled/failed/cancelled; содержимое сообщений, callbacks, контакты, initData и строки исключений не копируются. IDs включаются лишь `include_ids=True`. Ошибка recorder не ломает handler; это best-effort telemetry, не durable audit/inbox.

Регистрация handler и allowed_updates не заменяют права Telegram. Для `message_reaction`/`message_reaction_count` нужны admin и явная подписка; для `chat_member` — admin и явное указание. Пустой allowed_updates по умолчанию исключает эти три вида. Middleware само не добавляет их в подписку. Учитывайте privacy mode группы, BotFather settings, ограничения Business и срок хранения Update.

В обычном Bot API нет универсальных read receipts, событий каждого клика по URL/copy-кнопке или наблюдения за набором текста пользователем. `sendChatAction("typing")` показывает действие **бота**, а не читает ввод пользователя. Нельзя получать всю историю личных чатов аккаунта через этот механизм; MTProto требует отдельной явно поставленной задачи с собственной сессией.

Команды/текст/contact/location/users_shared/chat_shared/poll, ACK и edit меню разобраны в [keyboards_bot.py](../../examples/python/keyboards_bot.py). [offline_keyboards.py](../../examples/python/offline_keyboards.py) исполняет тот же Dispatcher без HTTP и проверяет исходящие методы. При реальной проверке фиксируйте Telegram client/version/chat context отдельно.
