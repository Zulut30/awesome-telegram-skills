"""Actual python-telegram-bot Application for a Stars subscription with Bot API 10.2 subscription updates; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns import STARS_SUBSCRIPTION_PERIOD, StarsSubscription
from telegram_patterns.ptb import offline_application
from ptb_stars_subscription_bot import attach_stars_subscription

ANNA = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}
CHAT = {'id': 7, 'type': 'private', 'first_name': 'Анна'}
T0, DAY = 1_790_000_000, 86400


async def main():
    application, stub = offline_application()
    helped, stored, now = [], {}, [float(T0)]

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))

    async def load(user_id, payload):
        data = stored.get((user_id, payload))
        return None if data is None else StarsSubscription.from_dict(json.loads(data))

    async def save(sub):
        stored[(sub.user_id, sub.invoice_payload)] = json.dumps(sub.as_dict())
    attach_stars_subscription(application, load=load, save=save, clock=lambda: now[0])
    stub.respond('createInvoiceLink', 'https://t.me/$fixture-invoice')
    stub.respond('answerPreCheckoutQuery', True)
    stub.respond('sendMessage', lambda p: {'message_id': 500, 'date': T0, 'chat': CHAT, 'text': p['text']})
    index = [0]

    async def feed(**fields):
        index[0] += 1
        await application.process_update(Update.de_json({'update_id': index[0], **fields}, application.bot))

    def message(at, **fields):
        return {'message_id': index[0] + 1, 'date': at, 'chat': CHAT, 'from': ANNA, **fields}

    def command(at, text):
        return message(at, text=text, entities=[{'type': 'bot_command', 'offset': 0, 'length': len(text)}])

    def charge(charge_id, at, first=False):
        return message(at, successful_payment={'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:7', 'telegram_payment_charge_id': charge_id,
                                               'provider_payment_charge_id': '', 'subscription_expiration_date': at + STARS_SUBSCRIPTION_PERIOD,
                                               'is_recurring': True, 'is_first_recurring': first})

    async def pro(at):
        now[0] = at
        await feed(message=command(at, '/pro'))
        return stub.calls[-1][1]['text'] == 'Раздел Pro открыт.'
    await application.initialize()
    try:
        await feed(message=command(T0, '/subscribe'))
        invoice = next(p for m, p in stub.calls if m == 'createInvoiceLink')
        assert invoice['subscription_period'] == STARS_SUBSCRIPTION_PERIOD and invoice['currency'] == 'XTR' and invoice['payload'] == 'pro:7'
        await feed(pre_checkout_query={'id': 'pc1', 'from': ANNA, 'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:7'})
        await feed(pre_checkout_query={'id': 'pc2', 'from': ANNA, 'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:8'})
        answers = [p for m, p in stub.calls if m == 'answerPreCheckoutQuery']
        assert answers[0] == {'pre_checkout_query_id': 'pc1', 'ok': True} and answers[1]['ok'] is False
        assert not await pro(T0), 'checkout alone grants nothing'
        await feed(message=charge('c1', T0, first=True))
        end = T0 + STARS_SUBSCRIPTION_PERIOD
        assert await pro(T0 + DAY) and not await pro(end)
        await feed(message=charge('c2', end - DAY))
        await feed(message=charge('c2', end - DAY))
        assert len((await load(7, 'pro:7')).charges) == 2 and await pro(end + DAY), 'a renewal charge extends once'
        await feed(subscription={'user': ANNA, 'invoice_payload': 'pro:7', 'state': 'canceled'})
        extended = end - DAY + STARS_SUBSCRIPTION_PERIOD
        assert (await load(7, 'pro:7')).renewal == 'canceled' and await pro(extended - 1) and not await pro(extended)
        await feed(subscription={'user': ANNA, 'invoice_payload': 'pro:7', 'state': 'active'})
        now[0] = extended - DAY
        await feed(subscription={'user': ANNA, 'invoice_payload': 'pro:7', 'state': 'failed'})
        assert stub.calls[-1] == ('sendMessage', {'chat_id': 7, 'text': 'Продление не прошло. Pro работает до конца оплаченного месяца.'})
        await feed(message=command(T0, '/help'))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'unknown_update_via_api_kwargs': True, 'checkout_grants_nothing': True, 'renewal_extends': True,
                      'canceled_keeps_paid_month': True, 'failed_notifies': True, 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
