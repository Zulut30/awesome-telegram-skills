# Безопасный конструктор сообщений

Доступно с 0.19.0, проверено на 0.24.0.

Термины: **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **entitlement** — право на возможность (custom emoji, оплаченный доступ), которое проверяется отдельно от самого запроса; **fallback** — запасной вариант, если основная возможность недоступна.

Core `telegram_patterns` работает без aiogram. Для имеющегося aiogram-проекта используйте установленный локальный wheel с aiogram extra; сохраняйте текущий Dispatcher, middleware, storage и язык проекта. Публикация в PyPI/npm не заявлена. Другой SDK принимает те же JSON text/entities через свой официальный adapter.

## Контракт

| API | Результат / отказ / владение |
| --- | --- |
| `EntityKind` | Literal: `bold`, `italic`, `underline`, `strikethrough`, `spoiler`, `code`, `pre`, `text_link`, `custom_emoji`, `blockquote`, `expandable_blockquote`. Это часть форматирования для исходящих сообщений, а не разбор всех входящих entities и не Rich Message API. `date_time`, `text_mention` и остальные типы остаются у SDK проекта |
| `TextEntity(kind, offset, length, url=None, language=None, custom_emoji_id=None)` | Frozen descriptor; целые UTF-16 units, offset ≥0, length >0; bool отвергается. Дополнительные metadata разрешены только своему типу. `.as_dict()` возвращает свежий Bot API JSON |
| `FormattedText(text, entities=())` | Frozen текст и sorted tuple snapshot. Проверяются bounds/scalar boundaries, дубликаты, crossing ranges и допустимая вложенность. Raw offsets задаются в UTF-16, а не Python index/UTF-8 bytes. Отдельный TextEntity не подтверждает границу до помещения в FormattedText |
| `MessageBuilder(value=FormattedText(''))` | Immutable fluent `.text(literal)`, `.style(literal,kind,url=...,language=...,custom_emoji_id=...)`, `.append(FormattedText)`, `.custom_emoji(fallback,id)`, `.build()`. Каждая операция возвращает новый builder; исходный объект сохраняется даже при ошибке. Append сдвигает spans по UTF-16; пользовательский текст никогда не становится разметкой |
| `utf16_length(text)` | int units; malformed surrogate, C0 controls кроме tab/CR/LF и локальный overflow → ValueError. Неверный тип → TypeError. Unicode normalization не выполняется |
| `escape_html(literal)` | Экранирует `<`, `>`, `&`, quotes/apostrophe; HTML literal в тексте или quoted attribute. Это не URL trust check, DOM sanitizer или прием произвольной разметки. Повторное экранирование меняет отображение |
| `escape_markdown_v2(literal, context='text')` | text — все reserved symbols и backslash; code — backtick/backslash внутри code/pre; link — closing parenthesis/backslash внутри destination. Неверный context → ValueError. Выбор контекста принадлежит вызывающему коду; не экранируйте целый готовый template как literal |
| `TextPayload` / `.as_kwargs(limit=4096, custom_emoji_entitlement_verified=False)` | Свежий JSON text/entities/parse_mode=None; явный None подавляет default HTML/MarkdownV2 текущего SDK. Text empty/whitespace-only, превышение limit или >100 entities → ValueError. В SDK использован SendMessage.model_validate; не смешивайте entities с ненулевым parse_mode |
| `split_formatted(value,limit=4096)` / `.split(limit=...)` | tuple полностью проверенных и отправляемых фрагментов; concat texts равен исходнику byte-for-byte в UTF-8. Разрыв делается после перевода строки, затем после пробела, если так занята хотя бы половина лимита; одинаковые стили после обрезки вложенных диапазонов схлопываются. Стили, code/pre пересекаются и rebased, language сохраняется. Ссылки, обе quotes и custom emoji переносятся целиком; oversized atomic block → ValueError. Все chunks вычисляются до возвращения, функция ничего не отправляет |

Локальные ограничения: composition ≤262144 UTF-16 units, ≤512 entities, ≤256 chunks; one payload/chunk ≤100 entities. Limit — точный int 1..4096. Это консервативная политика библиотеки, а не утверждение обо всех лимитах Telegram. Для caption выберите 1024 и переименуйте `text/entities` в `caption/caption_entities` через текущий SDK: payload по умолчанию относится к сообщению. Empty composition split дает пустой tuple, `.as_kwargs()` отвергает пустую отправку.

Style spans могут быть вложены друг в друга и в поддерживаемые прочие spans; code/pre не пересекаются с другими. Прочие non-style spans не вкладываются друг в друга. Raw entities обязаны иметь целые scalar boundaries; crossing ranges запрещены. Конструктор не исправляет произвольные offsets молча.

Разбиение не разрезает суррогатные пары, комбинируемые знаки, распространенные emoji с ZWJ, флаги, селекторы вариантов, модификаторы, последовательности тегов и keycap и CRLF. Это ограниченная явная политика, не полная Unicode UAX #29 segmentation для всех письменностей/версий Unicode. Если обязательна полная extended-grapheme сегментация, host сам группирует целые graphemes в допустимые по UTF-16 chunks подходящим Unicode инструментом, затем строит payload каждой части через .as_kwargs() без вызова нашего .split(); нельзя обещать full UAX29 по этим проверкам. Непомещающаяся сохраняемая последовательность отклоняется без потери текста. Фрагмент только из пробельных символов (Telegram его не принимает) присоединяется к соседнему или забирает у него край без разрезания ссылок, цитат и custom emoji; если пробельная серия длиннее лимита и так сделать нельзя, возвращается ValueError — текст не теряется и не дополняется искусственным содержимым.

