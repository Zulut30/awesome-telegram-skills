"""Selection UI composition; demo intent only, no destructive business effect."""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from telegram_patterns import BotSettings, SelectionContext, SelectionMenu, SelectionOption, SelectionResult, SelectionSpec, UnknownOutcome
from telegram_patterns.aiogram import run_bot, selection_keyboard, selection_router


def demo_spec() -> SelectionSpec:
    return SelectionSpec([
        SelectionOption('alpha', 'Пакет Alpha', ['basic']),
        SelectionOption('beta', 'Пакет Beta', ['extra']),
        SelectionOption('gamma', 'Пакет Gamma', ['extra']),
    ], toggles={'notify': 'Уведомлять'}, filters={'all': 'Все', 'basic': 'Основные', 'extra': 'Дополнительные'},
        quantity_min=1, quantity_max=5, min_selected=1, max_selected=2, confirm_text='Подтвердить выбор')


def build_selection_router(*, current_spec: Callable[[], SelectionSpec] = demo_spec,
                           on_result: Callable[[CallbackQuery, SelectionResult], Awaitable[None]] | None = None
                           ) -> tuple[Router, dict[int, SelectionMenu]]:
    """Attach to existing Dispatcher; bounded demo registry, host owns its lifetime."""
    router = Router()
    menus: dict[int, SelectionMenu] = {}

    async def load(query: CallbackQuery, menu: SelectionMenu) -> SelectionSpec:
        return current_spec()  # Production host supplies its current DB rules/ACL.

    def resolve(query: CallbackQuery) -> SelectionMenu | None:
        # Actual identity/context/token checks remain inside the component.
        message = query.message
        return menus.get(message.chat.id) if isinstance(message, Message) else None

    @router.message(Command('choose'))
    async def choose(message: Message) -> None:
        if message.chat.type != 'private' or message.message_thread_id is not None or message.from_user is None or message.bot is None:
            return
        bot = message.bot
        owner = message.from_user.id
        menu = menus.get(message.chat.id)
        if menu is not None and (menu.state.context.owner_id != owner or menu.state.context.bot_id != bot.id):
            return
        rules = current_spec()
        if menu is None:
            if len(menus) >= 100:
                await message.answer('Демонстрационный лимит меню достигнут.', parse_mode=None)
                return
            # Explicit command sends once. A send exception propagates without retry.
            sent = await message.answer('Открываю выбор…', parse_mode=None)
            if (sent.chat.id != message.chat.id or sent.message_id <= 0 or sent.date.timestamp() <= 0 or
                    sent.from_user is None or sent.from_user.id != bot.id or not sent.from_user.is_bot):
                raise UnknownOutcome('Initial selection message response was not confirmed')
            menu = SelectionMenu(rules, SelectionContext(bot.id, owner, message.chat.id, sent.message_id))
        elif menu.state.phase in {'confirmed', 'cancelled'} or menu.check(menu.state.callback('refresh'), menu.state.context) is not None:
            # New explicit intent in the same known message; production retains durable operation records separately.
            menu = SelectionMenu(rules, menu.state.context)
        else:
            menu.replace_spec(rules)
        menus[message.chat.id] = menu
        state = menu.state
        await bot.edit_message_text(state.text(), chat_id=state.context.chat_id, message_id=state.context.message_id,
                                    parse_mode=None, reply_markup=selection_keyboard(state))

    router.include_router(selection_router(resolve, load_spec=load, on_result=on_result))
    return router, menus


async def main() -> None:
    dispatcher = Dispatcher()
    router, _ = build_selection_router()
    dispatcher.include_router(router)
    await run_bot(dispatcher, BotSettings.from_env())


if __name__ == '__main__':
    asyncio.run(main())
