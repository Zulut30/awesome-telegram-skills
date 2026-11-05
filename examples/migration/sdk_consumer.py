"""The same legacy public composition runs unchanged on both installed aiogram adapters."""

import asyncio, json, sys
from pathlib import Path
import importlib.metadata
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import (
    SendMessage,
    AnswerCallbackQuery,
    EditMessageText,
    EditMessageReplyMarkup,
    GetMe,
    SetMyCommands,
)
from aiogram.types import Update
from telegram_patterns import BotSettings, Recipe, RecipeCatalog, StarterPlan
from telegram_patterns.aiogram import (
    Action,
    ActionResult,
    ActionButton,
    CommandReply,
    command_menu,
    command_router,
    start_router,
    callback_router,
    action_menu,
    paginated_menu,
    page_number,
    TextField,
    FormSubmission,
    text_form_router,
    stars_invoice,
    UpdateTrace,
    InvalidField,
    run_bot,
)
from telegram_patterns.testing import StubSession
import telegram_patterns

assert (
    Path(telegram_patterns.__file__)
    .resolve()
    .is_relative_to(Path(sys.prefix).resolve())
)

mode, out_name = sys.argv[1:]
out = Path(out_name)
TOKEN = "100:MIGRATION_SYNTHETIC_ONLY"


def response(method):
    return {
        "message_id": 200,
        "date": 1000,
        "chat": {"id": 42, "type": "private"},
        "text": method.text,
    }


async def run():
    session = (
        StubSession()
        .respond(SendMessage, response)
        .respond(AnswerCallbackQuery, True)
        .respond(EditMessageText, True)
        .respond(EditMessageReplyMarkup, True)
    )
    bot = Bot(TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    commands = [CommandReply("help", "Help", "Literal <help>")]
    assert command_menu(commands)[0].command == "help"
    markup = action_menu(
        [ActionButton("One", "one"), ActionButton("Two", "two")], columns=2
    )
    assert len(markup.inline_keyboard[0]) == 2
    page = paginated_menu(
        [ActionButton(str(i), str(i)) for i in range(5)], page=1, page_size=2, columns=2
    )
    assert page.page == 1 and page_number("page:1") == 1
    invoice = stars_invoice("Title", "Description", "server-payload", 1)
    assert invoice.currency == "XTR" and invoice.prices[0].amount == 1
    assert isinstance(InvalidField("Fix value"), ValueError)
    trace = UpdateTrace(1, "message", "received")
    assert trace.update_id == 1
    # Old positional dataclass calls are still accepted; new fields have defaults.
    record = Recipe(
        "fixture",
        "Title",
        "Summary",
        "example",
        "python",
        (),
        "pass",
        "mock",
        "offline",
        ("https://example.test",),
    )
    assert record.id == "fixture"
    assert (
        StarterPlan(Path("never-created"), "bot", "0.5.0", (), False).created is False
    )
    assert RecipeCatalog().get("two-columns").id == "two-columns"
    actions = []
    submissions = []

    async def execute(action: Action):
        actions.append(action.key)
        return ActionResult("accepted", "Done")

    async def notify(query, result):
        pass

    async def submit(value: FormSubmission):
        assert (
            value.actor_id == 42
            and value.bot_id == 100
            and value.values["name"] == "Tester"
        )
        submissions.append(value.operation_id)
        return "Submitted"

    dp.include_router(start_router("Literal <start>", markup))
    dp.include_router(command_router(commands))
    dp.include_router(callback_router(execute, notify))
    dp.include_router(
        text_form_router(
            [TextField("name", "Name", "Enter name")],
            submit,
            name="legacy",
            command="apply",
        )
    )

    def update(n, text=None, data=None, user=42):
        msg = {
            "message_id": n if data is None else 200,
            "date": 1000,
            "chat": {"id": user if data is None else 42, "type": "private"},
            "from": {"id": user, "is_bot": False, "first_name": "Fixture"},
            "text": text or "Review",
        }
        value = (
            {"update_id": n, "message": msg}
            if data is None
            else {
                "update_id": n,
                "callback_query": {
                    "id": str(n),
                    "from": msg["from"],
                    "chat_instance": "fixture",
                    "message": msg,
                    "data": data,
                },
            }
        )
        return Update.model_validate(value, context={"bot": bot})

    try:
        await dp.feed_update(bot, update(1, "/start"))
        await dp.feed_update(bot, update(2, "/help"))
        await dp.feed_update(bot, update(3, data="act:one"))
        assert actions == ["one"]
        await dp.feed_update(bot, update(4, "/apply"))
        await dp.feed_update(bot, update(5, "Tester"))
        review = next(
            call
            for call in reversed(session.calls)
            if isinstance(call, SendMessage) and call.reply_markup is not None
        )
        submit_data = next(
            button.callback_data
            for row in review.reply_markup.inline_keyboard
            for button in row
            if button.callback_data.endswith(":submit")
        )
        await dp.feed_update(bot, update(6, data=submit_data, user=99))
        assert not submissions
        await dp.feed_update(bot, update(7, data=submit_data))
        assert len(submissions) == 1
        await dp.feed_update(bot, update(8, data=submit_data))
        assert len(submissions) == 1
    finally:
        await dp.storage.close()
        await dp.fsm.events_isolation.close()
        await bot.session.close()
    assert session.closed

    class HostDispatcher(Dispatcher):
        async def start_polling(self, *bots, **kwargs):
            self.called = True

    dispatcher = HostDispatcher()
    dispatcher.called = False
    transport = (
        StubSession()
        .respond(
            GetMe,
            {
                "id": 100,
                "is_bot": True,
                "first_name": "Fixture",
                "username": "fixture_bot",
            },
        )
        .respond(SetMyCommands, True)
    )
    await run_bot(
        dispatcher,
        BotSettings.from_env(environ={"BOT_TOKEN": TOKEN}),
        commands=command_menu(commands),
        session=transport,
        handle_signals=False,
    )
    names = [type(call).__name__ for call in transport.calls]
    assert names == (
        ["SetMyCommands"] if mode == "before" else ["GetMe", "SetMyCommands"]
    )
    assert dispatcher.called and transport.closed
    await dispatcher.storage.close()
    result = {
        "passed": True,
        "mode": mode,
        "version": importlib.metadata.version("awesome-telegram-patterns"),
        "aiogram": importlib.metadata.version("aiogram"),
        "legacy_composition": [
            "commands",
            "markup",
            "pagination",
            "callback",
            "FSM-review-submit",
            "foreign-actor",
            "duplicate-submit",
            "invoice-builder",
            "exceptions",
            "dataclass-defaults",
            "resource-cleanup",
        ],
        "runner_calls": names,
        "preflight_probe_scope": "Public host Dispatcher subclass skips polling to isolate library preflight order; no live token/API validation claim.",
        "scope": "Real installed SDK objects and synthetic transport only; no external requests.",
    }
    (out / ("sdk-" + mode + ".json")).write_text(
        json.dumps(result, indent=2) + "\n", "utf8"
    )
    print(json.dumps(result))


asyncio.run(run())
