"""Persist old public FSM snapshots, then retain unknown identity on the new adapter."""

import asyncio, json, sys, importlib.metadata
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import SendMessage, AnswerCallbackQuery
from aiogram.types import Update
from telegram_patterns.aiogram import TextField, text_form_router
from telegram_patterns.testing import StubSession
import telegram_patterns

assert (
    Path(telegram_patterns.__file__)
    .resolve()
    .is_relative_to(Path(sys.prefix).resolve())
)

mode, output = sys.argv[1:]
out = Path(output)
source = out / "legacy-fsm.json"
TOKEN = "100:MIGRATION_SYNTHETIC_ONLY"


def event(number, text=None, callback=None, actor=42):
    user = {"id": actor, "is_bot": False, "first_name": "Fixture"}
    message = {
        "message_id": number if callback is None else 200,
        "date": 1000,
        "chat": {"id": 42, "type": "private"},
        "from": user,
        "text": text or "Review",
    }
    value = (
        {"update_id": number, "message": message}
        if callback is None
        else {
            "update_id": number,
            "callback_query": {
                "id": str(number),
                "from": user,
                "message": message,
                "chat_instance": "fixture",
                "data": callback,
            },
        }
    )
    return Update.model_validate(value)


async def probe(*, schema=None, legacy=None):
    session = (
        StubSession()
        .respond(
            SendMessage,
            lambda method: {
                "message_id": 200,
                "date": 1000,
                "chat": {"id": 42, "type": "private"},
                "text": method.text,
            },
        )
        .respond(AnswerCallbackQuery, True)
    )
    bot = Bot(TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    attempts = []

    async def submit(value):
        attempts.append(value.operation_id)
        if mode == "before":
            raise RuntimeError("Synthetic unknown outcome")
        assert value.operation_id == legacy["operation_id"]
        return "Existing operation reconciled locally; no new financial/send effect"

    options = {} if schema is None else {"schema_version": schema}
    dp.include_router(
        text_form_router(
            [TextField("name", "Name", "Enter name")],
            submit,
            name="preserved",
            **options,
        )
    )
    context = dp.fsm.get_context(bot=bot, chat_id=42, user_id=42)
    try:
        if legacy is not None:
            await context.set_state(legacy["state"])
            await context.set_data(legacy["data"])
        if mode == "before":
            await dp.feed_update(bot, event(1, "/apply"))
            await dp.feed_update(bot, event(2, "Tester"))
            review = next(
                call
                for call in reversed(session.calls)
                if isinstance(call, SendMessage) and call.reply_markup
            )
            callback = review.reply_markup.inline_keyboard[0][0].callback_data
            try:
                await dp.feed_update(bot, event(3, callback=callback))
            except RuntimeError as error:
                assert str(error) == "Synthetic unknown outcome"
            else:
                raise AssertionError("Unknown fixture did not occur")
            assert len(attempts) == 1
            saved = {
                "state": await context.get_state(),
                "data": await context.get_data(),
                "callback": callback,
                "operation_id": attempts[0],
            }
            source.write_text(json.dumps(saved, indent=2) + "\n", "utf8")
            assert saved["state"] and saved["operation_id"] in json.dumps(saved["data"])
            return {"unknown_old_identity_persisted": True, "operation_id": attempts[0]}
        initial = json.dumps(await context.get_data(), sort_keys=True)
        if schema == 2:
            try:
                await dp.feed_update(bot, event(4, "/apply"))
            except RuntimeError:
                pass
            else:
                raise AssertionError("Old schema accepted under explicit new schema")
            assert (
                not attempts
                and json.dumps(await context.get_data(), sort_keys=True) == initial
            )
            return {"explicit_schema_change_refused_without_identity_loss": True}
        await dp.feed_update(bot, event(4, "/apply"))
        await dp.feed_update(bot, event(5, "/cancel"))
        assert (
            not attempts
            and json.dumps(await context.get_data(), sort_keys=True) == initial
        )
        await dp.feed_update(bot, event(6, callback=legacy["callback"], actor=99))
        assert not attempts
        assert json.dumps(await context.get_data(), sort_keys=True) == initial
        await dp.feed_update(bot, event(7, callback=legacy["callback"]))
        assert (
            attempts == [legacy["operation_id"]] and await context.get_state() is None
        )
        await dp.feed_update(bot, event(8, callback=legacy["callback"]))
        assert len(attempts) == 1
        return {
            "default_schema_legacy_resume": True,
            "unknown_cannot_cancel_or_restart": True,
            "foreign_actor_denied": True,
            "original_id_reconciled_once": True,
        }
    finally:
        await dp.storage.close()
        await dp.fsm.events_isolation.close()
        await bot.session.close()


async def main():
    if mode == "before":
        result = await probe()
    else:
        original = source.read_bytes()
        legacy = json.loads(original)
        result = await probe(legacy=legacy)
        result.update(await probe(schema=2, legacy=legacy))
        assert source.read_bytes() == original
    report = {
        "passed": True,
        "mode": mode,
        "version": importlib.metadata.version("awesome-telegram-patterns"),
        "observations": result,
        "scope": "Old adapter created its own unknown submission. Snapshot moved only through host public FSM state/data API; no financial status inference or live calls.",
    }
    (out / ("fsm-" + mode + ".json")).write_text(
        json.dumps(report, indent=2) + "\n", "utf8"
    )
    print(json.dumps(report))


asyncio.run(main())