Custom emoji по умолчанию остаются буквальным regular emoji fallback без custom span. Для явного opt-in host проверяет entitlement бота и контекст непосредственной отправки, реальный sticker ID и его валидный regular emoji fallback по metadata `getCustomEmojiStickers`; placeholder ID fixture не доказывает наличие/права. Core проверяет форму ID/range (fallback ≤32 units), не Unicode emoji registry, metadata или Telegram Premium. `custom_emoji_entitlement_verified=True` не добывает эти сведения и не обходит ограничения API. Host не устанавливает флаг на основе присутствия SDK-поля.

HTTP(S) link destination должен быть абсолютным, без credentials/backslash/whitespace, ≤2048 символов; проверка не выполняет HTTP и не подтверждает безопасный домен, отсутствие tracking или доступ. tg:// links и text_mention в этой версии не принимаются этим helper: для native сценария используйте SDK и соответствующие permission/privacy условия.

## Полная композиция с существующим Dispatcher

Пример явно принимает только обычный private chat: группы, темы (включая private forum) и Business markers отвергаются до отправки. Formatter SDK-free; для другого контекста host выбирает собственный handler и сохраняет соответствующие routing parameters.

Сохраните блок как `message_text_bot.py` и вызовите `attach_reports(current_dispatcher)`. Модуль не запускает polling, не создает новую БД или обязательный сервис. Пример показывает только общедоступный synthetic отчет; реальные приватные записи требуют server-owned scope/ACL проекта. Delivery нескольких chunks может закончиться после успешного префикса: timeout/unknown не разрешает автоматический повтор всего отчета. Durable outbox и reconciliation относятся к отдельному прикладному сценарию; builder не обещает exactly-once Telegram delivery.

```python
"""Attach a literal report handler to the host Dispatcher; no polling on import."""
from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.methods import SendMessage
from telegram_patterns import FormattedText, MessageBuilder


def compose_report(name: str, notes: str, *, emoji_id: str | None = None) -> tuple[FormattedText, ...]:
    # Both values are literal, even when they contain Telegram markup.
    builder = MessageBuilder().style('Отчет\n', 'bold').text('Имя: ').style(name, 'italic')
    builder = builder.text('\nЗаметки:\n').text(notes).text('\n').style('Документация', 'text_link', url='https://core.telegram.org/bots/api')
    if emoji_id is not None:
        # Host inspects sticker metadata to choose its valid regular emoji fallback.
        builder = builder.text(' ').custom_emoji('👍', emoji_id)
    return builder.build().split()


def attach_reports(dispatcher: Dispatcher) -> Router:
    router = Router(name='message-report')

    private = (F.chat.type == 'private') & (F.message_thread_id == None) & (F.is_topic_message != True) & (F.business_connection_id == None)
    @router.message(Command('report'), private)
    async def report(message: Message):
        if message.from_user is None or message.from_user.is_bot:
            return
        # Example policy: only a public synthetic report, no private records/ACL claim.
        chunks = compose_report(message.from_user.full_name, '<b>буквальный текст</b> *_ [] & 😀\n' * 160)
        for chunk in chunks:
            # Explicit None overrides host HTML/MarkdownV2 defaults. SDK validates JSON.
            # Delivery may stop after a partial prefix. Never retry the whole sequence blindly.
            await message.bot(SendMessage.model_validate({'chat_id': message.chat.id, **chunk.as_kwargs()}))

    dispatcher.include_router(router)
    return router
```

## Проверка и источники

Тестируйте внедрение разметки, символы вне базовой плоскости перед entities, неверные диапазоны и диапазоны посреди символа, вложенность, текст длиннее 4096 и 1024 единиц, неделимый блок больше лимита, запасной вариант для custom emoji и `parse_mode` по умолчанию. Сравните исходные/собранные texts и style coverage; SDK fixture должна сериализовать каждую entity и не выполнять HTTP. Проверка partial delivery требует остановки после unknown chunk. Copied guide выполняется через установленный wheel в отдельном consumer; это авторская SDK/mock приемка, не live rendering, реальные устройства или независимая оценка навыка.

Проверено 2026-10-05 только указанное содержание: [Bot API formatting](https://core.telegram.org/bots/api#formatting-options), [MessageEntity UTF-16/metadata](https://core.telegram.org/bots/api#messageentity), [sendMessage text/entities/parse_mode](https://core.telegram.org/bots/api#sendmessage), HTML/MarkdownV2 escaping contexts и custom emoji fallback/entitlement в этих разделах Bot API 10.3. Установленный aiogram 3.31.0 принимает JSON entities и явный parse_mode=None; его фактические модели и BaseSession.prepare_value использованы в fixtures. Весь Bot API, rich messages, новые date-time entities, live rights и Unicode emoji registry в этом проходе не перепроверялись.
