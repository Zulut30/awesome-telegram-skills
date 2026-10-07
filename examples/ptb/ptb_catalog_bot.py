"""python-telegram-bot: paged catalog from the SDK-free markup core; no polling on import."""
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from telegram_patterns import MarkupPage, markup_page_number, paginated_markup
from telegram_patterns.ptb import ptb_inline_markup, ptb_markup

ITEMS = [(f'Компонент {index}', f'item-{index}') for index in range(1, 8)]
PAGE, ACTION = 'catalog-page:', 'act:'


def catalog(page: int = 0) -> MarkupPage:
    # The same buttons and callback data as the aiogram demo-catalog.
    return paginated_markup(ITEMS, page=page, page_size=3, page_prefix=PAGE, action_prefix=ACTION, style='primary')


def heading(page: MarkupPage) -> str:
    return f'Пример каталога · страница {page.page + 1}/{page.page_count}\nВыберите компонент.'


def attach_catalog(application: Application) -> None:  # type: ignore[type-arg]
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is not None:
            first = catalog()
            await update.effective_message.reply_text(heading(first), reply_markup=ptb_markup(first.markup))

    async def change_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        target = markup_page_number(query.data, prefix=PAGE)
        if target is None or query.message is None:
            await query.answer('Откройте актуальное меню командой /start.')
            return
        await query.answer()
        page = catalog(target)
        await query.edit_message_text(heading(page), reply_markup=ptb_inline_markup(page.markup))

    async def choose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        # Public fixtures only; a private object needs service ACL and idempotence before any effect.
        selected = next((text for text, key in ITEMS if ACTION + key == query.data), None)
        await query.answer()
        if query.message is not None and update.effective_chat is not None:
            text = f'Вы выбрали: {selected}.' if selected else 'Откройте новый каталог командой /start.'
            await context.bot.send_message(update.effective_chat.id, text)

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(change_page, pattern='^' + PAGE))
    application.add_handler(CallbackQueryHandler(choose, pattern='^' + ACTION))
