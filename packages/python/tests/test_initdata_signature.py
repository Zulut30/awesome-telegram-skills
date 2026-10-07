"""Third-party initData validation: Ed25519 `signature` with Telegram's public key, no bot token."""
import base64
import hmac
import json
import sys
import unittest
from unittest import mock
from urllib.parse import urlencode

from telegram_patterns import (
    TELEGRAM_PUBLIC_KEYS, InvalidInitData, UnsupportedCapability, ValidationFailure, validate_init_data,
    validate_init_data_signature,
)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
except ImportError:  # the signature extra is optional; the delivery verifier installs it
    Ed25519PrivateKey = None

# Independent vector from aiogram's test suite (its own key pair, bot 42), not produced by this code.
AIOGRAM_PUBLIC_KEY = bytes.fromhex('4112765021341e5415e772cd65903f6b94e3ea1c2ab669e6d3e18ee2db00da61')
AIOGRAM_SIGNATURE = 'JQ0JR2tjC65yq_jNZV0wuJVX6J-SWPMV0mprUXG34g-NvxL4RcF1Rz5n4VVo00VRghEUBf5t___uoeb1-jU_Cw'
AIOGRAM_FIELDS = 'auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test'
AIOGRAM_NOW = 1650385342


@unittest.skipIf(Ed25519PrivateKey is None, 'install the signature extra (cryptography)')
class InitDataSignatureTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def signed(self, fields: dict, bot_id: int = 7, *, padded: bool = False, token: str | None = None) -> str:
        check = f'{bot_id}:WebAppData\n' + '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
        signature = base64.urlsafe_b64encode(self.key.sign(check.encode())).decode()
        fields = {**fields, 'signature': signature if padded else signature.rstrip('=')}
        if token is not None:  # the bot owner's hash covers every field but hash, signature included
            secret = hmac.digest(b'WebAppData', token.encode(), 'sha256')
            data = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
            fields['hash'] = hmac.digest(secret, data.encode(), 'sha256').hex()
        return urlencode(fields)

    def test_published_keys_match_the_documentation(self):
        self.assertEqual(TELEGRAM_PUBLIC_KEYS['production'].hex(), 'e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d')
        self.assertEqual(TELEGRAM_PUBLIC_KEYS['test'].hex(), '40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec')
        with self.assertRaises(TypeError):
            TELEGRAM_PUBLIC_KEYS['production'] = b''  # type: ignore[index]

    def test_independent_aiogram_vector(self):
        raw = f'{AIOGRAM_FIELDS}&hash=123&signature={AIOGRAM_SIGNATURE}'
        launch = validate_init_data_signature(raw, 42, public_key=AIOGRAM_PUBLIC_KEY, now=AIOGRAM_NOW)
        self.assertEqual((launch.user_id, launch.user['first_name'], launch.query_id, launch.auth_date), (42, 'Test', 'test', AIOGRAM_NOW))
        for label, changed, bot_id in (
                ('other bot', raw, 43),
                ('other signature', raw.replace('-jU_Cw', '-j1U_w'), 42),
                ('changed field', raw.replace('query_id=test', 'query_id=tesT'), 42),
                ('no signature', AIOGRAM_FIELDS, 42)):
            with self.subTest(label), self.assertRaises(InvalidInitData):
                validate_init_data_signature(changed, bot_id, public_key=AIOGRAM_PUBLIC_KEY, now=AIOGRAM_NOW)
        with self.assertRaises(InvalidInitData):  # production and test keys are not this key
            validate_init_data_signature(raw, 42, now=AIOGRAM_NOW)
        with self.assertRaises(InvalidInitData):
            validate_init_data_signature(raw, 42, environment='test', now=AIOGRAM_NOW)

    def test_all_signed_fields_and_both_signatures_on_one_launch(self):
        fields = {'auth_date': '1000', 'query_id': 'AAF', 'chat_type': 'sender', 'chat_instance': '-77', 'start_param': 'ref_1',
                  'can_send_after': '5', 'user': json.dumps({'id': 42, 'first_name': 'Анна', 'username': 'a&b=c'}),
                  'chat': json.dumps({'id': -100, 'type': 'group', 'title': 'Чат'}), 'receiver': json.dumps({'id': 9, 'first_name': 'B'})}
        raw = self.signed(fields, token='7:TOKEN')
        third_party = validate_init_data_signature(raw, 7, public_key=self.public, now=1001)
        owner = validate_init_data(raw, '7:TOKEN', now=1001)
        self.assertEqual(third_party, owner)
        self.assertEqual((third_party.user['first_name'], third_party.chat['title'], third_party.can_send_after), ('Анна', 'Чат', 5))
        self.assertEqual(validate_init_data_signature(self.signed(fields, padded=True), 7, public_key=self.public, now=1001), third_party)

    def test_freshness_identity_and_ambiguity_are_checked_after_the_signature(self):
        fields = {'auth_date': '1000', 'user': json.dumps({'id': 42})}
        raw = self.signed(fields)
        for label, case, now in (('too old', raw, 1000 + 3600), ('from the future', raw, 1000 - 31),
                                 ('no user', self.signed({'auth_date': '1000'}), 1001),
                                 ('duplicate field', raw + '&auth_date=1000', 1001),
                                 ('broken base64url', raw.replace('signature=', 'signature=%2B'), 1001)):
            with self.subTest(label), self.assertRaises(InvalidInitData):
                validate_init_data_signature(case, 7, public_key=self.public, now=now)

    def test_configuration_errors_are_not_launch_errors(self):
        raw = self.signed({'auth_date': '1000', 'user': json.dumps({'id': 42})})
        for label, kwargs in (('bool bot id', {'bot_id': True}), ('zero bot id', {'bot_id': 0}), ('text bot id', {'bot_id': '7'}),
                              ('unknown environment', {'bot_id': 7, 'environment': 'staging'}),
                              ('short key', {'bot_id': 7, 'public_key': b'x' * 31}), ('hex key', {'bot_id': 7, 'public_key': self.public.hex()}),
                              ('bad age', {'bot_id': 7, 'public_key': self.public, 'max_age_seconds': 0})):
            with self.subTest(label), self.assertRaises(ValidationFailure) as caught:
                validate_init_data_signature(raw, now=1001, **kwargs)
            self.assertNotIsInstance(caught.exception, InvalidInitData)

    def test_missing_extra_is_reported_as_unsupported(self):
        modules = {'cryptography': None, 'cryptography.exceptions': None, 'cryptography.hazmat.primitives.asymmetric.ed25519': None}
        with mock.patch.dict(sys.modules, modules), self.assertRaisesRegex(UnsupportedCapability, r'\[signature\]'):
            validate_init_data_signature('auth_date=1', 7, now=1)


if __name__ == '__main__':
    unittest.main()
