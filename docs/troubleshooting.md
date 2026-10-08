# Частые проблемы Telegram-ботов и Mini Apps

Каждая ситуация описана по схеме «симптом → причина → проверка → решение». Комментарий `# → …` в коде — ожидаемый вывод строки. Проверки только читают состояние: они не удаляют webhook, не сбрасывают очередь updates и ничего не отправляют пользователям. Тексты ошибок приведены в том виде, в каком их обычно возвращает Bot API; поле `description` в ответе может отличаться в деталях.

## Инструмент проверки

Сохраните скрипт как `tg.py` рядом с ботом. Он выполняет только безопасные методы `get*` из короткого списка, берёт BOT_TOKEN из окружения или из `.env` в текущем каталоге и не печатает токен. С `TELEGRAM_TEST_ENVIRONMENT=1` запросы идут в тестовое окружение Telegram.

<!-- troubleshooting:tg.py -->
```python
"""Read-only Bot API check: python tg.py METHOD[?param=value&...]"""
import json, os, sys, urllib.error, urllib.request
from pathlib import Path

SAFE = {'getMe', 'getWebhookInfo', 'getMyCommands', 'getChat', 'getChatMember', 'getChatAdministrators',
        'getChatMemberCount', 'getChatMenuButton', 'getMyDefaultAdministratorRights', 'getFile'}
if len(sys.argv) != 2 or sys.argv[1].split('?')[0] not in SAFE:
    sys.exit('Использование: python tg.py METHOD[?параметры]; METHOD: ' + ', '.join(sorted(SAFE)))
env = dict(line.split('=', 1) for line in Path('.env').read_text(encoding='utf-8').splitlines()
           if '=' in line and not line.lstrip().startswith('#')) if Path('.env').is_file() else {}
token = os.environ.get('BOT_TOKEN') or env.get('BOT_TOKEN', '').strip()
if not token:
    sys.exit('Задайте BOT_TOKEN в окружении или в .env')
test = os.environ.get('TELEGRAM_TEST_ENVIRONMENT', env.get('TELEGRAM_TEST_ENVIRONMENT', '')).strip().lower()
prefix = 'test/' if test in ('1', 'true', 'yes', 'on') else ''
try:
    body = urllib.request.urlopen(f'https://api.telegram.org/bot{token}/{prefix}{sys.argv[1]}', timeout=15).read()
except urllib.error.HTTPError as error:
    body = error.read()  # Bot API отвечает JSON и при ошибке
except urllib.error.URLError:
    sys.exit('Bot API недоступен: проверьте сеть, прокси (HTTPS_PROXY) и DNS')
answer = json.loads(body)
print(json.dumps(answer, ensure_ascii=False, indent=2))
sys.exit(0 if answer.get('ok') else 1)
```

Запуск: `python tg.py getMe` (Windows) или `python3 tg.py getMe` (Linux, macOS). Код выхода 0 означает `"ok": true`, 1 — ошибку Bot API (её текст в `description`). Если в проекте установлен awesome-telegram-patterns, `python -m telegram_patterns doctor . --webhook --expect polling` дополнительно разбирает ответ `getWebhookInfo` и даёт рекомендации.

`getUpdates` в списке нет намеренно: он забирает и подтверждает updates у работающего бота и конфликтует с ним.

## Запуск и токен

### 1. `401 Unauthorized` при запуске

**Причина.** Токен неверный, отозван через @BotFather или скопирован с пробелом или кавычками. Токен основного бота не действует в тестовом окружении, и наоборот.

**Проверка.**

```bash
python3 tg.py getMe
```

**Решение.** `"ok": true` и ваш `username` означают, что токен в порядке. При `401` возьмите токен в @BotFather (`/token`), а если он мог утечь — выпустите новый (`/revoke`).

### 2. `404 Not Found` на любой метод

**Причина.** Строка не похожа на токен (нет части `123456:`), в URL лишний символ или опечатка в имени метода. Имена методов чувствительны к регистру.

**Проверка.**

```bash
python3 tg.py getMe
```

