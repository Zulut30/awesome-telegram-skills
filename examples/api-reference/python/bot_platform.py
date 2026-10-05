"""Public platform API, mandatory host hooks and native multipart story bridge."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import CreateForumTopic, GetChat, GetChatMember, GetManagedBotToken, GetMe, PostStory
from aiogram.types import BufferedInputFile, InputFile, Update
from telegram_patterns.aiogram import (PlatformContract, PlatformScope, PlatformPermit, PlatformAction,
    PlatformReceipt, PlatformResult, PlatformHooks, SecretToken, PlatformEvent, PlatformLookup, PlatformObserver,
    platform_contracts, execute_platform_action, managed_bot_link, platform_event, platform_events_router,
    StoryPhotoUpload, StoryVideoUpload)
from telegram_patterns.testing import StubSession


async def main():
    contract:PlatformContract=platform_contracts()[0]
    assert contract.family=='topics' and contract.verification=='sdk'
    scope=PlatformScope(100,42,'reference-topic',chat_id=-100)
    action=PlatformAction(scope,CreateForumTopic(chat_id=-100,name='Topic'))
    class Host:
        def __init__(self):self.claimed=set();self.receipts=[]
        async def authorize(self,action:PlatformAction)->PlatformPermit:
            return PlatformPermit(allowed=action.scope.actor_id==42,managed_bot_bound=True)
        async def claim(self,action:PlatformAction,permit:PlatformPermit)->bool:
            key=(action.scope.bot_id,action.scope.operation_id)
            if key in self.claimed:return False
            self.claimed.add(key);return True  # Memory fixture; production host persists atomically.
        async def record(self,action:PlatformAction,receipt:PlatformReceipt)->None:self.receipts.append(receipt)
    host=Host();hooks:PlatformHooks=host
    bot_user={'id':100,'is_bot':True,'first_name':'Bot','username':'fixture_bot','can_manage_bots':True}
    types={'unlimited_gifts':True,'limited_gifts':True,'unique_gifts':True,'premium_subscription':True,'gifts_from_channels':True}
    session=StubSession().respond(GetMe,bot_user).respond(GetChat,{'id':-100,'type':'supergroup','is_forum':True,
        'accent_color_id':0,'max_reaction_count':1,'accepted_gift_types':types})
    session.respond(GetChatMember,{'status':'creator','user':bot_user,'is_anonymous':False})
    session.respond(CreateForumTopic,{'message_thread_id':17,'name':'Topic','icon_color':7322096})
    session.respond(GetManagedBotToken,'500:REFERENCE_SECRET_TOKEN_123456789')
    bot=Bot('100:PLATFORM_REFERENCE_FIXTURE',session=session);dispatcher=Dispatcher();seen=[]
    async def locate(event:PlatformEvent)->PlatformScope|None:
        return PlatformScope(100,42,'reference-event',chat_id=-100,message_thread_id=17)
    async def observed(event:PlatformEvent,scope:PlatformScope)->None:seen.append(event.kind)
    lookup:PlatformLookup=locate;observer:PlatformObserver=observed
    dispatcher.include_router(platform_events_router(lookup,observer))
    try:
        result:PlatformResult=await execute_platform_action(bot,action,hooks)
        receipt:PlatformReceipt=result.receipt
        assert receipt.result_id==17 and len(host.receipts)==1
        secret_result=await execute_platform_action(bot,PlatformAction(PlatformScope(100,42,'reference-secret',owner_id=42,child_bot_id=500),GetManagedBotToken(user_id=500)),hooks)
        assert isinstance(secret_result.value,SecretToken) and 'SECRET' not in repr(secret_result.value)
        assert secret_result.value.reveal().startswith('500:')  # Explicit host secret-store handoff, not logging.
        assert '%26' in managed_bot_link('ManagerBot','ExampleBot',name='Example & Bot')
        for content in (StoryPhotoUpload(photo=BufferedInputFile(b'PHOTO','photo.jpg')),
                        StoryVideoUpload(video=BufferedInputFile(b'VIDEO','video.mp4'),duration=1)):
            request=PostStory(business_connection_id='fixture',content=content,active_period=21600,parse_mode=None)
            files:dict[str,InputFile]={};encoded=bot.session.prepare_value(request.model_dump(warnings=False),bot,files)
            data=json.loads(encoded);key=data['content'][content.type].removeprefix('attach://')
            uploaded=files[key]
            assert isinstance(uploaded,BufferedInputFile) and uploaded.data in (b'PHOTO',b'VIDEO')
        update=Update.model_validate({'update_id':1,'message':{'message_id':10,'message_thread_id':17,'date':1780000000,
            'chat':{'id':-100,'type':'supergroup'},'forum_topic_created':{'name':'Topic','icon_color':7322096}}})
        event=platform_event(update,bot_id=100);assert isinstance(event,PlatformEvent) and event.kind=='forum_topic_created'
        await dispatcher.feed_update(bot,update);assert seen==['forum_topic_created']
    finally:await dispatcher.fsm.close();await bot.session.close()
    print(json.dumps({'case':'bot_platform','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__':asyncio.run(main())
