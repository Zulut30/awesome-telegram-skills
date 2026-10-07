import asyncio
from dataclasses import FrozenInstanceError
import json
import importlib.util
import logging
from pathlib import Path
import base64
import ast
import struct
import zlib
import traceback
import unittest

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import EditMessageMedia, GetFile, SendAudio, SendDocument, SendPhoto, SendVideo
from telegram_patterns import FormattedText, MessageBuilder, safe_error_report
from telegram_patterns.aiogram import MediaFile, MediaItem, media_request, media_album, media_edit, download_media
from telegram_patterns.errors import TransportFailure, UnsupportedCapability, ValidationFailure
from telegram_patterns.testing import StubSession


class StreamSession(StubSession):
    def __init__(self, chunks=(b'abc',b'def'), *, size=6, path='documents/file.txt'):
        super().__init__()
        self.chunks=chunks; self.streams=0; self.stream_closed=0
        self.respond(GetFile,{'file_id':'opaque','file_unique_id':'unique','file_size':size,'file_path':path})

    async def stream_content(self,url,headers=None,timeout=30,chunk_size=65536,raise_for_status=True):
        self.streams+=1
        try:
            for chunk in self.chunks:
                if isinstance(chunk,BaseException): raise chunk
                if chunk=='wait': await asyncio.sleep(10)
                else: yield chunk
        finally: self.stream_closed+=1


class MediaCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session=StubSession()
        self.bot=Bot('100:MEDIA_TEST',session=self.session,default=DefaultBotProperties(parse_mode='HTML'))

    async def asyncTearDown(self): await self.bot.session.close()

    def item(self,kind='photo',*,caption=None):
        return MediaItem(MediaFile(kind,b'actual upload bytes',filename='fixture.bin'),caption=caption)

    async def test_each_kind_builds_native_request_and_multipart_bytes(self):
        for kind,model in [('photo',SendPhoto),('document',SendDocument),('video',SendVideo),('audio',SendAudio)]:
            request=media_request(self.item(kind),bot_id=100,chat_id=-42,message_thread_id=7)
            self.assertIsInstance(request,model)
            self.assertEqual(request.message_thread_id,7)
            files={}
            reference=self.session.prepare_value(getattr(request,kind),bot=self.bot,files=files)
            self.assertTrue(reference.startswith('attach://'))
            content=files[reference.removeprefix('attach://')]
            chunks=[chunk async for chunk in content.read(self.bot)]
            self.assertEqual(b''.join(chunks),b'actual upload bytes')
            self.assertEqual(content.filename,'fixture.bin')
        self.assertEqual(self.session.calls,[])

    async def test_bot_scoped_reuse_does_not_apply_upload_size_or_change_kind(self):
        source=MediaFile('document','opaque_id',bot_id=100)
        self.assertEqual(source.as_input(100),'opaque_id')
        with self.assertRaises(ValidationFailure): source.as_input(101)
        with self.assertRaises(ValidationFailure): MediaFile('photo','opaque_id')
        with self.assertRaises(ValidationFailure): MediaFile('document','opaque_id',filename='x',bot_id=100)

    async def test_upload_snapshot_and_native_results_are_independent(self):
        item=self.item()
        first=media_request(item,bot_id=100,chat_id=42)
        second=media_request(item,bot_id=100,chat_id=42)
        first.photo.data=b'mutated'
        self.assertEqual(second.photo.data,b'actual upload bytes')
        with self.assertRaises(FrozenInstanceError): item.file.filename='new'
        with self.assertRaises(TypeError): MediaFile('photo',bytearray(b'bytes'),filename='x')

    async def test_source_does_not_accept_path_url_attach_or_unsupported_kind(self):
        for value in ('https://example.invalid/photo','C:\\secret','attach://a','../file','a b',''):
            with self.subTest(value=value),self.assertRaises(ValueError): MediaFile('photo',value,bot_id=100)
        with self.assertRaises(UnsupportedCapability): MediaFile('sticker',b'x',filename='x')
        for name in ('../file','a/b','a\\b','x:\\y','\nname','.'):
            with self.subTest(name=name),self.assertRaises(ValueError): MediaFile('photo',b'x',filename=name)

    async def test_upload_byte_limits_and_photo_dimensions_are_explicit(self):
        MediaFile('photo',b'x'*10_000_000,filename='photo.png',width=5000,height=5000)
        with self.assertRaises(ValidationFailure): MediaFile('photo',b'x'*10_000_001,filename='photo.png')
        with self.assertRaises(ValidationFailure): MediaFile('document',b'x'*50_000_001,filename='file')
        for changes in ({'width':10000,'height':1},{'width':21,'height':1},{'width':True,'height':1},
                        {'width':1},{'width':0,'height':1}):
            with self.subTest(changes=changes),self.assertRaises(ValueError): MediaFile('photo',b'x',filename='x',**changes)
        with self.assertRaises(ValueError): MediaFile('audio',b'x',filename='x',width=1,height=1)
        with self.assertRaises(ValueError): MediaFile('document',b'',filename='x')

    async def test_literal_caption_utf16_entities_and_default_parse_mode_override(self):
        caption=MessageBuilder().text('😀 ').style('<b>literal</b>_*','bold').build()
        request=media_request(self.item(caption=caption),bot_id=100,chat_id=42)
        self.assertEqual(request.caption,'😀 <b>literal</b>_*')
        self.assertIsNone(self.session.prepare_value(request.parse_mode,bot=self.bot,files={}))
        entities=json.loads(self.session.prepare_value(request.caption_entities,bot=self.bot,files={}))
        self.assertEqual(entities,[{'type':'bold','offset':3,'length':16}])

    async def test_empty_caption_removal_and_astral_limit_no_truncation(self):
        for text in ('',' \n', '😀'*512):
            request=media_edit(self.item(caption=FormattedText(text)),bot_id=100,chat_id=42,message_id=3)
            self.assertEqual(request.media.caption,text)
            self.assertIsNone(request.media.parse_mode)
        with self.assertRaises(ValueError): self.item(caption=FormattedText('😀'*513))

    async def test_custom_emoji_fallback_and_presentation_types(self):
        item=MediaItem(self.item().file,MessageBuilder().custom_emoji('👍','12345').build(),spoiler=True,caption_above=True)
        fallback=media_request(item,bot_id=100,chat_id=42)
        native=media_request(item,bot_id=100,chat_id=42,custom_emoji_entitlement_verified=True)
        self.assertEqual(fallback.caption,'👍');self.assertEqual(fallback.caption_entities,[])
        self.assertEqual(native.caption_entities[0].length,2)
        self.assertTrue(native.has_spoiler);self.assertTrue(native.show_caption_above_media)
        with self.assertRaises(TypeError): item.caption_kwargs(custom_emoji_entitlement_verified='yes')
        with self.assertRaises(UnsupportedCapability): MediaItem(self.item('document').file,spoiler=True)

    async def test_album_mixed_visual_and_homogeneous_document_audio(self):
        for kinds in (('photo','video'),('document','document'),('audio','audio')):
            items=[self.item(kind) for kind in kinds]
            album=media_album(items,bot_id=100,chat_id=42,message_thread_id=8)
            items.clear()
            wire=json.loads(self.session.prepare_value(album.media,bot=self.bot,files={}))
            self.assertEqual([item['type'] for item in wire],list(kinds))
            self.assertTrue(all('parse_mode' not in item for item in wire))
            self.assertEqual(album.message_thread_id,8)
        self.assertEqual(self.session.calls,[])

    async def test_album_bounds_invalid_mix_and_cross_bot_rejected_before_send(self):
        for count in (0,1,11):
            with self.assertRaises(ValueError): media_album([self.item()]*count,bot_id=100,chat_id=42)
        for kinds in (('photo','document'),('audio','document'),('video','audio')):
            with self.assertRaises(UnsupportedCapability): media_album([self.item(k) for k in kinds],bot_id=100,chat_id=42)
        with self.assertRaises(ValueError): media_album([self.item(),MediaItem(MediaFile('photo','opaque',bot_id=101))],bot_id=100,chat_id=42)
        self.assertEqual(self.session.calls,[])

    async def test_inline_and_album_replacement_guards(self):
        reused=MediaItem(MediaFile('photo','opaque',bot_id=100))
        self.assertIsInstance(media_edit(reused,bot_id=100,inline_message_id='inline_1',album_kind='photo-video'),EditMessageMedia)
        with self.assertRaises(UnsupportedCapability): media_edit(self.item(),bot_id=100,inline_message_id='inline_1')
        with self.assertRaises(ValueError): media_edit(reused,bot_id=100,chat_id=42,message_id=1,inline_message_id='inline_1')
        with self.assertRaises(ValueError): media_edit(reused,bot_id=100,chat_id=42)
        with self.assertRaises(UnsupportedCapability): media_edit(reused,bot_id=100,chat_id=42,message_id=1,album_kind='document')
        with self.assertRaises(ValueError): media_edit(reused,bot_id=100,chat_id=42,message_id=True)

    async def test_telegram_unsupported_format_permission_and_retry_after_no_auto_retry(self):
        request=media_request(self.item(),bot_id=100,chat_id=42)
        for error in (TelegramBadRequest(method=request,message='PHOTO_INVALID_DIMENSIONS'),
                      TelegramBadRequest(method=request,message='IMAGE_PROCESS_FAILED'),
                      TelegramForbiddenError(method=request,message='blocked'),
                      TelegramRetryAfter(method=request,message='flood',retry_after=12),TimeoutError('unknown')):
            def fail(method): raise error
            self.session.respond(SendPhoto,fail)
            before=len(self.session.calls)
            with self.assertRaises(type(error)): await self.bot(request)
            self.assertEqual(len(self.session.calls),before+1)
            report=safe_error_report(error,operation='write')
            self.assertEqual(report.recovery,'reconcile')
            self.assertNotIn(str(error),report.message)

    async def test_demo_stops_after_successful_photo_when_document_receipt_unknown(self):
        path=Path(__file__).resolve().parents[3]/'examples/python/media_bot.py'
        spec=importlib.util.spec_from_file_location('media_example',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.session.respond(SendPhoto,{'message_id':100,'date':1,'chat':{'id':42,'type':'private'}})
        def fail(request): raise TimeoutError('unknown document receipt')
        self.session.respond(SendDocument,fail)
        with self.assertRaises(TimeoutError): await module.send_media_demo(self.bot,42)
        self.assertEqual([type(c).__name__ for c in self.session.calls],['SendPhoto','SendDocument'])

    async def test_demo_contains_a_valid_small_png_and_unmodified_plain_document(self):
        path=Path(__file__).resolve().parents[3]/'examples/python/media_bot.py'
        tree=ast.parse(path.read_text(encoding='utf-8'))
        value=next(n.value.args[0].value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PHOTO' for t in n.targets))
        image=base64.b64decode(value)
        self.assertEqual(image[:8],b'\x89PNG\r\n\x1a\n')
        offset=8;chunks=[];pixels=b''
        while offset<len(image):
            length=struct.unpack('>I',image[offset:offset+4])[0]
            tag=image[offset+4:offset+8];body=image[offset+8:offset+8+length]
            expected=struct.unpack('>I',image[offset+8+length:offset+12+length])[0]
            self.assertEqual(zlib.crc32(tag+body)&0xffffffff,expected)
            chunks.append(tag)
            if tag==b'IHDR': self.assertEqual(struct.unpack('>IIBBBBB',body),(1,1,8,4,0,0,0))
            if tag==b'IDAT': pixels+=body
            offset+=12+length
        self.assertEqual(chunks,[b'IHDR',b'IDAT',b'IEND'])
        self.assertEqual(zlib.decompress(pixels),b'\x01\xff\xff')
        self.assertEqual(offset,len(image))

    async def test_demo_download_error_uses_safe_feedback_and_preserves_host_handler(self):
        from aiogram import Dispatcher
        from aiogram.types import Update
        path=Path(__file__).resolve().parents[3]/'examples/python/media_bot.py'
        spec=importlib.util.spec_from_file_location('media_example_error',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        dp=Dispatcher();module.attach_media(dp)
        def fail(request): raise TimeoutError('DO_NOT_ECHO_TOKEN_PATH')
        from aiogram.methods import SendMessage
        self.session.respond(GetFile,fail)
        self.session.respond(SendMessage,{'message_id':100,'date':1,'chat':{'id':42,'type':'private'}})
        incoming=Update.model_validate({'update_id':1,'message':{'message_id':1,'date':1,'chat':{'id':42,'type':'private'},
            'from':{'id':42,'is_bot':False,'first_name':'Actor'},'document':{'file_id':'opaque','file_unique_id':'unique'}}})
        try:
            await dp.feed_update(self.bot,incoming)
            self.assertEqual([type(c).__name__ for c in self.session.calls],['GetFile','SendMessage'])
            self.assertNotIn('DO_NOT_ECHO',self.session.calls[-1].text)
            self.assertIsNone(self.session.calls[-1].parse_mode)
        finally: await dp.fsm.close()


class MediaDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.sessions=[]
    async def asyncTearDown(self):
        for session in self.sessions: await session.close()
    def bot(self,**kwargs):
        session=StreamSession(**kwargs);self.sessions.append(session)
        return Bot('100:DOWNLOAD_TEST',session=session),session

    async def test_actual_stream_bytes_metadata_no_disk_and_private_repr(self):
        bot,session=self.bot()
        result=await download_media(bot,'opaque',max_bytes=6)
        self.assertEqual(result.data,b'abcdef');self.assertEqual(result.bot_id,100)
        self.assertEqual(result.file_id,'opaque');self.assertEqual(result.file_unique_id,'unique')
        self.assertEqual(session.stream_closed,1)
        self.assertNotIn('abcdef',repr(result));self.assertNotIn('opaque',repr(result))

    async def test_declared_oversize_rejected_before_stream(self):
        bot,session=self.bot(size=7)
        with self.assertRaises(ValueError): await download_media(bot,'opaque',max_bytes=6)
        self.assertEqual(session.streams,0);self.assertEqual(len(session.calls),1)

    async def test_missing_size_still_enforces_actual_bound_and_closes_stream(self):
        bot,session=self.bot(chunks=(b'abc',b'def'),size=None)
        with self.assertRaises(ValueError): await download_media(bot,'opaque',max_bytes=5)
        self.assertEqual(session.stream_closed,1)

    async def test_declared_smaller_size_truncation_and_empty_are_rejected(self):
        for chunks,size in (((b'abc',),6),((b'abcdef',),3),((),None)):
            bot,session=self.bot(chunks=chunks,size=size)
            with self.assertRaises(ValueError): await download_media(bot,'opaque',max_bytes=10)
            self.assertEqual(session.stream_closed,1)

    async def test_absolute_traversal_url_missing_and_encoded_path_never_stream(self):
        for path in (None,'/absolute','../private','a/../b','a//b','C:\\file','https://host/file','a/%2e%2e/b','a?x=1'):
            bot,session=self.bot(path=path)
            with self.subTest(path=path),self.assertRaises(ValueError): await download_media(bot,'opaque')
            self.assertEqual(session.streams,0)

    async def test_local_api_rejected_without_getfile_or_filesystem_access(self):
        bot,session=self.bot()
        session.api=TelegramAPIServer.from_base('http://127.0.0.1:8081',is_local=True)
        with self.assertRaises(UnsupportedCapability): await download_media(bot,'opaque')
        self.assertEqual(session.calls,[]);self.assertEqual(session.streams,0)

    async def test_total_timeout_and_cancellation_close_stream_without_retry(self):
        bot,session=self.bot(chunks=(b'abc','wait'),size=None)
        with self.assertRaises(TimeoutError): await download_media(bot,'opaque',timeout=.02)
        self.assertEqual(session.stream_closed,1);self.assertEqual(len(session.calls),1)
        bot,session=self.bot(chunks=(b'abc','wait'),size=None)
        task=asyncio.create_task(download_media(bot,'opaque'))
        while not session.streams: await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(session.stream_closed,1);self.assertEqual(len(session.calls),1)

    async def test_read_failure_and_invalid_chunk_close_stream_no_private_error_echo(self):
        for chunk in (TimeoutError('token-private-url'),bytearray(b'bad')):
            bot,session=self.bot(chunks=(b'abc',chunk),size=None)
            with self.assertRaises((TimeoutError,ValueError)) as raised: await download_media(bot,'opaque')
            self.assertEqual(session.stream_closed,1);self.assertEqual(len(session.calls),1)
            self.assertNotIn('token-private-url',safe_error_report(raised.exception,operation='read').message)

    def assert_token_hidden(self,error,token):
        rendered=''.join(traceback.format_exception(error))  # what logging.exception prints
        for text in (str(error),repr(error),rendered):
            self.assertNotIn(token,text)

    async def test_real_http_error_never_exposes_token_in_error_or_log(self):
        from aiohttp import web
        from aiogram.client.session.aiohttp import AiohttpSession
        token='123456:SECRET-DOWNLOAD-TOKEN'
        async def get_file(request):
            return web.json_response({'ok':True,'result':{'file_id':'opaque','file_unique_id':'unique','file_size':3,'file_path':'photos/a.jpg'}})
        async def content(request): return web.Response(status=404,text='missing')
        app=web.Application();app.router.add_post(f'/bot{token}/getFile',get_file);app.router.add_get(f'/file/bot{token}/photos/a.jpg',content)
        runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        port=runner.addresses[0][1]
        bot=Bot(token,session=AiohttpSession(api=TelegramAPIServer.from_base(f'http://127.0.0.1:{port}')))
        try:
            with self.assertRaises(TransportFailure) as raised: await download_media(bot,'opaque')
            self.assertEqual(str(raised.exception),'Telegram file endpoint returned HTTP 404')
            self.assertIsNone(raised.exception.__context__);self.assertIsNone(raised.exception.__cause__)
            self.assert_token_hidden(raised.exception,token)
            with self.assertLogs('aiogram.event',level='ERROR') as logs:
                logging.getLogger('aiogram.event').exception('Cause exception while process update\n%s: %s',
                    type(raised.exception).__name__,raised.exception,exc_info=raised.exception)
            self.assertNotIn(token,'\n'.join(logs.output))
        finally:
            await bot.session.close();await runner.cleanup()

    async def test_stream_timeout_and_transport_errors_with_token_url_are_replaced(self):
        url='https://api.telegram.org/file/bot100:DOWNLOAD_TEST/photos/a.jpg'
        class StatusError(Exception):
            status=503
        for chunk,expected in ((TimeoutError(f'Connection timeout to host {url}'),TimeoutError),
                               (StatusError(f'503, url={url}'),TransportFailure),(OSError(url),TransportFailure)):
            bot,session=self.bot(chunks=(b'abc',chunk),size=None)
            with self.subTest(error=type(chunk).__name__),self.assertRaises(expected) as raised:
                await download_media(bot,'opaque')
            self.assertEqual(session.stream_closed,1)
            self.assert_token_hidden(raised.exception,'DOWNLOAD_TEST')

    async def test_invalid_download_parameters_never_getfile(self):
        for options in ({'max_bytes':True},{'max_bytes':0},{'max_bytes':20_000_001},{'timeout':float('nan')},{'timeout':True},{'timeout':0}):
            bot,session=self.bot()
            with self.subTest(options=options),self.assertRaises(ValueError): await download_media(bot,'opaque',**options)
            self.assertEqual(session.calls,[])

    async def test_total_deadline_also_covers_getfile_without_starting_stream(self):
        bot,session=self.bot()
        async def wait(request):
            await asyncio.sleep(10)
        session.respond(GetFile,wait)
        with self.assertRaises(TimeoutError): await download_media(bot,'opaque',timeout=.02)
        self.assertEqual(session.streams,0);self.assertEqual(len(session.calls),1)


if __name__=='__main__': unittest.main()
