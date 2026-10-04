"""SDK request construction; ничего не отправляется и file не читается."""
import json
from aiogram.methods import SendMessage
from telegram_patterns.aiogram import MethodSpec, InvalidAPIRequest, method_catalog, build_request

catalog = method_catalog()
spec: MethodSpec = next(item for item in catalog if item.name == 'sendMessage')
assert 'chat_id' in spec.required and spec.sdk_class == 'SendMessage' and spec.url.startswith('https://')
request = build_request(spec.name, {'chat_id': 42, 'text': 'Публичная fixture', 'parse_mode': None})
assert isinstance(request, SendMessage) and request.chat_id == 42 and request.text == 'Публичная fixture'
try: build_request(spec.name, {'chat_id': 42, 'text': 'Fixture', 'invented': True})
except InvalidAPIRequest: pass
else: raise AssertionError('Unknown field accepted')
# SDK validation не подтверждает права, доставку, rate limits или оплату.
print(json.dumps({'passed': True, 'case': 'bot_methods', 'network': False}))
