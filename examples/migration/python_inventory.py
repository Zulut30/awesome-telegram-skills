"""Inspect explicitly selected public installed symbols, never private module code."""

import dataclasses
import importlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import sys
import typing

spec = json.loads(Path(sys.argv[1]).read_text("utf8"))


def signature(obj):
    try:
        return str(inspect.signature(obj))
    except (ValueError, TypeError):
        return None


def describe(obj):
    if inspect.isclass(obj):
        members = {}
        for name, member in vars(obj).items():
            if name.startswith("_"):
                continue
            target = (
                member.__func__
                if isinstance(member, (classmethod, staticmethod))
                else member
            )
            members[name] = (
                signature(target) if callable(target) else type(member).__name__
            )
        return {
            "kind": "class",
            "init": signature(obj),
            "members": members,
            "fields": [
                (
                    f.name,
                    str(f.type),
                    f.default is dataclasses.MISSING
                    and f.default_factory is dataclasses.MISSING,
                )
                for f in dataclasses.fields(obj)
            ]
            if dataclasses.is_dataclass(obj)
            else None,
            "bases": [base.__name__ for base in obj.__mro__[1:] if base is not object],
        }
    if callable(obj) and typing.get_origin(obj) is None:
        return {"kind": "function", "signature": signature(obj)}
    return {"kind": "type-or-value", "value": str(obj)}


symbols = {}
missing = []
for module_name, names in spec.items():
    module = importlib.import_module(module_name)
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    for name in names:
        key = module_name + "." + name
        if not hasattr(module, name):
            missing.append(key)
        else:
            symbols[key] = describe(getattr(module, name))
print(
    json.dumps(
        {
            "version": importlib.metadata.version("awesome-telegram-patterns"),
            "symbols": symbols,
            "missing": missing,
        },
        sort_keys=True,
    )
)
