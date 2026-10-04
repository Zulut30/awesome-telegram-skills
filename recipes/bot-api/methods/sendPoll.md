# sendPoll

[Официальные ограничения](https://core.telegram.org/bots/api#sendpoll). SDK: aiogram 3.31.0 / SendPoll.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'question': 'FIXTURE_REPLACE', 'options': [{'text': 'FIXTURE_REPLACE'}]}
request = build_request("sendPoll", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `question`, `options`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_thread_id`, `question`, `question_parse_mode`, `question_entities`, `options`, `is_anonymous`, `type`, `allows_multiple_answers`, `allows_revoting`, `shuffle_options`, `allow_adding_options`, `hide_results_until_closes`, `members_only`, `country_codes`, `correct_option_ids`, `explanation`, `explanation_parse_mode`, `explanation_entities`, `explanation_media`, `open_period`, `close_date`, `is_closed`, `description`, `description_parse_mode`, `description_entities`, `media`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`, `reply_parameters`, `reply_markup`.