**Решение.** Проверьте формат `<число>:<строка>` без пробелов. Имя метода сверяйте с документацией Bot API.

### 3. Бот запускается, но токен «не тот»

**Причина.** В окружении процесса задан другой BOT_TOKEN: переменная окружения важнее `.env`, поэтому бот работает от имени старого бота.

**Проверка.**

```bash
python3 tg.py getMe
```

**Решение.** Сравните `username` в ответе с ожидаемым ботом. Уберите лишнюю переменную окружения (`unset BOT_TOKEN`, в PowerShell `Remove-Item Env:BOT_TOKEN`) или исправьте её значение.

### 4. `ModuleNotFoundError: No module named 'aiogram'`

**Причина.** Бот запущен не тем Python: зависимости установлены в `.venv`, а команда использует системный интерпретатор.

**Проверка.**

```bash
.venv/bin/python -c "import aiogram, sys; print(aiogram.__version__, sys.prefix)"
```

**Решение.** Запускайте бота явным путём к интерпретатору окружения (`.venv/bin/python app.py`, в Windows `.\.venv\Scripts\python.exe app.py`). `python -m telegram_patterns doctor .` показывает, какой SDK виден этому интерпретатору.

## Получение updates

### 5. Бот молчит

**Причина.** Процесс не запущен или упал; у бота установлен webhook, и polling не получает updates; updates забирает другой процесс; обработчик не подходит под сообщение.

**Проверка.**

```bash
python3 tg.py getWebhookInfo
```

**Решение.** Пустой `url` и растущий `pending_update_count` значат, что polling-процесс не работает. Непустой `url` — updates уходят на webhook. Затем проверьте логи процесса и фильтры обработчиков.

### 6. `409 Conflict: terminated by other getUpdates request`

**Причина.** Запущены два polling-процесса одного бота: второй терминал, старый контейнер, сервер или IDE.

**Проверка.**

```bash
ps aux | grep -E "app.py|telegram" | grep -v grep
```

**Решение.** Оставьте один процесс. Если второй работает на другом сервере, остановите его там; смена токена (`/revoke`) отключит все старые копии.

### 7. `409 Conflict: can't use getUpdates method while webhook is active`

**Причина.** У бота установлен webhook, а код запускает polling.

**Проверка.**

```bash
python -m telegram_patterns doctor . --webhook --expect polling
```

**Решение.** Если webhook больше не нужен, вызовите `deleteWebhook` без `drop_pending_updates` — очередь сохранится. Если нужен, запускайте бота в режиме webhook. Polling и webhook одновременно не работают.

### 8. Webhook установлен, но updates не приходят

**Причина.** Telegram не может доставить update: сервер недоступен, сертификат не принят или обработчик отвечает ошибкой. Подробности — в `last_error_message`.

**Проверка.**

```bash
python3 tg.py getWebhookInfo
```

**Решение.** «Connection refused» или timeout — проверьте DNS, firewall и порт (поддерживаются 443, 80, 88 и 8443). «SSL error» — нужна полная цепочка сертификата. «Wrong response from the webhook: 5xx» — смотрите логи обработчика.

### 9. Webhook отвечает 401 или 403

**Причина.** Сервер проверяет заголовок `X-Telegram-Bot-Api-Secret-Token`, а `secret_token`, переданный в `setWebhook`, другой или не задан. Так же выглядит блокировка WAF или firewall.

**Проверка.**

```bash
python -m telegram_patterns doctor . --webhook --expect webhook
```

**Решение.** Передайте в `setWebhook` тот же секрет, который проверяет сервер. Допустимы 1–256 символов `A-Z`, `a-z`, `0-9`, `_`, `-`. `getWebhookInfo` секрет не показывает.

### 10. После перезапуска пропали updates

**Причина.** Код вызывает `deleteWebhook(drop_pending_updates=True)` или `start_polling` со сбросом очереди. Кроме того, Telegram хранит неполученные updates не дольше 24 часов.

**Проверка.**

```bash
grep -rn "drop_pending_updates" .
```

**Решение.** Не сбрасывайте очередь при каждом старте. Если бот простаивал больше суток, старые updates не вернуть.

