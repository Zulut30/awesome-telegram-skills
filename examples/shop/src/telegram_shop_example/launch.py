"""Explicit launch configurations. Parameters select a screen, never an actor or permission."""
from __future__ import annotations

import re
from urllib.parse import urlencode, urlsplit, urlunsplit

from aiogram.methods import SetChatMenuButton
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram_patterns import ValidationFailure


def screen_hint(raw: str | None) -> str:
    if raw is None or raw == '':return 'catalog'
    if not isinstance(raw,str) or len(raw)>64 or raw not in {'catalog','orders'}:raise ValidationFailure('Unknown shop navigation hint')
    return raw


def launch_url(url: str, hint: str = 'catalog') -> str:
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValidationFailure('Configure an HTTPS Mini App URL without credentials, query or fragment')
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode({'tgWebAppStartParam':screen_hint(hint)}),''))


def launch_configuration(url: str, bot_username: str, *, hint: str = 'catalog') -> dict:
    """Build models for owner review; no BotFather change or API request happens here.

    reply-web-app lacks user initData: it opens the public catalog and cannot buy.
    Main Mini App must first be configured by the owner in BotFather. A normal
    inline keyboard web_app is different from a Mini App launched in inline mode.
    """
    if not isinstance(bot_username,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',bot_username):raise ValidationFailure('Configure the real bot username')
    target=launch_url(url,hint)
    web=WebAppInfo(url=target)
    return {
        'menu':SetChatMenuButton(menu_button=MenuButtonWebApp(text='Магазин',web_app=web)),
        'inline':InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Открыть магазин',web_app=web)]]),
        'reply':ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text='Каталог без входа',web_app=web)]],resize_keyboard=True),
        'main_link':f'https://t.me/{bot_username}?'+urlencode({'startapp':screen_hint(hint)}),
        'bot_link':f'https://t.me/{bot_username}?'+urlencode({'start':screen_hint(hint)}),
    }
