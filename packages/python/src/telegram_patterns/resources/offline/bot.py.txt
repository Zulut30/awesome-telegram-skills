"""Public catalog demo. Set BOT_TOKEN for a test bot to run real polling."""
from __future__ import annotations

import asyncio
from aiogram import Dispatcher, F, Router
from aiogram.types import BotCommand, CallbackQuery, Message

from telegram_patterns import BotSettings
from telegram_patterns.aiogram import (Action, ActionButton, ActionResult, CommandReply, MenuPage,
                                      callback_router, command_menu, command_router,
                                      page_number, paginated_menu, run_bot)


ITEMS = tuple(ActionButton(f"Компонент {index}", f"item-{index}", style="primary")
              for index in range(1, 8))


def catalog(page: int = 0) -> MenuPage:
    return paginated_menu(ITEMS, page=page, page_size=3, page_prefix="catalog-page:")


def page_heading(page: MenuPage) -> str:
    return f"Пример каталога · страница {page.page + 1}/{page.page_count}\nВыберите компонент."


def create_app() -> tuple[Dispatcher, list[BotCommand]]:
    """Same composition for real polling and the no-network example."""
    first = catalog()
    commands = [
        CommandReply("start", "Открыть каталог", page_heading(first), first.markup),
        CommandReply("help", "Помощь", "Кнопки и страницы собираются общей библиотекой. Это публичный каталог без покупок."),
    ]
    dispatcher = Dispatcher()
    dispatcher.include_router(command_router(commands))
    pages = Router()

    @pages.callback_query(F.data.startswith("catalog-page:"))
    async def change_page(query: CallbackQuery) -> None:
        target = page_number(query.data, prefix="catalog-page:")
        if target is None or not isinstance(query.message, Message):
            await query.answer("Откройте актуальное меню командой /start.")
            return
        await query.answer()
        page = catalog(target)
        await query.message.edit_text(page_heading(page), parse_mode=None, reply_markup=page.markup)

    async def execute(action: Action) -> ActionResult:
        # All items are public fixtures. Private objects require service-side ACL,
        # revision checks and idempotence before any business effect.
        selected = next((item for item in ITEMS if item.key == action.key), None)
        if selected is None:
            return ActionResult("stale", "Откройте новый каталог командой /start.")
        return ActionResult("accepted", f"Вы выбрали: {selected.text}. Добавьте прикладную логику своего бота.")

    async def notify(query: CallbackQuery, result: ActionResult) -> None:
        # Public feedback stays in the originating chat; no implicit private DM.
        if isinstance(query.message, Message):
            await query.message.answer(result.text, parse_mode=None)

    dispatcher.include_router(pages)
    dispatcher.include_router(callback_router(execute, notify))
    return dispatcher, command_menu(commands)


async def main() -> None:
    try:
        settings = BotSettings.from_env()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    dispatcher, commands = create_app()
    # Explicit opt-in: this demo replaces the default command menu of the TEST bot.
    await run_bot(dispatcher, settings, commands=commands)


if __name__ == "__main__":
    asyncio.run(main())
