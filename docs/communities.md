# Сообщества

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Сообщество (Community, Bot API 10.2+) — несколько супергрупп, каналов и ботов, связанных общей темой или аудиторией. Участники сообщества видят его видимые чаты и вступают в них без пригласительной ссылки. Скрытые чаты видят только администраторы сообщества и участники самого чата. По умолчанию добавлять чаты может любой участник; если администраторы это ограничили, добавление становится предложением ([объявление Telegram, 14 июля 2026](https://telegram.org/blog/communities-editor-invisible-messages)).

## Что видит бот

| Событие | Где приходит | Поле |
| --- | --- | --- |
| Чат или бот добавлен в сообщество | сервисное сообщение в этом чате | `Message.community_chat_added` → [CommunityChatAdded](https://core.telegram.org/bots/api#communitychatadded) `.community` |
| Чат или бот удален из сообщества | сервисное сообщение в этом чате | `Message.community_chat_removed` — [CommunityChatRemoved](https://core.telegram.org/bots/api#communitychatremoved) без полей |
| Пользователь вступил в чат из сообщества (10.3) | сервисное сообщение в этом чате | `Message.community_chat_joined` → [CommunityChatJoined](https://core.telegram.org/bots/api#communitychatjoined) `.community` |
| Текущее сообщество чата | ответ `getChat` | `ChatFullInfo.community` |

[Community](https://core.telegram.org/bots/api#community) содержит `id` и `name`. Идентификатор может занимать больше 32 бит (до 52): храните его 64-битным целым, а не 32-битным.

Сервисные сообщения в группах бот получает при любом privacy mode ([Bot FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get)); в канале бот состоит только администратором, и событие приходит как `channel_post`. В aiogram 3.31.0 это фильтры `F.community_chat_added`, `F.community_chat_removed`, `F.community_chat_joined` и типы содержимого `ContentType.COMMUNITY_CHAT_*`; регистрируйте обработчики и для `message`, и для `channel_post`.

## Границы прав

- Bot API не создает сообщество, не добавляет и не удаляет чаты, не перечисляет чаты и участников сообщества и не сообщает роль пользователя в нем. Бот знает о сообществе только из сервисных сообщений в чатах, где он состоит, и из `getChat` для конкретного чата.
- Принадлежность к сообществу не дает прав. Права бота и инициатора проверяйте в каждом чате отдельно через `getChatMember`; разрешение, выданное в одном чате сообщества, не переносите на другой.
- `CommunityChatRemoved` не называет сообщество. Чтобы знать, откуда удален чат, храните связь из `community_chat_added`; `getChat` показывает только текущее сообщество чата.
- Сервисное сообщение может быть пропущено: бот не состоял в чате, update потерян или обработчик упал. Сверяйте сохраненную связь с `ChatFullInfo.community` — по команде, при старте или перед действием, которое от нее зависит.
- Вступление из сообщества идет без пригласительной ссылки, поэтому учет по `invite_link` в [ChatMemberUpdated](https://core.telegram.org/bots/api#chatmemberupdated) не отнесет его ни к одной ссылке. Факт членства берите из `chat_member` (бот-администратор и `allowed_updates`), а `community_chat_joined` — как источник прихода. Как вступление из сообщества сочетается с заявками на вступление, Bot API не описывает: проверьте в тестовой группе.

## Рецепт

```python
from community_bot import attach_community_events

attach_community_events(dispatcher, save=save_link, joined=count_arrival)
```

`save(chat_id, community)` сохраняет связь чата с сообществом (`None` — чат удален), `joined(chat_id, user_id, community)` учитывает приход участника; боты не учитываются. Команда `/community` в группе читает `getChat`, исправляет сохраненную связь и отвечает названием сообщества.

`telegram-patterns run-recipe demo-community --offline` выполняет пример на настоящем `Dispatcher` без сети: добавление супергруппы и канала, приход участника и отказ учитывать бота, удаление без полей, сверку пропущенного события через `getChat`, 52-битный идентификатор и сохранность существующего обработчика `/help`. Доставку сервисных сообщений, скрытые чаты и вступление по заявке офлайн-проверка не подтверждает: проверьте в тестовом сообществе со вторым аккаунтом.

Источники: [Community](https://core.telegram.org/bots/api#community), [CommunityChatAdded](https://core.telegram.org/bots/api#communitychatadded), [CommunityChatRemoved](https://core.telegram.org/bots/api#communitychatremoved), [CommunityChatJoined](https://core.telegram.org/bots/api#communitychatjoined), [ChatFullInfo](https://core.telegram.org/bots/api#chatfullinfo), [Bot FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get), [объявление Telegram](https://telegram.org/blog/communities-editor-invisible-messages). Проверено 7 октября 2026 года по Bot API 10.3 и aiogram 3.31.0.
