"""Искусственная HMAC-подпись и независимый вектор Ed25519 для локального примера, без Telegram и login."""
import hmac
import json
from urllib.parse import urlencode
from telegram_patterns import (BotSettings, InvalidInitData, TELEGRAM_PUBLIC_KEYS, UnsupportedCapability, VerifiedLaunch,
                               validate_init_data, validate_init_data_signature)

settings = BotSettings.from_env(environ={'BOT_TOKEN': '100:REFERENCE_FIXTURE'})
fields = {'auth_date': '1000', 'user': json.dumps({'id': 42})}
check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
secret = hmac.digest(b'WebAppData', settings.token.encode(), 'sha256')
raw = urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})
launch: VerifiedLaunch = validate_init_data(raw, settings.token, now=1001)
assert (launch.user_id, launch.auth_date, launch.user['id']) == (42, 1000, 42)
try:
    validate_init_data(raw + '&user=duplicate', settings.token, now=1001)
except InvalidInitData:
    pass
else:
    raise AssertionError('Ambiguous launch accepted')
assert 'REFERENCE_FIXTURE' not in repr(settings)
# Сторонняя проверка без токена бота: подпись Ed25519 и bot_id. Вектор и ключ из тестов aiogram, не ключ Telegram.
signed = ('auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test'
          '&signature=JQ0JR2tjC65yq_jNZV0wuJVX6J-SWPMV0mprUXG34g-NvxL4RcF1Rz5n4VVo00VRghEUBf5t___uoeb1-jU_Cw')
fixture_key = bytes.fromhex('4112765021341e5415e772cd65903f6b94e3ea1c2ab669e6d3e18ee2db00da61')
assert len(TELEGRAM_PUBLIC_KEYS['production']) == 32  # настоящая initData проверяется этим ключом
third_party: VerifiedLaunch | None
try:
    third_party = validate_init_data_signature(signed, 42, public_key=fixture_key, now=1650385342)
except UnsupportedCapability:
    third_party = None  # без extra signature (cryptography) функция сообщает, что Ed25519 недоступна
else:
    assert (third_party.user_id, third_party.query_id) == (42, 'test')
# Настоящие initData приходят от Telegram; ACL/session/replay проверяет backend.
print(json.dumps({'passed': True, 'case': 'core_identity', 'network': False}))
