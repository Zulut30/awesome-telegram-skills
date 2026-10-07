# Рецепты Python-бота

Доступно с 0.3.0, проверено на 0.24.0.

Требуется локальная поставка awesome-telegram-patterns с extra aiogram. Не устанавливайте пакет по одному имени из реестра: публикация не подтверждена. Публичные API ниже проверены с aiogram 3.31.0.

## Две статические команды

```python
import asyncio
from aiogram import Dispatcher
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import CommandReply, command_menu, command_router, run_bot

commands = [CommandReply("start", "Начать", "Привет!"),
            CommandReply("help", "Помощь", "Поддерживаются /start и /help.")]
dispatcher = Dispatcher()
dispatcher.include_router(command_router(commands))
asyncio.run(run_bot(dispatcher, BotSettings.from_env(), commands=command_menu(commands)))
```

Для текущего бота используйте его Dispatcher и lifecycle. Router не требует замены middleware/storage. CommandReply — статический plain text; динамические ответы и FSM пишите обычными SDK handlers. Command filter отклоняет mention другого бота. Reply keyboard сохраняется snapshot при сборке Router.

Команды для Telegram menu создаются отдельно: command_menu возвращает DTO. Run_bot с commands=None сохраняет существующее меню; переданный список заменяет DEFAULT scope, [] очищает его. Для scope/language используйте bot.set_my_commands явно. Не называйте такую установку чисто локальным действием.

## Меню и страницы

```python
from telegram_patterns.aiogram import ActionButton, action_menu, page_number, paginated_menu

buttons = [ActionButton("Тарифы", "plans", style="primary"), ActionButton("Помощь", "help")]
keyboard = action_menu(buttons, columns=2, prefix="catalog:")
page = paginated_menu(buttons, page=0, page_size=6,
                      action_prefix="catalog:", page_prefix="catalog-page:")
target = page_number(callback_data, prefix="catalog-page:")  # int либо None
```

Builders не регистрируют обработчики. Подключите callback_router(execute,notify,prefix='catalog:') или текущий handler; actor/key передайте авторизованному сервису. Page callback ACK обрабатывается перед обновлением представления. Неверный target отклоняйте. Callback data не является правом на объект, paginated_menu не предоставляет tenant filtering.

Rows допускают 1..8 колонок, до 100 action buttons; keys уникальны. Это ограничения компонента, не обещание любого общего Telegram limit. Пагинация local sequence использует page_size 1..98, разные prefixes, 0-based page и clamp после уменьшения списка. Пустая view: page=0/page_count=1/total_items=0, markup без кнопок. Для крупной БД выбирайте product cursor/query. Emoji entitlement передавайте только после серверной проверки целевого bot/chat context.

## Запуск и зависимости

Run_bot принимает текущий Dispatcher и BotSettings, создает один Bot и владеет его session после preflight. Она закрывается при обычном завершении, setup/polling error и cancellation; переданную session не используйте одновременно в другом Bot. При отмене используется SDK stop_polling, ожидание ограничивает shutdown_timeout=10 секунд, включая зависший startup-hook. Отказ preflight оставляет session caller. Dispatcher используется эксклюзивно одним polling entrypoint. Для custom webhook/multibot entrypoint используйте SDK.

`workflow_data={'service': service}` позволяет SDK инъекцию. Reserved polling keys запрещены; polling_timeout/handle_signals/handle_as_tasks/tasks_concurrency_limit передаются явно. Defaults соответствуют SDK. Лимит concurrency/последовательность не заменяет durable acceptance и idempotence. Run_bot не вызывает deleteWebhook и не сбрасывает updates. Application DB/clients и завершение прикладных handler tasks организуются lifecycle проекта; общего task-drain runner не предоставляет.

BotSettings.from_env читает BOT_TOKEN либо явно указанную переменную, не загружает .env автоматически. Repr и ошибки формата исключают token; settings.token/asdict содержат секрет. Не логируйте их.

## Проверка без сети

```python
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery
from telegram_patterns.testing import StubSession

async def check():
    session = StubSession().respond(AnswerCallbackQuery, True)
    async with Bot("100:TEST_FIXTURE", session=session) as bot:
        await bot.answer_callback_query("fixture-query")
    assert session.closed and isinstance(session.calls[0], AnswerCallbackQuery)
```

Ответ — SDK модель/словарь, константа или sync/async function от TelegramMethod; возвращаемый тип проверяет SDK/Pydantic. Проверяйте исходящие chat/text/markup и бизнес-эффект, не только число calls. Незарегистрированный API method и file streaming проваливают пробу, HTTP fallback отсутствует. Synthetic updates/fake transport не подтверждают настоящую доставку/Telegram permissions.

Источники, частично сверенные 3 октября 2026: [BotCommand](https://core.telegram.org/bots/api#botcommand), [aiogram Command](https://docs.aiogram.dev/en/latest/dispatcher/filters/command.html), [polling](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html), [BaseSession](https://docs.aiogram.dev/en/latest/api/session/base.html), [keyboard builder](https://docs.aiogram.dev/en/latest/_modules/aiogram/utils/keyboard.html). Сравните с фактически установленной версией.
