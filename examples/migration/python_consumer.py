"""Public-only migration consumer; transport-free and deliberately stores no real credential."""

from pathlib import Path
from contextlib import closing
import hashlib
import hmac
import importlib.metadata as metadata
import importlib.util
import json
import sqlite3
import sys
from urllib.parse import urlencode

from telegram_patterns import (
    SQLiteOnce,
    OperationConflict,
    BotSettings,
    RecipeCatalog,
    validate_init_data,
    create_starter,
)
from telegram_patterns.cli import doctor

mode, root_name, wheel_name = sys.argv[1:]
root = Path(root_name)
root.mkdir(exist_ok=True)
wheel = Path(wheel_name)
version = metadata.version("awesome-telegram-patterns")
assert importlib.util.find_spec("aiogram") is None
import telegram_patterns

assert (
    Path(telegram_patterns.__file__)
    .resolve()
    .is_relative_to(Path(sys.prefix).resolve())
)
database = root / "business.sqlite"
backup_sha = None
if mode == "after":
    # Read-only source and a real SQLite backup precede any new-library access.
    backup_path = root / "pre-migration-backup.sqlite"
    if backup_path.exists():
        raise FileExistsError("Use a new owned output; keep the prior backup")
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as source:
        source.execute("PRAGMA query_only=ON")
        with closing(sqlite3.connect(backup_path)) as backup:
            source.backup(backup)
            assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert backup.execute(
                "SELECT status FROM legacy_financial_state ORDER BY id"
            ).fetchall() == [("legacy-unbound",), ("unknown",)]
        assert source.execute("SELECT count FROM business").fetchone()[0] == 1
    backup_sha = hashlib.sha256(backup_path.read_bytes()).hexdigest()
store = SQLiteOnce(database)
store.initialize()
canonical = {
    "service": "server-owned",
    "tags": ["one", "two"],
    "label": "\u0417\u0430\u043a\u0430\u0437 \U0001f600",
}
legacy_tuple = canonical | {"tags": ("one", "two")}
scope, key = "merchant:100:user:42", "original-order-operation"
with closing(sqlite3.connect(database)) as db, db:
    db.execute(
        "CREATE TABLE IF NOT EXISTS business(id TEXT PRIMARY KEY, count INTEGER NOT NULL)"
    )
    db.execute("INSERT OR IGNORE INTO business VALUES ('order',0)")
    if mode == "before":
        db.execute(
            "CREATE TABLE legacy_financial_state(id TEXT PRIMARY KEY,operation_id TEXT NOT NULL,status TEXT NOT NULL)"
        )


def effect(connection):
    connection.execute("UPDATE business SET count=count+1 WHERE id='order'")
    return {"receipt": "local-business-effect", "quantity": 1}


def never(_):
    raise AssertionError("A saved operation must not execute again")


observations = []
if mode == "before":
    first = store.run(scope, key, canonical, effect)
    assert not first.replayed
    assert store.run(scope, key, canonical, never).replayed
    assert not store.run(
        scope, "tuple-operation", legacy_tuple, lambda _: {"receipt": "tuple-completed"}
    ).replayed
    # This ambiguous historical input has no automatic migration path.
    assert not store.run(
        scope,
        "int-key-operation",
        {1: "one"},
        lambda _: {"receipt": "int-key-completed"},
    ).replayed

    # Host-owned legacy state uses the old public transaction boundary.
    # A completed local transaction is NOT evidence of payment success.
    def legacy_finance(connection):
        connection.executemany(
            "INSERT INTO legacy_financial_state VALUES (?,?,?)",
            [
                ("unknown-order", "original-unknown-operation", "unknown"),
                ("unbound-order", "original-unbound-operation", "legacy-unbound"),
            ],
        )
        return {"local_fixture_saved": True, "payment_verified": False}

    assert not store.run(
        scope, "legacy-financial-fixture", {"fixture": "host-owned"}, legacy_finance
    ).replayed
    observations += ["original-effect-once", "tuple-and-int-key-historically-accepted"]
else:
    assert store.run(scope, key, canonical, never).replayed
    try:
        store.run(scope, "tuple-operation", legacy_tuple, never)
    except ValueError:
        pass
    else:
        raise AssertionError("New payload validation did not reject a tuple")
    # A server-approved array mapping retains exactly the known completed operation.
    assert store.run(scope, "tuple-operation", canonical, never).replayed
    try:
        store.run(scope, "int-key-operation", {1: "one"}, never)
    except ValueError:
        pass
    else:
        raise AssertionError("Ambiguous old keys were silently normalized")
    from telegram_patterns import PermissionDenied

    try:
        store.run_guarded(
            scope, key, canonical, never, check=lambda connection, replayed: False
        )
    except PermissionDenied:
        pass
    else:
        raise AssertionError("A saved replay bypassed current authorization")
    checked = []
    assert store.run_guarded(
        scope,
        key,
        canonical,
        never,
        check=lambda connection, replayed: checked.append(replayed) or True,
    ).replayed
    assert checked == [True]
    assert store.run(
        scope, "legacy-financial-fixture", {"fixture": "host-owned"}, never
    ).replayed
    observations += [
        "completed-replay-preserved",
        "explicit-tuple-array-mapping-keeps-key",
        "ambiguous-legacy-key-refused",
        "current-acl-on-saved-replay",
    ]
try:
    store.run(scope, key, canonical | {"service": "different"}, never)
except OperationConflict:
    pass
else:
    raise AssertionError("Changed payload reused the original operation")
