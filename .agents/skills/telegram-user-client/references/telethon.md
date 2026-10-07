# Telethon и сессии

Первичные источники: [Telethon](https://docs.telethon.dev/en/stable/), [client reference](https://docs.telethon.dev/en/stable/modules/client.html), [signing in](https://docs.telethon.dev/en/stable/basic/signing-in.html), [session storage](https://docs.telethon.dev/en/stable/concepts/sessions.html).

Используйте `api_id`, `api_hash` и авторизованную user session. Для аккаунта с 2FA предусмотрен соответствующий вход; credentials не должны появляться в исходниках или выводе диагностики. `api_id/api_hash` не заменяют пользовательскую авторизацию.

Типичные операции: `get_me`, `iter_dialogs`, `iter_messages`, `get_entity`, events новых/измененных/удаленных сообщений. Перед использованием сверяйте сигнатуры установленной версии. Не смешивайте `telethon.sync` со случайно вложенным event loop в async backend.

Каждая параллельная session должна иметь понятного владельца процесса; совместное использование SQLite-файла может вызывать блокировки. Для масштабирования выберите модель владения аккаунтом до запуска нескольких workers.

Telethon — библиотека сообщества поверх MTProto. Официальный клиентский фундамент Telegram — [TDLib](https://core.telegram.org/tdlib). [Pyrogram](https://docs.pyrogram.org/) сообщает о прекращении поддержки; не выбирайте оригинальный пакет для нового проекта без учета этого состояния. Поддержка форков проверяется отдельно.
