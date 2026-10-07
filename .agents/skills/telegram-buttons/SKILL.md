---
name: telegram-buttons
description: "Реализует Telegram-кнопки: цветные styles, custom emoji icons, inline/reply keyboards и ограничения действий. Используйте для оформления кнопок и их поддержки в Python SDK. Не для другого метода Bot API → telegram-bot-api; не для запросов @bot query → telegram-inline-mode."
license: MIT
metadata:
  version: "0.24.0"
---

# Кнопки Telegram

## Когда использовать

Нужно добавить, оформить или исправить кнопку бота: inline-кнопку под сообщением, reply-клавиатуру, цвет кнопки, иконку custom emoji, неактивную кнопку или кнопку-запрос (контакт, геопозиция, пользователь, чат).

## Когда не использовать

Кнопки внутри Mini App — это компоненты frontend, их делают в коде интерфейса. Другие методы Bot API — telegram-bot-api, ответы на `@bot query` — telegram-inline-mode, многошаговые формы на кнопках — telegram-dialogs.

## Алгоритм

1. **Вид и действие.** У inline-кнопки ровно одно действие: `callback_data`, `url`, `web_app`, `login_url`, `switch_inline_query*`, `copy_text`, `callback_game`, `pay` или `disabled`; поля `text`, `style` и `icon_custom_emoji_id` действием не считаются. Reply-кнопка отправляет свой текст или запрос (`request_contact`, `request_location`, `request_users`, `request_chat`, `request_poll`, `request_managed_bot`); запросы работают только в личном чате, а reply-клавиатура — не в каналах и не в Business.
2. **Версия SDK.** Сайт Bot API не доказывает поддержку в проекте. Проверьте установленную версию (`python -c "import aiogram; print(aiogram.__version__)"`) и поле в модели (`"style" in InlineKeyboardButton.model_fields`). В aiogram 3.31.0 есть `style`, `icon_custom_emoji_id` и `disabled`.
3. **Итоговый JSON.** Соберите кнопку и посмотрите, что уйдет в Telegram: `button.model_dump(exclude_none=True, mode="json")`. Если поля нет, выберите минимальное обновление SDK или отправьте `reply_markup` готовым JSON через HTTP-клиент, который уже есть в проекте. Не подменяйте поле похожим.
4. **Цвет.** Его задает только `style`: `danger` — красный, `success` — зеленый, `primary` — синий; без поля оформление выбирает клиент. Произвольного цвета нет, значение `link` из перечисления aiogram допустимо только у callback-кнопок rich-сообщений. Текст понятен без цвета: «Удалить заказ», а не «Да».
5. **Иконка.** `icon_custom_emoji_id` — ID custom emoji перед текстом кнопки. Это не entity `custom_emoji` в тексте сообщения. Право на иконку — entitlement (право на возможность, которое проверяется отдельно от запроса): у бота есть дополнительный username, купленный на Fragment, или сообщение отправлено самим ботом в личный чат, группу или супергруппу, а у владельца бота Telegram Premium. Premium того, кто нажимает, не важен. Без права отправьте ту же кнопку без иконки — это fallback (запасной вариант, если основная возможность недоступна).
6. **Неактивная кнопка.** `disabled=DisabledButton()` — кнопка ничего не делает и не присылает callback; это и есть ее единственное действие. Неактивность не изображают серым текстом или кнопкой с пустым обработчиком.
7. **Обработчик нажатия.** `callback_data` (1–64 байта UTF-8, кириллица — 2 байта на букву) может подделать любой клиент. Сервер проверяет, кто нажал, существует ли объект и доступен ли он этому пользователю, допускает ли текущее состояние действие; повторное нажатие не повторяет эффект. На каждое нажатие отвечайте `answerCallbackQuery` — это ACK (ответ на нажатие кнопки: клиент убирает индикатор ожидания; это не сообщение об успехе операции).

Подробности о `style`, иконках, раскладке и reply-клавиатурах — в [references/buttons.md](references/buttons.md).

## Пример

```python
from aiogram import F, Router
from aiogram.types import CallbackQuery, DisabledButton, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()


def order_keyboard(order_id: int, icon_id: str | None) -> InlineKeyboardMarkup:
    icon = {"icon_custom_emoji_id": icon_id} if icon_id else {}  # только после проверки права на custom emoji
    delete = InlineKeyboardButton(text="Удалить заказ", style="danger", callback_data=f"order:delete:{order_id}", **icon)
    cancel = InlineKeyboardButton(text="Отмена", callback_data=f"order:cancel:{order_id}")  # обычный вид
    return InlineKeyboardMarkup(inline_keyboard=[[delete, cancel]])


PAID = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Оплачено ✓", disabled=DisabledButton())]])


@router.callback_query(F.data.startswith("order:delete:"))
async def delete_order(callback: CallbackQuery, orders) -> None:  # orders — хранилище проекта из workflow_data
    order = await orders.get(int(callback.data.rsplit(":", 1)[1]))
    if order is None or order.owner_id != callback.from_user.id:
        await callback.answer("Заказ недоступен", show_alert=True)
        return
    deleted = await orders.delete_once(order.id, expected_version=order.version)  # повтор не удаляет второй раз
    await callback.answer("Заказ удален" if deleted else "Заказ уже удален")
```

Тот же `reply_markup` без SDK: `{"inline_keyboard": [[{"text": "Удалить заказ", "style": "danger", "callback_data": "order:delete:42"}]]}`.

## Типичные ошибки

- Два действия на одной inline-кнопке (`callback_data` и `url`) — Telegram отклонит сообщение.
- Цвет изображают emoji 🔴 в тексте, а неактивность — серым словом «недоступно» вместо `style` и `DisabledButton`.
- Ждут `callback_query` от кнопок `url`, `copy_text`, `switch_inline_query*` и `disabled` — они его не присылают.
- Нет `answerCallbackQuery`: у пользователя крутится индикатор ожидания, а повторные нажатия выглядят как сбой.
- `callback_data` считают доказательством прав или превышают 64 байта длинным русским текстом.
- Право на иконку связывают с Premium нажавшего пользователя или ставят иконку без запасного варианта.
- `pay` или `callback_game` не первой кнопкой первого ряда; `pay` вне сообщения со счетом.

## Проверка

- Итоговый JSON содержит ожидаемые поля и ровно одно действие у каждой inline-кнопки.
- Тест обработчика с подставным транспортом: чужой пользователь получает отказ, повторное нажатие не повторяет эффект, `answerCallbackQuery` вызван в каждой ветке.
- Отображение в целевых клиентах (Android, iOS, Desktop, Web): старый клиент может показать кнопку без цвета. Запишите проверенные версии клиентов и источник права на custom emoji.

## Источники

[InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [DisabledButton](https://core.telegram.org/bots/api#disabledbutton), [answerCallbackQuery](https://core.telegram.org/bots/api#answercallbackquery), [getCustomEmojiStickers](https://core.telegram.org/bots/api#getcustomemojistickers).

Проверено: 2026-10-07, Bot API 10.3, aiogram 3.31.0.
