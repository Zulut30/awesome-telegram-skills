"""Send an order card as a rich message, or the same content as ordinary text; no polling on import."""
from typing import Callable, Sequence

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage, SendRichMessage
from aiogram.types import CallbackQuery, Message
from telegram_patterns import RichButton, RichMessage, RichMessageBuilder, RichSpan

TERMS_URL = 'https://core.telegram.org/bots/api'


def order_card(order_id: int, items: Sequence[tuple[str, int, str]], total: str, receipt_file_id: str | None) -> RichMessage:
    """One card: heading, compact table, checklist, collapsible note, details, receipt and a button row."""
    rows = [['Товар', 'Кол-во', 'Цена'], *([name, str(count), price] for name, count, price in items)]
    delivery = RichMessageBuilder().paragraph('Курьер привезет заказ в течение двух дней.').bullets(['Сверьте состав', 'Подпишите акт'])
    card = (RichMessageBuilder()
            .heading(f'Заказ №{order_id}', size=1)
            .paragraph(['Статус: ', RichSpan('bold', 'оплачен'), '. Подробнее — в ', RichSpan('url', 'условиях', url=TERMS_URL), '.'])
            .table(rows, compact=True, caption=f'Итого: {total}')
            .checklist([('Оплата получена', True), ('Передан в доставку', False)])
            .quote('Оставьте у двери, позвоните за час до приезда.', credit='Комментарий покупателя', expandable=True)
            .details('Как проходит доставка', delivery))
    if receipt_file_id is not None:
        card = card.document(receipt_file_id, caption='Чек')  # file_id this bot received earlier
    return card.buttons([RichButton('Подтвердить', callback_data=f'order:confirm:{order_id}', style='success'),
                         RichButton('Отменить', callback_data=f'order:cancel:{order_id}', style='link')]).build()


def attach_order_cards(dispatcher: Dispatcher, *, receipt_file_id: str | None = None,
                       rich_supported: Callable[[Message], bool] = lambda message: message.business_connection_id is None) -> Router:
    """The host decides where rich messages are allowed; elsewhere the same card goes as text and an inline keyboard."""
    router = Router(name='order-card')

    @router.message(Command('order'), F.chat.type == 'private')
    async def show(message: Message) -> None:
        # Example data; a real handler loads the order of message.from_user and checks access first.
        card = order_card(42, [('Книга', 1, '500 ₽'), ('Ручка', 2, '100 ₽')], '700 ₽', receipt_file_id)
        if rich_supported(message):
            # SDK models validate the JSON before anything is sent.
            await message.bot(SendRichMessage.model_validate({'chat_id': message.chat.id, 'rich_message': card.as_input()}))
            return
        parts = card.fallback().split()
        keyboard = card.fallback_keyboard()
        for index, part in enumerate(parts):
            extra = {'reply_markup': {'inline_keyboard': keyboard}} if keyboard and index == len(parts) - 1 else {}
            await message.bot(SendMessage.model_validate({'chat_id': message.chat.id, **part.as_kwargs(), **extra}))

    @router.callback_query(F.data.startswith('order:'))
    async def act(query: CallbackQuery) -> None:
        # ACK only; the service checks the user and the order before confirming or cancelling it.
        await query.answer('Запрос принят')

    dispatcher.include_router(router)
    return router
