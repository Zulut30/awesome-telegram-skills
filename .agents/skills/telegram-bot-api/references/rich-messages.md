# Rich-сообщения

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции.

Rich-сообщение (Bot API 10.1+) — структурированный текст с заголовками, списками, таблицами, цитатами, раскрывающимися блоками, медиа и кнопками внутри сообщения. Отправляется методом [sendRichMessage](https://core.telegram.org/bots/api#sendrichmessage) с полем `rich_message` типа [InputRichMessage](https://core.telegram.org/bots/api#inputrichmessage); черновик для потокового ответа — [sendRichMessageDraft](https://core.telegram.org/bots/api#sendrichmessagedraft). В `InputRichMessage` задается ровно одно из полей: `blocks`, `html` или `markdown`.

## Лимиты Telegram

По [разделу о форматировании](https://core.telegram.org/bots/api#rich-message-formatting-options):

- до 32768 символов текста, включая альтернативный текст custom emoji и исходный текст формул;
- до 500 блоков с учетом вложенных, пунктов списков, строк таблиц, цитат и блоков `details`;
- до 16 уровней вложенности форматирования и блоков;
- до 50 медиавложений;
- до 20 столбцов в таблице;
- в ряду кнопок от 1 до 8 кнопок ([InputRichBlockButtons](https://core.telegram.org/bots/api#inputrichblockbuttons)).

## Блоки без библиотеки

Модели aiogram 3.31.0 (`InputRichMessage`, `InputRichBlockTable`, `RichMessageButton` и другие) проверяют JSON до отправки:

```python
from aiogram.methods import SendRichMessage

request = SendRichMessage.model_validate({'chat_id': chat_id, 'rich_message': {'blocks': [
    {'type': 'heading', 'text': 'Заказ №42', 'size': 1},
    {'type': 'table', 'is_compact': True, 'cells': [
        [{'text': 'Товар', 'is_header': True, 'align': 'left', 'valign': 'top'}],
        [{'text': 'Книга', 'align': 'left', 'valign': 'top'}]]},
    {'type': 'expandable_blockquote', 'text': 'Длинный комментарий'},
    {'type': 'buttons', 'buttons': [{'text': 'Подтвердить', 'callback_data': 'order:confirm:42', 'style': 'success'}]},
]}})
await bot(request)
```

У ячейки таблицы поля `align` и `valign` обязательны. Стиль кнопки `link` (кнопка-ссылка без рамки) разрешен только для callback-кнопок. Для документа в блоке `document` подпись в `InputMediaDocument` игнорируется — подпись блока задает поле `caption`.

## С библиотекой awesome-telegram-patterns

Если библиотека уже есть в проекте, `RichMessageBuilder` из ядра (без SDK) собирает частые блоки и проверяет лимиты при `build()`:

```python
from telegram_patterns import RichButton, RichMessageBuilder, RichSpan

delivery = RichMessageBuilder().paragraph('Курьер привезет заказ за два дня.')
card = (RichMessageBuilder()
        .heading('Заказ №42', size=1)
        .paragraph(['Статус: ', RichSpan('bold', 'оплачен')])
        .table([['Товар', 'Цена'], ['Книга', '500 ₽']], compact=True, caption='Итого: 500 ₽')
        .checklist([('Оплата получена', True), ('Передан в доставку', False)])
        .quote('Оставьте у двери', credit='Покупатель', expandable=True)
        .details('Как проходит доставка', delivery)
        .document(receipt_file_id, caption='Чек')
        .buttons([RichButton('Подтвердить', callback_data='order:confirm:42', style='success')])
        .build())
await bot(SendRichMessage.model_validate({'chat_id': chat_id, 'rich_message': card.as_input()}))
```

- Блоки: `heading`, `paragraph`, `bullets`, `numbered`, `checklist`, `table` (`compact`, `bordered`, `striped`, `caption`), `buttons`, `quote` (обычная или сворачиваемая `expandable=True`), `details`, `document`, `code`, `divider`, `footer`.
- Встроенное форматирование `RichSpan`: `bold`, `italic`, `code` и `url` (только HTTP(S)).
- `card.block_count` и `card.media_count` считают так же, как Telegram; превышение лимита — `ValueError` при `build()`.
- Остальные блоки (фото, видео, карты, коллажи, формулы) и формы `html`/`markdown` задавайте напрямую моделями SDK.

## Запасной вариант

Где rich-сообщение недоступно — например, Business-аккаунт, пользователь которого не может отправлять rich-сообщения, — то же содержимое уходит обычным сообщением. `card.fallback()` возвращает `FormattedText`: заголовки жирным, таблица строками `ячейка | ячейка`, чек-лист значками ☑/☐, цитаты и `details` сущностями `blockquote` и `expandable_blockquote`. Делите его `.split()` и отправляйте `sendMessage` с `parse_mode=None`; `card.fallback_keyboard()` дает ряды inline-клавиатуры для последней части (стиль `link` в обычной клавиатуре не существует и отбрасывается). Где отправлять rich-сообщение, решает проект.

## Проверка

`telegram-patterns run-recipe demo-rich-message --offline` выполняет пример на настоящем `Dispatcher` без сети: JSON на проводе совпадает с `card.as_input()` (кроме `parse_mode` по умолчанию проекта, который aiogram добавляет в объект документа и Telegram игнорирует), запасной текст и клавиатура, ACK нажатия и лимиты. Отображение блоков в клиентах Telegram офлайн-проверка не подтверждает: проверьте его на тестовом боте.

Источники: [sendRichMessage](https://core.telegram.org/bots/api#sendrichmessage), [InputRichMessage](https://core.telegram.org/bots/api#inputrichmessage), [InputRichBlock](https://core.telegram.org/bots/api#inputrichblock), [RichMessageButton](https://core.telegram.org/bots/api#richmessagebutton), [Rich Message Formatting Options](https://core.telegram.org/bots/api#rich-message-formatting-options). Проверено 7 октября 2026 года по Bot API 10.3 и aiogram 3.31.0.
