# First run: a bot and a Mini App screen

This example is verified on Windows (PowerShell), Ubuntu and macOS (bash) with Python 3.13, Node.js 24 and the local release **0.24.0**. Every step has two variants: PowerShell for Windows and bash for Linux and macOS; run one of them. You need Python >=3.11 and Node.js >=20 (22 or newer recommended). The packages are not on PyPI or npm yet: download the wheel and tarball from GitHub Releases or get them from the project owner. Both files must come from the same release.

Before you start: installing Python/npm dependencies may use the internet. `init`, `offline.py` and the local form need no real token, no Telegram account and no payment keys. The bot runs a real aiogram Dispatcher through `StubSession`; the screen validates input locally. A backend, server-side authorization and form submission are not connected here yet.

## 1. Install the local CLI

Open PowerShell (Windows) or a terminal (Linux, macOS). Replace `$tgArtifacts` / `TG_ARTIFACTS` with the directory that holds the provided files. `$tgWorkspace` / `TG_WORKSPACE` must be new: if it already exists, choose another name. The commands never delete existing projects. If the port is used by another application, set another `$tgPreviewPort` / `TG_PREVIEW_PORT`. Each bash block is one chain of commands: on an error it stops and prints a hint without closing the terminal.

<!-- quickstart:parameters -->
```powershell
$tgArtifacts = 'C:\path\to\pattern-library-0.24.0\artifacts'
$tgWorkspace = Join-Path $env:TEMP 'telegram-first-run'
$tgPreviewPort = 4173
```

<!-- quickstart-bash:parameters -->
```bash
TG_ARTIFACTS="$HOME/Downloads/pattern-library-0.24.0/artifacts"
TG_WORKSPACE="${TMPDIR:-/tmp}/telegram-first-run"
TG_PREVIEW_PORT=4173
```

<!-- quickstart:setup -->
```powershell
$ErrorActionPreference = 'Stop'
$tgWheel = Join-Path $tgArtifacts 'awesome_telegram_patterns-0.24.0-py3-none-any.whl'
$tgTarball = Join-Path $tgArtifacts 'awesome-telegram-patterns-0.24.0.tgz'
if (!(Test-Path -LiteralPath $tgWheel -PathType Leaf) -or !(Test-Path -LiteralPath $tgTarball -PathType Leaf)) { throw 'Both local 0.24.0 artifacts are required' }
if (Test-Path -LiteralPath $tgWorkspace) { throw 'Choose a new tgWorkspace directory' }
New-Item -ItemType Directory -Path $tgWorkspace | Out-Null
Set-Location -LiteralPath $tgWorkspace
python -m venv tools
if ($LASTEXITCODE -ne 0) { throw 'Could not create the tools venv' }
& .\tools\Scripts\python.exe -m pip install --no-input --disable-pip-version-check $tgWheel
if ($LASTEXITCODE -ne 0) { throw 'Could not install the local wheel' }
```

<!-- quickstart-bash:setup -->
```bash
TG_WHEEL="$TG_ARTIFACTS/awesome_telegram_patterns-0.24.0-py3-none-any.whl" &&
TG_TARBALL="$TG_ARTIFACTS/awesome-telegram-patterns-0.24.0.tgz" &&
test -f "$TG_WHEEL" && test -f "$TG_TARBALL" &&
mkdir "$TG_WORKSPACE" && cd "$TG_WORKSPACE" &&
python3 -m venv tools &&
tools/bin/python -m pip install --no-input --disable-pip-version-check "$TG_WHEEL" ||
{ echo 'Failed: both 0.24.0 artifacts and a new TG_WORKSPACE directory are required' >&2; false; }
```

