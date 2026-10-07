"""Ephemeral messages: groups only, a human receiver, the 15-second window and how edits are addressed."""

import unittest

from telegram_patterns import (
    EphemeralMessageRef,
    EphemeralNotAllowed,
    EphemeralTrigger,
    ValidationFailure,
    ephemeral_parameters,
)


def plan(**overrides):
    values = dict(chat_type='supergroup', receiver_user_id=7, trigger=EphemeralTrigger.callback('q1', 100.0), now=105.0)
    return ephemeral_parameters(**{**values, **overrides})


class EphemeralTests(unittest.TestCase):
    def test_button_press_answer_names_the_callback(self):
        self.assertEqual(plan(), {'ephemeral_message_parameters': {'receiver_user_id': 7, 'callback_query_id': 'q1'}})
        self.assertEqual(
            plan(replace_original=True)['ephemeral_message_parameters']['replace_callback_query_message'], True
        )
        self.assertEqual(
            plan(now=115.0)['ephemeral_message_parameters']['callback_query_id'], 'q1', '15 seconds inclusive'
        )

    def test_answer_to_an_ephemeral_command_replies_to_it(self):
        result = plan(trigger=EphemeralTrigger.reply_to(55, 100.0))
        self.assertEqual(
            result,
            {'ephemeral_message_parameters': {'receiver_user_id': 7}, 'reply_parameters': {'ephemeral_message_id': 55}},
        )

    def test_who_may_receive_and_when(self):
        cases = {
            'private chat': dict(chat_type='private'),
            'channel': dict(chat_type='channel'),
            'bot receiver': dict(receiver_is_bot=True),
            'late answer': dict(now=115.5),
            'no trigger': dict(trigger=None),
            'replace from an ephemeral message': dict(
                trigger=EphemeralTrigger.callback('q1', 100.0, from_ephemeral_message=True), replace_original=True
            ),
            'replace an ephemeral command': dict(trigger=EphemeralTrigger.reply_to(55, 100.0), replace_original=True),
            'replace after the window as admin': dict(bot_is_admin=True, now=200.0, replace_original=True),
        }
        for label, overrides in cases.items():
            with self.subTest(label), self.assertRaises(EphemeralNotAllowed):
                plan(**overrides)

    def test_administrator_bot_may_write_at_any_time_without_a_trigger(self):
        self.assertEqual(
            plan(bot_is_admin=True, trigger=None), {'ephemeral_message_parameters': {'receiver_user_id': 7}}
        )
        late = plan(bot_is_admin=True, now=500.0)
        self.assertEqual(
            late, {'ephemeral_message_parameters': {'receiver_user_id': 7}}, 'a stale trigger is dropped, not sent'
        )
        with self.assertRaises(EphemeralNotAllowed):
            plan(bot_is_admin=True, receiver_is_bot=True)

    def test_inputs_and_references_are_validated(self):
        for make in (
            lambda: EphemeralTrigger.callback('', 1.0),
            lambda: EphemeralTrigger.reply_to(0, 1.0),
            lambda: EphemeralTrigger('callback', 1.0, callback_query_id='q', ephemeral_message_id=3),
            lambda: EphemeralTrigger.callback('q', True),
            lambda: plan(receiver_user_id=0),
            lambda: plan(now=-1),
            lambda: plan(bot_is_admin=1),
            lambda: EphemeralMessageRef(100, 7, 5),
            lambda: EphemeralMessageRef(-100, 7, 0),
        ):
            with self.subTest(make=make), self.assertRaises(ValidationFailure):
                make()
        self.assertNotIsInstance(self.catch(lambda: plan(receiver_user_id=0)), EphemeralNotAllowed)
        ref = EphemeralMessageRef(-1001, 7, 5)
        self.assertEqual(ref.target(), {'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5})

    @staticmethod
    def catch(action):
        try:
            action()
        except Exception as error:  # noqa: BLE001 - the test inspects the type
            return error
        return None


if __name__ == '__main__':
    unittest.main()
