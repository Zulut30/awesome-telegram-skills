# __PROJECT_NAME__

Начальный Python-бот с aiogram и предоставленной локальной библиотекой. CLI не устанавливал пакеты, не запускал процессы и не обращался к Telegram. Локальные artifact references рассчитаны на вашу машину: Python использует file URI, npm — file filesystem path с буквальными пробелами. При переносе предоставьте свои пути.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install .
./.venv/Scripts/python.exe offline.py
./.venv/Scripts/python.exe -m telegram_patterns doctor .
```

В Linux и macOS используйте `.venv/bin/python`. Для запуска в Telegram скопируйте `.env.example` в `.env`, вставьте токен тестового бота от @BotFather и выполните `python app.py` в выбранном окружении (переменная окружения BOT_TOKEN важнее файла). Перед запуском бот вызывает getMe: неверный токен или отсутствие сети дают понятную ошибку. Token не хранится в коде и не выводится; `.env` не коммитится. Без основного аккаунта бот можно запустить в тестовом окружении Telegram: отдельный аккаунт, бот из тестового @BotFather и строка `TELEGRAM_TEST_ENVIRONMENT=1` в `.env`. Проверьте отсутствие другого polling consumer и webhook. Запуск явно устанавливает default command menu; webhook не удаляется. Offline пример проверяет ту же композицию без HTTP.

В bot-mini-app дополнительно есть frontend starter:

```powershell
cd mini-app
npm.cmd install
npm.cmd run typecheck
npm.cmd run build
python -m http.server 4173 --bind 127.0.0.1
```

Откройте http://127.0.0.1:4173. В шаблоне bot каталога mini-app нет.

Frontend показывает адаптивную форму, переиспользует shell/fields/theme bridge, ничего не отправляет и не аутентифицирует пользователя. Для запуска внутри Telegram нужны официальный WebApp SDK, HTTPS deployment, выбранная точка запуска, проверка raw initData на backend и объектные права. Готовый backend/session/payment этим starter не создаются. Browser preview не подтверждает Telegram-личность. Существующий framework, SDK и БД не заменяются: для текущего проекта подключайте нужные компоненты напрямую.