### 11. Одно и то же сообщение обработано дважды

**Причина.** Процесс упал после действия, но до подтверждения update, и Telegram доставил его снова. Повторы — нормальная часть доставки.

**Проверка.** Найдите в логах один `update_id` дважды:

```bash
grep -o "update_id[^,]*" bot.log | sort | uniq -d
```

**Решение.** Делайте эффекты идемпотентными: храните ключ операции и результат в одной транзакции. В awesome-telegram-patterns для этого есть `SQLiteOnce`.

### 12. Не приходят `chat_member` или реакции

**Причина.** По умолчанию Bot API не присылает `chat_member`, `message_reaction` и `message_reaction_count`: их нужно явно перечислить в `allowed_updates`.

**Проверка.**

<!-- troubleshooting:run -->
```python
from aiogram import Dispatcher, Router

router = Router()

@router.chat_member()
async def member_changed(event): ...

dp = Dispatcher()
dp.include_router(router)
print(dp.resolve_used_update_types())  # → ['chat_member']
```

**Решение.** Передайте этот список в `dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())` или в `setWebhook`. Для `chat_member` бот должен быть администратором чата.

## Группы и каналы

### 13. Бот не видит сообщения в группе

**Причина.** Включён privacy mode: в группах бот получает команды, ответы на свои сообщения и упоминания, но не весь текст.

**Проверка.**

```bash
python3 tg.py getMe
```

**Решение.** `can_read_all_group_messages: false` — privacy mode включён. Выключите его в @BotFather (`/setprivacy`) и заново добавьте бота в группу, либо сделайте бота администратором.

### 14. `Bad Request: chat not found`

**Причина.** Неверный `chat_id`, бот не состоит в чате, пользователь ни разу не писал боту, или для канала передано имя без `@`.

**Проверка.**

```bash
python3 tg.py "getChat?chat_id=@your_channel"
```

**Решение.** Для групп и каналов используйте числовой id (у супергрупп он начинается с `-100`) или `@username`. Бот должен быть участником.

### 15. `Bad Request: group chat was upgraded to a supergroup chat`

**Причина.** Группа стала супергруппой и получила новый id. Старый больше не работает.

**Проверка.**

<!-- troubleshooting:run -->
```python
from aiogram.exceptions import TelegramMigrateToChat
from aiogram.methods import SendMessage

error = TelegramMigrateToChat(SendMessage(chat_id=-123, text='...'),
                              'Bad Request: group chat was upgraded to a supergroup chat',
                              migrate_to_chat_id=-1001234567890)
print(error.migrate_to_chat_id)  # → -1001234567890
```

**Решение.** Перехватывайте `TelegramMigrateToChat`: `migrate_to_chat_id` — новый id чата. Обновите его в базе и повторите отправку. Храните id как 64-битное целое.

### 16. `Bad Request: not enough rights to send text messages to the chat`

**Причина.** В группе ограничены права участников, бот не администратор канала или у него нет нужного права.

**Проверка.** Подставьте id чата и id бота (поле `id` из `getMe`):

```bash
python3 tg.py "getChatMember?chat_id=-1001234567890&user_id=123456789"
```

**Решение.** Смотрите `status` и флаги `can_post_messages`, `can_send_messages`. Выдайте права в настройках чата.

### 17. `Forbidden: bot is not a member of the channel chat`

**Причина.** Бот не добавлен в канал или удалён из него.

**Проверка.**

```bash
python3 tg.py "getChatAdministrators?chat_id=@your_channel"
```

**Решение.** Добавьте бота администратором канала с правом публикации.

## Отправка сообщений

### 18. `Forbidden: bot was blocked by the user`

**Причина.** Пользователь заблокировал бота или удалил чат с ним.

**Проверка.**

<!-- troubleshooting:run -->
```python
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

inactive: set[int] = set()
try:
    raise TelegramForbiddenError(SendMessage(chat_id=42, text='...'), 'Forbidden: bot was blocked by the user')
except TelegramForbiddenError:
    inactive.add(42)  # больше не отправляем, пока пользователь сам не напишет боту
print(sorted(inactive))  # → [42]
```

