"""Attach the menu Router to an existing Dispatcher; polling starts only explicitly."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from telegram_patterns.aiogram import (
    ActionButton, KeyboardLayout, MessageNavigation, NavigationResult,
    NavigationScreen, navigation_router,
)


def build_menu() -> tuple[MessageNavigation, Router]:
    menu = MessageNavigation([
        NavigationScreen('home', 'Выберите раздел', [
            ActionButton('Каталог', 'catalog'), ActionButton('Помощь', 'help'),
        ], KeyboardLayout((2,))),
        NavigationScreen('catalog', 'Каталог услуг', [
            ActionButton('Доставка', 'delivery'), ActionButton('Самовывоз', 'pickup'),
            ActionButton('Условия', 'terms'),
        ], KeyboardLayout((3,))),
        NavigationScreen('delivery', 'Доставка: правила и сроки'),
        NavigationScreen('pickup', 'Самовывоз: адрес и время'),
        NavigationScreen('terms', 'Условия обслуживания'),
        NavigationScreen('help', 'Помощь: /menu восстанавливает экран'),
    ])
    router = Router()

    @router.message(F.chat.type == 'private', Command('start', 'menu'))
    async def open_menu(message: Message) -> None:
        if message.from_user is not None and not message.from_user.is_bot:
            bot = message.bot
            if bot is None:
                raise ValueError('Bind the native message to a Bot before handling')
            await menu.open(bot, message.from_user.id, message.chat.id)

    async def notify(query: CallbackQuery, result: NavigationResult) -> None:
        if result.status != 'accepted':
            # ACK was already sent before the lock/edit. Additional feedback is
            # best effort in live Telegram; host may use its existing UI channel.
            await query.answer(result.text, show_alert=True)
    router.include_router(navigation_router(menu, on_result=notify))
    return menu, router


if __name__ == '__main__':
    import asyncio
    from aiogram import Dispatcher
    from telegram_patterns.aiogram import BotSettings, run_bot

    async def main() -> None:
        _, router = build_menu()
        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        try:
            await run_bot(dispatcher, BotSettings.from_env())
        finally:
            await dispatcher.fsm.close()
    asyncio.run(main())
