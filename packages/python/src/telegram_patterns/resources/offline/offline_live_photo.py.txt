"""Actual host Dispatcher and SDK serialization of live photos and live photo albums; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import SendLivePhoto, SendMediaGroup, SendMessage
from aiogram.types import Chat, FSInputFile, Message, Update, User
from telegram_patterns import ValidationFailure
from telegram_patterns.testing import StubSession
from live_photo_bot import MAX_UPLOAD, attach_live_photos, live_photo_source

CHAT = Chat(id=7, type='private')
ANNA = User(id=7, is_bot=False, first_name='Анна')
WHEN = datetime(2026, 10, 7, tzinfo=timezone.utc)


async def main():
    session = StubSession()
    bot = Bot('100:LIVE_PHOTO_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    store = {}

    async def remember(chat_id, video, photo):
        store.setdefault(chat_id, []).append((video, photo))

    async def recall(chat_id):
        return list(store.get(chat_id, []))

    attach_live_photos(dispatcher, remember=remember, recall=recall)
    texts, lives, albums = [], [], []
    message = {'message_id': 900, 'date': 1, 'chat': {'id': 7, 'type': 'private'}}
    session.respond(SendMessage, lambda method: texts.append(method.text) or {**message, 'text': method.text})
    session.respond(SendLivePhoto, lambda method: lives.append(json.loads(method.model_dump_json(include={'live_photo', 'photo', 'caption'}))) or message)
    session.respond(SendMediaGroup, lambda method: albums.append([json.loads(item.model_dump_json(include={'type', 'media', 'photo'})) for item in method.media]) or [message])

    def live(index, video, photo=True):
        payload = {'file_id': video, 'file_unique_id': 'u' + video, 'width': 1080, 'height': 1920, 'duration': 3}
        if photo:
            payload['photo'] = [{'file_id': 'p' + video, 'file_unique_id': 'pu' + video, 'width': 1080, 'height': 1920}]
        return Update(update_id=index, message=Message.model_validate({'message_id': index, 'date': WHEN, 'chat': CHAT, 'from_user': ANNA, 'live_photo': payload}))

    def command(index, text):
        return Update(update_id=index, message=Message(message_id=index, date=WHEN, chat=CHAT, from_user=ANNA, text=text))
    try:
        await dispatcher.feed_update(bot, command(1, '/album'))
        assert texts[-1] == 'Для альбома нужно хотя бы два live photo.' and not albums
        await dispatcher.feed_update(bot, live(2, 'v1'))
        assert texts[-1] == 'Сохранено: 3 с, 1080×1920.' and store[7] == [('v1', 'pv1')]
        await dispatcher.feed_update(bot, live(3, 'v2', photo=False))
        assert texts[-1].startswith('Не удалось') and len(store[7]) == 1, 'no static photo, nothing to resend'
        await dispatcher.feed_update(bot, command(4, '/last'))
        assert lives == [{'live_photo': 'v1', 'photo': 'pv1', 'caption': 'Последнее live photo'}]
        await dispatcher.feed_update(bot, live(5, 'v3'))
        await dispatcher.feed_update(bot, command(6, '/album'))
        assert albums == [[{'type': 'live_photo', 'media': 'v1', 'photo': 'pv1'}, {'type': 'live_photo', 'media': 'v3', 'photo': 'pv3'}]]

        for bad in ('https://example.com/live.mp4', 'attach://video', ''):
            try:
                live_photo_source(bad)
            except ValidationFailure:
                continue
            raise AssertionError('URL accepted for a live photo')
        with tempfile.TemporaryDirectory() as folder:
            small, large = Path(folder, 'small.mp4'), Path(folder, 'large.mp4')
            small.write_bytes(b'0' * 1024)
            large.write_bytes(b'0' * (MAX_UPLOAD + 1))
            assert isinstance(live_photo_source(small), FSInputFile)
            try:
                live_photo_source(large)
            except ValidationFailure:
                pass
            else:
                raise AssertionError('A video over 10 MB accepted')
        await dispatcher.feed_update(bot, command(7, '/help'))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'received_saved': True,
                      'missing_static_photo_refused': True, 'resent_by_file_id': True, 'album_of_live_photos': True,
                      'url_refused': True, 'upload_size_checked': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
