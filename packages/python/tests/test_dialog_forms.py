import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from telegram_patterns.aiogram import (ContactField, DateField, DialogSubmission, EmailField, FileField,
    InvalidField, LocationField, NumberField, PhoneField, TextField, dialog_form_router)
from telegram_patterns.testing import StubSession

DATE = datetime(2026,10,5,tzinfo=timezone.utc)
BOT = User(id=100,is_bot=True,first_name='Fixture',username='dialog_bot')
OWNER = User(id=42,is_bot=False,first_name='Owner')
FILE = dict(file_id='opaque-not-a-path',file_unique_id='unique',file_name='report.pdf',mime_type='application/pdf',file_size=1024)
CONTACT = dict(phone_number='+48123456789',first_name='Owner',last_name=None,user_id=42)
LOCATION = dict(latitude=52.2,longitude=21.0,horizontal_accuracy=50.0)
# UTF-8, прочитанный как CP1251: такие пары не встречаются в обычном русском тексте.
MOJIBAKE = '|'.join(ch.encode('utf-8').decode('cp1251')[:2] for ch in '—анлосиет')


class FieldTests(unittest.TestCase):
    def test_exact_decimal_and_bounds(self):
        f=NumberField('n','Число','Число?',minimum='-1.5',maximum=Decimal('100'),decimal_places=2)
        self.assertEqual(f.restore(' +001,50 '),'1.5')
        self.assertEqual(f.restore('-0.00'),'0')
        for value in ('1.005','1e2','NaN','100.01','-1.51','١٢',True,1.0,None,'\ud800'):
            with self.subTest(value=value),self.assertRaises(InvalidField): f.restore(value)
        for kwargs in ({'minimum':1.0},{'minimum':True},{'minimum':'Infinity'},{'minimum':2,'maximum':1},{'decimal_places':True},{'decimal_places':19},{'minimum':Decimal('1e-64')},{'maximum':Decimal('1e64')},{'minimum':Decimal('0e-63')}):
            with self.subTest(kwargs=kwargs),self.assertRaises((ValueError,TypeError)): NumberField('x','X','X?',**kwargs)

    def test_email_policy_and_non_verification(self):
        f=EmailField('email','Email','Email?')
        self.assertEqual(f.restore(' Case.Name+tag@EXAMPLE.COM '),'Case.Name+tag@example.com')
        for value in ('a..b@example.com','a@localhost','a@-example.com','a@com.','ü@example.com','a b@example.com','a@example.com\nBcc:x','a'*65+'@example.com'):
            with self.subTest(value=value),self.assertRaises(InvalidField): f.restore(value)

    def test_international_phone_no_guess_or_identity(self):
        f=PhoneField('phone','Телефон','Телефон?')
        self.assertEqual(f.restore('+48 (123) 456-789'),'+48123456789')
        for value in ('123456789','+01234567','+12345','+1234567890123456','+１２３４５６７','+48\n123456789'):
            with self.subTest(value=value),self.assertRaises(InvalidField): f.restore(value)

    def test_dates_real_leap_and_limits(self):
        f=DateField('date','Дата','Дата?',minimum='2024-02-01',maximum='2024-03-01')
        self.assertEqual(f.restore('2024-02-29'),'2024-02-29')
        for value in ('2023-02-29','2024-2-29','29.02.2024','2024-03-02','20240229','0000-01-01'):
            with self.subTest(value=value),self.assertRaises(InvalidField): f.restore(value)
        for kwargs in ({'minimum':'20240229'},{'minimum':True},{'minimum':'2025-01-01','maximum':'2024-01-01'}):
            with self.assertRaises(ValueError): DateField('x','X','X?',**kwargs)

    def test_document_metadata_and_untrusted_names(self):
        f=FileField('file','Файл','Файл?',max_bytes=2048,mime_types=('application/pdf',))
        self.assertEqual(f.restore(FILE),FILE)
        self.assertNotIn(FILE['file_id'],f.display(FILE))
        for changes in ({'file_size':None},{'file_size':2049},{'file_size':True},{'mime_type':'text/plain'},{'file_id':''},{'file_name':'a\nb'}):
            with self.subTest(changes=changes),self.assertRaises(InvalidField): f.restore(FILE|changes)
        for kwargs in ({'max_bytes':True},{'max_bytes':0},{'mime_types':None},{'mime_types':'application/pdf'},{'mime_types':('a'*128+'/b',)}):
            with self.subTest(kwargs=kwargs),self.assertRaises((ValueError,TypeError)): FileField('x','X','X?',**kwargs)
        self.assertEqual(f.restore(FILE|{'file_name':'../<b>report</b>.pdf'})['file_name'],'../<b>report</b>.pdf')

    def test_contact_owner_missing_id_and_forward(self):
        f=ContactField('contact','Контакт','Контакт?')
        m=Message(message_id=1,date=DATE,chat=Chat(id=42,type='private'),from_user=OWNER,contact=CONTACT)
        self.assertEqual(f.read(m),CONTACT)
        with self.assertRaises(InvalidField): f.read(m.model_copy(update={'contact':m.contact.model_copy(update={'user_id':99})}))
        with self.assertRaises(InvalidField): f.restore(CONTACT|{'user_id':None})
        self.assertEqual(ContactField('third','Контакт','Контакт?',own=False).restore(CONTACT|{'user_id':None})['user_id'],None)
        forwarded=Message.model_validate(m.model_dump()|{'forward_origin':{'type':'hidden_user','date':1,'sender_user_name':'Other'}})
        with self.assertRaises(InvalidField): f.read(forwarded)

    def test_location_bounds_nan_overflow_static_only(self):
        f=LocationField('geo','Место','Место?')
        self.assertEqual(f.restore(LOCATION),LOCATION)
        # JSON serializers may rewrite integral floats; parser retains one payload for replay.
        self.assertIs(type(f.restore(LOCATION|{'horizontal_accuracy':50})['horizontal_accuracy']),float)
        self.assertEqual(json.dumps(f.restore(LOCATION)),json.dumps(f.restore(LOCATION|{'horizontal_accuracy':50})))
        for changes in ({'latitude':float('nan')},{'longitude':181},{'horizontal_accuracy':1501},{'latitude':True},{'latitude':10**1000},{'horizontal_accuracy':10**1000}):
            with self.subTest(changes=changes),self.assertRaises(InvalidField): f.restore(LOCATION|changes)
        m=Message(message_id=1,date=DATE,chat=Chat(id=42,type='private'),from_user=OWNER,location=LOCATION|{'live_period':60})
        with self.assertRaises(InvalidField): f.read(m)

    def test_submission_deep_snapshot_and_json_copy(self):
        values={'file':dict(FILE),'email':'Case@example.com'}
        s=DialogSubmission(100,42,42,'abc',values)
        values['file']['file_id']='changed'
        self.assertEqual(s.values['file']['file_id'],FILE['file_id'])
        with self.assertRaises(TypeError): s.values['file']['file_id']='changed'
        fresh=s.as_dict();fresh['file']['file_id']='changed'
        self.assertEqual(s.values['file']['file_id'],FILE['file_id'])
        self.assertNotIn('Case@example',repr(s))
        self.assertEqual(json.loads(json.dumps(s.as_dict()))['file'],FILE)
        for invalid in ({'x': {'nested': {'value': 1}}}, {'x': {'lat': float('nan')}}, {'x': {'size': True}}, {'x': 1.0}, {}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): DialogSubmission(100,42,42,'abc',invalid)


class DialogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent=[];self.index=0;self.submissions=[]
        self.session=StubSession().respond(SendMessage,self.response).respond(AnswerCallbackQuery,True)
        self.bot=Bot('100:TEST',session=self.session,default=DefaultBotProperties(parse_mode='HTML'))
        self.dp=self.app([EmailField('email','Email','Email?'),ContactField('contact','Контакт','Контакт?')])

    async def asyncTearDown(self):
        await self.dp.fsm.close();await self.bot.session.close()

    def response(self,method):
        result=Message(message_id=1000+len(self.sent),date=DATE,chat=Chat(id=method.chat_id,type='private'),from_user=BOT,text=method.text)
        self.sent.append((method,result));return result

    async def submit(self,submission):
        self.assertIsInstance(self.session.calls[-1],AnswerCallbackQuery)
        self.submissions.append(submission);return 'Сохранено.'

    def app(self,fields,**kwargs):
        dp=Dispatcher(events_isolation=SimpleEventIsolation())
        dp.include_router(dialog_form_router(fields,self.submit,**kwargs))
        existing=Router()
        @existing.message(Command('help'))
        async def help(message): await message.answer('Existing help',parse_mode=None)
        dp.include_router(existing);return dp

    async def replace(self,fields,**kwargs):
        await self.dp.fsm.close();self.dp=self.app(fields,**kwargs)

    def state(self,actor=42,chat=42): return self.dp.fsm.get_context(bot=self.bot,chat_id=chat,user_id=actor)

    async def data(self): return (await self.state().get_data())['__telegram_patterns_dialog']

    async def message(self,text=None,*,reply=True,actor=42,chat=42,chat_type='private',message_id=None,**media):
        self.index+=1
        previous=self.sent[-1][1] if reply and self.sent else None
        message=Message(message_id=message_id or self.index,date=DATE,chat=Chat(id=chat,type=chat_type),
            from_user=User(id=actor,is_bot=False,first_name='Actor'),text=text,reply_to_message=previous,**media)
        await self.dp.feed_update(self.bot,Update(update_id=self.index,message=message))

    def button(self):
        method,message=self.sent[-1]
        return message,method.reply_markup.inline_keyboard[0][0].callback_data

    async def click(self,button=None,*,actor=42):
        self.index+=1
        message,data=button or self.button()
        await self.dp.feed_update(self.bot,Update(update_id=self.index,callback_query=CallbackQuery(id=str(self.index),
            from_user=User(id=actor,is_bot=False,first_name='Actor'),chat_instance='fixture',message=message,data=data)))

    async def complete(self):
        await self.message('/collect');await self.message('Case@EXAMPLE.COM')
        await self.message(contact=CONTACT);await self.click()
        return self.button()

    async def test_visible_texts_match_readable_reference(self):
        await self.message('/collect')
        self.assertEqual(self.sent[-1][0].text, 'Шаг 1/2. Email?\n/back — назад · /cancel — отмена')
        await self.message('Case@EXAMPLE.COM')
        prompt = self.sent[-1][0]
        self.assertEqual(prompt.text, 'Шаг 2/2. Контакт?\n/back — назад · /cancel — отмена')
        self.assertEqual(prompt.reply_markup.keyboard[0][0].text, 'Поделиться контактом')
        await self.message(contact=CONTACT)
        self.assertEqual(self.sent[-1][0].reply_markup.inline_keyboard[0][0].text, 'Подтвердить')
        await self.click()
        review = self.sent[-1][0]
        self.assertIn('Клавиатура ввода закрыта.', [method.text for method, _ in self.sent])
        self.assertTrue(review.text.startswith('Проверьте ответы:\n'))
        self.assertTrue(review.text.endswith('\n/back — исправить · /cancel — отмена'))
        self.assertEqual(review.reply_markup.inline_keyboard[0][0].text, 'Отправить')
        await self.message('/cancel')
        self.assertEqual(self.sent[-1][0].text, 'Форма отменена. Начать заново: /collect.')
        for method, _ in self.sent:
            self.assertNotRegex(method.text, MOJIBAKE)

    async def test_native_candidate_not_step_until_confirmation(self):
        await self.replace([EmailField('email','Email','Email?'),ContactField('contact','Контакт','Контакт?')],name='x'*16)
        await self.message('/collect');self.assertTrue(self.sent[-1][0].reply_markup.force_reply)
        await self.message('Case@EXAMPLE.COM')
        self.assertTrue(self.sent[-1][0].reply_markup.keyboard[0][0].request_contact)
        await self.message(contact=CONTACT)
        self.assertEqual(len((await self.data())['operation_id']),32)
        self.assertEqual(len(self.button()[1].encode('utf-8')),64)
        self.assertEqual((await self.data())['index'],1);self.assertEqual(self.submissions,[])
        self.assertTrue(any(getattr(m.reply_markup,'remove_keyboard',False) for m,_ in self.sent))
        await self.click();self.assertEqual((await self.data())['index'],2)
        self.assertEqual(self.submissions,[])
        await self.click();self.assertEqual(len(self.submissions),1)
        self.assertEqual(self.submissions[0].values['email'],'Case@example.com')
        self.assertIsNone(await self.state().get_state())
        self.assertTrue(self.sent[-1][0].reply_markup.remove_keyboard)
        self.assertTrue(all(m.parse_mode is None for m,_ in self.sent))

    async def test_reply_author_and_expected_question_guards(self):
        await self.message('/collect');first=self.sent[-1][1]
        await self.message('one@example.com',reply=False)
        self.assertEqual((await self.data())['index'],0)
        # Same message id on an attacker-authored reply cannot prove origin.
        spoof=first.model_copy(update={'from_user':OWNER})
        self.sent.append((self.sent[0][0],spoof))
        await self.message('one@example.com');self.assertEqual((await self.data())['index'],0)
        await self.message('/collect');current=self.sent[-1][1]
        self.sent.append((self.sent[0][0],first))
        await self.message('one@example.com');self.assertEqual((await self.data())['index'],0)
        self.sent.append((self.sent[0][0],current))
        await self.message('one@example.com');self.assertEqual((await self.data())['index'],1)

    async def test_wrong_owner_chat_group_business_and_other_state(self):
        await self.message('/collect');before=deepcopy(await self.data())
        await self.message('one@example.com',actor=99)
        await self.message('one@example.com',chat=43)
        await self.message('/collect',chat_type='group',chat=-42)
        await self.message('one@example.com',business_connection_id='business')
        await self.message('one@example.com',message_thread_id=7)
        await self.message('one@example.com',is_topic_message=True)
        self.assertEqual(await self.data(),before)
        await self.state(actor=99).set_state('host:other')
        await self.message('/collect',actor=99);self.assertEqual(await self.state(actor=99).get_state(),'host:other')

    async def test_replaced_native_candidate_stale_and_foreign_buttons(self):
        await self.message('/collect');await self.message('one@example.com');await self.message(contact=CONTACT)
        old=self.button()
        await self.message(contact=CONTACT|{'phone_number':'+48111111111'});current=self.button()
        await self.click(old);self.assertEqual((await self.data())['index'],1)
        await self.click(current,actor=99);self.assertEqual((await self.data())['index'],1)
        await self.click(current);self.assertEqual((await self.data())['values']['contact']['phone_number'],'+48111111111')
        await self.click(current);self.assertEqual(len(self.submissions),0)

    async def test_back_discards_later_values_rotates_intent_and_cancel_preserves_host(self):
        await self.state().update_data(host='preserved')
        button=await self.complete();old=(await self.data())['operation_id']
        await self.message('/back');d=await self.data()
        self.assertEqual(d['index'],1);self.assertEqual(set(d['values']),{'email'});self.assertNotEqual(d['operation_id'],old)
        await self.click(button);self.assertEqual(self.submissions,[])
        await self.message('/back');self.assertEqual((await self.data())['values'],{})
        await self.message('/cancel');self.assertIsNone(await self.state().get_state())
        self.assertEqual(await self.state().get_data(),{'host':'preserved'})

    async def test_resume_preserves_answers_but_invalidates_old_review(self):
        old=await self.complete();values=deepcopy((await self.data())['values']);key=(await self.data())['operation_id']
        await self.message('/collect');current=self.button()
        self.assertEqual((await self.data())['values'],values);self.assertEqual((await self.data())['operation_id'],key)
        await self.click(old);self.assertEqual(self.submissions,[])
        await self.click(current);self.assertEqual(len(self.submissions),1)
        await self.click(current);self.assertEqual(len(self.submissions),1)

    async def test_all_seven_fields_with_text_and_wrong_file_type(self):
        await self.replace([TextField('text','Текст','Текст?'),NumberField('number','Число','Число?'),
            EmailField('email','Email','Email?'),PhoneField('phone','Телефон','Телефон?'),DateField('date','Дата','Дата?'),
            FileField('file','Файл','Файл?'),ContactField('contact','Контакт','Контакт?'),LocationField('geo','Место','Место?')])
        await self.message('/collect')
        for text in ('Hi','12,50','Case@EXAMPLE.COM','+48 (123) 456-789','2024-02-29'): await self.message(text)
        await self.message('not a file');self.assertEqual((await self.data())['index'],5)
        await self.message(document=FILE)
        await self.message(contact=CONTACT);await self.click()
        await self.message(location=LOCATION);self.assertEqual((await self.data())['index'],7)
        await self.click();await self.click()
        s=self.submissions[0];self.assertEqual(s.values['number'],'12.5');self.assertEqual(s.values['date'],'2024-02-29')
        self.assertEqual(s.values['file']['file_id'],FILE['file_id']);self.assertEqual(s.values['geo']['latitude'],52.2)

    async def test_invalid_native_inputs_do_not_advance_or_confirm(self):
        await self.message('/collect');await self.message('one@example.com')
        for contact in (CONTACT|{'user_id':99},CONTACT|{'user_id':None}):
            await self.message(contact=contact);self.assertEqual((await self.data())['index'],1)
            self.assertIsNone((await self.data())['candidate'])
        await self.message('plain text');self.assertEqual((await self.data())['index'],1)

    async def test_unknown_submission_frozen_and_same_intent_retry(self):
        keys=[]
        async def unknown(submission):
            keys.append(submission.operation_id)
            if len(keys)==1: raise TimeoutError('lost receipt after host effect')
            return 'Reconciled.'
        await self.dp.fsm.close();self.dp=Dispatcher(events_isolation=SimpleEventIsolation())
        self.dp.include_router(dialog_form_router([EmailField('email','Email','Email?')],unknown))
        await self.message('/collect');await self.message('one@example.com');button=self.button()
        with self.assertRaises(TimeoutError): await self.click(button)
        pending=deepcopy(await self.data())
        for text in ('/back','/cancel','/collect','other@example.com'): await self.message(text)
        self.assertEqual(await self.data(),pending)
        await self.click(button);self.assertEqual(keys,[pending['operation_id']]*2)
        self.assertIsNone(await self.state().get_state())

    async def test_task_cancellation_retains_started_intent(self):
        started=asyncio.Event()
        async def waits(submission): started.set();await asyncio.Event().wait()
        await self.dp.fsm.close();self.dp=Dispatcher(events_isolation=SimpleEventIsolation())
        self.dp.include_router(dialog_form_router([EmailField('email','Email','Email?')],waits))
        await self.message('/collect');await self.message('one@example.com');button=self.button()
        task=asyncio.create_task(self.click(button));await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue((await self.data())['submission_started'])
        await self.message('/cancel');self.assertTrue((await self.data())['submission_started'])

    async def test_lost_prompt_resume_and_lost_success_feedback(self):
        async def lost(method): raise TimeoutError('unknown send')
        self.session.respond(SendMessage,lost)
        with self.assertRaises(TimeoutError): await self.message('/collect')
        self.assertIsNone((await self.data())['prompt_message_id'])
        self.session.respond(SendMessage,self.response)
        await self.message('one@example.com');self.assertEqual((await self.data())['index'],0)
        await self.message('/collect');await self.message('one@example.com');await self.message(contact=CONTACT);await self.click()
        button=self.button();self.session.respond(SendMessage,lost)
        with self.assertRaises(TimeoutError): await self.click(button)
        self.assertIsNone(await self.state().get_state());self.assertEqual(len(self.submissions),1)
        self.session.respond(SendMessage,self.response);await self.click(button);self.assertEqual(len(self.submissions),1)

    async def test_concurrent_final_confirmation_with_host_event_isolation(self):
        button=await self.complete()
        await asyncio.gather(self.click(button),self.click(button))
        self.assertEqual(len(self.submissions),1)

    async def test_schema_and_owner_corruption_fail_closed_without_reset(self):
        await self.message('/collect');data=await self.data()
        for key,value in (('schema',[999]),('owner',[100,42,99]),('index',True),('values',{'email':'bad'}),('prompt_message_id',-1)):
            corrupt=deepcopy(data);corrupt[key]=value
            await self.state().update_data(__telegram_patterns_dialog=corrupt)
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'reconciliation'): await self.message('/collect')
            self.assertEqual(await self.data(),corrupt)
        await self.state().update_data(__telegram_patterns_dialog=data)

    async def test_out_of_order_duplicate_message_and_existing_help(self):
        await self.message('/collect');await self.message('one@example.com');before=deepcopy(await self.data())
        await self.message(contact=CONTACT,message_id=1);self.assertEqual(await self.data(),before)
        await self.message('/help');self.assertEqual(self.sent[-1][0].text,'Existing help');self.assertEqual(await self.data(),before)

    async def test_disabled_fsm_and_bad_configuration_rejected(self):
        await self.dp.fsm.close();self.dp=Dispatcher()
        self.dp.include_router(dialog_form_router([EmailField('email','Email','Email?')],self.submit))
        with self.assertRaisesRegex(RuntimeError,'events_isolation'): await self.message('/collect')
        f=EmailField('x','X','X?')
        for fields,kwargs in (([],{}),([f,f],{}),([f],{'name':'x'*17}),([f],{'schema_version':True}),([f],{'command':'cancel'})):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError): dialog_form_router(fields,self.submit,**kwargs)


if __name__=='__main__':unittest.main()
