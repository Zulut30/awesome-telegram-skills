# Профили

Доступно с 0.21.0, проверено на 0.24.0.

Термины: **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **fallback** — запасной вариант, если основная возможность недоступна.

Для предоставленного локального wheel `awesome-telegram-patterns` с aiogram extra. Сохраняйте Bot, Dispatcher, FSM, storage и серверную политику проекта. Пакет не опубликован в PyPI/npm; core не требует SDK. В другом SDK используйте его native методы, сохраняя те же границы.

## Контракты

| API | Результат и границы |
| --- | --- |
| `ProfileSource`, `ProfileAuthorizer` | Literal update/getMe; async host callback `(actor_id, bot_id, method) -> bool`. `read` и точные setMy*/removeMy* имена. Только результат `True` разрешает действие |
| `user_profile(User, source='update', observed_at=None)` / `UserProfile` | Неизменяемая запись: числовой ID; имя, username, язык и Premium, если известны; возможности могут быть `None`. Копирует значения; ввода-вывода нет. Source — объявленное наблюдение, не доказательство авторизации |
| `chat_profile(ChatFullInfo, observed_at=None)` / `ChatProfile` | Неизменяемая выборка из ответа getChat: био, описание, дата рождения, emoji-статус, личный канал, ID фото и права по умолчанию. None сохраняется; permissions не представляют роль инициатора |
| `ProfilePhotoSize.as_media()` | Bot/user-scoped IDs, размеры и optional file_size. Возвращает MediaFile для сообщения того же бота; file_unique_id не используется для отправки/скачивания/нового аватара |
| `read_profile_photos(bot, user_id, offset=0, limit=1)` / `ProfilePhotos` | Один явный getUserProfilePhotos; offset >=0, limit 1..100, immutable tuple-of-tuples размеров и visible total_count. Пустая страница не доказывает отсутствие скрытого фото |
| `read_bot_profile(bot, language_code='', include_photos=False)` / `BotProfile` | Свежий getMe с проверкой ID бота, `GetMyName`, `GetMyDescription`, `GetMyShortDescription` и время наблюдения с часовым поясом. Без include_photos поле photos остается None; явное чтение и photo patch получают own-bot страницу через getUserProfilePhotos. Последовательные чтения не являются atomic snapshot; locale getter может вернуть fallback |
| `BotProfilePatch(...)` | None — пропустить поле; пустая строка — явно удалить dedicated localized text. Локальные bounds: name <=64, description <=512, short <=120 Unicode code points, без unpaired surrogate и truncation. Только выбранные поля отправляются |
| `update_bot_profile(bot, patch, actor_id=..., authorize=..., language_code='')` | Явный own-bot write. Host `read` ACL, fresh getMe, текущий ACL каждого метода, последовательные записи, затем ACL и fresh readback. Автоматического повтора, отката, CAS и надежной квитанции нет |
| `ProfileEditIncomplete` | UnknownOutcome; safe `completed_methods` и `pending_method`. Native False, потерянный ответ, отзыв права после prefix или readback failure требуют explicit read/reconciliation; prefix не доказывает полный успех |

Результаты наблюдений не держат mutable SDK objects; mappings копируются и становятся read-only. Source/time нормализуются к aware UTC. Premium, username, фото, default chat permissions и capability flags не задают серверную роль. ID устойчив, username может измениться/отсутствовать. Другие доступные SDK-поля остаются у native User/ChatFullInfo: helper не обещает получение скрытых данных, произвольный username lookup или историю личной переписки.

## Локализация, фото и права

`language_code=''` задает default; две lowercase ASCII буквы задают форму кода языка (при необходимости проект проверяет ISO vocabulary). Пропуск description не очищает его. Пустая ru-description удаляет override: чтение может вернуть default text, не пустую строку. Фото глобально для бота, даже когда текстовый patch относится к ru.

`photo=MediaFile('photo', bytes, filename='avatar.jpg')` дает InputProfilePhotoStatic. JPG suffix и начальный/конечный marker — лишь базовая проверка; host декодирует и проверяет actual codec/content, размеры, privacy и свою политику uploads. Для animated MPEG4: `MediaFile('video', bytes, filename='avatar.mp4')`, optional finite nonnegative `main_frame_timestamp`; duration/frame validity проверяет host. Наследуются byte limits MediaFile (10 MB photo / 50 MB video), это локальная политика, не гарантия Telegram acceptance. Native avatar требует **новую загрузку**: file_id, URL и неявное чтение пути отклоняются. `remove_photo=True` нельзя совместить с upload.

App ACL проверяется перед каждым выбранным методом, а target всегда текущий Bot.id с fresh getMe. Проверка ACL и удаленный effect не являются общей транзакцией: host сериализует административные изменения, определяет scope, проверяет контент и обновляет кеш из возвращенного наблюдения. Произвольный пользователь, Business connection и MTProto не редактируются этим API; для них нужны явно выбранные отдельные методы и права.

После `ProfileEditIncomplete` покажите safe_error_report и выполните явное повторное чтение для сверки текущего состояния. Не повторяйте весь patch автоматически: предыдущие поля или неизвестная запись уже могли примениться. Cancellation распространяется, сессия принадлежит host; отмена ожидания не доказывает отмену Telegram effect. Не логируйте raw исключения, token, полный профиль, bio или file IDs.

## Полная композиция

Сохраните один блок ниже как `profiles_bot.py`, включите `profile_router(authorize)` в существующий Dispatcher. Host authorizer использует текущие серверные роли, а не Premium/username из Update. `/profile` показывает только профиль инициатора в его личном чате; `/configure_bot`, `/clear_bot_description`, `/remove_bot_photo` — явные административные действия. Fixture JPG — доверенный статический пример, не проверка пользовательских uploads. Нет polling/Telegram HTTP на import.

