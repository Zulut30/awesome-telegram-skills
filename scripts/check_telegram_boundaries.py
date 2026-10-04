"""Offline semantic probes; no token, Telegram HTTP or user-account login."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
from pathlib import Path

from aiogram.types import BusinessBotRights, BusinessConnection, Update, User
from telegram_patterns.aiogram import InvalidAPIRequest, build_request, method_catalog, update_kinds

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'catalog/api-boundaries.json')
    args = parser.parse_args()
    data = json.loads(args.catalog.read_text(encoding='utf-8'))
    assert data['schema_version'] == 1
    assert set(data['surfaces']) == {'bot-api', 'mini-app', 'business-bot', 'user-client'}
    assert data['automatic_user_session'] is data['sdk_construction_is_permission'] is data['native_presence_is_launch_permission'] is False
    assert len({row['id'] for row in data['scenarios']}) == len(data['scenarios'])
    routes = {row['id']: row['surface'] for row in data['scenarios']}
    assert routes['account-history'] == 'user-client'
    assert routes['business-reply'] == routes['business-read-mark'] == 'business-bot'
    assert routes['keyboard-send-data'] == routes['direct-launch'] == routes['inline-result'] == 'mini-app'
    available = {method.name for method in method_catalog()}
    for row in data['scenarios']:
        assert row['surface'] in data['surfaces'] and row['checks']
        assert all(method in available for method in row.get('methods', []))
        if 'rpc' in row: assert row['surface'] == 'user-client'
        if 'native_methods' in row: assert row['surface'] == 'mini-app'
    assert set(data['ordinary_update_absent_fields']) == {'user_typing', 'message_read', 'url_button_click', 'copy_text_click'}
    assert all(field not in Update.model_fields for field in data['ordinary_update_absent_fields'])
    # SDK request exists for profile-linked chat, not arbitrary cloud history.
    request = build_request('getUserPersonalChatMessages', {'user_id':42, 'limit':1})
    assert request.__api_method__ == 'getUserPersonalChatMessages'
    try: build_request('messages.getHistory', {'peer':42})
    except InvalidAPIRequest: pass
    else: raise AssertionError('Bot API silently accepted user history RPC')
    assert 'can_read_messages' in BusinessBotRights.model_fields
    assert 'can_edit_name' in BusinessBotRights.model_fields and 'can_change_name' not in BusinessBotRights.model_fields
    connection = BusinessConnection(id='fixture', user=User(id=42,is_bot=False,first_name='Fixture'),
        user_chat_id=42,date=1791072000,is_enabled=False,rights=BusinessBotRights(can_reply=True))
    update = Update(update_id=1,business_connection=connection)
    assert update_kinds(update) == ('business_connection',)
    assert connection.rights is not None and connection.rights.can_reply and not connection.is_enabled
    assert 'guest_message' in Update.model_fields and 'business_message' in Update.model_fields
    print(json.dumps({'passed':True,'network':False,'user_login':False,'sdk':importlib.metadata.version('aiogram'),
        'scenarios':len(data['scenarios']),'absent_update_fields':len(data['ordinary_update_absent_fields']),
        'profile_request_constructed':True,'user_rpc_rejected_by_bot_builder':True,
        'revoked_connection_fixture_has_right_but_is_disabled':True,
        'limits':'Source/model probes, not live permissions or independent blind agent acceptance'}))


if __name__ == '__main__':
    if not __debug__: raise SystemExit('Run the developer probe without Python optimization')
    main()
