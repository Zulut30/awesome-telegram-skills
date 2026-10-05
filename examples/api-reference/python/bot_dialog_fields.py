"""Public mixed dialog API; synthetic parser/controller construction, no HTTP."""
import json
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Message
from telegram_patterns.aiogram import (FieldValue, NumberField, EmailField, PhoneField, DateField,
    FileField, ContactField, LocationField, DialogSubmission, dialog_form_router)

message=Message.model_validate({'message_id':1,'date':1,'chat':{'id':42,'type':'private'},
    'from':{'id':42,'is_bot':False,'first_name':'Owner'},
    'document':{'file_id':'opaque','file_unique_id':'unique','file_size':128},
    'contact':{'phone_number':'+48123456789','first_name':'Owner','user_id':42},
    'location':{'latitude':52.2,'longitude':21.0}})
fields: list[NumberField | EmailField | PhoneField | DateField | FileField | ContactField | LocationField] = [NumberField('number','Число','Число?',minimum=1,decimal_places=2),EmailField('email','Email','Email?'),
    PhoneField('phone','Телефон','Телефон?'),DateField('date','Дата','Дата?'),FileField('file','Файл','Файл?'),
    ContactField('contact','Контакт','Контакт?'),LocationField('geo','Место','Место?')]
value:FieldValue=fields[0].restore('12,50')
values={'number':value,'email':fields[1].restore('Case@EXAMPLE.COM'),'phone':fields[2].restore('+48 123 456 789'),
    'date':fields[3].restore('2024-02-29'),'file':fields[4].read(message),'contact':fields[5].read(message),'geo':fields[6].read(message)}
submission=DialogSubmission(100,42,42,'example-intent',values)
assert submission.values['number']=='12.5'
assert json.loads(json.dumps(submission.as_dict()))['contact']['user_id']==42
async def host_submit(s:DialogSubmission)->str:
    # Replace with host current ACL + durable operation_id transaction.
    raise RuntimeError('Reference construction does not run business effects')
dispatcher=Dispatcher(events_isolation=SimpleEventIsolation())
dispatcher.include_router(dialog_form_router(fields,host_submit))
print(json.dumps({'passed':True,'case':'bot_dialog_fields','network':False,'field_types':len(fields),'constructed_router':True}))
