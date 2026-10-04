"""Искусственная HMAC-подпись для локального примера, без Telegram и login."""
import hmac
import json
from urllib.parse import urlencode
from telegram_patterns import BotSettings, InvalidInitData, VerifiedLaunch, validate_init_data

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
# Настоящие initData приходят от Telegram; ACL/session/replay проверяет backend.
print(json.dumps({'passed': True, 'case': 'core_identity', 'network': False}))
