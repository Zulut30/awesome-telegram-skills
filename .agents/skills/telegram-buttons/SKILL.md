---
name: telegram-buttons
description: "Реализует Telegram-кнопки: цветные styles, custom emoji icons, inline/reply keyboards и ограничения действий. Используйте для оформления кнопок и их поддержки в Python SDK. Не для другого метода Bot API → telegram-bot-api; не для запросов @bot query → telegram-inline-mode."
license: MIT
metadata:
  version: "0.24.0"
---

# Кнопки Telegram

Определите вид кнопки, действие и тип чата. Прочитайте [references/buttons.md](references/buttons.md) для цветов и premium/custom emoji; проверьте версию API и библиотеку проекта. Кнопки Mini App являются frontend-компонентами и требуют другой реализации.

Используйте актуальные типы установленной библиотеки. Проверьте итоговый serialized payload: новая настройка может отсутствовать в старом SDK или быть проигнорирована моделью. При несовместимости выберите минимальное обновление либо документированный низкоуровневый вызов существующим транспортом.

Цвет и иконка не заменяют понятный текст действия. Для удаления и подтверждения сохраняйте смысл при стандартном оформлении клиента. Иконки должны иметь fallback; не обещайте произвольный цвет Bot API-кнопки.

У inline-кнопки выберите ровно одно поддерживаемое действие; у reply-кнопки проверьте ограничения request-полей. Callback должен проверять пользователя, состояние процесса и доступ к объекту, отвечать на нажатие и управлять повторной отправкой. Если требуется disabled-состояние, сначала проверьте актуальный API и client support, а не имитируйте его только цветом.

Проверьте payload, реальное отображение в целевых клиентах, действие кнопки и неподходящий chat context. Отдельно зафиксируйте entitlement на custom emoji и фактически проверенные версии клиента.

## Источники

[InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [getCustomEmojiStickers](https://core.telegram.org/bots/api#getcustomemojistickers).

Проверено: 2026-10-07, Bot API 10.3, aiogram 3.31.0.
