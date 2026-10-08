# Навигация в одном сообщении

Доступно с 0.15.0, проверено на 0.24.0.

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Optional aiogram extra, Python >=3.11, предоставленный локальный wheel. Подключайте `navigation_router` к текущему Dispatcher. Компонент хранит меню в памяти одного event loop: durable FSM, несколько worker и бизнес-операции требуют отдельного хранилища/сервиса проекта. Меню не заменяет авторизацию заказа или оплаты.

## Экраны и история

```python
from telegram_patterns.aiogram import (
    ActionButton, KeyboardLayout, MessageNavigation, NavigationScreen, navigation_router,
)

menu = MessageNavigation([
    NavigationScreen('home', 'Выберите раздел', [
        ActionButton('Каталог', 'catalog'), ActionButton('Помощь', 'help'),
    ], KeyboardLayout([2])),
    NavigationScreen('catalog', 'Услуги', [ActionButton('Доставка', 'delivery')]),
    NavigationScreen('delivery', 'Правила доставки'),
    NavigationScreen('help', 'Помощь'),
])
router = navigation_router(menu)
# Existing Dispatcher: dispatcher.include_router(router)
# Existing authenticated /menu handler:
# await menu.open(message.bot, message.from_user.id, message.chat.id)
```

Первый `open()` отправляет одно plain-text сообщение. Link использует `ActionButton.key` как ключ объявленного экрана; неизвестный или недоступный с текущего экрана переход отвергается. После подтвержденного редактирования текущий экран попадает в history. «Назад» снимает последний экран history; на корне возврата нет. «Обновить» перерисовывает текущий экран с новой версией. Повторный explicit `open()` для того же bot/owner/chat/thread редактирует то же сообщение и сбрасывает history к выбранному экрану — это действие пользователя, например `/menu`, не автоматический retry.

Plain text передается с `parse_mode=None`, независимо от глобального SDK default. Native styles/custom emoji используют явные `KeyboardCapabilities`; unknown defaults сохраняют стандартную текстовую кнопку. В private/group/supergroup выбирайте соответствующий `chat_type`, для темы передавайте `message_thread_id`. Inline, Business, channel, guest и сообщения другого бота этот компонент не обслуживает.

## Проверки кнопки

Callback содержит opaque session token, revision и target. Token не является отдельным правом доступа. До edit проверяются owner, bot, chat, thread, message, доступность сообщения, expiry, revision и разрешенный transition. После ожидания lock те же проверки выполняются снова. Два одновременных нажатия одной версии дают один переход; второе получает stale. ACK отправляется перед ожиданием lock/API. `NavigationResult` сообщает accepted/denied/stale/unavailable/unknown; foreign scope не раскрывает чужое состояние.

`NavigationState` — frozen snapshot с token, scope, message_id, screen, history, revision, expires_at и phase. `get_state()` — host API; проект проверяет identity до выдачи такого snapshot клиенту. DTO-конструкторы сами не устанавливают права. `on_result(query,result)` optional async hook выбирает безопасный feedback-канал; ошибка hook не откатывает уже подтвержденный edit. Пример делает дополнительный callback answer после ACK; доставка такого уведомления в live Telegram проверяется отдельно.

## Отказы и восстановление

| Событие | Состояние и следующее действие |
| --- | --- |
| Чужой owner, другой bot/chat/thread/message, неверный target/revision, expired token | ACK и отказ, без edit и изменения history |
| Явный TelegramBadRequest на edit | Подтвержденный экран/history сохранены. Ошибка не выводит server text; повтор допустим по прежней действительной кнопке. Номер неудачной попытки больше не используется |
| Timeout, cancel или неподходящий ответ после возможного edit | Phase unknown; текущий подтвержденный экран/history сохранены. Обычные переходы заблокированы; stale/foreign guard остается. Explicit owner `/menu` перерисовывает известный экран на том же message_id с новой revision. Это безопасная перерисовка UI, не сверка оплаты |
| Неизвестный исход первого SendMessage | message_id неизвестен; повторный open отказывает без повторной отправки даже после TTL. Host принимает отдельное решение о `discard()` и новом меню; возможно осиротевшее сообщение |
| Перезапуск процесса | Старый token отсутствует, кнопки stale. Новый explicit `/menu` начинает новое сообщение; восстановление прежней history не обещано |
| Deleted/inaccessible сообщение | Guard/SDK rejection; автоматической отправки замены нет. Host может явно discard и создать новое меню |

Component limits: 1..100 экранов, ключ 1..24 ASCII `[A-Za-z0-9_-]`, reserved `_back`/`_refresh`, до 98 links на экран плюс controls. Prefix 1..8 ASCII символов с `:`, callback до 64 UTF-8 bytes. `max_history=50` (1..1000) ограничивает глубину; при переполнении возвращается unavailable, история не обрезается молча. `max_sessions=1000` (1..100000) и TTL 1800 секунд ограничивают локальную память. TTL использует monotonic process clock и продлевается только после подтвержденного edit/send. Expired ready меню освобождаются при open; unknown send/edit не удаляются автоматически даже после TTL. Explicit recovery edit сохраняет прежний message_id после истечения TTL; unknown initial send по-прежнему не повторяется. `discard(bot_id,owner_id,chat_id,message_thread_id=...)` дожидается edit и забывает локальное меню, не удаляя его из Telegram.

Бот, session, Dispatcher/FSM и handler tasks принадлежат host. Завершайте прикладные tasks до закрытия SDK session. Cancellation edit оставляет unknown и освобождает menu lock. Компонент не отправляет network retry, не меняет webhook/polling и не обещает сохранение после рестарта или exactly-once Telegram delivery.

## Пример и evidence

`navigation_bot.py` показывает private `/start` и `/menu`, ряды 2/3, history и безопасный feedback. `offline_navigation.py` запускает ту же композицию через настоящий SDK Dispatcher/StubSession: owner, back, stale, unknown edit и explicit reopen. `bot_navigation.py` в справочнике — полный standalone пример через публичные exports, включая state/result snapshots и discard. В галерее найдите `demo-navigation` по «назад», «история» или «одно сообщение»; closed offline fixture не исполняет произвольный найденный код.

SDK/mock evidence подтверждает guard и исходящие методы, а не live appearance/доставку уведомления, права Telegram или физические устройства. Live acceptance остается отдельной задачей. Копированный навык использует предоставленный installed wheel и свои references; исходный репозиторий для чтения этого контракта не требуется.

Источники частично сверены 5 октября 2026 года: [CallbackQuery](https://core.telegram.org/bots/api#callbackquery), [answerCallbackQuery](https://core.telegram.org/bots/api#answercallbackquery), [InaccessibleMessage](https://core.telegram.org/bots/api#inaccessiblemessage), [editMessageText](https://core.telegram.org/bots/api#editmessagetext), [aiogram Router 3.31.0](https://docs.aiogram.dev/en/latest/dispatcher/router.html). Проверяйте установленную SDK/API версию; эта проверка не обновляет весь source catalog.
