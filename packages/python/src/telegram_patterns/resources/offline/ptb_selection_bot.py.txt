"""python-telegram-bot: server-owned selection with the SDK-free SelectionMenu; no polling on import."""
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionSpec, selection_markup
from telegram_patterns.ptb import ptb_inline_markup


def demo_spec() -> SelectionSpec:
    return SelectionSpec([SelectionOption('alpha', 'Пакет Alpha', ['basic']), SelectionOption('beta', 'Пакет Beta', ['extra']),
                          SelectionOption('gamma', 'Пакет Gamma', ['extra'])],
                         toggles={'notify': 'Уведомлять'}, filters={'all': 'Все', 'basic': 'Основные', 'extra': 'Дополнительные'},
                         quantity_min=1, quantity_max=5, min_selected=1, max_selected=2, confirm_text='Подтвердить выбор')


def attach_selection(application: Application, menus: dict[int, SelectionMenu]) -> None:  # type: ignore[type-arg]
    """menus is the host registry: one menu per private chat; the host owns its lifetime."""

    async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None or message.chat.type != 'private':
            return
        sent = await message.reply_text('Открываю выбор…')  # an explicit command sends once, no retry
        menu = SelectionMenu(demo_spec(), SelectionContext(context.bot.id, user.id, message.chat.id, sent.message_id))
        menus[message.chat.id] = menu
        await context.bot.edit_message_text(menu.state.text(), chat_id=message.chat.id, message_id=sent.message_id,
                                            reply_markup=ptb_inline_markup(selection_markup(menu.state)))

    async def pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()  # ACK first: it is not approval
        menu = menus.get(query.message.chat.id)
        if menu is None:
            return
        # Identity comes from the update, never from callback data; apply re-checks owner, message and revision.
        result = menu.apply(query.data or '', SelectionContext(context.bot.id, query.from_user.id, query.message.chat.id, query.message.message_id))
        if result.status in ('denied', 'stale', 'invalid'):
            await query.answer(result.text, show_alert=result.status == 'denied')
            return
        state = menu.state
        markup = selection_markup(state)
        # A closed menu has no buttons: editing without reply_markup removes the keyboard.
        await query.edit_message_text(state.text(), reply_markup=ptb_inline_markup(markup) if markup['inline_keyboard'] else None)

    application.add_handler(CommandHandler('choose', choose))
    application.add_handler(CallbackQueryHandler(pressed, pattern='^sel:'))
