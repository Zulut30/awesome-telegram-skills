"""SDK-free paid access from a Stars subscription: charges, renewal states and refunds; no network."""
import json
from telegram_patterns import STARS_SUBSCRIPTION_PERIOD, RenewalState, StarsCharge, StarsSubscription, SubscriptionEventRejected

paid_at = 1_790_000_000  # Message.date of the successful_payment service message
charge = {'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'pro:7', 'telegram_payment_charge_id': 'fixture-charge',
          'subscription_expiration_date': paid_at + STARS_SUBSCRIPTION_PERIOD, 'is_recurring': True, 'is_first_recurring': True}
sub = StarsSubscription(user_id=7, invoice_payload='pro:7').record_payment(charge, user_id=7, paid_at=paid_at)
assert sub.has_access(paid_at) and sub.access_until(paid_at) == paid_at + STARS_SUBSCRIPTION_PERIOD
assert sub.record_payment(charge, user_id=7, paid_at=paid_at) is sub  # a repeated charge extends nothing
canceled = sub.record_update({'user': {'id': 7}, 'invoice_payload': 'pro:7', 'state': 'canceled'})  # BotSubscriptionUpdated
assert canceled.has_access(paid_at + 1) and not canceled.renews(paid_at + 1)  # the paid month stays
renewal: RenewalState = canceled.renewal
first: StarsCharge = canceled.charges[0]
assert renewal == 'canceled' and first.first and first.amount == 250
refunded = sub.record_refund({'currency': 'XTR', 'invoice_payload': 'pro:7', 'telegram_payment_charge_id': 'fixture-charge'}, user_id=7)
assert not refunded.has_access(paid_at + 1)
try:
    sub.record_update({'user': {'id': 8}, 'invoice_payload': 'pro:7', 'state': 'failed'})
except SubscriptionEventRejected:
    pass  # another user's event changes nothing
else:
    raise AssertionError('Foreign subscription event accepted')
assert StarsSubscription.from_dict(json.loads(json.dumps(sub.as_dict()))) == sub  # the host stores this JSON
print(json.dumps({'case': 'core_stars_subscription', 'passed': True, 'network': False}))
