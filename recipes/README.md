# Рецепты Telegram

Код для конкретной задачи выбирается по каталогу; aiogram выполняет транспорт и предоставляет native типы. Это cookbook общей библиотеки, версия 0.4.0. Python требует extra `[aiogram]`, TypeScript — локальный пакет `@awesome-telegram/patterns`. Установка и публичные контракты: [Python](../packages/python/README.md), [TypeScript](../packages/typescript/README.md).

| Задача | Готовый материал |
| --- | --- |
| Две/три кнопки, разные строки, цвета и emoji | [Клавиатуры](bot-api/keyboards.md), функции `two_in_row`, `three_in_row`, `colored_buttons`, `mixed_rows` в [боте-примере](../examples/python/keyboards_bot.py) |
| Контакт, геопозиция, poll, выбор users/chat, ввод | [Клавиатуры и ввод](bot-api/keyboards.md), команды `/requests`, `/input`, `/hide` того же бота |
| Нажатия, редактирование меню, события | [События](bot-api/events.md), owner-bound callback и UpdateObserver в боте |
| Произвольный метод Bot API | [185 Python примеров](bot-api/README.md), [поиск SDK](../examples/python/api_catalog.py) |
| Native функции Mini App | [99 методов / 44 события](mini-app/README.md), [примеры TypeScript](../examples/mini-app/src/native-recipes.ts) |
| Форма с подтверждением и повтором заявки | [Рабочая форма](../examples/python/form_bot.py), [сценарий без сети](../examples/python/offline_form.py) |
| Адаптивный интерфейс на телефоне/планшете/ПК | [Mini App](../examples/mini-app/src/index.ts), shared shell/fields/styles |

Без токена и сети, из корня:

```powershell
uv run --with-editable "./packages/python[aiogram]" python examples/python/offline_keyboards.py
uv run --with-editable "./packages/python[aiogram]" python examples/python/api_catalog.py reaction
```

Чтобы открыть примеры в Telegram, передайте BOT_TOKEN **тестового** бота через окружение и выполните `uv run --with-editable "./packages/python[aiogram]" python examples/python/keyboards_bot.py`. Пример устанавливает default command menu. Перед запуском проверьте отсутствие другого polling consumer и webhook; пример не удаляет webhook автоматически.

[Машиночитаемая карта](../catalog/telegram-capabilities.json) содержит методы, параметры, типы, ссылки и границы проверки. Все 185 request-рецептов проходят SDK construction и локальную сериализацию, а не отправку в Telegram. Демонстрация клавиатур проверяется отдельно через Dispatcher. Native Mini App facade проверяется с mock: физические Telegram-клиенты требуют отдельной проверки. Полные бизнес-сценарии для каждого метода, MTProto пользовательского аккаунта и внешние платежные адаптеры не объявляются готовыми этим каталогом.

Обновление официального индекса и генерация по сохраненному HTML описаны в [обзоре 0.4.0](../docs/internal/telegram-cookbook-review.md). Новое API нельзя молча объявлять проверенным: generator останавливается при расхождении с SDK, catalog check — при изменении результатов.