with closing(sqlite3.connect(database)) as db:
    assert db.execute("SELECT count FROM business WHERE id='order'").fetchone()[0] == 1
    rows = db.execute(
        "SELECT * FROM telegram_pattern_operations ORDER BY operation_key"
    ).fetchall()
    columns = db.execute("PRAGMA table_info(telegram_pattern_operations)").fetchall()
    business = db.execute("SELECT * FROM business").fetchall()
    financial = db.execute(
        "SELECT * FROM legacy_financial_state ORDER BY id"
    ).fetchall()
    assert financial == sorted(
        [
            ("unknown-order", "original-unknown-operation", "unknown"),
            ("unbound-order", "original-unbound-operation", "legacy-unbound"),
        ]
    )
data = json.loads(
    json.dumps(
        {
            "rows": rows,
            "columns": columns,
            "business": business,
            "legacy_financial": financial,
        }
    )
)
state_file = root / "before-state.json"
if mode == "before":
    state_file.write_text(json.dumps(data, ensure_ascii=False), "utf8")
else:
    assert data == json.loads(state_file.read_text("utf8"))

# Signed synthetic user contains nested extension data to exercise recursive immutability.
token = "100:MIGRATION_SYNTHETIC_ONLY"
fields = {
    "auth_date": "1000",
    "user": json.dumps(
        {"id": 42, "first_name": "Fixture", "profile": {"tags": ["legacy"]}},
        separators=(",", ":"),
    ),
    "start_param": "catalog",
}
check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
launch = validate_init_data(urlencode(fields), token, now=1001)
assert launch.user_id == 42
if mode == "before":
    copied = json.loads(json.dumps(dict(launch.user)))
    launch.user["profile"]["tags"].append("old-mutation")
    assert copied["profile"]["tags"] == ["legacy"]
    observations.append("old-shallow-freeze-only")
else:
    try:
        launch.user["profile"]["tags"].append("mutate")
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("Signed nested state was mutable")
    try:
        json.dumps(dict(launch.user))
    except TypeError:
        pass
    else:
        raise AssertionError(
            "Legacy shallow serializer unexpectedly handled deep readonly data"
        )
    copied = launch.as_dict()
    copied["user"]["profile"]["tags"].append("local-copy")
    assert tuple(launch.user["profile"]["tags"]) == ("legacy",)
    observations.append("as-dict-detached-copy-for-recursive-readonly")
try:
    validate_init_data(urlencode(fields), token, now=100000)
except ValueError:
    pass
else:
    raise AssertionError("Expired launch was accepted")
for invalid in [
    urlencode(fields) + "&hash=duplicate",
    urlencode(fields).replace("catalog", "tampered"),
]:
    try:
        validate_init_data(invalid, token, now=1001)
    except ValueError:
        pass
    else:
        raise AssertionError("Forged or duplicate signed fields were accepted")

try:
    BotSettings("")
except ValueError:
    observations.append("invalid-direct-settings-rejected-on-both-versions")
else:
    raise AssertionError("Invalid direct settings were accepted")
try:
    BotSettings.from_env(environ={"BOT_TOKEN": "100:REPLACE_WITH_TOKEN"})
except ValueError:
    assert mode == "after"
    observations.append("placeholder-config-now-rejected")
else:
    assert mode == "before"
    observations.append("placeholder-config-historically-accepted")
assert "MIGRATION_SYNTHETIC_ONLY" not in repr(
    BotSettings.from_env(environ={"BOT_TOKEN": token})
)
diagnostic = doctor(root)
assert diagnostic["network"] is False
assert (
    all("detail" in c for c in diagnostic["checks"])
    if mode == "before"
    else all("reason" in c and "remediation" in c for c in diagnostic["checks"])
)
assert token not in json.dumps(diagnostic)
observations.append(
    "doctor-schema-" + ("detail" if mode == "before" else "reason-remediation")
)

target = root / ("starter-" + mode)
try:
    plan = create_starter(target, library=wheel)
except FileNotFoundError:
    assert mode == "before" and not target.exists()
    observations.append("frozen-0.5-starter-missing-env-resource-before-target-create")
else:
    assert mode != "before", (
        "Baseline packaging gap unexpectedly disappeared; inspect before claims"
    )
    assert plan.created and (target / ".env.example").is_file()
    marker = target / "caller.txt"
    marker.write_bytes(b"keep existing project\n")
    try:
        create_starter(target, library=wheel)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Starter adopted an existing project")
    assert marker.read_bytes() == b"keep existing project\n"
    observations.append("new-starter-complete-and-existing-target-refused")
result = {
    "passed": True,
    "version": version,
    "mode": mode,
    "sdk_free": True,
    "origin": str(telegram_patterns.__file__),
    "prefix": sys.prefix,
    "observations": observations,
    "recipe_count": len(RecipeCatalog().recipes),
    "sqlite_rows_sha256": hashlib.sha256(
        json.dumps(data, sort_keys=True).encode()
    ).hexdigest(),
    "source_database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
    "pre_migration_backup_sha256": backup_sha,
    "legacy_financial_policy": "Host-owned unknown/unbound rows remain quarantined with original IDs; read-only snapshot and backup precede new-library access; no paid or new send transition.",
    "scope": "Real file SQLite and supplied installed wheel; no Telegram, registry publication, live payment or 1.0 RC proof.",
}
(root / ("python-" + mode + ".json")).write_text(
    json.dumps(result, indent=2) + "\n", "utf8"
)
print(json.dumps(result))
