"""One-message calendar -> time -> confirmation, backed by file SQLite.

Attach build_calendar_router to the project's Dispatcher. The host supplies its
current ACL, schedule, trusted clock and thread lifecycle; no polling on import.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram_patterns import (BotSettings, CalendarMonth, ConflictFailure, SelectionContext, SelectionMenu,
    SelectionOption, SelectionResult, SelectionSpec, SelectionState, SlotSchedule, SQLiteSlotStore,
    TimeSlot, UnknownOutcome, ValidationFailure, resolve_local_time)
from telegram_patterns.aiogram import calendar_keyboard, run_bot, selection_keyboard, selection_router, time_slot_keyboard


async def database_call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Join the owned SQLite work before releasing the controller on cancellation."""
    task = asyncio.create_task(asyncio.to_thread(partial(function, *args, **kwargs)))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if task.done() and not task.cancelled():
            task.exception()  # Observed; durable operation ID remains for reconciliation.
        raise


@dataclass
class CalendarSession:
    menu: SelectionMenu
    schedule: SlotSchedule
    year: int
    month: int
    selected_date: date | None = None
    receipt: dict[str, Any] | None = None
    error: str | None = None
    request: dict[str, Any] | None = None
    booking_status: str | None = None


def build_calendar_router(store: SQLiteSlotStore, resource: str, *, time_zone: str = 'UTC',
                          clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                          disabled_buttons: bool = False,
                          on_result: Callable[[CallbackQuery, SelectionResult], Awaitable[None]] | None = None
                          ) -> tuple[Router, dict[int, CalendarSession]]:
    """Private-chat example, at most 100 sessions and 60 slots per shown date.

    Registry/selection are ephemeral; booking and receipt survive restart. A
    known message is edited on explicit /book recovery, never auto-resending.
    disabled_buttons=True requires host-verified native support; default uses
    weekday/date fallback. Current user identity always comes from SDK Update.
    """
    zone = timezone.utc if time_zone == 'UTC' else ZoneInfo(time_zone)
    router = Router()
    sessions: dict[int, CalendarSession] = {}

    def month_view(session: CalendarSession) -> CalendarMonth:
        dates = {slot.start.astimezone(zone).date() for slot in session.schedule.slots if slot.enabled}
        return CalendarMonth(session.year, session.month, time_zone,
            [day for day in dates if (day.year, day.month) == (session.year, session.month)])

    def day_slots(session: CalendarSession) -> tuple[TimeSlot, ...]:
        return tuple(slot for slot in session.schedule.slots if slot.start.astimezone(zone).date() == session.selected_date)

    def rules(session: CalendarSession) -> SelectionSpec:
        if session.selected_date is None:
            month = month_view(session)
            options = [SelectionOption('d' + day.isoformat().replace('-', ''), str(day.day), enabled=month.allows(day))
                       for week in month.weeks for day in week if day is not None]
            filters = {'all': 'Даты', 'prev': 'Предыдущий месяц', 'next': 'Следующий месяц'}
        else:
            slots = day_slots(session)
            if len(slots) > 60:
                raise ValidationFailure('This example supports at most 60 slots per date; host must paginate larger schedules')
            options = [SelectionOption(slot.key, slot.label(time_zone), enabled=slot.enabled) for slot in slots]
            options = options or [SelectionOption('unavailable', 'Нет свободного времени', enabled=False)]
            filters = {'all': 'Время', 'dates': 'Другие даты'}
        return SelectionSpec(options, quantity_min=0, quantity_max=0, max_selected=1,
            min_selected=1 if any(option.enabled for option in options) else 0,
            filters=filters, confirm_text='Записаться',
            resource_version=f'{session.schedule.revision}:{session.year:04d}{session.month:02d}:{session.selected_date or "dates"}')

    def render(state: SelectionState) -> tuple[str, InlineKeyboardMarkup]:
        session = sessions[state.context.chat_id]
        if state.phase == 'cancelled':
            return 'Выбор отменен. Запись не создавалась.', InlineKeyboardMarkup(inline_keyboard=[])
        if state.phase == 'confirmed':
            if session.receipt:
                return 'Запись сохранена. Номер: ' + session.receipt['booking_id'] + '\nСтатус: ' + (session.booking_status or 'active') + '\nДля новой записи: /book new', InlineKeyboardMarkup(inline_keyboard=[])
            return session.error or 'Результат записи уточняется. Используйте /book для сверки.', InlineKeyboardMarkup(inline_keyboard=[])
        if state.phase == 'confirming':
            selected = next((slot for slot in day_slots(session) if slot.key in state.selected), None)
            if selected is None:
                return 'Время не выбрано. Вернитесь к датам.', InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='Изменить выбор', callback_data=state.callback('back'))]])
            return f'Запись на {session.selected_date:%d.%m.%Y}\n{selected.label(time_zone)}\nПодтвердить?', selection_keyboard(state)
        if session.selected_date is None:
            month = month_view(session)
            keyboard = calendar_keyboard(month, lambda day: state.callback('s:d' + day.isoformat().replace('-', '')),
                navigation=(state.callback('f:prev'), state.callback('f:next')), disabled_buttons=disabled_buttons)
            keyboard.inline_keyboard.append([InlineKeyboardButton(text='Отмена', callback_data=state.callback('cancel'))])
            return month.text(), keyboard
        keyboard = time_slot_keyboard(day_slots(session), time_zone, lambda slot: state.callback('s:' + slot.key))
        selected = next((slot for slot in day_slots(session) if slot.key in state.selected and slot.enabled), None)
        if selected is not None:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text='Подтвердить: ' + selected.label(time_zone), callback_data=state.callback('ask'))])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text='Другие даты', callback_data=state.callback('f:dates')),
                                        InlineKeyboardButton(text='Отмена', callback_data=state.callback('cancel'))])
        return f'Выберите время: {session.selected_date:%d.%m.%Y} · {time_zone}\nВремя недоступно, если уже занято.', keyboard

    def resolve(query: CallbackQuery) -> SelectionMenu | None:
        session = sessions.get(query.message.chat.id) if isinstance(query.message, Message) else None
        return session.menu if session else None

    async def load(query: CallbackQuery, menu: SelectionMenu) -> SelectionSpec:
        session = sessions[menu.state.context.chat_id]
        session.schedule = await database_call(store.schedule, resource, actor_id=query.from_user.id, now=clock())
        return rules(session)

    async def reserve(session: CalendarSession, actor_id: int) -> None:
        assert session.request is not None
        try:
            result = await database_call(store.reserve, resource, session.request['slot_key'], actor_id=actor_id,
                expected_revision=session.request['revision'], operation_id=session.request['operation_id'], now=clock())
            session.receipt = result.value
        except ConflictFailure:
            session.error = 'Запись не создана: расписание изменилось или время занято. Откройте /book.'

    async def feedback(query: CallbackQuery, result: SelectionResult) -> None:
        session = sessions.get(query.message.chat.id) if isinstance(query.message, Message) else None
        if session is not None and result.state is not None and result.status == 'accepted':
            state = session.menu.state
            if session.selected_date is None and state.filter_key in {'prev', 'next'}:
                offset = session.year * 12 + session.month - 1 + (-1 if state.filter_key == 'prev' else 1)
                year, month = divmod(offset, 12)
                if 1 <= year <= 9999:
                    session.year, session.month = year, month + 1
                session.menu.replace_spec(rules(session))
                session.menu.apply(session.menu.state.callback('f:all'), session.menu.state.context)
            elif session.selected_date is not None and state.filter_key == 'dates':
                session.selected_date = None
                session.menu.replace_spec(rules(session))
            elif session.selected_date is None and state.selected:
                session.selected_date = datetime.strptime(state.selected[0][1:], '%Y%m%d').date()
                session.menu.replace_spec(rules(session))
            elif session.selected_date is not None and state.selected:
                if (query.data or '').endswith(':back'):
                    session.menu.apply(state.callback('s:' + state.selected[0]), state.context)
                else:
                    session.menu.apply(state.callback('ask'), state.context)
        elif session is not None and result.status == 'confirmed' and result.state is not None:
            if session.selected_date is None or len(result.state.selected) != 1 or result.state.operation_id is None:
                session.error = 'Запись не создана: время не выбрано. Откройте /book.'
            else:
                session.request = {'slot_key': result.state.selected[0], 'revision': session.schedule.revision,
                                   'operation_id': result.state.operation_id}
                await reserve(session, query.from_user.id)
        if on_result is not None:
            await on_result(query, result)

    @router.message(Command('book'))
    async def book(message: Message) -> None:
        if message.chat.type != 'private' or message.message_thread_id is not None or message.from_user is None or message.bot is None:
            return
        bot, owner = message.bot, message.from_user.id
        session = sessions.get(message.chat.id)
        if session is not None and (session.menu.state.context.owner_id != owner or session.menu.state.context.bot_id != bot.id):
            return
        if session is not None and session.request is not None and session.receipt is None and session.error is None:
            # Explicit reconciliation of this exact intent; no fresh operation ID.
            await reserve(session, owner)
        elif session is not None and session.receipt is not None and (message.text or '').split(maxsplit=1)[1:] != ['new']:
            current_booking = await database_call(store.booking, resource, session.receipt['booking_id'], actor_id=owner)
            session.booking_status = current_booking.status if current_booking is not None else 'unknown'
        else:
            schedule = await database_call(store.schedule, resource, actor_id=owner, now=clock())
            if session is None:
                if len(sessions) >= 100:
                    await message.answer('Лимит демонстрационных меню достигнут.', parse_mode=None)
                    return
                sent = await message.answer('Открываю календарь…', parse_mode=None)
                if (sent.chat.id != message.chat.id or sent.message_id <= 0 or sent.date.timestamp() <= 0 or
                        sent.from_user is None or sent.from_user.id != bot.id or not sent.from_user.is_bot):
                    raise UnknownOutcome('Initial calendar message was not confirmed')
                context = SelectionContext(bot.id, owner, message.chat.id, sent.message_id)
            else:
                context = session.menu.state.context
            if session is None or session.menu.state.phase in {'confirmed', 'cancelled'} or session.menu.check(session.menu.state.callback('refresh'), context) is not None:
                current = clock().astimezone(zone)
                session = CalendarSession(SelectionMenu(SelectionSpec([SelectionOption('initial', 'Календарь')]), context),
                                          schedule, current.year, current.month)
            else:
                session.schedule = schedule
            session.menu.replace_spec(rules(session))
            sessions[message.chat.id] = session
        state = session.menu.state
        text, markup = render(state)
        edited = await bot.edit_message_text(text, chat_id=state.context.chat_id, message_id=state.context.message_id,
                                            parse_mode=None, reply_markup=markup)
        if (not isinstance(edited, Message) or edited.chat.id != state.context.chat_id or edited.message_id != state.context.message_id or
                edited.date.timestamp() <= 0 or edited.from_user is None or edited.from_user.id != bot.id or not edited.from_user.is_bot):
            raise UnknownOutcome('Calendar display was not confirmed; use the known message on explicit recovery')

    router.include_router(selection_router(resolve, load_spec=load, on_result=feedback, render=render))
    return router, sessions


async def main() -> None:
    # Explicit demo startup: public resource; replace this policy with project ACL.
    store = SQLiteSlotStore(Path('calendar.sqlite3'), authorize=lambda connection, actor, resource: resource == 'consultation')
    await database_call(store.initialize)
    now = datetime.now(timezone.utc)
    try:
        await database_call(store.schedule, 'consultation', actor_id=1, now=now)
    except ConflictFailure:
        day = now.astimezone(ZoneInfo('Europe/Warsaw')).date() + timedelta(days=1)
        start = resolve_local_time(datetime.combine(day, datetime.min.time()).replace(hour=10), 'Europe/Warsaw')
        await database_call(store.publish, 'consultation', [TimeSlot('morning', start, start + timedelta(minutes=30))], expected_revision=0)
    router, _ = build_calendar_router(store, 'consultation', time_zone='Europe/Warsaw')
    dispatcher = Dispatcher(); dispatcher.include_router(router)
    await run_bot(dispatcher, BotSettings.from_env())


if __name__ == '__main__': asyncio.run(main())
