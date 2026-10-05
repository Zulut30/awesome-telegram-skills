"""Actual Dispatcher, SDK multipart reads and an explicit local content stream."""
import asyncio
import json
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.methods import EditMessageMedia, GetFile, SendDocument, SendMediaGroup, SendMessage, SendPhoto
from aiogram.types import Message, Update
from telegram_patterns.testing import StubSession
from media_bot import PHOTO, DOCUMENT, attach_media


class FixtureSession(StubSession):
    def __init__(self):
        super().__init__()
        self.stream_closed = False

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        try:
            yield DOCUMENT[:7]
            yield DOCUMENT[7:]
        finally:
            self.stream_closed = True


async def main():
    session = FixtureSession()
    bot = Bot('100:MEDIA_FIXTURE', session=session, default=DefaultBotProperties(parse_mode='HTML'))
    dispatcher = Dispatcher()
    helped = []
    help_router = Router(name='existing-help')
    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    attach_media(dispatcher)
    uploads = []
    async def inspect_input(source):
        files = {}
        attachment = session.prepare_value(source, bot=bot, files=files)
        chunks = [chunk async for chunk in files[attachment.removeprefix('attach://')].read(bot)]
        uploads.append(b''.join(chunks))
    def response(request, index=0):
        return {'message_id': 100+index, 'date': 1, 'chat': {'id': request.chat_id, 'type': 'private'}}
    async def photo_response(request):
        assert request.parse_mode is None
        assert request.caption_entities[0].offset == 3
        await inspect_input(request.photo)
        return response(request)
    async def document_response(request):
        assert request.parse_mode is None
        await inspect_input(request.document)
        return response(request)
    async def album_response(request):
        assert len(request.media) == 2
        wire = json.loads(session.prepare_value(request.media, bot=bot, files={}))
        assert all('parse_mode' not in item for item in wire)
        for item in request.media: await inspect_input(item.media)
        return [response(request,index) for index in range(2)]
    async def edit_response(request):
        assert request.message_id == 100 and request.media.parse_mode is None
        await inspect_input(request.media.media)
        return response(request)
    session.respond(SendPhoto,photo_response).respond(SendDocument,document_response)
    session.respond(SendMediaGroup,album_response).respond(EditMessageMedia,edit_response)
    session.respond(GetFile,{'file_id':'opaque','file_unique_id':'unique','file_size':len(DOCUMENT),'file_path':'documents/file.txt'})
    session.respond(SendMessage,lambda request: {**response(request),'text':request.text})
    def incoming(index, *, text=None, document=None, **changes):
        message = {'message_id':index,'date':1,'chat':{'id':42,'type':'private'},
                   'from':{'id':42,'is_bot':False,'first_name':'Actor'},'text':text,'document':document,**changes}
        return Update.model_validate({'update_id':index,'message':message})
    try:
        await dispatcher.feed_update(bot,incoming(1,text='/media'))
        assert [type(c).__name__ for c in session.calls] == ['SendPhoto','SendDocument','SendMediaGroup','EditMessageMedia']
        assert uploads == [PHOTO,DOCUMENT,PHOTO,PHOTO,PHOTO]
        count=len(session.calls)
        for changes in ({'chat':{'id':-42,'type':'group'}},{'message_thread_id':7,'is_topic_message':True},
                        {'is_topic_message':True},{'business_connection_id':'unsupported-business'}):
            await dispatcher.feed_update(bot,incoming(10,text='/media',**changes))
            await dispatcher.feed_update(bot,incoming(11,document={'file_id':'opaque','file_unique_id':'unique'},**changes))
        assert len(session.calls)==count
        await dispatcher.feed_update(bot,incoming(2,document={'file_id':'opaque','file_unique_id':'unique','file_name':'../untrusted','mime_type':'application/x-not-trusted'}))
        assert session.stream_closed and session.calls[-1].text == f'Получено {len(DOCUMENT)} байт.'
        await dispatcher.feed_update(bot,incoming(3,text='/help'))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'uploaded_parts':len(uploads),
        'photo_document_album_edit':True,'caption_entities':True,'explicit_parse_mode_none':True,
        'bounded_stream_download':session.stream_closed,'private_context_guards':True,'existing_dispatcher_preserved':bool(helped)}))


if __name__=='__main__': asyncio.run(main())
