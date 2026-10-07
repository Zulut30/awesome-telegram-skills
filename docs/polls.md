# Опросы, quiz и доступные события

Доступно с 0.22.0, проверено на 0.24.0.

Локальный experimental пакет с aiogram >=3.31,<4. Сохраните Bot/Dispatcher/storage проекта; другой SDK не требует миграции ради helper. Ни один constructor не отправляет запрос и не доказывает права.

## Контракты и границы

`PollSpec` копирует 1–12 initial options, question 1–300 characters и option text 1–100 characters. `PollChoice` принимает literal/FormattedText и явное native SDK media. Question/option допускают только custom emoji entities; default сохраняет glyph и удаляет special entity до явно подтвержденного entitlement. UTF-16 offsets относятся к entities, лимиты этих текстов считаются в characters. Все parse modes явно None, включая explanation/description.

Для quiz передайте `correct_option_ids`: непустые уникальные монотонно возрастающие 0-based indices; несколько правильных ответов и multiple answers поддерживаются текущим контрактом. Deprecated `correct_option_id` не создается. Regular не принимает correct IDs/explanation. `allows_revoting=None` оставляет native default, explicit bool сохраняется; shuffle/hide flags поддержаны. Adding options разрешен только nonanonymous regular poll. Explanation 0–200 characters и до двух line feeds, description 0–1024; SDK unions поддерживают native option/description/explanation media. Native models и buffered bytes копируются, но физический файл/URL/codec/metadata принадлежат host; constructor не читает, скачивает и не проверяет контент.

`poll_request` создает один SendPoll. Контекст chat/thread/business задается явно и не подтверждает реальный chat type или права. Members/country restrictions channel-only, country codes — 0–12 unique uppercase pairs, включая FT; проверяется форма, не полная ISO-база. Open period/close date взаимно исключены, 5–2628000 seconds; close date aware и проверяется относительно явного now. Channel direct messages не являются допустимым назначением poll; исходные SDK options вроде protect_content/reply_markup host выбирает непосредственно через текущий SDK.

`PollState` и `PollOptionState` — immutable observations. Optional correct IDs/fields остаются None; reported option voter_count=0 может обозначать неизвестный count и не превращается в доказанные ноль голосов. Full JSON details сохраняют доступные и неизвестные поля; детали не логируются целиком. Локальный incoming bound 1024 не объявляется лимитом Telegram после добавления вариантов.

`PollVote` сохраняет ordinal и persistent IDs, ровно один user/chat voter kind; пустые arrays — retraction. Ordinals могут измениться после удаления/добавления, поэтому идентификация выбранного варианта использует persistent ID. Anonymous voter_chat не раскрывает скрытого user ID. Это не полный voter ledger, не счетчик и не гарантия доставки/порядка Updates.

`PollBinding.from_message` применяется к собственному подтвержденному SendPoll response; произвольный DTO не подтверждает владение. Host сохраняет bot/poll/chat/message/thread/business binding. `poll_events_router` делает fresh lookup перед каждым Poll/PollAnswer/service Message, проверяет scope, kind и анонимность. Lookup должен учитывать текущую host policy. Foreign/unregistered/anonymous-answer events не передаются observer. PollOptionAdded может не иметь poll_message или иметь InaccessibleMessage: exact address можно сопоставить только с host binding, а отсутствие address не позволяет угадать association. Option text entities и неизвестные service поля сохранены в details.

Host observer получает Update ID для durable dedup и прикладного state policy; повтор не увеличивает автоматически votes. Poll updates доступны только для вручную закрытых опросов или опросов, отправленных ботом; PollAnswer — nonanonymous опросы, отправленные самим ботом. Bot API не предоставляет getPoll: не закрывайте опрос для скрытой «сверки». Explicit stopPoll собственному опросу делает текущий SDK после fresh ACL/host receipt; его returned Poll — отдельное наблюдение, а не чтение истории чата.

## Полная композиция

Host `claim` сохраняет scoped pending intent до native send, при replay/pending/unknown возвращает False; он проверяет совпадение payload и current ACL в нужной транзакции. `confirm` атомарно сохраняет binding и receipt, `mark_unknown` сохраняет неопределенный исход. Повтор и restart не разрешают заново sendPoll. Native отказ классифицирует host; пример консервативно сохраняет unknown после ошибки возможной отправки. Cancellation не снимает durable claim. Потеря SendPoll response не может быть автоматически восстановлена несуществующим getPoll или чтением истории через Bot API.

