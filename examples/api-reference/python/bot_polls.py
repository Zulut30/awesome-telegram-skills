"""All public poll symbols, native quiz and available scoped observations."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.types import Message, Poll, PollAnswer, Update
from telegram_patterns.aiogram import (PollKind, PollChoice, PollSpec, PollOptionState, PollState, PollVote,
    PollOptionAddition, PollBinding, PollLocator, PollObservation, PollEvent, PollObserver, PollLookup,
    poll_request, poll_state, poll_vote, poll_option_added, poll_events_router)
from telegram_patterns.testing import StubSession


async def main():
    kind: PollKind='quiz'
    request=poll_request(PollSpec('Even numbers',[PollChoice('2'),'3','4'],kind=kind,correct_option_ids=[0,2],
                        allows_multiple_answers=True),chat_id=42)
    assert request.correct_option_ids==[0,2] and request.correct_option_id is None
    native=Poll.model_validate({'id':'p','question':'Q','options':[{'text':'A','voter_count':0,'persistent_id':'stable-a'}],
        'total_voter_count':1,'is_closed':False,'is_anonymous':False,'type':'regular','allows_multiple_answers':False,
        'allows_revoting':True,'members_only':False})
    state: PollState=poll_state(native); option: PollOptionState=state.options[0]
    assert option.persistent_id=='stable-a' and state.correct_option_ids is None
    answer=PollAnswer.model_validate({'poll_id':'p','option_ids':[0],'option_persistent_ids':['stable-a'],
                                     'user':{'id':42,'is_bot':False,'first_name':'Voter'}})
    selection: PollVote=poll_vote(answer); observation: PollObservation=selection
    assert selection.option_persistent_ids==('stable-a',)
    sent=Message.model_validate({'message_id':10,'date':1780000000,'chat':{'id':42,'type':'private'},
                                 'from':{'id':100,'is_bot':True,'first_name':'Bot'},'poll':native})
    binding=PollBinding.from_message(sent,bot_id=100)
    service=sent.model_copy(update={'poll':None}).model_dump(mode='json',by_alias=True)
    service['poll_option_added']={'option_persistent_id':'stable-new','option_text':'B','poll_message':{
        'chat':{'id':42,'type':'private'},'message_id':10,'date':0}}
    addition: PollOptionAddition=poll_option_added(Message.model_validate(service))
    assert addition.poll_id is None and addition.message_id==10
    events=[]
    async def lookup(locator:PollLocator)->PollBinding|None:
        return binding if locator.bot_id==100 and locator.poll_id==binding.poll_id else None
    async def observe(event:PollEvent)->None: events.append(event)
    host_lookup: PollLookup=lookup; host_observer: PollObserver=observe
    assert PollEvent(1,binding,observation).binding==binding
    session=StubSession(); bot=Bot('100:POLL_REFERENCE',session=session); dispatcher=Dispatcher()
    dispatcher.include_router(poll_events_router(host_lookup,host_observer))
    try:
        await dispatcher.feed_update(bot,Update(update_id=2,poll_answer=answer))
        assert len(events)==1 and events[0].update_id==2 and not session.calls
    finally:
        await dispatcher.fsm.close(); await bot.session.close()
    print(json.dumps({'case':'bot_polls','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__': asyncio.run(main())
