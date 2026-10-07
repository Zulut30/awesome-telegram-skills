"""python-telegram-bot: a literal report with entities from the SDK-free MessageBuilder; no polling on import."""
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from telegram_patterns import FormattedText, MessageBuilder
from telegram_patterns.ptb import ptb_text


def compose_report(name: str, notes: str) -> tuple[FormattedText, ...]:
    # Both values stay literal even when they contain Telegram markup; entities carry the formatting.
    builder = MessageBuilder().style('Отчет\n', 'bold').text('Имя: ').style(name, 'italic')
    builder = builder.text('\nЗаметки:\n').text(notes).text('\n').style('Документация', 'text_link', url='https://core.telegram.org/bots/api')
    return builder.build().split()  # parts of at most 4096 UTF-16 units, entities split with them


def attach_reports(application: Application) -> None:  # type: ignore[type-arg]
    async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None or user.is_bot:
            return
        for part in compose_report(user.full_name, '<b>буквальный текст</b> *_ [] & 😀\n' * 160):
            # parse_mode=None overrides any Defaults; a failed part stops the sequence, nothing is retried blindly.
            await context.bot.send_message(message.chat.id, **ptb_text(part))

    application.add_handler(CommandHandler('report', report, filters=filters.ChatType.PRIVATE))