**Решение.** Помечайте пользователя неактивным и исключайте из рассылок. Повтор отправки не поможет.

### 19. `Forbidden: bot can't initiate conversation with a user`

**Причина.** Бот не может написать первым: пользователь должен сам открыть бота и нажать «Старт».

**Проверка.** Найдите в своей базе, был ли от этого пользователя `/start`. Bot API такой проверки не даёт.

```bash
grep -c "chat_id=42" bot.log
```

**Решение.** Дайте пользователю ссылку `https://t.me/<username_бота>?start=...` и отправляйте сообщение после `/start`.

### 20. `429 Too Many Requests: retry after N`

**Причина.** Превышен лимит частоты. В ответе есть `retry_after` — сколько секунд ждать. В тестовом окружении лимиты не выше, иногда строже.

**Проверка.**

<!-- troubleshooting:run -->
```python
import asyncio
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

async def send_with_retry(call, attempts=3):
    for attempt in range(attempts):
        try:
            return await call()
        except TelegramRetryAfter as error:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(error.retry_after)

calls = []
async def send():
    calls.append(1)
    if len(calls) == 1:
        raise TelegramRetryAfter(SendMessage(chat_id=1, text='...'), 'Too Many Requests: retry after 0', retry_after=0)
    return 'sent'

print(asyncio.run(send_with_retry(send)), len(calls))  # → sent 2
```

**Решение.** Ждите `retry_after` и повторяйте ограниченное число раз; рассылки растягивайте во времени. 429 означает, что запрос не выполнен, поэтому повтор безопасен.

### 21. `Bad Request: message is not modified`

**Причина.** `editMessageText` или `editMessageReplyMarkup` получили тот же текст и ту же клавиатуру, что уже в сообщении. Часто — двойное нажатие кнопки.

**Проверка.**

<!-- troubleshooting:run -->
```python
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

def not_modified(error: TelegramBadRequest) -> bool:
    return 'message is not modified' in error.message

error = TelegramBadRequest(EditMessageText(text='Тот же текст', chat_id=1, message_id=1),
                           'Bad Request: message is not modified')
print(not_modified(error))  # → True
```

**Решение.** Сравнивайте новое содержимое со старым до вызова или считайте эту ошибку успехом. Другие `TelegramBadRequest` не глушите.

### 22. `Bad Request: can't parse entities`

**Причина.** В тексте с `parse_mode` HTML или MarkdownV2 есть неэкранированные `<`, `&` или символы Markdown, часто из пользовательского ввода.

**Проверка.**

<!-- troubleshooting:run -->
```python
from telegram_patterns import escape_html  # или html.escape из стандартной библиотеки

name = 'Tom & <Jerry>'
print(f'<b>Привет, {escape_html(name)}</b>')  # → <b>Привет, Tom &amp; &lt;Jerry&gt;</b>
```

**Решение.** Экранируйте каждую вставку под выбранный режим (`escape_markdown_v2` для MarkdownV2) или отправляйте текст без `parse_mode` с entities.

### 23. `Bad Request: message is too long`

**Причина.** Текст длиннее 4096 символов после разбора entities (подпись к медиа — 1024).

**Проверка.**

<!-- troubleshooting:run -->
```python
from telegram_patterns import FormattedText, split_formatted

parts = split_formatted(FormattedText('строка\n' * 1000), limit=4096)
print(len(parts), [len(part.text) for part in parts])  # → 2 [4095, 2905]
```

**Решение.** Разбивайте текст на части по границам строк; `split_formatted` сохраняет форматирование и не рвёт ссылки.

### 24. `Bad Request: message text is empty`

**Причина.** Отправляется пустая строка или строка из одних пробелов, например после шаблона без данных.

**Проверка.**

<!-- troubleshooting:run -->
```python
text = '   '
print(bool(text.strip()))  # → False
```

**Решение.** Проверяйте текст перед отправкой и показывайте пользователю понятную заглушку.

### 25. Меню команд не обновилось

**Причина.** Команды заданы для другой области (`scope`) или языка (`language_code`), либо клиент ещё показывает старый список.