```python
"""Attach profile commands to the existing Dispatcher; host supplies current ACL."""
from __future__ import annotations
import base64
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from telegram_patterns import MessageBuilder, PermissionDenied, safe_error_report
from telegram_patterns.aiogram import (
    BotProfilePatch, MediaFile, ProfileAuthorizer, ProfileEditIncomplete,
    chat_profile, user_profile, read_profile_photos, read_bot_profile, update_bot_profile,
)

# Trusted 16x16 JPG fixture produced by Windows System.Drawing; not a user upload.
AVATAR = base64.b64decode('/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDq6KKK/os/Kj//2Q==')


def profile_router(authorize: ProfileAuthorizer) -> Router:
    router = Router(name='profile-example')
    router.message.filter(F.chat.type == 'private', F.from_user.is_bot == False,
                          ~F.message_thread_id, ~F.is_topic_message, ~F.business_connection_id)

    @router.message(Command('profile'))
    async def own_profile(message: Message) -> None:
        if message.from_user is None or message.from_user.id != message.chat.id:
            return
        observed = user_profile(message.from_user)
        premium = 'неизвестно' if observed.is_premium is None else ('да' if observed.is_premium else 'нет')
        try:
            detail = chat_profile(await message.bot.get_chat(message.chat.id))
            photos = await read_profile_photos(message.bot, observed.id, limit=1)
        except Exception as error:
            await message.answer(safe_error_report(error, operation='read').message, parse_mode=None)
            return
        text = MessageBuilder().text('Имя: ').text(observed.first_name).text('\nPremium: ').text(premium)
        text = text.text('\nBio: ').text('неизвестно' if detail.bio is None else detail.bio)
        # An empty API page never proves absence of a private avatar.
        text = text.text('\nДоступных фото: ').text(str(photos.total_count))
        await message.answer(**text.build().as_kwargs())
        if photos.photos:
            await message.answer_photo(photo=photos.photos[0][-1].as_media().as_input(message.bot.id))

    @router.message(Command('bot_profile'))
    async def own_bot_profile(message: Message) -> None:
        if message.from_user is None:
            return
        if await authorize(message.from_user.id, message.bot.id, 'read') is not True:
            await message.answer('Недостаточно прав.', parse_mode=None)
            return
        observed = await read_bot_profile(message.bot, language_code='ru')
        text = MessageBuilder().text(observed.name).text('\n').text(observed.description)
        await message.answer(**text.build().as_kwargs())

    async def apply(message: Message, patch: BotProfilePatch) -> None:
        if message.from_user is None:
            return
        try:
            observed = await update_bot_profile(message.bot, patch, actor_id=message.from_user.id,
                                                authorize=authorize, language_code='ru')
        except (PermissionDenied, ProfileEditIncomplete) as error:
            await message.answer(safe_error_report(error, operation='write').message, parse_mode=None)
            return
        # Fresh readback is not an atomic/CAS receipt. Host updates its cache from this observation.
        await message.answer(**MessageBuilder().text('Текущее описание: ').text(observed.description).build().as_kwargs())

    @router.message(Command('configure_bot'))
    async def configure(message: Message) -> None:
        await apply(message, BotProfilePatch(name='Бот записи', description='Запись на консультацию',
                                            short_description='Выберите удобное время',
                                            photo=MediaFile('photo', AVATAR, filename='avatar.jpg')))

    @router.message(Command('clear_bot_description'))
    async def clear(message: Message) -> None:
        await apply(message, BotProfilePatch(description=''))

    @router.message(Command('remove_bot_photo'))
    async def remove(message: Message) -> None:
        await apply(message, BotProfilePatch(remove_photo=True))

    return router
```

## Проверка и evidence

`telegram-patterns plan-recipe demo-profiles` показывает требования; `telegram-patterns run-recipe demo-profiles --offline` запускает закрытый bundled fixture. Настоящий `Dispatcher` на синтетических updates проверяет неизвестные поля, фото только этого бота, пропуск и очистку значения для языка и запасной вариант, отказ пользователю без Premium, права на каждый метод, загрузку нового JPG через multipart и удаление фото, потерянную квитанцию и сверку, а также сохранение справки проекта. Это авторская проверка через SDK и подставной транспорт, а не независимая приемка агентом или пользователем и не доказательство видимости, кодеков, прав и поведения на устройствах в живом Telegram.

После копирования этого навыка `references/profiles.md` самодостаточен; соседние навыки не требуются. Полный repository helper `scripts/verify_profile_recipe.py <copied-skill>` исполняет точный блок и offline composition через установленный пакет.

## Источники — проверенный scope 2026-10-05

Bot API 10.3 / установленный aiogram 3.31.0: [User](https://core.telegram.org/bots/api#user), [getMe](https://core.telegram.org/bots/api#getme), [getChat/ChatFullInfo](https://core.telegram.org/bots/api#chatfullinfo), [getUserProfilePhotos](https://core.telegram.org/bots/api#getuserprofilephotos), [setMyName](https://core.telegram.org/bots/api#setmyname), [setMyDescription](https://core.telegram.org/bots/api#setmydescription), [setMyShortDescription](https://core.telegram.org/bots/api#setmyshortdescription) и соответствующие getMy*; [setMyProfilePhoto](https://core.telegram.org/bots/api#setmyprofilephoto), [removeMyProfilePhoto](https://core.telegram.org/bots/api#removemyprofilephoto), [InputProfilePhotoStatic](https://core.telegram.org/bots/api#inputprofilephotostatic), [InputProfilePhotoAnimated](https://core.telegram.org/bots/api#inputprofilephotoanimated). Эти источники не обновляют даты Business/MTProto, остальных методов или платежных провайдеров.
