import json
import unittest

from telegram_patterns import STARS_SUBSCRIPTION_PERIOD, StarsSubscription, SubscriptionEventRejected, ValidationFailure

DAY = 86400
T0 = 1_790_000_000


def payment(charge, paid_at, *, first=False, payload='plan:pro:7', amount=250):
    return {'currency': 'XTR', 'total_amount': amount, 'invoice_payload': payload, 'telegram_payment_charge_id': charge,
            'provider_payment_charge_id': '', 'subscription_expiration_date': paid_at + STARS_SUBSCRIPTION_PERIOD,
            'is_recurring': True, 'is_first_recurring': first}


def update(state, *, user=7, payload='plan:pro:7'):
    return {'user': {'id': user, 'is_bot': False, 'first_name': 'Анна'}, 'invoice_payload': payload, 'state': state}


class StarsSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.sub = StarsSubscription(7, 'plan:pro:7').record_payment(payment('c1', T0, first=True), user_id=7, paid_at=T0)

    def test_charge_grants_a_half_open_period(self):
        end = T0 + STARS_SUBSCRIPTION_PERIOD
        self.assertFalse(self.sub.has_access(T0 - 1))
        self.assertTrue(self.sub.has_access(T0) and self.sub.has_access(end - 1))
        self.assertFalse(self.sub.has_access(end))
        self.assertEqual((self.sub.access_until(T0), self.sub.renewal, self.sub.charges[0].first), (end, 'active', True))
        self.assertTrue(self.sub.renews(T0))

    def test_renewal_charge_extends_once_and_conflicts_are_rejected(self):
        renewed = T0 + STARS_SUBSCRIPTION_PERIOD - DAY  # Telegram charges shortly before the end
        sub = self.sub.record_payment(payment('c2', renewed), user_id=7, paid_at=renewed)
        self.assertEqual(sub.access_until(T0), renewed + STARS_SUBSCRIPTION_PERIOD)
        self.assertIs(sub.record_payment(payment('c2', renewed), user_id=7, paid_at=renewed), sub)
        with self.assertRaises(SubscriptionEventRejected):
            sub.record_payment(payment('c2', renewed, amount=1), user_id=7, paid_at=renewed)
        self.assertEqual(len(sub.charges), 2)

    def test_canceled_failed_and_active_change_renewal_but_not_paid_time(self):
        end = T0 + STARS_SUBSCRIPTION_PERIOD
        canceled = self.sub.record_update(update('canceled'))
        self.assertEqual((canceled.renewal, canceled.access_until(T0 + DAY), canceled.renews(T0 + DAY)), ('canceled', end, False))
        self.assertFalse(canceled.has_access(end))
        # A charge processed after the cancellation does not re-enable renewal by itself.
        late = canceled.record_payment(payment('c0', T0 - DAY), user_id=7, paid_at=T0 - DAY)
        self.assertEqual(late.renewal, 'canceled')
        self.assertTrue(canceled.record_update(update('active')).renews(T0 + DAY))
        failed = self.sub.record_update(update('failed'))
        self.assertTrue(failed.has_access(end - 1) and not failed.renews(end - 1))
        self.assertFalse(failed.has_access(end))
        retried = failed.record_payment(payment('c2', end + DAY), user_id=7, paid_at=end + DAY)
        self.assertEqual(retried.renewal, 'active')
        self.assertTrue(retried.has_access(end + DAY) and not retried.has_access(end + DAY - 1))

    def test_refund_withdraws_only_its_charge_even_when_it_arrives_first(self):
        renewed = T0 + STARS_SUBSCRIPTION_PERIOD - DAY
        sub = self.sub.record_payment(payment('c2', renewed), user_id=7, paid_at=renewed)
        refund = {'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'plan:pro:7', 'telegram_payment_charge_id': 'c1'}
        refunded = sub.record_refund(refund, user_id=7)
        self.assertFalse(refunded.has_access(T0 + DAY))
        self.assertTrue(refunded.has_access(renewed))
        early = StarsSubscription(7, 'plan:pro:7').record_refund(refund, user_id=7)
        late = early.record_payment(payment('c1', T0, first=True), user_id=7, paid_at=T0)
        self.assertFalse(late.has_access(T0))
        self.assertTrue(late.charges[0].refunded and not late.refunds_before_payment)

    def test_foreign_or_malformed_events_change_nothing(self):
        for event in ({**payment('x', T0), 'currency': 'USD'}, {**payment('x', T0), 'is_recurring': None},
                      payment('x', T0, payload='plan:pro:8'), {**payment('x', T0), 'subscription_expiration_date': T0}):
            with self.assertRaises(SubscriptionEventRejected):
                self.sub.record_payment(event, user_id=7, paid_at=T0)
        with self.assertRaises(SubscriptionEventRejected):
            self.sub.record_payment(payment('x', T0), user_id=8, paid_at=T0)
        for event in (update('paused'), update('canceled', user=8), update('canceled', payload='other'), {'state': 'active'}):
            with self.assertRaises(SubscriptionEventRejected):
                self.sub.record_update(event)
        self.assertEqual(self.sub.renewal, 'active')
        with self.assertRaises(ValidationFailure):
            StarsSubscription(0, 'plan')

    def test_state_round_trips_through_json(self):
        sub = self.sub.record_update(update('canceled')).record_refund(
            {'currency': 'XTR', 'total_amount': 250, 'invoice_payload': 'plan:pro:7', 'telegram_payment_charge_id': 'c9'}, user_id=7)
        stored = json.loads(json.dumps(sub.as_dict()))
        self.assertEqual(StarsSubscription.from_dict(stored), sub)
        for broken in ({**stored, 'version': 2}, {**stored, 'charges': [{'charge_id': 'c1'}]},
                       {**stored, 'charges': stored['charges'] * 2}, {**stored, 'refunds_before_payment': ['c1']}):
            with self.assertRaises(ValidationFailure):
                StarsSubscription.from_dict(broken)


if __name__ == '__main__':
    unittest.main()
