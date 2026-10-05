"""All public media symbols against SDK objects and a synthetic byte stream."""
import asyncio
import json
from aiogram import Bot
from aiogram.methods import GetFile, SendPhoto
from telegram_patterns import MessageBuilder
from telegram_patterns.aiogram import (
    MediaKind, MediaSendRequest, MediaFile, MediaItem, DownloadedMedia,
    media_request, media_album, media_edit, download_media,
)
from telegram_patterns.testing import StubSession


class MediaSession(StubSession):
    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b'actual fixture bytes'


async def main():
    session=MediaSession()
    bot=Bot('100:MEDIA_REFERENCE',session=session)
    kind: MediaKind='photo'
    item=MediaItem(MediaFile(kind,'opaque',bot_id=bot.id),MessageBuilder().style('Фото','bold').build())
    request: MediaSendRequest=media_request(item,bot_id=bot.id,chat_id=42)
    assert isinstance(request,SendPhoto) and request.parse_mode is None
    native=item.as_input_media(bot.id)
    assert native.caption_entities is not None and native.caption_entities[0].length==4
    assert len(media_album([item,item],bot_id=bot.id,chat_id=42).media)==2
    assert media_edit(item,bot_id=bot.id,inline_message_id='inline_fixture').inline_message_id=='inline_fixture'
    session.respond(GetFile,{'file_id':'opaque','file_unique_id':'unique','file_size':20,'file_path':'documents/fixture.txt'})
    try:
        downloaded: DownloadedMedia=await download_media(bot,'opaque',max_bytes=20)
        assert downloaded.data==b'actual fixture bytes' and downloaded.bot_id==bot.id
    finally:
        await bot.session.close()
    print(json.dumps({'case':'bot_media','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__': asyncio.run(main())
