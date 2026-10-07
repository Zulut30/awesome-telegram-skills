# Проверка initData

Перед изменением алгоритма сверьте [официальную схему Telegram](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app). Для существующего aiogram есть [WebApp utils](https://docs.aiogram.dev/en/latest/utils/web_app.html).

## HMAC на сервере владельца бота

Разберите URL-encoded строку в пары с однократным декодированием. Сохраните полученные строковые значения без повторной JSON-сериализации. Отклоняйте неоднозначные дубли, отсутствующие обязательные поля и неверный формат подписи.

Исключите `hash`, отсортируйте остальные поля по имени и соедините `key=value` через LF (`\n`). Если присутствует `signature`, в HMAC-пути она остается подписанным полем. Не переносите исключение `signature` из Ed25519-пути в HMAC.

```text
secret_key = HMAC_SHA256(key = UTF8("WebAppData"), message = UTF8(bot_token))
expected = HMAC_SHA256(key = secret_key, message = UTF8(data_check_string))
```

Первый результат используйте как байты, а не hex-строку. Сравните ожидаемые байты с декодированным `hash` в constant time. Проверьте `auth_date` с серверным временем и явно заданной политикой свежести.

## Проверка третьей стороной (Ed25519)

Если проверяющей стороне нельзя раскрывать токен бота, используйте [схему для третьей стороны](https://core.telegram.org/bots/webapps#validating-data-for-third-party-use): ей нужны только `bot_id` и публичный ключ Telegram. Не передавайте токен бота сторонней службе ради проверки.

- Поле `signature` — подпись Ed25519 в base64url (64 байта, 86 символов без `=`).
- Строка для проверки: `<bot_id>:WebAppData`, перевод строки, затем все поля, кроме `hash` и `signature`, отсортированные по имени, в виде `key=value` через LF.
- Ключи Telegram (hex): боевое окружение `e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d`, тестовое — `40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec`. Ключ тестового окружения не принимает боевые данные, и наоборот.
- После подписи так же проверьте `auth_date` и разберите `user` как JSON-объект с положительным `id`.

```text
data_check_string = "<bot_id>:WebAppData\n" + join("\n", sorted("key=value" для всех полей, кроме hash и signature))
Ed25519_verify(public_key, UTF8(data_check_string), base64url_decode(signature))
```

Проверку выполняйте проверенной криптографической библиотекой: в Python — `cryptography` (так делает и `aiogram.utils.web_app_signature`), в браузере и Node 20+ — WebCrypto (`crypto.subtle`, алгоритм `Ed25519`). Для теста возьмите вектор, подписанный не вашим кодом, например из тестов aiogram с их собственным ключом.

Если в проекте уже есть awesome-telegram-patterns: `validate_init_data_signature(raw, bot_id, environment='production')` в Python (extra `signature`) и `verifyInitDataSignature(raw, botId, {environment: 'production'})` в TypeScript возвращают тот же проверенный результат, что и HMAC-проверка; без `cryptography` или Ed25519 в WebCrypto они сообщают `UnsupportedCapability`, а не успех.

При офлайн-разработке пометьте совместимость с живыми данными Telegram как непроверенную: настоящая `initData` подписана закрытым ключом Telegram, и без запуска Mini App ее не получить.
