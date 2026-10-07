<p align="center">
  <img src="assets/readme/cover.png" alt="Awesome Telegram Skills — Python bots. TypeScript Mini Apps." width="100%">
</p>

# Awesome Telegram Skills

[![Version](https://img.shields.io/badge/version-0.24.0-229ED9)](CHANGELOG.md)
[![Skills](https://img.shields.io/badge/skills-42-334155)](#skills)
[![Status](https://img.shields.io/badge/status-experimental-f59e0b)](docs/v1-maturity.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](LICENSE)

**Practical AI skills, reusable components and examples for building Telegram bots and Mini Apps.**

Skills help an AI coding agent choose a solution and verify the result. The library gives you reusable code, and recipes show how to plug it into your project. The main stack is **Python + aiogram for bots and backends, TypeScript for Mini Apps**.

[Русская версия](README.md) · [Quickstart](docs/en/quickstart.md) · [Guide for AI agents](docs/en/for-agents.md) · [Releases](https://github.com/Zulut30/awesome-telegram-skills/releases)

> The skill instructions themselves are written in Russian; modern AI agents follow them in any conversation language. This page, the quickstart and the agent guide are in English.

## Can I use it in production?

| Part | Status | What it means for you |
| --- | --- | --- |
| 42 skills for AI agents | 🟢 Ready to use | They are instructions: the agent applies them to your code, you keep the decisions and the review |
| Python components (36 groups) | 🟡 Experimental | Tested with real aiogram and a test transport; the API may change in the next minor version |
| TypeScript components (7 groups) | 🟡 Experimental | Checked in Chrome at several screen sizes, not inside Telegram on a phone |
| Recipes (311) | 🟡 Verified without Telegram | 196 run on the real SDK offline, 16 on stubs, 99 are reference snippets that were not executed |
| Example applications | 🟡 Educational | Show how to build a service bot, a shop and a group bot; not finished products |
| Real Telegram clients, devices and payments | 🔴 Not verified | No live acceptance on Telegram clients or payment providers yet |

**Bottom line:** there are no stable components yet. Use the library as a foundation with your own tests and pin the exact version; the skills are useful today. [Maturity details](docs/v1-maturity.md) (Russian).

## Quickstart

Commands are shown for Windows (PowerShell) and for Linux and macOS (bash); where they are identical there is one block.

```bash
git clone https://github.com/Zulut30/awesome-telegram-skills.git
cd awesome-telegram-skills
```

**For AI agents.** Open the repository in Codex, Claude Code or another agent and call a skill:

```text
$telegram-bot-python Build a booking bot for consultations.
$telegram-code-patterns Add the ready-made forms and calendar.
$telegram-mini-app-architecture Design a Mini App for phone, tablet and desktop.
```

In Claude Code, all 42 skills install with one command as a plugin from this repository:

```bash
claude plugin marketplace add Zulut30/awesome-telegram-skills && claude plugin install telegram-skills@awesome-telegram-skills
```

After restarting the session the skills are available as `/telegram-skills:telegram-bot-python` and so on; update with `claude plugin marketplace update awesome-telegram-skills`. Inside a session, `/plugin marketplace add Zulut30/awesome-telegram-skills` and `/plugin install telegram-skills@awesome-telegram-skills` do the same.

In Gemini CLI it is one command as well; all skills go to `~/.gemini/skills/`:

```bash
gemini skills install https://github.com/Zulut30/awesome-telegram-skills.git --path .agents/skills
```

To use skills in an existing project, copy whole directories from `.agents/skills/`, including `references`, or use the [installer](scripts/install_skills.py):

```bash
python3 scripts/install_skills.py --project ~/projects/my-bot --skill telegram-bot-python --skill telegram-code-patterns --dry-run
```

```powershell
python scripts/install_skills.py --project "C:\path\to\my-bot" --skill telegram-bot-python --skill telegram-code-patterns --dry-run
```

Check the list, then repeat without `--dry-run`. Skills go to `.agents/skills/`, which Codex, GitHub Copilot, Cursor and Gemini CLI read. For Claude Code add `--agent claude`: it only reads `.claude/skills/`, and the installed skill becomes `/telegram-bot-python`. `--agent all` installs into both directories, `--agent copilot|cursor|gemini` into that agent's own directory, and `--user` instead of `--project` into your home directory for every project. Installing skills and installing packages are separate steps.

**For Python developers.** Python 3.11 or newer; no venv activation needed.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "./packages/python[aiogram]"
.venv/bin/python -m telegram_patterns recipes --show two-columns
.venv/bin/python examples/python/offline_keyboards.py
```

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "./packages/python[aiogram]"
.\.venv\Scripts\python.exe -m telegram_patterns recipes --show two-columns
.\.venv\Scripts\python.exe examples/python/offline_keyboards.py
```

The last command runs an example through a test transport, with no token and no requests to Telegram. [Step-by-step bot and Mini App quickstart](docs/en/quickstart.md).

**For Mini Apps.** Node.js 22 or newer (20 still works but is past upstream end of life).

```bash
npm ci
npm run demo
```

```powershell
npm.cmd ci
npm.cmd run demo
```

Open **http://127.0.0.1:4173**. This is a local UI and request-recovery demo; a real Mini App needs the Telegram host and your backend.

**Use the packages in your own project without cloning.** Each release publishes the wheel, the npm tarball and `SHA256SUMS` on [GitHub Releases](https://github.com/Zulut30/awesome-telegram-skills/releases):

```bash
pip install "awesome-telegram-patterns[aiogram] @ https://github.com/Zulut30/awesome-telegram-skills/releases/download/v0.24.0/awesome_telegram_patterns-0.24.0-py3-none-any.whl"
npm install https://github.com/Zulut30/awesome-telegram-skills/releases/download/v0.24.0/awesome-telegram-patterns-0.24.0.tgz
```

The packages are not on PyPI or npm yet; do not install packages with these names from public registries. [How releases are made](docs/releasing.md) (Russian).

## Two buttons per row

```python
from telegram_patterns.aiogram import ActionButton, action_menu

keyboard = action_menu([
    ActionButton("Catalog", "catalog", style="primary"),
    ActionButton("Help", "help"),
    ActionButton("Confirm", "confirm", style="success"),
    ActionButton("Cancel", "cancel", style="danger"),
], columns=2)

# In your handler: await message.answer("Choose an action", reply_markup=keyboard)
```

Use `columns=3` for three buttons per row. Permissions, click handling and style availability are checked by your application.

More ready-made layouts are in the **[recipe gallery](https://zulut30.github.io/awesome-telegram-skills/recipes/)**: search by task, SDK and chat context filters, keyboard previews and copyable code; it works on phones too. The interface is in Russian.

## Skills

Start with `telegram-project-planner` for a new project, `telegram-code-patterns` for ready-made code, or a specific skill for a narrow task. Every directory is self-contained; you never need to load the whole set.

| Skill | Use it to |
| --- | --- |
| [telegram-project-planner](.agents/skills/telegram-project-planner/SKILL.md) | Plan a new bot or Mini App, choose the stack and the MVP scope |
| [telegram-mini-app-ux](.agents/skills/telegram-mini-app-ux/SKILL.md) | Improve the first launch, navigation, forms and the purchase path |
| [telegram-bot-api](.agents/skills/telegram-bot-api/SKILL.md) | Add messages, media, buttons or a new Bot API method |
| [telegram-bot-python](.agents/skills/telegram-bot-python/SKILL.md) | Create or change a bot on aiogram, python-telegram-bot or pyTelegramBotAPI |
| [telegram-python-backend](.agents/skills/telegram-python-backend/SKILL.md) | Build a Python API, database, migrations, permissions and reliable server operations |
| [telegram-mini-app-architecture](.agents/skills/telegram-mini-app-architecture/SKILL.md) | Design structure, state and adaptive screens for phone, tablet and desktop |
| [telegram-mini-app-performance](.agents/skills/telegram-mini-app-performance/SKILL.md) | Measure and improve loading, responsiveness, lists and requests |
| [telegram-mini-app-network-recovery](.agents/skills/telegram-mini-app-network-recovery/SKILL.md) | Keep allowed drafts and recover requests on a bad network |
| [telegram-mini-app-typescript](.agents/skills/telegram-mini-app-typescript/SKILL.md) | Connect the bridge/SDK, types, API client and build of a TypeScript Mini App |
| [telegram-mini-app-native-capabilities](.agents/skills/telegram-mini-app-native-capabilities/SKILL.md) | Use location, biometrics, QR, storage, sharing and downloads with fallbacks |
| [telegram-dialogs](.agents/skills/telegram-dialogs/SKILL.md) | Build multi-step dialogs, FSM, menus and scenario recovery |
| [telegram-notifications](.agents/skills/telegram-notifications/SKILL.md) | Add reminders and broadcasts with a queue, unsubscribe and controlled retries |
| [telegram-ai-bot](.agents/skills/telegram-ai-bot/SKILL.md) | Connect a language model: streamed answers, stopping generation, limits and privacy |
| [telegram-inline-mode](.agents/skills/telegram-inline-mode/SKILL.md) | Implement search and sending results via `@bot query` |
| [telegram-groups](.agents/skills/telegram-groups/SKILL.md) | Work with groups, channels, moderation and topics |
| [telegram-mini-app-ui](.agents/skills/telegram-mini-app-ui/SKILL.md) | Create a polished adaptive Mini App UI with themes, safe areas and accessibility |
| [telegram-mini-app-design-system](.agents/skills/telegram-mini-app-design-system/SKILL.md) | Create reusable components, tokens, themes and consistent UI states |
| [telegram-mini-app-visual-regression](.agents/skills/telegram-mini-app-visual-regression/SKILL.md) | Set up screenshot comparison against reviewed baselines |
| [telegram-mini-app-auth](.agents/skills/telegram-mini-app-auth/SKILL.md) | Validate `initData` on the server and create a user session |
| [telegram-web-login](.agents/skills/telegram-web-login/SKILL.md) | Add Telegram Login (OIDC) to a website and link accounts safely |
| [telegram-mini-app-integration](.agents/skills/telegram-mini-app-integration/SKILL.md) | Connect bot, Mini App and backend; configure launch points and deep links |
| [telegram-payments](.agents/skills/telegram-payments/SKILL.md) | Add Stars, physical goods payments, subscriptions or refunds |
| [telegram-subscription-access](.agents/skills/telegram-subscription-access/SKILL.md) | Grant and revoke paid access by periods and payment events |
| [telegram-admin-panel](.agents/skills/telegram-admin-panel/SKILL.md) | Implement operator actions with roles, scope and an audit log |
| [telegram-media-processing](.agents/skills/telegram-media-processing/SKILL.md) | Receive, validate and transform media, create previews and background jobs |
| [telegram-testing](.agents/skills/telegram-testing/SKILL.md) | Test handlers, integrations and real scenarios in Telegram |
| [telegram-mini-app-device-qa](.agents/skills/telegram-mini-app-device-qa/SKILL.md) | Run acceptance in target Telegram clients on available real devices |
| [telegram-deploy](.agents/skills/telegram-deploy/SKILL.md) | Deploy the bot and Mini App, configure webhooks and operations |
| [telegram-debugging](.agents/skills/telegram-debugging/SKILL.md) | Find the cause of missing updates, API errors or WebView problems |
| [telegram-observability](.agents/skills/telegram-observability/SKILL.md) | Add correlated events, metrics and safe logs across frontend, backend and workers |
| [telegram-security-review](.agents/skills/telegram-security-review/SKILL.md) | Review authorization, payments, uploads and calls to external services |
| [telegram-buttons](.agents/skills/telegram-buttons/SKILL.md) | Button colors, custom emoji icons and keyboard limits |
| [telegram-profiles](.agents/skills/telegram-profiles/SKILL.md) | Profile data, Premium, photos, bio and permitted profile changes |
| [telegram-localization](.agents/skills/telegram-localization/SKILL.md) | Align languages, plural forms, dates, amounts and long labels across bot and Mini App |
| [telegram-user-client](.agents/skills/telegram-user-client/SKILL.md) | Read selected chats and history of an authorized account via Telethon (MTProto) |
| [telegram-business-bots](.agents/skills/telegram-business-bots/SKILL.md) | Officially connect a bot to the permitted chats of a business account |
| [telegram-library-selection](.agents/skills/telegram-library-selection/SKILL.md) | Choose an SDK and check support for new features |
| [telegram-code-patterns](.agents/skills/telegram-code-patterns/SKILL.md) | Plug in ready-made components of the shared Python/TypeScript library |
| [telegram-cryptopay](.agents/skills/telegram-cryptopay/SKILL.md) | CryptoBot / Crypto Pay: invoices, signatures and payment reconciliation |
| [telegram-platega](.agents/skills/telegram-platega/SKILL.md) | Platega.io: payment links, callbacks, statuses, refunds and subscriptions |
| [telegram-yookassa](.agents/skills/telegram-yookassa/SKILL.md) | YooKassa: API, provider invoices, capture, refunds and notifications |
| [telegram-payment-provider](.agents/skills/telegram-payment-provider/SKILL.md) | Stripe, Robokassa and other providers through a separate adapter |

## Quality and limits

Release 0.24.0 passed 77 acceptance stages: 460 Python tests, 26 TypeScript tests, 2435 automated browser checks and 60 first-run checks. The built wheel and tarball were installed into separate consumer projects. [Acceptance report](docs/v1-checks/031.json) · [Support matrix](docs/support-matrix.md) · [Support policy](docs/versioning.md#политика-поддержки).

The API catalog contains request examples; it does not mean that every Telegram feature is implemented and tested in a production app. Bot API, Mini Apps and user MTProto sessions have separate access boundaries.

## License and community

MIT licensed ([LICENSE](LICENSE)). Report vulnerabilities privately according to [SECURITY.md](SECURITY.md). Contributors follow the [code of conduct](CODE_OF_CONDUCT.md); see [CONTRIBUTING.md](CONTRIBUTING.md) (Russian) for how to propose changes.
