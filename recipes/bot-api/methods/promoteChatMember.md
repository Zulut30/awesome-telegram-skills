# promoteChatMember

[Официальные ограничения](https://core.telegram.org/bots/api#promotechatmember). SDK: aiogram 3.31.0 / PromoteChatMember.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'user_id': 1}
request = build_request("promoteChatMember", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `user_id`.

Все параметры официального снимка: `chat_id`, `user_id`, `is_anonymous`, `can_manage_chat`, `can_delete_messages`, `can_manage_video_chats`, `can_restrict_members`, `can_promote_members`, `can_change_info`, `can_invite_users`, `can_post_stories`, `can_edit_stories`, `can_delete_stories`, `can_post_messages`, `can_edit_messages`, `can_pin_messages`, `can_manage_topics`, `can_manage_direct_messages`, `can_manage_tags`, `can_send_welcome_messages`.
