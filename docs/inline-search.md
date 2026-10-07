# Inline-поиск и персональная пагинация

Доступно с 0.22.0, проверено на 0.24.0.

Локальный experimental пакет с aiogram >=3.31,<4. Существующие SDK, Bot/Dispatcher и хранилище сохраняются; inline mode отличается от inline-кнопок. В другом SDK используйте его типы и сверяйте контракт. Пакет не предполагается опубликованным в PyPI.

## Контракты и границы

`InlineItem` содержит stable ID (1–64 UTF-8 bytes), title/description и literal `str` либо `FormattedText`. По умолчанию `shareable=False`: запись исключается до поиска и ACL. Выбор результата отправляет его в выбранный чат; `is_personal=True` ограничивает серверный кеш Telegram по пользователю, но не делает отправленный текст приватным. Не выдавайте секреты или личную заметку как shareable автоматически. ACL проверяет сервер; название private/sender не дает ID партнера чата. Unknown `chat_type=None` требует отдельного явного решения.

`InlineSearch` копирует до 10000 items — это локальный bound, не ограничение Telegram. Передайте host-owned persistent secret (32–128 bytes), catalog revision и async authorizer. Поиск strip/casefold ищет по title/description/content, использует 1–50 результатов и не раскрывает unshareable записи. Современный `answerInlineQuery` принимает не более 50 результатов и offset до 64 bytes. Page связан с bot/actor/query ID/normalized query/chat_type; нельзя ответить им на другую query. Native articles создаются заново, `parse_mode=None` не наследует HTML default. Emoji fallback сохраняет glyph; custom emoji entities включаются только при явно проверенных metadata/entitlement.

Personal cursor — HMAC с bot/actor/query/context, catalog revision/content/order/page size и permission revision. Секрет не хранит библиотека; его ротация инвалидирует старые cursors. Цепочка сохраняет первоначальное expiry; next page не продлевает TTL. ACL проверяется заново для remaining items. Host permission revision проверяется до и после поиска, но это не атомарная транзакция прав с внешним Telegram. Крупное хранилище, индексы, isolation, concurrency и rate limits принадлежат приложению.

`InlineCachePolicy` default: cache_time=0, is_personal=True. Положительный cache_time может вернуть прежний результат без нового Update и ACL после отзыва роли; для ограниченных текущими правами данных оставляйте 0, как в примере. Shared cache разрешен лишь для `public_catalog=True`, без actor authorizer/revision и с разрешением всех chat contexts. Shared cursor допускает другого actor/context, поскольку Telegram может переиспользовать ответ; он сохраняет bot/query/catalog/expiry scope. Cache TTL не превышает cursor TTL; локальный maximum 86400 не объявляется лимитом Bot API.

`inline_query_router` встраивается в текущий Dispatcher. Deadline (по умолчанию 2 секунды, локально до 60) охватывает catalog provider/ACL/revision, а не native answer. Denied/stale/search-timeout дает пустой personal answer с cache=0; stale cursor не сбрасывает выдачу на начало. Storage/programming ошибки и внешняя cancellation доходят до host error handler. Один native answer без retry; lost response имеет неизвестный исход, False confirmation — явная ошибка.

Для реального inline mode включите `/setinline` в BotFather; `/setinlinefeedback` — отдельная настройка необязательного sampling. `ChosenInlineResult` может отсутствовать из-за настроек или кеша: отсутствие не доказывает, что результат не отправлен. Feedback не должен выдавать доступ, проводить оплату или становиться полной аналитикой доставок. Host выбирает allowed_updates, privacy/logging policy и управление секретом.

## Полная композиция

Передайте host loader, текущий authorizer, permission revision и persistent cursor secret, затем добавьте возвращенный Router в текущий Dispatcher. Loader возвращает revision и snapshot; предметные роли не находятся в callback/query text.

```python
"""Attach shareable-note search; host supplies catalog, ACL and a persistent secret."""
from __future__ import annotations
from typing import Awaitable, Callable, Sequence
from aiogram import Router
from aiogram.types import ChosenInlineResult, InlineQuery
from telegram_patterns.aiogram import InlineAuthorizer, InlineItem, InlineSearch, inline_query_router

CatalogLoader = Callable[[int], Awaitable[tuple[str, Sequence[InlineItem]]]]
PermissionRevision = Callable[[int], Awaitable[str]]
FeedbackObserver = Callable[[ChosenInlineResult], Awaitable[None]]


def inline_search_router(load_catalog: CatalogLoader, authorize: InlineAuthorizer,
                         permission_revision: PermissionRevision, *, cursor_secret: bytes,
                         page_size: int = 20, feedback: FeedbackObserver | None = None) -> Router:
    async def provider(query: InlineQuery) -> InlineSearch:
        revision, items = await load_catalog(query.from_user.id)
        # Items are explicitly shareable. A chosen item is sent to a chat partner,
        # even with is_personal=True; private notes must retain shareable=False.
        # cache_time=0 keeps restricted results from Telegram's reusable cache.
        return InlineSearch(items, secret=cursor_secret, revision=revision, page_size=page_size,
                            allowed_chat_types=('sender', 'private', 'group', 'supergroup', 'channel'))

    router = inline_query_router(provider, authorize=authorize, permission_revision=permission_revision)
    if feedback is not None:
        @router.chosen_inline_result()
        async def chosen(result: ChosenInlineResult) -> None:
            # Optional observation only. Absence of feedback never proves that
            # nothing was sent; this callback must not grant access or charge.
            await feedback(result)
    return router
```

## Проверка и источники

`telegram-patterns plan-recipe demo-inline-search` показывает требования. `telegram-patterns run-recipe demo-inline-search --offline` использует закрытый bundled fixture без реального токена/HTTP. Авторские unit/Dispatcher/SQLite/SDK проверки не подтверждают живой Telegram, реальные права, независимую usability или physical rendering. Перед live запуском проверьте текущую конфигурацию бота, допустимые Updates и один основной сценарий с двумя пользователями, правами/анонимностью и негативным случаем. Не запускайте второй getUpdates consumer.

Проверены 05.10.2026 Bot API 10.3 и aiogram 3.31.0: [InlineQuery](https://core.telegram.org/bots/api#inlinequery), [answerInlineQuery](https://core.telegram.org/bots/api#answerinlinequery), [article](https://core.telegram.org/bots/api#inlinequeryresultarticle), [text content](https://core.telegram.org/bots/api#inputtextmessagecontent), [feedback](https://core.telegram.org/bots/inline#collecting-feedback).
