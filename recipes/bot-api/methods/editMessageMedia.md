# editMessageMedia

[Официальные ограничения](https://core.telegram.org/bots/api#editmessagemedia). SDK: aiogram 3.31.0 / EditMessageMedia.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'media': {'media': 'FIXTURE_REPLACE', 'type': 'animation'}}
request = build_request("editMessageMedia", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `media`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_id`, `inline_message_id`, `media`, `reply_markup`.