The `tools` environment holds the CLI and the library core; aiogram is installed in the environment of the generated bot. You do not need to activate the venv or change the PowerShell ExecutionPolicy. On Linux and macOS Python is `python3`, and environment files live in `bin/` instead of `Scripts\`.

## 2. Create a new project

The first command lists the 11 files to be created with `created: false`. The second creates `my-bot` with a Python bot and a TypeScript form. The CLI does not install dependencies. The manifests contain absolute local references (a Python file URI and an npm file path): if you move the project, provide new paths to the artifacts.

<!-- quickstart:init -->
```powershell
& .\tools\Scripts\python.exe -m telegram_patterns init .\my-bot --library $tgWheel --template bot-mini-app --typescript $tgTarball --dry-run
if ($LASTEXITCODE -ne 0) { throw 'Could not check the project plan' }
& .\tools\Scripts\python.exe -m telegram_patterns init .\my-bot --library $tgWheel --template bot-mini-app --typescript $tgTarball
if ($LASTEXITCODE -ne 0) { throw 'Could not create the new project' }
Set-Location -LiteralPath .\my-bot
```

<!-- quickstart-bash:init -->
```bash
tools/bin/python -m telegram_patterns init ./my-bot --library "$TG_WHEEL" --template bot-mini-app --typescript "$TG_TARBALL" --dry-run &&
tools/bin/python -m telegram_patterns init ./my-bot --library "$TG_WHEEL" --template bot-mini-app --typescript "$TG_TARBALL" &&
cd ./my-bot ||
{ echo 'Could not create the new project' >&2; false; }
```

## 3. Run the offline bot

<!-- quickstart:offline -->
```powershell
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the bot environment' }
& .\.venv\Scripts\python.exe -m pip install --no-input --disable-pip-version-check .
if ($LASTEXITCODE -ne 0) { throw 'Could not install the project and aiogram' }
& .\.venv\Scripts\python.exe offline.py
if ($LASTEXITCODE -ne 0) { throw 'The offline scenario failed' }
& .\.venv\Scripts\python.exe -m telegram_patterns doctor .
if ($LASTEXITCODE -ne 0) { throw 'Local problems found: read the checks reported by doctor' }
```

<!-- quickstart-bash:offline -->
```bash
python3 -m venv .venv &&
.venv/bin/python -m pip install --no-input --disable-pip-version-check . &&
.venv/bin/python offline.py &&
.venv/bin/python -m telegram_patterns doctor . ||
{ echo 'The offline scenario or doctor failed: read the output above' >&2; false; }
```

Expected `offline.py` result: `passed: true`, `network: false`, methods `SendMessage`, `AnswerCallbackQuery`, `SendMessage`, then `session_closed: true`. That is `/start`, a press on the help button and the bot's answer. `app.py` contains the composition in use. A `token-format` warning from `doctor` is fine for this run; `passed` does not prove that a real token or backend works.

## 4. Open the Mini App screen

<!-- quickstart:frontend -->
```powershell
Set-Location -LiteralPath .\mini-app
npm.cmd install --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies' }
npm.cmd run typecheck
if ($LASTEXITCODE -ne 0) { throw 'Frontend type errors' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'The frontend did not build' }
```

<!-- quickstart-bash:frontend -->
```bash
cd ./mini-app &&
npm install --ignore-scripts --no-audit --no-fund &&
npm run typecheck &&
npm run build ||
{ echo 'The frontend did not build: read the npm output' >&2; false; }
```

<!-- quickstart:preview -->
```powershell
& ..\.venv\Scripts\python.exe -m http.server $tgPreviewPort --bind 127.0.0.1 --directory .
```

<!-- quickstart-bash:preview -->
```bash
../.venv/bin/python -m http.server "$TG_PREVIEW_PORT" --bind 127.0.0.1 --directory .
```

Open **http://127.0.0.1:4173** in a browser (use your port if you changed it). HTTP is required because the page imports ES modules. The interface of the generated screen is in Russian: press the check button with an empty field, an error appears and focus moves to the field. Enter a name and repeat: a message confirms the local check and that nothing was sent. Resize the window and switch the OS light/dark theme: the entered name is kept. The server listens on loopback only; stop it with `Ctrl+C` in this window.

## When you need Telegram

For a real bot get a separate test BOT_TOKEN from BotFather, copy `.env.example` to `.env` and paste the token (or pass BOT_TOKEN in the process environment, which wins over the file). Before starting, the bot calls getMe: a wrong token or no network produces a clear message. From the `my-bot` directory run `.\.venv\Scripts\python.exe app.py` (Windows) or `.venv/bin/python app.py` (Linux, macOS). This run talks to Telegram and explicitly sets the default command menu. First make sure no other polling consumer runs and check the webhook configuration; the template never deletes a webhook automatically.

A Mini App inside Telegram needs HTTPS hosting, the official WebApp SDK and a chosen launch point. Before handling user data, connect a backend, raw initData validation, a session and object permissions. The local form grants no access and proves no identity. Business permissions and a user MTProto session are never connected automatically. Real Telegram clients and payments are verified separately.

If an existing project uses React, Vue, another bot library or database, plug the public APIs you need into its current architecture. This starter is meant for a new small example; 1.0 stability is not declared for it yet.
