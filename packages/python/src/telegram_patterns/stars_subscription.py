"""Paid access from a Telegram Stars subscription: charges grant periods, BotSubscriptionUpdated changes renewal.

A subscription is one user and one invoice payload (Bot API: a user may hold several concurrent subscriptions,
so the payload must name the subscription). Each recurring SuccessfulPayment is a charge that grants
[paid_at, subscription_expiration_date). BotSubscriptionUpdated (Bot API 10.2+) carries no date and no charge:
"canceled", "active" and "failed" change only whether a next charge is expected and never add or remove paid
time. A RefundedPayment withdraws the period of its own charge. The host stores the state (as_dict/from_dict)
and checks has_access(now) on every protected action.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

from .errors import ErrorCode, ValidationFailure

STARS_SUBSCRIPTION_PERIOD = 2592000  # seconds; the only period Telegram accepts for now
RenewalState = Literal['pending', 'active', 'canceled', 'failed']
_STATES = ('active', 'canceled', 'failed')


class SubscriptionEventRejected(ValidationFailure):
    """The event does not belong to this subscription or contradicts a stored charge; nothing was applied."""
    code: ErrorCode = 'validation-failed'


@dataclass(frozen=True, slots=True)
class StarsCharge:
    """One recurring payment and the period it pays for."""
    charge_id: str
    paid_at: int
    expires_at: int
    amount: int
    first: bool
    refunded: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.charge_id, str) or not self.charge_id:
            raise ValidationFailure('charge_id must be a nonempty string')
        for name in ('paid_at', 'expires_at', 'amount'):
            _positive(getattr(self, name), name)
        if self.expires_at <= self.paid_at or type(self.first) is not bool or type(self.refunded) is not bool:
            raise ValidationFailure('Malformed charge')

    def grants(self, now: float) -> bool:
        return not self.refunded and self.paid_at <= now < self.expires_at


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SubscriptionEventRejected(f'{key} must be a nonempty string')
    return value


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise SubscriptionEventRejected(f'{name} must be a positive integer')
    return value


@dataclass(frozen=True, slots=True)
class StarsSubscription:
    """Immutable state of one subscription; every record_* returns the next state or raises."""
    user_id: int
    invoice_payload: str
    charges: tuple[StarsCharge, ...] = ()
    renewal: RenewalState = 'pending'
    refunds_before_payment: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _positive(self.user_id, 'user_id')
        if not isinstance(self.invoice_payload, str) or not 1 <= len(self.invoice_payload.encode('utf-8')) <= 128:
            raise ValidationFailure('invoice_payload must contain 1..128 bytes')
        if self.renewal not in ('pending', *_STATES):
            raise ValidationFailure('Unknown renewal state')
        ids = [charge.charge_id for charge in self.charges]
        if not all(isinstance(charge, StarsCharge) for charge in self.charges) or len(set(ids)) != len(ids):
            raise ValidationFailure('Charges must be StarsCharge values with unique ids')
        if not isinstance(self.refunds_before_payment, frozenset) or self.refunds_before_payment & set(ids):
            raise ValidationFailure('refunds_before_payment holds refunds of charges not yet seen')

    def _own(self, user_id: Any, payload: Any) -> None:
        if user_id != self.user_id or payload != self.invoice_payload:
            raise SubscriptionEventRejected('The event belongs to another user or invoice payload')

    def record_payment(self, payment: Mapping[str, Any], *, user_id: int, paid_at: int) -> StarsSubscription:
        """Apply a SuccessfulPayment (Bot API JSON fields); paid_at is the date of its service message.

        A repeated charge returns the same state; the same charge id with other data is rejected.
        """
        if not isinstance(payment, Mapping):
            raise SubscriptionEventRejected('Expected SuccessfulPayment fields')
        self._own(user_id, payment.get('invoice_payload'))
        if payment.get('currency') != 'XTR':
            raise SubscriptionEventRejected('A Stars subscription is paid in XTR')
        if payment.get('is_recurring') is not True:
            raise SubscriptionEventRejected('A one-time payment is not a subscription charge')
        paid_at = _positive(paid_at, 'paid_at')
        expires_at = _positive(payment.get('subscription_expiration_date'), 'subscription_expiration_date')
        if expires_at <= paid_at:
            raise SubscriptionEventRejected('subscription_expiration_date must be after the payment')
        charge = StarsCharge(_text(payment, 'telegram_payment_charge_id'), paid_at, expires_at,
                             _positive(payment.get('total_amount'), 'total_amount'), payment.get('is_first_recurring') is True)
        charge = replace(charge, refunded=charge.charge_id in self.refunds_before_payment)
        for stored in self.charges:
            if stored.charge_id == charge.charge_id:
                if replace(stored, refunded=charge.refunded) != charge:
                    raise SubscriptionEventRejected('The charge id is already stored with other data')
                return self
        # A successful charge shows renewal works again; a user's cancellation stays until "active" arrives.
        renewal: RenewalState = 'active' if self.renewal in ('pending', 'failed') else self.renewal
        return replace(self, charges=(*self.charges, charge), renewal=renewal,
                       refunds_before_payment=self.refunds_before_payment - {charge.charge_id})

    def record_update(self, update: Mapping[str, Any]) -> StarsSubscription:
        """Apply BotSubscriptionUpdated: the renewal changes, paid periods stay as they are."""
        if not isinstance(update, Mapping) or not isinstance(update.get('user'), Mapping):
            raise SubscriptionEventRejected('Expected BotSubscriptionUpdated fields')
        self._own(cast(Mapping[str, Any], update['user']).get('id'), update.get('invoice_payload'))
        state = update.get('state')
        if state not in _STATES:
            raise SubscriptionEventRejected('Unknown subscription state; reconcile before changing access')
        return replace(self, renewal=cast(RenewalState, state))

    def record_refund(self, refund: Mapping[str, Any], *, user_id: int) -> StarsSubscription:
        """Apply RefundedPayment: only the refunded charge stops granting; a refund may arrive first."""
        if not isinstance(refund, Mapping):
            raise SubscriptionEventRejected('Expected RefundedPayment fields')
        self._own(user_id, refund.get('invoice_payload'))
        if refund.get('currency') != 'XTR':
            raise SubscriptionEventRejected('A Stars subscription is refunded in XTR')
        charge_id = _text(refund, 'telegram_payment_charge_id')
        if not any(charge.charge_id == charge_id for charge in self.charges):
            return replace(self, refunds_before_payment=self.refunds_before_payment | {charge_id})
        return replace(self, charges=tuple(replace(charge, refunded=True) if charge.charge_id == charge_id else charge
                                           for charge in self.charges))

    def has_access(self, now: float) -> bool:
        """True while a charge that was not refunded covers now; renewal state does not matter."""
        return any(charge.grants(now) for charge in self.charges)

    def access_until(self, now: float) -> int | None:
        """End of the continuous paid access that covers now, or None without access."""
        current = [charge.expires_at for charge in self.charges if charge.grants(now)]
        if not current:
            return None
        end, extended = max(current), True
        while extended:  # a renewal paid before the end continues the access
            extended = False
            for charge in self.charges:
                if not charge.refunded and charge.paid_at <= end < charge.expires_at:
                    end, extended = charge.expires_at, True
        return end

    def renews(self, now: float) -> bool:
        """A next charge is expected: access is current and the renewal is active."""
        return self.renewal == 'active' and self.has_access(now)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready state for the host's storage."""
        return {'version': 1, 'user_id': self.user_id, 'invoice_payload': self.invoice_payload, 'renewal': self.renewal,
                'refunds_before_payment': sorted(self.refunds_before_payment),
                'charges': [{'charge_id': c.charge_id, 'paid_at': c.paid_at, 'expires_at': c.expires_at, 'amount': c.amount,
                             'first': c.first, 'refunded': c.refunded} for c in self.charges]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StarsSubscription:
        if not isinstance(data, Mapping) or data.get('version') != 1:
            raise ValidationFailure('Unsupported subscription state')
        try:
            charges = tuple(StarsCharge(**charge) for charge in data['charges'])
            return cls(data['user_id'], data['invoice_payload'], charges, data['renewal'], frozenset(data['refunds_before_payment']))
        except (KeyError, TypeError) as error:
            raise ValidationFailure('Malformed subscription state') from error
