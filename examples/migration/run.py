"""Run public before/after consumers against four explicitly supplied local artifacts.

Python 3.11+, Node and npm are required. SDK/type witnesses are optional tooling;
they never become dependencies of the SDK-free core consumer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent


def dump(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def executable(value: str | None, default: str) -> str:
    found = shutil.which(value or default)
    if found is None:
        raise ValueError(f"Required executable not found: {value or default}")
    return str(Path(found).resolve())


def environment() -> dict[str, str]:
    result = dict(
        os.environ,
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    for name in [
        "BOT_TOKEN",
        "TELEGRAM_TEST_ENVIRONMENT",
        "PYTHONPATH",
        "PYTHONHOME",
        "NODE_OPTIONS",
    ]:
        result.pop(name, None)
    return result


def venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


class Run:
    def __init__(self, output: Path, env: dict[str, str]) -> None:
        self.output, self.env = output, env
        self.stages: list[dict] = []

    def call(
        self, name: str, command: list, *, cwd: Path | None = None, expected: int = 0
    ) -> str:
        command = list(map(str, command))
        done = subprocess.run(
            command,
            cwd=cwd or self.output,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        log = name + ".log"
        (self.output / log).write_text(done.stdout + done.stderr, encoding="utf-8")
        self.stages.append(
            {
                "stage": name,
                "command": command,
                "cwd": str(cwd or self.output),
                "expected_exit": expected,
                "exit_code": done.returncode,
                "log": log,
            }
        )
        dump(self.output / "stages.json", self.stages)
        print(name, done.returncode, flush=True)
        if done.returncode != expected:
            raise RuntimeError(
                f"{name}: expected exit {expected}, got {done.returncode}; see {log}"
            )
        if (
            expected
            and "error TS" not in done.stdout + done.stderr
            and name.startswith("types-")
        ):
            raise RuntimeError(
                f"{name}: expected a declaration diagnostic, not a tool failure"
            )
        return done.stdout


def inventories(output: Path, python_data: dict, typescript_data: dict) -> dict:
    result: dict = {
        "passed": True,
        "scope": "Historical explicitly public Python names and transitive root TypeScript declarations; no exhaustive semantic equivalence claim.",
    }
    for language, snapshots in [
        ("python", python_data),
        ("typescript", typescript_data),
    ]:
        if not snapshots:
            continue
        before, after = snapshots["before"], snapshots["after"]
        old, new = before["symbols"], after["symbols"]
        missing = before.get("missing", []) + after.get("missing", [])
        result[language] = {
            "before_version": before["version"],
            "after_version": after["version"],
            "before": len(old),
            "after": len(new),
            "removed": sorted(old.keys() - new.keys()),
            "missing": missing,
            "changed": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
            "added": sorted(new.keys() - old.keys()),
        }
        if language == "typescript":
            result[language]["legacy_native_records_unchanged"] = all(
                after["nativeMethods"].get(k) == v
                for k, v in before["nativeMethods"].items()
            )
        result["passed"] &= not result[language]["removed"] and not missing
    dump(output / "inventory" / "report.json", result)
    if not result["passed"]:
        raise RuntimeError(
            "Historical public names are missing; see inventory/report.json"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ["before", "after"]:
        parser.add_argument("--" + role + "-wheel", type=Path, required=True)
        parser.add_argument("--" + role + "-tarball", type=Path, required=True)
    parser.add_argument("--after-version", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory only; never adopts or overwrites an existing directory",
    )
    parser.add_argument(
        "--with-sdk",
        action="store_true",
        help="Separate aiogram==3.31.0 environments and real SDK/FSM witnesses",
    )
    parser.add_argument(
        "--with-types",
        action="store_true",
        help="Separate TypeScript 7.0.2 compiler and 5.9.3 declaration parser tooling",
    )
    parser.add_argument(
        "--python", help="Python 3.11+ executable; default: current interpreter"
    )
    parser.add_argument(
        "--npm", help="npm executable; discovers npm.cmd on Windows, npm elsewhere"
    )
    parser.add_argument("--node", help="Node executable; default: discovered node")
    args = parser.parse_args()
    output = args.output.resolve()
    # Check BEFORE inspecting artifacts or running installers. No existing owner marker grants overwrite rights.
    if output.exists():
        parser.error("--output already exists; preserve it and choose a new directory")
    try:
        python = executable(args.python or sys.executable, "python")
        npm = executable(args.npm, "npm.cmd" if os.name == "nt" else "npm")
        node = executable(args.node, "node")
        paths = {
            role: [
                getattr(args, role + "_wheel").resolve(strict=True),
                getattr(args, role + "_tarball").resolve(strict=True),
            ]
            for role in ["before", "after"]
        }
        if any(not p.is_file() for group in paths.values() for p in group):
            raise ValueError("Every artifact must be a local regular file")
        if any(
            group[0].suffix != ".whl" or group[1].suffix != ".tgz"
            for group in paths.values()
        ):
            raise ValueError("Expected a .whl and .tgz for each role")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    artifacts = {
        role: [
            {"name": p.name, "sha256": digest(p), "bytes": p.stat().st_size}
            for p in group
        ]
        for role, group in paths.items()
    }
    output.mkdir(parents=True, exist_ok=False)
    owner = {
        "kind": "awesome-telegram-migration",
        "id": str(uuid.uuid4()),
        "artifacts": artifacts,
        "before_version": "0.5.0",
        "after_version": args.after_version,
    }
    dump(output / ".migration-owner.json", owner)
    run = Run(output, environment())
    report = {
        "passed": False,
        "before": "0.5.0",
        "after": args.after_version,
        "artifacts": artifacts,
        "owner_id": owner["id"],
        "with_sdk": args.with_sdk,
        "with_types": args.with_types,
        "platform": platform.platform(),
        "python": sys.version,
        "scope": "Local public installed consumers, synthetic transports and real file state; no Telegram/device/payment/1.0 RC acceptance.",
    }
    python_api: dict = {}
    ts_api: dict = {}
    try:
        (output / "inventory").mkdir()
        spec = json.loads((HERE / "public-api-0.5.json").read_text("utf-8"))
        if not args.with_sdk:
            spec = {
                k: v
                for k, v in spec.items()
                if k in {"telegram_patterns", "telegram_patterns.cli"}
            }
        dump(output / "inventory" / "public-spec.json", spec)
        for role, version in [("before", "0.5.0"), ("after", args.after_version)]:
            wheel, tarball = paths[role]
            core = output / (role + "-python")
            run.call(role + "-venv", [python, "-m", "venv", core])
            py = venv_python(core)
            run.call(
                role + "-install",
                [py, "-I", "-m", "pip", "install", "--no-deps", wheel],
            )
            origin_code = (
                "import importlib.metadata as m, pathlib,sys,telegram_patterns as t;assert m.version('awesome-telegram-patterns')=="
                + repr(version)
                + ";assert pathlib.Path(t.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve());print(m.version('awesome-telegram-patterns'),t.__file__)"
            )
            run.call(role + "-origin", [py, "-I", "-c", origin_code])
            project = output / (role + "-typescript")
            project.mkdir()
            dump(
                project / "package.json",
                {
                    "name": "migration-consumer-" + role,
                    "private": True,
                    "type": "module",
                    "dependencies": {
                        "@awesome-telegram/patterns": "file:" + tarball.as_posix()
                    },
                },
            )
            run.call(
                role + "-node-install",
                [npm, "install", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=project,
            )
            shutil.copyfile(HERE / "typescript_consumer.mjs", project / "consumer.mjs")
            run.call(
                "python-" + role,
                [py, "-I", HERE / "python_consumer.py", role, output / "state", wheel],
            )
            node_snapshot = run.call(
                "node-" + role,
                [node, "consumer.mjs", role, output / "state"],
                cwd=project,
            )
            if json.loads(node_snapshot)["version"] != version:
                raise RuntimeError(
                    f"{role}: installed Node package version differs from requested version"
                )
            run.call(
                role + "-cli-version",
                [py, "-I", "-m", "telegram_patterns", "--version"],
                expected=2 if role == "before" else 0,
            )
            shutil.copyfile(
                HERE / "api_contract_consumer.mjs", project / "api-contract.mjs"
            )
            run.call(
                "api-contract-" + role,
                [
                    node,
                    "api-contract.mjs",
                    role,
                    output / ("api-contract-" + role + ".json"),
                ],
                cwd=project,
            )
            inventory_python = py
            if args.with_sdk:
                sdk = output / (role + "-sdk")
                run.call(role + "-sdk-venv", [python, "-m", "venv", sdk])
                inventory_python = venv_python(sdk)
                run.call(
                    role + "-sdk-install",
                    [
                        inventory_python,
                        "-I",
                        "-m",
                        "pip",
                        "install",
                        wheel,
                        "aiogram==3.31.0",
                    ],
                )
                for kind in ["sdk", "fsm"]:
                    run.call(
                        kind + "-" + role,
                        [
                            inventory_python,
                            "-I",
                            HERE / (kind + "_consumer.py"),
                            role,
                            output,
                        ],
                    )
            snapshot = run.call(
                role + "-python-api",
                [
                    inventory_python,
                    "-I",
                    HERE / "python_inventory.py",
                    output / "inventory" / "public-spec.json",
                ],
            )
            python_api[role] = json.loads(snapshot)
            dump(output / "inventory" / (role + "-python.json"), python_api[role])
        if args.with_types:
            tools = output / "type-tools"
            tools.mkdir()
            dump(
                tools / "package.json",
                {
                    "name": "migration-type-tools",
                    "private": True,
                    "dependencies": {
                        "typescript": "7.0.2",
                        "typescript-parser": "npm:typescript@5.9.3",
                    },
                },
            )
            run.call(
                "type-tools-install",
                [npm, "install", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=tools,
            )
            typed = []
            for role in ["before", "after"]:
                project = output / (role + "-typescript")
                shutil.copyfile(
                    HERE / "typescript_inventory.mjs", project / "inventory.mjs"
                )
                snapshot = run.call(
                    role + "-typescript-api",
                    [
                        node,
                        "inventory.mjs",
                        project,
                        tools / "node_modules/typescript-parser",
                    ],
                    cwd=project,
                )
                ts_api[role] = json.loads(snapshot)
                dump(output / "inventory" / (role + "-typescript.json"), ts_api[role])
                for source in sorted((HERE / "types").glob("*.ts")):
                    if role == "before" and source.name == "after-adapted.ts":
                        continue
                    shutil.copyfile(source, project / source.name)
                    expected = (
                        1
                        if role == "after"
                        and source.name.startswith("legacy-")
                        and source.name != "legacy-valid.ts"
                        else 0
                    )
                    command = [
                        node,
                        tools / "node_modules/typescript/bin/tsc",
                        "--noEmit",
                        "--pretty",
                        "false",
                        "--strict",
                        "--module",
                        "NodeNext",
                        "--moduleResolution",
                        "NodeNext",
                        "--target",
                        "ES2022",
                        "--lib",
                        "ES2022,DOM",
                        "--skipLibCheck",
                        source.name,
                    ]
                    run.call(
                        "types-" + role + "-" + source.stem,
                        command,
                        cwd=project,
                        expected=expected,
                    )
                    typed.append(
                        {
                            "role": role,
                            "file": source.name,
                            "expected_compile_success": expected == 0,
                        }
                    )
            report["typed"] = {
                "passed": True,
                "compiler": "7.0.2",
                "declaration_parser": "5.9.3",
                "cases": typed,
            }
        report["inventory"] = inventories(output, python_api, ts_api)
        report["observations"] = {
            name: json.loads((output / relative).read_text("utf-8"))
            for name, relative in [
                ("python_before", "state/python-before.json"),
                ("python_after", "state/python-after.json"),
                ("typescript_before", "state/typescript-before.json"),
                ("typescript_after", "state/typescript-after.json"),
                ("api_before", "api-contract-before.json"),
                ("api_after", "api-contract-after.json"),
            ]
        }
        if args.with_sdk:
            report["observations"].update(
                {
                    name: json.loads(
                        (output / (name.replace("_", "-") + ".json")).read_text("utf-8")
                    )
                    for name in ["sdk_before", "sdk_after", "fsm_before", "fsm_after"]
                }
            )
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
    finally:
        report["stages"] = run.stages
        report["helper_sha256"] = {
            p.relative_to(HERE).as_posix(): digest(p)
            for p in sorted(HERE.rglob("*"))
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix in {".py", ".mjs", ".ts", ".json"}
        }
        dump(output / "report.json", report)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "stages": len(run.stages),
                "report": str(output / "report.json"),
            }
        ),
        flush=True,
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
