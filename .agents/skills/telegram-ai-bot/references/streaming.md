# Потоковый ответ и остановка генерации

Проверено 7 октября 2026 года по [Bot API 10.3](https://core.telegram.org/bots/api) и [changelog](https://core.telegram.org/bots/api-changelog); aiogram 3.31.0 поддерживает эти методы и update.

## Методы и поля

| Что | Детали |
| --- | --- |
| [`sendMessageDraft`](https://core.telegram.org/bots/api#sendmessagedraft) | `chat_id` личного чата, `message_thread_id`, ненулевой `draft_id`, `text` 0–4096 символов после разбора entities (пустой показывает «Thinking…»), `parse_mode` или `entities`, `can_stop`, `keep_on_stop`. Возвращает True |
| [`sendRichMessageDraft`](https://core.telegram.org/bots/api#sendrichmessagedraft) | То же для `rich_message` (InputRichMessage); загрузка новых файлов и файлов по URL не поддерживается; доступен блок `<tg-thinking>` |
| Окончательный ответ | `sendMessage` или `sendRichMessage`: черновик — временный предпросмотр на 30 секунд и сам в чате не сохраняется |
| [`MessageGenerationStopped`](https://core.telegram.org/bots/api#messagegenerationstopped) | Update `stopped_message_generation`: `chat`, необязательный `message_thread_id`, `draft_id` |
| `keep_on_stop` | Черновик остается после нажатия, но все равно исчезает через короткое время или после сообщения бота |

История: `sendMessageDraft` появился в Bot API 9.3, стал доступен всем ботам в 9.5, `sendRichMessageDraft` — в 10.2, `can_stop`, `keep_on_stop` и `MessageGenerationStopped` — в 10.3. Перед использованием сверьте версию SDK проекта: старый SDK не знает новых полей и update.

Изменения черновика с тем же `draft_id` анимируются, с другим — заменяют его без анимации. Пустой `allowed_updates` дает все update, кроме `chat_member` и reactions; при явном списке добавьте `stopped_message_generation`. aiogram при запуске polling сам собирает список из зарегистрированных обработчиков.

## Пример на aiogram

Самостоятельный пример без дополнительных пакетов. `generate(prompt)` — асинхронный итератор фрагментов текста от клиента модели проекта; при закрытии итератора клиент должен прервать HTTP-поток. `allow(user_id, prompt)` — политика проекта: бюджет, лимит запросов и длина вопроса.

<!-- ai-stream:run -->
```python
"""Streamed answer with a stop button: aiogram 3.31+, Bot API 10.3."""
import asyncio
from contextlib import aclosing

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.methods import SendMessage, SendMessageDraft
from aiogram.types import Message, MessageGenerationStopped


def utf16_parts(text: str, limit: int = 4096) -> list[str]:
    parts, current, size = [], [], 0
    for char in text:
        width = len(char.encode('utf-16-le')) // 2
        if size + width > limit:
            parts.append(''.join(current))
            current, size = [], 0
        current.append(char)
        size += width
    return parts + [''.join(current)] if current else parts


def ai_router(generate, allow, *, interval: float = 0.5, max_active: int = 4, max_waiting: int = 8) -> Router:
    router = Router(name='ai-answer')
    active: dict[int, tuple[int, asyncio.Task]] = {}  # chat_id -> (draft_id, task), running or waiting
    stopping: set[int] = set()
    slots = asyncio.Semaphore(max_active)  # bounded parallelism toward the model

    async def answer(message: Message, draft_id: int) -> None:
        chat_id, text, last, paused = message.chat.id, '', float('-inf'), 0.0
        loop = asyncio.get_running_loop()
        try:
            async with slots, aclosing(generate(message.text)) as pieces:  # closing stops token spend
                async for piece in pieces:
                    text += piece
                    now = loop.time()
                    if now - last < interval or now < paused:
                        continue
                    last = now
                    try:
                        await message.bot(SendMessageDraft(chat_id=chat_id, draft_id=draft_id, can_stop=True,
                                                           text=(utf16_parts(text)[-1:] or [''])[0], parse_mode=None))
                    except TelegramRetryAfter as error:
                        paused = now + error.retry_after
                    except TelegramAPIError:
                        pass  # the preview is optional; the final message carries the answer
        except asyncio.CancelledError:
            if chat_id not in stopping:
                raise  # process shutdown: send nothing
            text += '\n\n(генерация остановлена)'
        except Exception:
            text = 'Не удалось получить ответ. Попробуйте еще раз.'  # log the error category, not the prompt
        finally:
            active.pop(chat_id, None)
            stopping.discard(chat_id)
        for part in utf16_parts(text.strip() or 'Пустой ответ.'):
            await message.bot(SendMessage(chat_id=chat_id, text=part, parse_mode=None))

    @router.message(F.chat.type == 'private', F.text)
    async def ask(message: Message) -> None:
        if message.chat.id in active:
            await message.answer('Я еще отвечаю: дождитесь ответа или нажмите «Остановить».', parse_mode=None)
            return
        if len(active) >= max_active + max_waiting:
            await message.answer('Сейчас много запросов. Попробуйте через минуту.', parse_mode=None)
            return
        if not await allow(message.from_user.id, message.text):  # budget and prompt length before the model
            await message.answer('Лимит запросов исчерпан.', parse_mode=None)
            return
        active[message.chat.id] = (message.message_id, asyncio.create_task(answer(message, message.message_id)))

    @router.stopped_message_generation()
    async def stop(event: MessageGenerationStopped) -> None:
        current = active.get(event.chat.id)
        if current is not None and current[0] == event.draft_id:  # a stale draft changes nothing
            stopping.add(event.chat.id)
            current[1].cancel()

    return router
```

Пример держит одну генерацию на чат, не больше `max_active` обращений к модели одновременно и `max_waiting` ожидающих, а лишние запросы отклоняет сразу. Историю диалога он не хранит: добавьте ее с лимитом, сроком и командой удаления. В awesome-telegram-patterns то же вместе с историей и `/forget` дает рецепт `demo-ai-stream`.

## Частые ошибки

- Ответ отправлен только черновиками: через 30 секунд пользователь ничего не видит.
- Черновик на каждый токен: лишние запросы и 429; обновляйте по интервалу.
- Остановка отменяет задачу, но не закрывает поток модели: токены продолжают тратиться.
- `draft_id` не сверяется: старая кнопка или другой чат останавливают чужую генерацию.
- Текст модели передан с `parse_mode="HTML"`: разметка от модели ломает сообщение или подменяет ссылки.
- Каждый update запускает неограниченную задачу: при нагрузке растут память и счет за модель.
- Полные запросы и ответы пишутся в логи: личная переписка попадает в хранилище логов.
