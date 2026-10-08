# Медиа-компоненты

Доступно с 0.20.0, проверено на 0.24.0.

Термины: квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **entitlement** — право на возможность (custom emoji, оплаченный доступ), которое проверяется отдельно от самого запроса; **fallback** — запасной вариант, если основная возможность недоступна.

Для установленного локального wheel `awesome-telegram-patterns` с aiogram extra. Сохраняйте текущий Bot, Dispatcher, storage, middleware и стек. Core не получает SDK-зависимость. Пакеты не опубликованы в PyPI/npm.

## Контракты

| API | Результат, ошибки, побочные эффекты |
| --- | --- |
| `MediaKind`, `MediaSendRequest` | Literal photo/video/audio/document и union SendPhoto/SendVideo/SendAudio/SendDocument; другие native виды остаются у SDK |
| `MediaFile(kind, reference, filename=None, bot_id=None, width=None, height=None)` | Frozen bytes upload или opaque file_id с обязательным исходным bot_id. Upload требует basename и 1..10 MB для photo либо 1..50 MB для остальных; decimal bytes. Dimensions — обе, только photo upload; сумма ≤10000, ratio ≤20, exact int. Host измеряет их выбранным codec parser. `.as_input(bot_id)` дает свежий BufferedInputFile либо same-bot ID. Type/bounds/metadata mismatch → TypeError/ValueError; unsupported kind → UnsupportedCapability |
| `MediaItem(file, caption=None, spoiler=False, caption_above=False)` | Frozen источник и optional FormattedText. Caption ≤1024 UTF-16 units, ≤100 entities без обрезки; empty/whitespace допустимы. Flags exact bool, spoiler/above только photo/video. `.caption_kwargs(custom_emoji_entitlement_verified=False)` дает свежие caption/caption_entities/parse_mode=None; regular fallback по умолчанию. `.as_input_media(bot_id,...)` — свежий native объект |
| `media_request(item, *, bot_id, chat_id, message_thread_id=None, custom_emoji_entitlement_verified=False)` | Один native send request; не отправляет и не читает файл. Сохраняет явный thread ID. Chat — nonzero integer <2**52 по модулю или @username; IDs exact integers. Права/актуальный контекст у host |
| `media_album(items, *, bot_id, chat_id, message_thread_id=None, custom_emoji_entitlement_verified=False)` | SendMediaGroup, 2..10 элементов в list/tuple. Photo/video могут смешиваться; audio и document только со своим типом. Неверный состав или cross-bot file_id отклоняется до отправки. Один request, без молчаливого batching/splitting |
| `media_edit(item, *, bot_id, chat_id=None, message_id=None, inline_message_id=None, album_kind=None, custom_emoji_entitlement_verified=False)` | EditMessageMedia. Ровно один адрес: chat/message либо inline ID. Inline upload отвергается, same-bot file_id допускается. album_kind photo-video/document/audio задается по серверному объекту host и ограничивает replacement. Это guard входа, не проверка owner/ACL/edit deadline |
| `download_media(bot, file_id, *, max_bytes=5000000, timeout=30)` | Явная async read: GetFile и streaming в памяти. Bound 1..20000000 decimal bytes, total deadline 0<timeout≤300 секунд. Declared oversize отклоняется до stream, фактическое превышение лимита, несовпадение размера, пустой файл или фрагмент неподдерживаемого типа — `ValueError`. Stream закрывается при успехе, ошибке, timeout и cancellation. HTTP и транспортные ошибки потока заменяются на TransportFailure («HTTP 404») или TimeoutError без URL с token и без исходного исключения в цепочке traceback. Возвращает DownloadedMedia. Не закрывает host Bot/session и не выполняет retry |
| `DownloadedMedia(data, file_id, file_unique_id, bot_id)` | Frozen bytes и bot identifiers; максимум 20 MB. Без URL/file_path; repr скрывает bytes и IDs. Создание DTO само по себе не подтверждает Telegram/source/auth. file_unique_id нельзя отправлять или скачивать |

Bytes upload — snapshot, а не проверка codec, MIME, malware, архивов или содержимого PDF. Имя, расширение и MIME не доказывают формат. Host использует свой parser, ограничивает размер/распаковку/длительность/ресурсы и выбирает преобразование по задаче. Локальные photo dimensions могут отсутствовать: тогда корректность проверяет host/Telegram. Компонент не обещает, что произвольные bytes станут фото/видео/audio. Unsupported/corrupt content может вернуться TelegramBadRequest; проверка ловит IMAGE_PROCESS_FAILED как synthetic SDK error, не live decode acceptance.

Обычная отправка server-approved bytes не требует FFmpeg, Pillow, очереди или Local Bot API. Для такого pipeline выбирайте явную потребность и existing tools. Файл хранится/передается только после auth/ACL и с учетом retention проекта; код downloader ничего не записывает на диск. max_bytes ограничивает одну операцию, не concurrency/общую память процесса; host ограничивает параллелизм. Custom emoji opt-in требует реальных metadata, валидного regular fallback, entitlement и контекста.

