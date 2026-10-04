# Ветка pyTelegramBotAPI

Источник: [upstream pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI).

Различай `TeleBot` и `AsyncTeleBot`. Sync handler, async handler и threading требуют разного управления клиентами и зависимостями; не добавляй `await` к синхронному методу по аналогии с aiogram.

Сохраняй порядок handlers и фильтров. Общий обработчик может перехватить событие до специализированного. Для нового поля кнопки проверь types/serialization установленного пакета; наличие поля в raw API не означает, что старый TeleBot его отправит.

Состояние диалога и step handlers оцени по выбранному storage и требованиям рестарта. Polling/webhook lifecycle, отключение и error handling должны соответствовать версии и типу клиента.
