# __PROJECT_NAME__

Начальный Python-бот с aiogram и предоставленной локальной библиотекой. CLI не устанавливал пакеты, не запускал процессы и не обращался к Telegram. Локальные artifact URI в pyproject.toml рассчитаны на вашу машину; при переносе предоставьте свои пути.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install .
./.venv/Scripts/python.exe offline.py
./.venv/Scripts/python.exe -m telegram_patterns doctor .
```

В Linux используйте `.venv/bin/python`. Перед real запуском передайте BOT_TOKEN своего тестового бота в окружение и выполните `python app.py` в выбранном окружении. Token не хранится в коде и не выводится; .env.example не загружается автоматически. Проверьте отсутствие другого polling consumer и webhook. Запуск явно устанавливает default command menu; webhook не удаляется. Offline пример проверяет ту же композицию без HTTP.

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
