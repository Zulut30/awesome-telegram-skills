"""SDK-free ephemeral message rules: who may receive one and how to address edits; no network."""
import json
from telegram_patterns import EphemeralMessageRef, EphemeralNotAllowed, EphemeralTrigger, ephemeral_parameters

press = EphemeralTrigger.callback('fixture-query', received_at=100.0)
extra = ephemeral_parameters(chat_type='supergroup', receiver_user_id=7, trigger=press, now=101.0)
# sendMessage(chat_id=..., text=..., **extra): only user 7 sees the answer.
assert extra == {'ephemeral_message_parameters': {'receiver_user_id': 7, 'callback_query_id': 'fixture-query'}}
command = EphemeralTrigger.reply_to(55, received_at=100.0)
assert ephemeral_parameters(chat_type='group', receiver_user_id=7, trigger=command, now=110.0)['reply_parameters'] == {'ephemeral_message_id': 55}
try:
    ephemeral_parameters(chat_type='supergroup', receiver_user_id=7, trigger=press, now=116.0)
except EphemeralNotAllowed:
    pass  # a non-administrator bot has 15 seconds; then answer with an alert or an ordinary message
else:
    raise AssertionError('Late ephemeral answer accepted')
sent = EphemeralMessageRef(chat_id=-1001, receiver_user_id=7, ephemeral_message_id=5)  # Message.ephemeral_message_id
assert sent.target() == {'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5}  # editEphemeralMessage*/delete
print(json.dumps({'case': 'core_ephemeral', 'passed': True, 'network': False}))
