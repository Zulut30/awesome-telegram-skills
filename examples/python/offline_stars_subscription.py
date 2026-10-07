"""Actual host Dispatcher and SDK models for a Stars subscription: charges extend access, updates and expiry end it; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import AnswerPreCheckoutQuery, CreateInvoiceLink, SendMessage
from aiogram.types import BotSubscriptionUpdated, Chat, Message, PreCheckoutQuery, Update, User
from telegram_patterns import STARS_SUBSCRIPTION_PERIOD, StarsSubscription
from telegram_patterns.testing import StubSession
from stars_subscription_bot import attach_stars_subscription

ANNA = User(id=7, is_bot=False, first_name='Анна')
PRIVATE = Chat(id=7, type='private', first_name='Анна')
T0 = 1_790_000_000
DAY = 86400


async def main():
    session = StubSession()
    bot = Bot('100:STARS_SUBSCRIPTION_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    stored, now = {}, [float(T0)]

    async def load(user_id, payload):
        data = stored.get((user_id, payload))
        return None if data is None else StarsSubscription.from_dict(json.loads(data))

    async def save(sub):
        stored[(sub.user_id, sub.invoice_payload)] = json.dumps(sub.as_dict())  # what a database row would hold

    attach_stars_subscription(dispatcher, load=load, save=save, clock=lambda: now[0])
    invoices, checkouts, sent = [], [], []
    session.respond(CreateInvoiceLink, lambda method: invoices.append(method) or 'https://t.me/$fixture-invoice')
    session.respond(AnswerPreCheckoutQuery, lambda method: checkouts.append((method.ok, method.error_message)) or True)
    session.respond(SendMessage, lambda method: sent.append((method.chat_id, method.text)) or
                    {'message_id': 500 + len(sent), 'date': T0, 'chat': {'id': method.chat_id, 'type': 'private'}, 'text': method.text})
    index = [0]

    async def feed(**fields):
        index[0] += 1
        await dispatcher.feed_update(bot, Update(update_id=index[0], **fields))

    def message(at, **fields):
        return Message.model_validate({'message_id': index[0] + 1, 'date': datetime.fromtimestamp(at, timezone.utc),
                                       'chat': PRIVATE, 'from_user': ANNA, **fields})

    def charge(charge_id, at, *, first=False):
        return message(at, successful_payment={'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:7',
            'telegram_payment_charge_id': charge_id, 'provider_payment_charge_id': '',
            'subscription_expiration_date': at + STARS_SUBSCRIPTION_PERIOD, 'is_recurring': True, 'is_first_recurring': first})

    async def pro(at):
        now[0] = at
        await feed(message=message(at, text='/pro'))
        return sent[-1][1] == 'Раздел Pro открыт.'

    def renewal(state):
        return BotSubscriptionUpdated(user=ANNA, invoice_payload='pro:7', state=state)
    try:
        await feed(message=message(T0, text='/subscribe'))
        assert invoices[0].subscription_period == STARS_SUBSCRIPTION_PERIOD and invoices[0].currency == 'XTR' and invoices[0].payload == 'pro:7'
        await feed(pre_checkout_query=PreCheckoutQuery(id='pc1', from_user=ANNA, currency='XTR', total_amount=250, invoice_payload='pro:7'))
        await feed(pre_checkout_query=PreCheckoutQuery(id='pc2', from_user=ANNA, currency='XTR', total_amount=250, invoice_payload='pro:8'))
        assert checkouts == [(True, None), (False, 'Счет устарел, запросите новый: /subscribe')]
        assert not await pro(T0), 'checkout alone grants nothing'

        await feed(message=charge('c1', T0, first=True))
        end = T0 + STARS_SUBSCRIPTION_PERIOD
        assert await pro(T0 + DAY) and not await pro(end)

        renewed = end - DAY  # the next monthly charge extends access
        await feed(message=charge('c2', renewed))
        await feed(message=charge('c2', renewed))  # a duplicate delivery extends nothing
        sub = await load(7, 'pro:7')
        extended = renewed + STARS_SUBSCRIPTION_PERIOD
        assert len(sub.charges) == 2 and sub.access_until(renewed) == extended
        assert await pro(end + DAY)

        await feed(subscription=renewal('canceled'))
        assert (await load(7, 'pro:7')).renewal == 'canceled' and await pro(extended - 1), 'cancellation keeps the paid month'
        assert not await pro(extended), 'and access ends when it is over'

        await feed(subscription=renewal('active'))
        now[0] = extended - DAY
        await feed(subscription=renewal('failed'))
        last_day = datetime.fromtimestamp(extended, timezone.utc).strftime('%d.%m.%Y %H:%M UTC')
        assert sent[-1] == (7, f'Продление не прошло. Pro работает до {last_day}.'), sent[-1]
        assert await pro(extended - 1) and not await pro(extended)

        await feed(message=message(extended - 1, refunded_payment={'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:7',
                                                                   'telegram_payment_charge_id': 'c2'}))
        assert not await pro(end + DAY), 'the refunded renewal month is withdrawn'
        assert await pro(T0 + DAY), 'the first paid month stays'

        await feed(message=message(T0, text='/help'))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'monthly_invoice': True,
                      'checkout_grants_nothing': True, 'charge_grants_period': True, 'renewal_extends': True, 'duplicate_ignored': True,
                      'canceled_keeps_paid_month': True, 'failed_notifies_and_expires': True, 'refund_withdraws_its_month': True,
                      'state_round_trips_json': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