File ID host получает из SDK объекта именно этого бота и сохраняет вместе с исходным видом media. Невозможно надежно определить по строке, что пользователь подставил file_unique_id либо ID другого media kind: declared kind/bot scope не являются доказательством. Повтор file_id не меняет тип медиа и не подпадает под upload byte limits. HTTP URL/attach:// и filesystem path нельзя подавать в MediaFile как ID. Для URL и `FSInputFile`, живых фото, анимаций, миниатюр, параметров Business, личных сообщений канала и временных сообщений используйте SDK напрямую в проверенном контексте проекта; helper не переопределяет весь Bot API.

Hosted downloader разрешает только относительный ASCII file_path из GetFile, исключает absolute/traversal/URL/encoded path. Token-bearing URL создается внутри вызова и не возвращается/не логируется; не печатайте raw SDK exceptions. GetFile может не сохранить filename/MIME: исходные непроверенные metadata остаются у host. Local Bot API сервер может вернуть абсолютный путь; этот helper явно отказывает до GetFile и не читает его. Local API/большие файлы требуют отдельного выбранного adapter и storage policy.

## Полная композиция

Сохраните блок как `media_bot.py`, вызовите `attach_media(current_dispatcher)`. Он принимает обычный private chat; group, thread/private forum и Business markers отклоняются до отправки/скачивания. Synthetic public PNG/text не требуют доступа к приватным записям; заменяя их реальными данными, добавьте текущий host ACL и object scope.

Sending нескольких requests может завершиться после успешного префикса. Timeout/unknown не разрешает повтор всего demo; прикладная durable outbox/reconciliation задается отдельно. Telegram 429/retry_after, permission, bad format и unknown receipt проверены synthetic SDK exceptions; helper не выбирает автоматическую retry policy. Downloader — read, send/edit — write; `safe_error_report` показывает безопасную категорию без token/path/user payload.

```python
"""Attach media examples to the existing Dispatcher; no polling on import."""
import base64
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from telegram_patterns import MessageBuilder, safe_error_report
from telegram_patterns.aiogram import MediaFile, MediaItem, media_request, media_album, media_edit, download_media

# Public synthetic fixtures. Real uploads need the host's content/codec checks.
PHOTO = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=')
DOCUMENT = b'Telegram media example.\n'


async def send_media_demo(bot: Bot, chat_id: int) -> None:
    caption = MessageBuilder().text('😀 ').style('Фото <буквально>_*', 'bold').build()
    photo = MediaItem(MediaFile('photo', PHOTO, filename='sample.png', width=1, height=1), caption)
    document = MediaItem(MediaFile('document', DOCUMENT, filename='sample.txt'),
                         MessageBuilder().text('Документ без потери исходных байтов').build())
    await bot(media_request(photo, bot_id=bot.id, chat_id=chat_id))
    await bot(media_request(document, bot_id=bot.id, chat_id=chat_id))
    messages = await bot(media_album([photo, photo], bot_id=bot.id, chat_id=chat_id))
    # These IDs come from this bot's own response, not a user callback.
    await bot(media_edit(photo, bot_id=bot.id, chat_id=chat_id,
                         message_id=messages[0].message_id, album_kind='photo-video'))
    # A network timeout propagates. Never retry the whole sequence blindly.


def attach_media(dispatcher: Dispatcher) -> Router:
    router = Router(name='media-examples')
    ordinary_private = ((F.chat.type == 'private') & (F.message_thread_id == None)
                        & (F.is_topic_message != True) & (F.business_connection_id == None))

    @router.message(Command('media'), ordinary_private)
    async def demo(message: Message, bot: Bot) -> None:
        if message.from_user is None or message.from_user.is_bot:
            return
        await send_media_demo(bot, message.chat.id)

    @router.message(F.document, ordinary_private)
    async def receive(message: Message, bot: Bot) -> None:
        if message.from_user is None or message.from_user.is_bot or message.document is None:
            return
        # Bounded explicit read, not arbitrary filesystem access or a URL fetch.
        # The user's filename/MIME is not a trusted storage path or content type.
        try:
            result = await download_media(bot, message.document.file_id, max_bytes=1_000_000)
        except Exception as error:
            report = safe_error_report(error, operation='read')
            await message.answer(report.message, parse_mode=None)
            return
        await message.answer(f'Получено {len(result.data)} байт.', parse_mode=None)
        # Do not execute or parse the downloaded content in this demonstration.

    dispatcher.include_router(router)
    return router
```

## Проверка и источники

При разработке библиотеки выполняйте behavior tests, byte чтение multipart, actual Dispatcher, bounded stream и copied guide через installed wheel, затем полную поставку wheel/tarball с browser checks. Проверка PNG fixture отдельно сверяет chunk CRC, IHDR и zlib pixel data; не подменяйте этим live upload/decode. Реальный клиент, upload/download, все codec formats, реальные права, custom emoji и устройства здесь не подтверждены.

Сверено 2026-10-05: [sendPhoto](https://core.telegram.org/bots/api#sendphoto), [sendDocument](https://core.telegram.org/bots/api#senddocument), [sendMediaGroup](https://core.telegram.org/bots/api#sendmediagroup), [editMessageMedia](https://core.telegram.org/bots/api#editmessagemedia), [getFile](https://core.telegram.org/bots/api#getfile), [Sending files](https://core.telegram.org/bots/api#sending-files), [aiogram download](https://docs.aiogram.dev/en/latest/api/download_file.html). Bot API 10.3 и установленный aiogram 3.31.0; проверены названные разделы, не все возможности API.