**Проверка.**

```bash
python3 tg.py getMyCommands
python3 tg.py "getMyCommands?language_code=ru"
```

**Решение.** Вызывайте `setMyCommands` с той же областью и языком, которые проверяете. Клиенту может понадобиться перезапуск чата.

## Кнопки и callback

### 26. Кнопка «крутится» после нажатия

**Причина.** Бот не вызвал `answerCallbackQuery`: клиент показывает индикатор, пока ответа нет.

**Проверка.** Отвечайте на callback первым действием обработчика:

```python
@router.callback_query()
async def on_button(callback: CallbackQuery):
    await callback.answer()  # сразу убирает индикатор
    ...  # долгую работу выполняйте после ответа
```

**Решение.** Вызывайте `callback.answer()` в каждом обработчике, даже если уведомление пользователю не нужно.

### 27. `Bad Request: query is too old and response timeout expired or query ID is invalid`

**Причина.** На callback или inline query ответили слишком поздно: обработчик сначала выполнил долгую операцию, или update пришёл из очереди после простоя.

**Проверка.** Измерьте время до ответа:

```python
started = time.monotonic()
await callback.answer()
logging.info('callback answered in %.1f s', time.monotonic() - started)
```

**Решение.** Отвечайте сразу, долгую работу переносите после ответа. Ошибку для устаревшего callback можно записать в лог и не повторять.

### 28. `Bad Request: BUTTON_DATA_INVALID`

**Причина.** `callback_data` длиннее 64 байт. Кириллица занимает по 2 байта на символ.

**Проверка.**

<!-- troubleshooting:run -->
```python
data = 'order:' + 'заказ-№1234567890' * 3
print(len(data.encode('utf-8')), len(data.encode('utf-8')) <= 64)  # → 78 False
```

**Решение.** Кладите в кнопку короткий ключ (`o:123`), а данные храните на сервере. В кнопке не должно быть прав доступа и секретов.

### 29. Inline-режим не работает: `@бот запрос` ничего не показывает

**Причина.** Inline mode не включён в @BotFather или бот не обрабатывает `inline_query`.

**Проверка.**

```bash
python3 tg.py getMe
```

**Решение.** `supports_inline_queries: false` — включите режим командой `/setinline` в @BotFather. Ответ — не более 50 результатов на запрос.

## Файлы

### 30. `Bad Request: file is too big` при скачивании

**Причина.** Через облачный Bot API бот скачивает файлы до 20 МБ (`getFile`).

**Проверка.** Подставьте `file_id` из update:

```bash
python3 tg.py "getFile?file_id=FILE_ID"
```

**Решение.** Для больших файлов нужен локальный Bot API server, без ограничения размера на скачивание. Отправлять бот может фото до 10 МБ и другие файлы до 50 МБ (через локальный сервер — до 2000 МБ).

### 31. `Bad Request: wrong file identifier/HTTP URL specified`

**Причина.** `file_id` получен другим ботом (он уникален для каждого бота) или URL недоступен для серверов Telegram.

**Проверка.**

```bash
python3 tg.py "getFile?file_id=FILE_ID"
```

**Решение.** Используйте `file_id`, который получил этот же бот, или загрузите файл заново. URL должен открываться из интернета без авторизации.

## Mini App

### 32. Mini App открывается пустым экраном

**Причина.** Страница не по HTTPS или со смешанным содержимым, ошибка JavaScript, неверный путь или кэш старой сборки. HTTP без TLS разрешён только в тестовом окружении.

**Проверка.**

```bash
curl -sSI https://your-app.example.com/ | head -5
```

**Решение.** Откройте URL в обычном браузере и посмотрите консоль. В Telegram Desktop доступен инспектор WebView (Settings → Advanced → Experimental settings → Enable webview inspecting). Проверьте, что `index.html` и ресурсы отдаются с кодом 200.

### 33. `window.Telegram.WebApp` равен `undefined`

**Причина.** Не подключён официальный скрипт `telegram-web-app.js`, или страница открыта вне Telegram.