```python
"""Own polls and scoped observations; host owns durable intent, binding and receipts."""
from __future__ import annotations
import asyncio
from typing import Awaitable, Callable, cast
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendPoll
from aiogram.types import Message
from telegram_patterns import InvalidCompletion, InvalidType, safe_error_report
from telegram_patterns.aiogram import (ChatType, PollBinding, PollLookup, PollObserver, PollSpec,
                                      poll_events_router, poll_request)

Authorizer = Callable[[int, int, str], Awaitable[bool]]
Claim = Callable[[Message, SendPoll], Awaitable[bool]]
Confirm = Callable[[Message, PollBinding], Awaitable[None]]
MarkUnknown = Callable[[Message], Awaitable[None]]


def polls_router(authorize: Authorizer, claim: Claim, confirm: Confirm, mark_unknown: MarkUnknown,
                 lookup: PollLookup, observe: PollObserver) -> Router:
    router = Router(name='own-polls-example')
    commands = Router(name='own-polls-commands')
    commands.message.filter(F.chat.type.in_({'private','supergroup'}), F.from_user.is_bot == False)

    async def create(message: Message, spec: PollSpec) -> None:
        if message.from_user is None:
            return
        bot = message.bot
        if bot is None:
            raise InvalidType('Host Dispatcher must mount the message to its Bot')
        if await authorize(message.from_user.id,message.chat.id,'send') is not True:
            await message.answer('Недостаточно прав.',parse_mode=None)
            return
        request = poll_request(spec,chat_id=message.chat.id,chat_type=cast(ChatType,message.chat.type),
                               message_thread_id=message.message_thread_id,
                               business_connection_id=message.business_connection_id)
        # Host persists a scoped intent BEFORE sending. Replay/pending/unknown
        # must return False; a new attempt must never reuse a different payload.
        if await claim(message,request) is not True:
            await message.answer('Запрос уже принят. Проверьте его статус.',parse_mode=None)
            return
        try:
            sent = await bot(request)
            binding = PollBinding.from_message(sent,bot_id=bot.id)
            if binding.kind != spec.kind or binding.is_anonymous != spec.is_anonymous:
                raise InvalidCompletion('Own poll response does not match its request')
            # Host transaction records the binding and confirmed receipt.
            await confirm(message,binding)
        except asyncio.CancelledError:
            await mark_unknown(message)
            raise
        except Exception as error:
            await mark_unknown(message)
            await message.answer(safe_error_report(error,operation='write').message,parse_mode=None)
            return

    @commands.message(Command('poll'))
    async def regular(message: Message) -> None:
        await create(message,PollSpec('Когда встретиться?',['Утром','Днем','Вечером'],is_anonymous=False,
            allows_multiple_answers=True,allows_revoting=True,allow_adding_options=True))

    @commands.message(Command('quiz'))
    async def quiz(message: Message) -> None:
        await create(message,PollSpec('Какие числа четные?',['2','3','4'],kind='quiz',correct_option_ids=[0,2],
            allows_multiple_answers=True,explanation='2 и 4 делятся на 2 без остатка.',shuffle_options=True))

    router.include_router(commands)
    router.include_router(poll_events_router(lookup,observe))
    return router
```

## Проверка и источники

`telegram-patterns plan-recipe demo-polls` показывает требования. `telegram-patterns run-recipe demo-polls --offline` использует закрытый bundled fixture без реального токена/HTTP. Авторские unit/Dispatcher/SQLite/SDK проверки не подтверждают живой Telegram, реальные права, независимую usability или physical rendering. Перед live запуском проверьте текущую конфигурацию бота, допустимые Updates и один основной сценарий с двумя пользователями, правами/анонимностью и негативным случаем. Не запускайте второй getUpdates consumer.

Проверены 05.10.2026 Bot API 10.3 и aiogram 3.31.0: [sendPoll](https://core.telegram.org/bots/api#sendpoll), [Poll](https://core.telegram.org/bots/api#poll), [PollAnswer](https://core.telegram.org/bots/api#pollanswer), [PollOptionAdded](https://core.telegram.org/bots/api#polloptionadded), [Update](https://core.telegram.org/bots/api#update), [stopPoll](https://core.telegram.org/bots/api#stoppoll).
