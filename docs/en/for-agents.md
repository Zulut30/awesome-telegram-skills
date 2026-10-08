# Connecting the library as an AI agent

This guide helps an agent pick a ready-made component, confirm its public API and integrate it into an existing project. Skills and packages are installed separately. Do not treat the repository as an installed Python/npm package. The skill instructions are written in Russian; follow them in the user's language. [Русская версия](../for-agents.md).

## First determine what you were given

| Input | How to start |
| --- | --- |
| The whole repository | Read `AGENTS.md`, `components.json` and the README of the relevant package. Canonical skills live in `.agents/skills/` |
| One skill directory | Read its `SKILL.md` and only the local references you need. Neighbouring skills are optional |
| A Python wheel / npm tarball | Install the provided file into the project environment. Check the actual version and exports; the library is not published on PyPI/npm |
| Only the documentation site | Find the API and example you need. To import it, get the package or archive; an HTML page does not install the library |

```bash
python -c "from importlib.metadata import version; print(version('awesome-telegram-patterns'))"
npm ls @awesome-telegram/patterns
```

If the first command fails or the second shows no package, the import is not confirmed yet. Choose the provided installation source first. Never install a package from a public registry by name alone.

## Choose the smallest entry point

| Task | Where to look |
| --- | --- |
| Find ready-made code | `telegram-code-patterns`, the component catalog and CLI recipes |
| Button rows, colors, reply input | `telegram-buttons`; `ActionButton`, `action_menu`, `KeyboardLayout`, `inline_layout`, `reply_layout` |
| Add Python bot behaviour | `telegram-bot-python`; attach a Router to the existing Dispatcher |
| Multi-step input | `telegram-dialogs`; forms and the storage contracts of the current project |
| Mini App and server authorization | `telegram-mini-app-architecture`, `telegram-mini-app-auth`; the TypeScript bridge and backend `initData` validation |
| Another SDK or an existing React/PostgreSQL project | Keep the stack. Connect only a compatible core/adapter; aiogram and the DOM shell do not require migrating the project |
| Reading chats of a user account | A separate `telegram-user-client` / MTProto task, not the regular Bot API |

## Find a recipe and check its requirements

After installing the Python package locally, the commands work from the target project's environment:

```bash
python -m telegram_patterns recipes "две кнопки" --task keyboards --sdk aiogram --context private
python -m telegram_patterns recipes --show two-columns
python -m telegram_patterns run-recipe two-columns
python -m telegram_patterns run-recipe two-columns --offline
```

Recipe search understands Russian queries; `--show` and `run-recipe` take recipe IDs. `recipes` searches and shows code. `run-recipe` without `--offline` prints a plan: dependencies, data, context and limits. `--offline` runs a closed synthetic fixture if the recipe ships one. Never run arbitrary `recipe.code` through `exec` and never put real credentials into sample requests.

For a specific symbol use the [API reference](../api-reference.md): the index contains the full import, the runtime/type kind, an example and limits. `ref.*` IDs are reference examples, not IDs for the `run-recipe` cookbook command.

## Confirm installation and integration

Python from a library checkout, into a separate environment of the target project:

```bash
python -m pip install "./packages/python[aiogram]"
python -c "from telegram_patterns.aiogram import ActionButton, action_menu; print(action_menu([ActionButton('Open', 'open')], columns=2).model_dump(exclude_none=True))"
```

The path refers to the library checkout: when running from another project, give its real absolute path or the provided wheel. The SDK-free core only needs `./packages/python`. For TypeScript, from the target project directory:

```bash
npm install /path/to/awesome-telegram-patterns-0.24.0.tgz
npm ls @awesome-telegram/patterns
```

```typescript
import { TelegramBridge, type BridgeSnapshot } from '@awesome-telegram/patterns';
import '@awesome-telegram/patterns/styles.css';
```

Replace the path with the provided archive and check the version against the documentation. Runtime and type exports differ; the CSS is a separate export for a frontend with a bundler. Detailed commands: [first run](quickstart.md) and the [distribution contract](../distribution-contract.md) (Russian).

Run the example on synthetic data first, then add the project's business logic. Keep the existing Bot/session, Dispatcher/router, storage, frontend framework and build tooling. Do not close resources owned by the host application.

## Check the meaning, not only the import

A button only builds markup; the callback handler checks the author, the object and current permissions. An ACK does not confirm business success. `validate_init_data` checks the signature and freshness, not access control. `SQLiteOnce` covers an effect only on the SQLite connection it was given. A lost write response keeps the same operation ID and requires reconciliation; a new ID is not a safe retry.

For a bot, test the main path and the related failure: a foreign callback, a stale step, a repeat or an unknown result. For a Mini App, test narrow and wide viewports, both themes, input, request cancellation and form recovery. A browser check does not prove behaviour on physical Telegram devices or a live payment.

`maturity` and `verification` are different properties. `sdk`/`mock`/`browser` are verification methods, not a production-readiness promise. For version-specific behaviour, check the official Telegram/SDK source listed in the relevant reference.

In your result, state the chosen API, the confirmed version, the changed files, the checks you ran and the duties left to the application. If the installed version lacks the API you need, show that fact and propose a compatible composition; never invent an export.
