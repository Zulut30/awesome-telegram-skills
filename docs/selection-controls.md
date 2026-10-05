# Составной выбор в боте — 0.16.0

`SelectionMenu` хранит server-owned черновик: toggle, multiselect, количество и фильтр. `SelectionSpec` задает разрешенные значения, границы и версию ресурса. Core импортируется без SDK. `selection_keyboard` и `selection_router` требуют optional aiogram extra; подключайте Router к существующему Dispatcher. Пакеты предоставляются локальными wheel/tarball.

```python
from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionSpec
from telegram_patterns.aiogram import selection_keyboard, selection_router

# Host получает эти IDs из аутентифицированного события и своего отправленного сообщения.
context = SelectionContext(bot_id=100, owner_id=42, chat_id=42, message_id=100)
spec = SelectionSpec(
    [SelectionOption('alpha', 'Alpha', ['basic']), SelectionOption('beta', 'Beta', ['extra'])],
    toggles={'notify': 'Уведомлять'},
    filters={'all': 'Все', 'basic': 'Основные', 'extra': 'Дополнительные'},
    quantity_min=1, quantity_max=5, min_selected=1, max_selected=2,
    confirm_text='Удалить выбранные элементы', resource_version='server-revision-1',
)
menu = SelectionMenu(spec, context)
markup = selection_keyboard(menu.state)
router = selection_router(menu)
# existing_dispatcher.include_router(router)
# await bot.edit_message_text(menu.state.text(), chat_id=context.chat_id,
#     message_id=context.message_id, parse_mode=None, reply_markup=markup)
```

## Значения и версии

Сервер проверяет owner, bot, chat, thread, message, opaque session token, canonical revision и TTL. `SelectionContext` создает host из проверенного события; callback data не является источником identity. `check()` — preflight, `apply()` повторяет guards под lock. Другой actor/context не получает чужой snapshot. DTO `SelectionState` можно использовать для отображения, но он не становится серверным состоянием при передаче от клиента.

`state.callback(action)` создает код кнопки; его создание не дает разрешение. `s:key` меняет multiselect, `t:key` — bool toggle, `q:inc/dec` — количество, `f:key` — фильтр. Нет передачи произвольного числа, цены, ID заказа или разрешений. Неизвестный, disabled или скрытый текущим фильтром вариант отклоняется. Фильтр сохраняет уже выбранные скрытые элементы: полный выбор виден в summary. `max_selected` ограничивает выбор, `min_selected` проверяется перед подтверждением. Цвет сохраняет понятный текст и использует существующий capability fallback; отсутствующий disabled вариант не показывается кнопкой.

Каждый принятый переход увеличивает revision. Повтор и одновременное нажатие одной версии не меняют выбор второй раз. Синхронные операции core сериализуются в одном процессе; UI Router дополнительно сериализует hooks/edit одного меню в одном event loop. Изменяйте меню через один прикладной поток, чтобы внешние записи не оставляли старый экран поверх нового.

## Опасное действие

`ask` сначала показывает summary и отдельную кнопку «Да», привязанную к текущему выбору, revision и случайному confirmation ID. Срок подтверждения по умолчанию 60 секунд и не превышает оставшийся TTL меню. `back` возвращает редактирование, `cancel` закрывает черновик, `refresh` отзывает открытое подтверждение. Новые значения требуют нового `ask`. Просроченная/чужая/повторная `y:<id>` не подтверждает действие.

Успешная `y:<id>` один раз закрывает локальное намерение и возвращает `operation_id` и `state.spec.resource_version`. **Она не выполняет удаление, оплату или другую бизнес-операцию.** Host в своей транзакции снова проверяет актуальные object ACL, версию ресурса, допустимые значения и idempotency key, записывает результат и сверяет unknown outcome. `on_result` вызывается после commit локального выбора, до edit UI. Ошибка или отмена hook не отменяет уже принятое намерение и не запускает его заново. Нужные durable receipts сохраняет приложение; RAM-черновик не заменяет это хранилище.

## Изменение серверных правил

Для динамических вариантов передавайте async `load_spec(query, menu)` в Router. Hook выполняется только после проверки owner/context/current callback; затем `apply()` проверяет версию еще раз. Hook возвращает текущие правила из сервиса проекта и может отказать при потере доступа. Не загружайте публичный клиентский список как server spec.

Для одного `SelectionMenu` Router наследует его prefix; при resolver по умолчанию используется `sel:`, другой prefix передается явно. Несовпадение prefix статического меню отклоняется при подключении.

`replace_spec()` с измененными правилами увеличивает revision и отзывает confirmation. Она сохраняет только доступные выбранные ключи в пределах нового лимита, убирает удаленные toggle, ограничивает количество новыми границами и возвращает редактирование. Пользователь должен увидеть обновленный summary и подтвердить заново. Та же spec сохраняет revision. Закрытый черновик сохраняет исходное намерение; для нового действия host создает новое меню. Обновление spec не продлевает истекший TTL.

## Отображение и жизненный цикл

`SelectionMenu` не делает I/O. После timeout/cancel/rejected edit серверный выбор уже сохранен, старые кнопки stale. Router не откатывает черновик и не повторяет network/business call. Host может по явной команде владельца перерисовать текущий snapshot в известном сообщении; не отправлять новое сообщение автоматически после неизвестного initial send. Неподходящий SDK response вызывает `UnknownOutcome`; Bot/session, Dispatcher, handlers и registry принадлежат host.

Компонент обслуживает обычные private/group/supergroup сообщения с известным положительным message ID и корректным `KeyboardCapabilities.chat_type`; forum thread входит в context. Inline/inaccessible/Business/channel требуют своих сценариев. Меню — память одного процесса, без durable/multiworker/exactly-once обещаний. TTL меню по умолчанию 1800 секунд использует process monotonic clock; expired меню требует нового явного host-открытия. Host ограничивает registry и освобождает его самостоятельно.

Лимиты компонента: 1..60 уникальных options, до 8 toggles и 8 filters (обязательный `all`), labels до 40 UTF-16 units, confirm label до 48, quantity 0..1000000, prefix 1..8 ASCII плюс `:`, keys 1..24 ASCII. Callback до 64 UTF-8 bytes. Snapshot копирует input collections и не сохраняет mutable ссылки.

`selection_bot.py` показывает private `/choose` без тем, registry до 100 меню и повторное открытие того же message ID. `offline_selection.py` исполняет тот же Router через real SDK/Dispatcher и StubSession: все четыре поля, owner/stale guards, fresh spec, back и одно confirmation intent. Бизнес-эффектов в примере нет. Unit tests дополнительно проверяют expiry, malformed/forged commands, конкуренцию, неизвестный edit и cancellation. Это авторская offline-проверка, не live Telegram или независимый human/AI usability study.

Частично сверены 5 октября 2026: [CallbackQuery](https://core.telegram.org/bots/api#callbackquery), [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [Router aiogram 3.31.0](https://docs.aiogram.dev/en/latest/dispatcher/router.html). Используйте проверенный установленный SDK и текущие условия контекста; дата всего source catalog этим не обновляется.
