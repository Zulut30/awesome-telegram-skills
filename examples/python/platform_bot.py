"""Host-owned SQLite intents and native platform composition; no live startup."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from telegram_patterns import ConflictFailure, PermissionDenied, safe_error_report
from telegram_patterns.aiogram import (PlatformAction, PlatformHooks, PlatformLookup, PlatformObserver,
    PlatformPermit, PlatformReceipt, PlatformResult, execute_platform_action, platform_events_router)

Policy = Callable[[PlatformAction], Awaitable[PlatformPermit]]
Resolve = Callable[[Message], Awaitable[PlatformAction | None]]
ResultSink = Callable[[PlatformAction, PlatformResult], Awaitable[None]]


class PlatformJournal:
    """Example host storage. ACL/revision/budget are authoritative SQL rows.

    Only the host provisions actors and budgets. Native eligibility, message/gift
    ownership, media and child bindings come from its current policy callback.
    A sending intent recovered after crash is unknown; it is never auto-retried.
    This small synchronous file-SQLite example is not a distributed job queue.
    """
    def __init__(self, connection: sqlite3.Connection, policy: Policy) -> None:
        if connection.in_transaction:
            raise ConflictFailure('Host must finish its transaction before initializing the journal')
        self.connection, self.policy = connection, policy
        connection.executescript('''
          CREATE TABLE IF NOT EXISTS platform_actors (
            bot_id INTEGER, actor_id INTEGER, revision INTEGER, enabled INTEGER,
            PRIMARY KEY(bot_id, actor_id));
          CREATE TABLE IF NOT EXISTS platform_budgets (
            bot_id INTEGER, actor_id INTEGER, remaining INTEGER CHECK(remaining >= 0),
            PRIMARY KEY(bot_id, actor_id));
          CREATE TABLE IF NOT EXISTS platform_intents (
            bot_id INTEGER, operation_id TEXT, actor_id INTEGER, fingerprint TEXT,
            method TEXT, status TEXT, result_id INTEGER,
            PRIMARY KEY(bot_id, operation_id));
        ''')

    def _allowed(self, action: PlatformAction) -> bool:
        row = self.connection.execute('SELECT revision,enabled FROM platform_actors WHERE bot_id=? AND actor_id=?',
            (action.scope.bot_id, action.scope.actor_id)).fetchone()
        return row == (action.scope.revision, 1)

    async def authorize(self, action: PlatformAction) -> PlatformPermit:
        permit = await self.policy(action)
        return replace(permit, allowed=permit.allowed and self._allowed(action))

    async def claim(self, action: PlatformAction, permit: PlatformPermit) -> bool:
        db, scope = self.connection, action.scope
        if db.in_transaction: raise ConflictFailure('Host must end its transaction before claiming an external intent')
        db.execute('BEGIN IMMEDIATE')
        try:
            if not self._allowed(action):
                raise PermissionDenied('Current host ACL/revision changed before claim')
            existing = db.execute('SELECT fingerprint FROM platform_intents WHERE bot_id=? AND operation_id=?',
                (scope.bot_id, scope.operation_id)).fetchone()
            if existing is not None:
                db.rollback()
                return False
            if action.contract.financial:
                cost = permit.star_cost
                if cost is None or permit.max_stars is None or not permit.financial_authorized or cost > permit.max_stars:
                    raise PermissionDenied('No current financial authorization')
                result = db.execute('UPDATE platform_budgets SET remaining=remaining-? WHERE bot_id=? AND actor_id=? AND remaining>=?',
                                    (cost, scope.bot_id, scope.actor_id, cost))
                if result.rowcount != 1: raise PermissionDenied('Atomic host budget is unavailable')
            db.execute('INSERT INTO platform_intents VALUES (?,?,?,?,?,?,NULL)',
                       (scope.bot_id, scope.operation_id, scope.actor_id, action.fingerprint, action.contract.method, 'sending'))
            db.commit()
            return True
        except BaseException:
            db.rollback()
            raise

    async def record(self, action: PlatformAction, receipt: PlatformReceipt) -> None:
        if self.connection.in_transaction:
            raise ConflictFailure('Host must finish its transaction before recording a native receipt')
        if (receipt.operation_id,receipt.fingerprint,receipt.method) != (action.scope.operation_id,action.fingerprint,action.contract.method):
            raise ConflictFailure('Receipt does not match its claimed intent')
        with self.connection:
            result = self.connection.execute('UPDATE platform_intents SET status=?,result_id=? WHERE bot_id=? AND operation_id=? AND fingerprint=? AND status=?',
                (receipt.outcome,receipt.result_id,action.scope.bot_id,action.scope.operation_id,action.fingerprint,'sending'))
            if result.rowcount != 1: raise ConflictFailure('Receipt requires the original sending intent')


def platform_router(resolve: Resolve, hooks: PlatformHooks, lookup: PlatformLookup, observe: PlatformObserver,
                    on_result: ResultSink) -> Router:
    """Mount into the current Dispatcher; host resolves configured targets and consent."""
    router = Router(name='platform-composition')
    commands = Router(name='platform-commands')
    commands.message.filter(F.chat.type == 'private', F.from_user.is_bot == False)

    @commands.message(Command('topic','reaction','join','business','story','gift','managed'))
    async def handle(message: Message) -> None:
        if message.from_user is None or message.bot is None: return
        action = await resolve(message)
        if action is None: return
        try:
            if (action.scope.bot_id,action.scope.actor_id) != (message.bot.id,message.from_user.id):
                raise PermissionDenied('Command actor does not match the host operation')
            result = await execute_platform_action(message.bot,action,hooks)
            # The host stores returned secrets explicitly; results never become
            # command replies. A vault integration belongs to the application.
            await on_result(action,result)
            await message.answer('Действие подтверждено.' if result.receipt.outcome=='succeeded' else 'Проверьте состояние действия.',parse_mode=None)
        except Exception as error:
            await message.answer(safe_error_report(error,operation='write').message,parse_mode=None)

    router.include_router(commands)
    router.include_router(platform_events_router(lookup,observe))
    return router