**Проверка.**

```bash
curl -sS https://your-app.example.com/ | grep -c "telegram.org/js/telegram-web-app.js"
```

**Решение.** Подключите `<script src="https://telegram.org/js/telegram-web-app.js"></script>` в `<head>` до своего кода. В обычном браузере предусмотрите режим без Telegram.

### 34. Сервер отклоняет initData: «Invalid signature»

**Причина.** Подпись проверяется токеном другого бота (часто — основного вместо тестового), строку декодировали дважды, изменили порядок параметров или проверили `initDataUnsafe` вместо исходной строки `initData`.

**Проверка.**

<!-- troubleshooting:run -->
```python
from telegram_patterns import InvalidInitData, validate_init_data

raw = ('auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D'
       '&query_id=test&hash=46d2ea5e32911ec8d30999b56247654460c0d20949b6277af519e76271182803')
print(validate_init_data(raw, '42:TEST', now=1650385342).user_id)  # → 42
try:
    validate_init_data(raw, '43:OTHER', now=1650385342)
except InvalidInitData as error:
    print(error)  # → Invalid signature
```

**Решение.** Передавайте на сервер `Telegram.WebApp.initData` как есть и проверяйте токеном того бота, через которого открыт Mini App.

### 35. initData отклонена как устаревшая

**Причина.** `auth_date` старше допустимого окна: Mini App долго был открыт, или на сервере сбиты часы.

**Проверка.**

<!-- troubleshooting:run -->
```python
from telegram_patterns import InvalidInitData, validate_init_data

raw = ('auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D'
       '&query_id=test&hash=46d2ea5e32911ec8d30999b56247654460c0d20949b6277af519e76271182803')
try:
    validate_init_data(raw, '42:TEST', now=1650385342 + 7200, max_age_seconds=3600)
except InvalidInitData as error:
    print(error)  # → Launch data outside freshness policy
```

**Решение.** Синхронизируйте время сервера (NTP). Выдавайте после проверки собственную короткую сессию, а не принимайте initData бесконечно.

## Платежи

### 36. Оплата зависает на подтверждении

**Причина.** Бот не ответил на `pre_checkout_query`: Bot API ждёт `answerPreCheckoutQuery` не дольше 10 секунд.

**Проверка.**

```python
@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    ok = await orders.can_pay(query.invoice_payload, query.total_amount)  # быстрая проверка заказа
    await query.answer(ok=ok, error_message=None if ok else 'Заказ устарел, оформите его заново')
```

**Решение.** Отвечайте быстро: тяжёлые проверки делайте до выставления счёта. Доступ выдавайте только после `successful_payment`.

### 37. Счёт в Telegram Stars не создаётся

**Причина.** Для Stars валюта должна быть `XTR`, `provider_token` пустым, а в `prices` — ровно одна позиция.

**Проверка.**

<!-- troubleshooting:run -->
```python
from telegram_patterns.aiogram import stars_invoice

invoice = stars_invoice('Доступ на месяц', 'Подписка', 'order-1', 100)
print(invoice.currency, repr(invoice.provider_token), len(invoice.prices))  # → XTR '' 1
```

**Решение.** Используйте эти параметры или `stars_invoice`. Оплату Stars можно свободно проверить в тестовом окружении Telegram.

## Источники

Сверено 2026-10-07 с [Bot API 10.3](https://core.telegram.org/bots/api) (`getUpdates`, `setWebhook`, `getWebhookInfo`, `ResponseParameters`, лимиты `sendMessage`, `getFile`, `InlineKeyboardButton`, `answerCallbackQuery`, `answerPreCheckoutQuery`, локальный Bot API server), [Bot FAQ](https://core.telegram.org/bots/faq), [privacy mode](https://core.telegram.org/bots/features#privacy-mode), [Testing your bot](https://core.telegram.org/bots/features#testing-your-bot), [Mini Apps: initData](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), [Telegram Stars](https://core.telegram.org/bots/payments-stars) и установленным aiogram 3.31.0 (`TelegramRetryAfter`, `TelegramMigrateToChat`, `resolve_used_update_types`).
