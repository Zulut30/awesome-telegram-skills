## Mini App за 15 минут: тестовое окружение Telegram

Тестовое окружение отделено от основного: нужны отдельный аккаунт и бот, зато Mini App открывается по HTTP без TLS и туннеля ([Testing Mini Apps](https://core.telegram.org/bots/webapps#testing-mini-apps)). Компьютер и телефон должны быть в одной сети.

| Шаг | Что сделать | Время |
|---|---|---|
| 1 | Войти в тестовое окружение (один раз). Telegram Desktop: ☰ Settings → Shift+Alt+правый клик по «Add Account» → Test Server. iOS: 10 раз нажать Settings → Accounts → Login to another account → Test. macOS: 10 раз нажать Settings → Debug Menu. Зарегистрировать тестовый аккаунт. | 4 мин |
| 2 | В тестовом аккаунте открыть @BotFather, выполнить `/newbot` и скопировать токен. | 2 мин |
| 3 | Установить Python-часть командами выше (venv, `pip install .`). | 3 мин |
| 4 | Скопировать `.env.example` в `.env`: `BOT_TOKEN=<тестовый токен>`, `TELEGRAM_TEST_ENVIRONMENT=1`, `MINI_APP_URL=http://<IP компьютера в локальной сети>:5173`. | 1 мин |
| 5 | `cd mini-app`, `npm install`, `npm run dev -- --host` (Vite с горячей перезагрузкой). | 3 мин |
| 6 | Во втором терминале `python app.py`: бот проверяет токен, ставит кнопку меню «Открыть» с `MINI_APP_URL` и запускает backend на `127.0.0.1:8080`. | 1 мин |
| 7 | В тестовом аккаунте написать боту `/start` и нажать кнопку меню «Открыть». | 1 мин |

Mini App показывает «Backend проверил initData: <имя> (id …)»: frontend отправил `GET /api/me` с сырой initData в заголовке `X-Init-Data`, Vite проксировал запрос в backend, а `mini_app_server.py` проверил подпись токеном бота (`validate_init_data`). Изменение `mini-app/src/*.ts` применяется в открытом Mini App без перезапуска: старая копия модуля снимает свой UI и подписки (`import.meta.hot.dispose`), новая монтируется заново. Повторный цикл после первой настройки — меньше минуты.

Что проверить, если не открылось:

- «Backend недоступен» — не запущен `python app.py` (или `python mini_app_server.py` без бота) либо `MINI_APP_API_PORT` в `.env` отличается от порта backend.
- «Backend отклонил initData» — токен в `.env` не того бота, который открыл Mini App, или initData старше часа: откройте Mini App заново.
- Страница не грузится на телефоне — Vite запущен без `--host`, телефон в другой сети или порт 5173 закрыт firewall.
- Без `TELEGRAM_TEST_ENVIRONMENT=1` бот откажется ставить кнопку с HTTP-адресом: основной Telegram принимает только HTTPS.

Отладка WebView на iOS, Android, Desktop и macOS описана в [Debug Mode for Mini Apps](https://core.telegram.org/bots/webapps#debug-mode-for-mini-apps). Вне Telegram (`npm run dev` в обычном браузере) интерфейс работает, но initData нет и backend пользователя не подтверждает.

### Основное окружение и выпуск

`npm run build` проверяет типы и собирает `mini-app/dist`; `python app.py` раздает его вместе с `/api` с одного origin `127.0.0.1:8080`. Перед ним нужен HTTPS reverse proxy, а `MINI_APP_URL` — публичный HTTPS-адрес. Для разработки в основном окружении укажите в `MINI_APP_URL` HTTPS-адрес туннеля к порту 5173: Vite разрешит этот домен (`allowedHosts`) из того же `.env`. Проверка initData подтверждает только запуск; права на объекты, сессии и повтор операций остаются задачей вашего backend. Существующий frontend, SDK и БД не заменяются: для текущего проекта подключайте нужные компоненты напрямую.
