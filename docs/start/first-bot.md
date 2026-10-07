# Мой первый Telegram-бот

Цель за 10 минут: рабочий бот с меню, который отвечает в Telegram. Нужны Python 3.11+ и аккаунт Telegram. Опыт с aiogram не обязателен.

## 1. Получите токен

Откройте [@BotFather](https://t.me/BotFather), отправьте `/newbot`, выберите имя и сохраните токен. Никому его не показывайте и не коммитьте.

## 2. Создайте проект

Скачайте wheel из [последнего релиза](https://github.com/Zulut30/awesome-telegram-skills/releases) в пустой каталог (или используйте путь `packages/python` из клона репозитория) и выполните:

```bash
python3 -m venv tools
tools/bin/python -m pip install ./awesome_telegram_patterns-0.24.0-py3-none-any.whl
tools/bin/python -m telegram_patterns init my-bot --library ./awesome_telegram_patterns-0.24.0-py3-none-any.whl
cd my-bot && python3 -m venv .venv && .venv/bin/python -m pip install .
```

```powershell
python -m venv tools
.\tools\Scripts\python.exe -m pip install .\awesome_telegram_patterns-0.24.0-py3-none-any.whl
.\tools\Scripts\python.exe -m telegram_patterns init my-bot --library .\awesome_telegram_patterns-0.24.0-py3-none-any.whl
Set-Location my-bot; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install .
```

## 3. Проверьте без сети, затем запустите

```bash
.venv/bin/python offline.py
cp .env.example .env   # вставьте токен вместо REPLACE_WITH_YOUR_TEST_BOT_TOKEN
.venv/bin/python app.py
```

```powershell
.\.venv\Scripts\python.exe offline.py
Copy-Item .env.example .env   # вставьте токен вместо REPLACE_WITH_YOUR_TEST_BOT_TOKEN
.\.venv\Scripts\python.exe app.py
```

`offline.py` печатает `passed: true` без токена и сети. `app.py` берет токен из `.env` и сначала проверяет его через getMe: при ошибке вы увидите, что именно исправить. После запуска `app.py` отправьте боту `/start` в Telegram: появится меню с кнопкой «Помощь». Остановите бота `Ctrl+C`.

## Что дальше

- Логика бота — в `app.py`: добавьте команды и кнопки по [примерам клавиатур](../keyboard-layouts.md).
- Если бот молчит: проверьте токен, что другой экземпляр не запущен и нет webhook (`python -m telegram_patterns doctor .`).
- Подробный разбор каждого шага — в [первом запуске](../quickstart.md); скиллы для ИИ-агента — на [странице для агента](ai-agent.md).
