"""Executable keyboard cookbook. Use only a test bot; /start installs its menu."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (BotCommand, CallbackQuery, CopyTextButton, DisabledButton, InlineKeyboardButton,
                           KeyboardButton, KeyboardButtonPollType, KeyboardButtonRequestChat,
                           KeyboardButtonRequestUsers, Message)
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import (UpdateObserver, UpdateTrace, inline_keyboard, input_prompt,
                                      reply_keyboard, remove_keyboard, run_bot)


def two_in_row():
    return inline_keyboard([[InlineKeyboardButton(text=f"Кнопка {n}", callback_data=f"demo:pick:{n}")
                             for n in (1, 2)],
                            [InlineKeyboardButton(text=f"Кнопка {n}", callback_data=f"demo:pick:{n}")
                             for n in (3, 4)]])


def three_in_row():
    return inline_keyboard([[InlineKeyboardButton(text=f"Кнопка {n}", callback_data=f"demo:pick:{n}")
                             for n in (1, 2, 3)],
                            [InlineKeyboardButton(text=f"Кнопка {n}", callback_data=f"demo:pick:{n}")
                             for n in (4, 5, 6)]])


def colored_buttons():
    return inline_keyboard([[
        InlineKeyboardButton(text="Основная", callback_data="demo:pick:primary", style="primary"),
        InlineKeyboardButton(text="Готово", callback_data="demo:pick:success", style="success"),
        InlineKeyboardButton(text="Отмена", callback_data="demo:pick:danger", style="danger"),
    ]])


def mixed_rows():
    buttons = [InlineKeyboardButton(text=f"Кнопка {n}", callback_data=f"demo:pick:{n}") for n in range(1, 7)]
    return inline_keyboard([buttons[:1], buttons[1:3], buttons[3:]])


def presentation(name: str, *, navigation: bool = True):
    markup = {"two": two_in_row, "three": three_in_row, "mixed": mixed_rows, "colors": colored_buttons}[name]()
    if not navigation:
        return markup
    return inline_keyboard([*markup.inline_keyboard, [
        InlineKeyboardButton(text="По 2", callback_data="demo:layout:two"),
        InlineKeyboardButton(text="По 3", callback_data="demo:layout:three"),
        InlineKeyboardButton(text="Цвета", callback_data="demo:layout:colors"),
    ]])


COMMANDS = [BotCommand(command=name, description=description) for name, description in (
    ("start", "Все примеры"), ("two", "Две кнопки в ряд"), ("three", "Три кнопки в ряд"),
    ("mixed", "Разные размеры строк"), ("colors", "Цветные кнопки"),
    ("reply", "Клавиатура под вводом"), ("requests", "Контакт, геопозиция, poll, users/chat"),
    ("actions", "Ссылка, копирование и выключенная кнопка"),
    ("input", "Подсказка и ответ на сообщение"), ("hide", "Убрать reply клавиатуру"),
)]


def create_app(record: Callable[[UpdateTrace], Awaitable[None]] | None = None) -> tuple[Dispatcher, list[BotCommand]]:
    """In-memory demo state resets on restart; no private business effect or account automation."""
    dispatcher, router = Dispatcher(), Router()
    menus: dict[tuple[int, int], tuple[int, str]] = {}
    edit_lock = asyncio.Lock()  # Demo-only: serialize edits in this single process.
    prompts: dict[tuple[int, int], int] = {}
    requests: set[tuple[int, int]] = set()
    if record is not None:
        dispatcher.update.outer_middleware(UpdateObserver(record))

    @router.message(Command("start"))
    async def start(message: Message):
        await message.answer("Примеры: /two /three /mixed /colors /reply /requests /actions /input /hide. "
                             "Кнопки меню обновляют это же сообщение. Ссылка, copy и disabled не дают callback.", parse_mode=None)

    @router.message(Command("two", "three", "mixed", "colors"))
    async def menu(message: Message):
        if message.from_user is None: return
        if message.business_connection_id:
            await message.answer("Этот пример предназначен для обычного чата с ботом.", parse_mode=None)
            return
        name = message.text.split()[0].split('@')[0][1:]
        result = await message.answer("Выберите кнопку. Нижняя строка переключает раскладку этого меню.", reply_markup=presentation(name), parse_mode=None)
        menus[(result.chat.id, result.message_id)] = (message.from_user.id, name)

    @router.callback_query(F.data.startswith("demo:"))
    async def clicked(query: CallbackQuery):
        if not isinstance(query.message, Message):
            await query.answer("Откройте новое меню.")
            return
        key = (query.message.chat.id, query.message.message_id)
        owner = menus.get(key)
        if owner is None or owner[0] != query.from_user.id:
            await query.answer("Откройте свое меню командой /two.")
            return
        data = query.data or ""
        if data.startswith("demo:pick:"):
            await query.answer("Выбрано: " + data.removeprefix("demo:pick:")[:16])
            return
        target = data.removeprefix("demo:layout:")
        if target not in {"two", "three", "colors"}:
            await query.answer("Неизвестная кнопка.")
            return
        await query.answer()  # Before editing; duplicate current layout is a no-op.
        async with edit_lock:
            current = menus.get(key)
            if current is not None and current[0] == query.from_user.id and current[1] != target:
                await query.message.edit_reply_markup(reply_markup=presentation(target))
                menus[key] = (current[0], target)

    @router.message(Command("reply", "requests", "input", "hide"))
    async def input_controls(message: Message):
        if message.from_user is None: return
        if message.chat.type != "private" or message.business_connection_id:
            await message.answer("Для примеров ввода откройте личный чат с ботом.", parse_mode=None)
            return
        name = message.text.split()[0].split('@')[0][1:]
        key = (message.chat.id, message.from_user.id)
        if name == "reply":
            await message.answer("Reply кнопка отправляет текст сообщения.", parse_mode=None,
                reply_markup=reply_keyboard([["Каталог", "Помощь"], ["Закрыть клавиатуру"]], placeholder="Выберите действие"))
        elif name == "hide":
            prompts.pop(key, None)
            requests.discard(key)
            await message.answer("Клавиатура скрыта, ожидание ввода отменено.", reply_markup=remove_keyboard(), parse_mode=None)
        elif name == "input":
            prompt = await message.answer("Ответьте на это сообщение: как вас называть?", parse_mode=None,
                                          reply_markup=input_prompt("Ваше имя"))
            prompts[key] = prompt.message_id
        else:
            requests.add(key)
            await message.answer("Данные добровольно отправляются после вашего действия. Выбор users/chat не дает боту доступ к их истории.", parse_mode=None,
                reply_markup=reply_keyboard([
                    [KeyboardButton(text="Мой контакт", request_contact=True), KeyboardButton(text="Геопозиция", request_location=True)],
                    [KeyboardButton(text="Опрос", request_poll=KeyboardButtonPollType(type="regular"))],
                    [KeyboardButton(text="Выбрать пользователей", request_users=KeyboardButtonRequestUsers(request_id=1, max_quantity=3)),
                     KeyboardButton(text="Выбрать группу", request_chat=KeyboardButtonRequestChat(request_id=2, chat_is_channel=False))],
                    ["Закрыть клавиатуру"],
                ], one_time=True, placeholder="Выберите пример запроса"))

    @router.message(Command("actions"))
    async def actions(message: Message):
        await message.answer("Эти кнопки не вызывают наш callback handler.", parse_mode=None,
            reply_markup=inline_keyboard([
                [InlineKeyboardButton(text="Документация", url="https://core.telegram.org/bots/api"),
                 InlineKeyboardButton(text="Скопировать пример", copy_text=CopyTextButton(text="telegram-patterns-demo"))],
                [InlineKeyboardButton(text="Недоступно", disabled=DisabledButton())],
            ], chat_type=message.chat.type, business=bool(message.business_connection_id)))

    @router.message(F.contact | F.location | F.users_shared | F.chat_shared | F.poll)
    async def shared_data(message: Message):
        if message.from_user is None: return
        key = (message.chat.id, message.from_user.id)
        if key not in requests: return
        if message.contact and message.contact.user_id != message.from_user.id:
            await message.answer("Это не ваш контакт; данные не приняты.", parse_mode=None)
            return
        if message.users_shared and message.users_shared.request_id != 1: return
        if message.chat_shared and message.chat_shared.request_id != 2: return
        kind = next(name for name in ("contact", "location", "users_shared", "chat_shared", "poll") if getattr(message, name))
        # No contact/location storage or logging. Sharing is not authorization.
        await message.answer("Получено событие: " + kind, parse_mode=None)

    @router.message(F.text.in_({"Каталог", "Помощь", "Закрыть клавиатуру"}))
    async def reply_action(message: Message):
        if message.chat.type != "private" or message.business_connection_id: return
        if message.text == "Закрыть клавиатуру":
            if message.from_user:
                key = (message.chat.id, message.from_user.id)
                prompts.pop(key, None); requests.discard(key)
            await message.answer("Клавиатура скрыта.", reply_markup=remove_keyboard(), parse_mode=None)
        else:
            # Plain text is never proof of an actual button click.
            await message.answer("Текстовое действие: " + message.text, parse_mode=None)

    @router.message(F.text)
    async def text_input(message: Message):
        if message.from_user is None or message.chat.type != "private" or message.business_connection_id: return
        key = (message.chat.id, message.from_user.id)
        expected = prompts.get(key)
        if expected is None or message.reply_to_message is None or message.reply_to_message.message_id != expected: return
        if not 1 <= len(message.text.strip()) <= 80 or message.text.startswith('/'):
            await message.answer("Нужно имя длиной 1–80 символов. Ответьте на тот же вопрос; /hide отменяет ввод.", parse_mode=None)
            return
        prompts.pop(key, None)
        await message.answer("Ответ принят; в этом примере имя не сохраняется.", reply_markup=remove_keyboard(), parse_mode=None)

    dispatcher.include_router(router)
    return dispatcher, list(COMMANDS)


async def main():
    try: settings = BotSettings.from_env()
    except ValueError as error: raise SystemExit(str(error)) from None
    dispatcher, commands = create_app()
    await run_bot(dispatcher, settings, commands=commands)


if __name__ == "__main__": asyncio.run(main())
