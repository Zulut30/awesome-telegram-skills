# Текстовые формы

Доступно с 0.3.0, проверено на 0.24.0.

Используй для короткой формы с несколькими текстовыми шагами в обычном личном чате Python-бота на aiogram. Extra aiogram устанавливается из предоставленного локального wheel/репозитория. Другой SDK/сложный существующий dialog сохраняются.

## Подключение

```python
from telegram_patterns.aiogram import InvalidField, TextField, text_form_router

def topic(value: str) -> str:
    value = value.casefold()
    if value not in {"python", "typescript"}:
        raise InvalidField("Введите Python или TypeScript.")
    return value

fields = [TextField("topic", "Стек", "Python или TypeScript?", validate=topic),
          TextField("brief", "Задача", "Кратко опишите задачу.", max_length=256)]
dispatcher.include_router(text_form_router(fields, applications.submit))
```

`applications` — сервис текущего проекта с `async submit(submission: FormSubmission) -> str`. Router добавляется перед общим message catch-all. /apply начинает форму; неверный текст/медиа оставляют текущий шаг; /back удаляет значения начиная с предыдущего шага; /cancel очищает draft. Последнее поле показывает plain-text сводку с кнопкой «Отправить», без преждевременного создания заявки. Команды проекта вроде /help проходят к его Router.

Требуется включенная FSM event isolation текущего Dispatcher. Для **нового** простого однопроцессного бота достаточно `Dispatcher(events_isolation=SimpleEventIsolation())` с импортом из `aiogram.fsm.storage.memory`. В существующем проекте сохрани его storage/lock; не меняй инфраструктуру молча. Default DisabledEventIsolation и выключенный FSM отклоняются до изменения данных. FSM key должен содержать actor/bot/chat. Имя формы уникально в приложении: 1..16 lowercase ASCII символов; command отличается от back/cancel. До 10 уникальных полей, value максимум 256 UTF-16 units. Синхронный validator возвращает строку или выбрасывает InvalidField; ошибки кода не маскируются как ошибки пользователя.

## Контракт сервиса и восстановления

FormSubmission содержит bot_id/actor_id/chat_id из update, стабильный operation_id и копию immutable values. Values исключены из repr; сериализация/логи могут раскрыть ответы. Личность update не дает прав на чужие объекты. Сервис проверяет значения/ACL перед effect и перед replay; стоимость и объектные права не берутся из ответов формы.

Сервис надежно сохраняет effect и результат по scope, построенному из проверенной личности, и operation_id. Для уже существующего SQLite проекта подойдет SQLiteOnce; таблица бизнес-записей принадлежит приложению, синхронный run выносится через asyncio.to_thread. В PostgreSQL реализуй дедупликацию/транзакцию текущим стеком. Не ограничивайся in-memory set, если нужна защита после рестарта.

Перед сервисом callback ACK снимает spinner; кнопка должна совпасть с текущими owner/operation/review message. Два конкурентных подтверждения сериализует выбранная SDK isolation. Успешный return очищает форму **до** отправки feedback, поэтому ошибка feedback сама по себе не повторяет service call.

Exception/cancellation оставляет ту же identity/values и блокирует /back, /cancel, новый /apply. Пользователь повторяет последнюю кнопку для сверки **той же операции**; service обязан возвращать сохраненный результат либо безопасно продолжать ее. Автоматического сетевого retry нет. Exception передается error handler проекта, текст ошибки пользователю контролируется. Service response — nonempty plain text до 4096 UTF-16 units.

MemoryStorage теряет форму при рестарте, SimpleEventIsolation — lock одного процесса. Настрой persistent storage/согласованный lock только если этого требует продукт; добавь durable recovery record для неизвестных операций и способ найти их после рестарта/удаления сообщения. Не удаляй pending identity по TTL обычного draft. Необработанная несовместимая схема состояния отклоняется; миграцию/сверку выполняет проект. Retention и очистка бездействующих форм не реализованы автоматически. Группы/Business, contacts/media и произвольные ветвления остаются у подходящего SDK dialog.

## Проверка интеграции

Через настоящий Dispatcher и StubSession проверь: неверный ввод, /back с изменением значения, отмену, двух пользователей, дубли текста, старую/чужую кнопку и ACK; затем реальные конкурентные подтверждения с блокирующим service callback. Смоделируй commit + потерю ответа: повтор должен использовать тот же operation_id и оставить одну бизнес-запись. Отдельно проверь ошибку feedback и cancellation. Статическая загрузка навыка не подтверждает решения агента; fake transport не подтверждает Telegram delivery.

Источники, сверенные для этого контракта 3 октября 2026: [FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [storage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html), [Dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html). Установленный aiogram 3.31.0 использует lock до чтения raw_state. Для иной версии проверь код и API проекта.
