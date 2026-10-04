import asyncio
from contextlib import closing
from datetime import datetime, timezone
import tempfile
from pathlib import Path
import sqlite3
import unittest

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, InaccessibleMessage, Message, Update, User
from aiogram.fsm.storage.memory import SimpleEventIsolation

from telegram_patterns import SQLiteOnce, InvalidCompletion, safe_error_report
from telegram_patterns.aiogram import (CommandReply, FormSubmission, InvalidField, TextField,
                                      command_router, text_form_router)
from telegram_patterns.testing import StubSession

DATE = datetime(2026, 10, 3, tzinfo=timezone.utc)
BOT_USER = User(id=100, is_bot=True, first_name='Fixture', username='forms_bot')


def topic(value):
    if value.lower() not in {'python', 'typescript'}:
        raise InvalidField('Выберите Python или TypeScript.')
    return value.lower()


class FieldTests(unittest.TestCase):
    def test_trim_validation_unicode_and_immutable_submission(self):
        field = TextField('topic', 'Тема', 'Какую тему выбрать?', validate=topic)
        self.assertEqual(field.read(' Python '), 'python')
        with self.assertRaisesRegex(InvalidField, 'Выберите'): field.read('other')
        for value in ('', ' ' * 3, '\ud800'):
            with self.assertRaises(InvalidField): field.read(value)
        with self.assertRaises(InvalidField): TextField('x', 'X', 'X?', max_length=3).read('😀😀')
        values = {'topic': 'python'}
        submission = FormSubmission(100, 42, 42, 'abc', values)
        values['topic'] = 'other'
        self.assertEqual(submission.values['topic'], 'python')
        self.assertNotIn('python', repr(submission))
        with self.assertRaises(TypeError): submission.values['topic'] = 'other'

    def test_bad_configuration_and_validator_contract(self):
        for kwargs in ({'name': 'bad:name'}, {'max_length': True}, {'max_length': 257}, {'label': ''}):
            with self.assertRaises(ValueError): TextField(**({'name': 'x', 'label': 'X', 'prompt': 'X?'} | kwargs))
        async def async_validator(value): return value
        with self.assertRaises(TypeError): TextField('x', 'X', 'X?', validate=async_validator)
        with self.assertRaises(ValueError): TextField('x', 'X', 'X?', validate=lambda value: None).read('ok')
        step = TextField('x', 'X', 'X?')
        for steps, kwargs in (([], {}), ([step, step], {}), ([step], {'name': 'x' * 17}), ([step], {'command': 'cancel'})):
            with self.assertRaises(ValueError): text_form_router(steps, lambda submission: None, **kwargs)
        with self.assertRaises(ValueError): InvalidField('error' * 100)


class FormTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        self.message_id = 0
        self.submissions = []
        self.session = (StubSession().respond(SendMessage, self.response)
                        .respond(AnswerCallbackQuery, True).respond(GetMe, BOT_USER))
        self.bot = Bot('100:TEST', session=self.session, default=DefaultBotProperties(parse_mode='HTML'))
        self.dp = self.app()

    async def asyncTearDown(self):
        await self.dp.fsm.close()
        await self.bot.session.close()

    def response(self, method):
        reply = Message(message_id=1000 + len(self.sent), date=DATE,
                        chat=Chat(id=method.chat_id, type='private'), text=method.text)
        self.sent.append((method, reply))
        return reply

    async def submit(self, submission):
        self.assertIsInstance(self.session.calls[-1], AnswerCallbackQuery, 'Submit did work before ACK')
        self.submissions.append(submission)
        return 'Заявка принята.'

    def app(self, submit=None, **kwargs):
        dp = Dispatcher(events_isolation=SimpleEventIsolation(), **kwargs)
        dp.include_router(text_form_router([
            TextField('topic', 'Тема', 'Python или TypeScript?', validate=topic),
            TextField('brief', 'Описание', 'Опишите задачу.', max_length=50)], submit or self.submit))
        dp.include_router(command_router([CommandReply('help', 'Помощь', 'Помощь проекта')]))
        return dp

    def event(self, text, actor=42, *, message_id=None, chat_type='private'):
        self.message_id += 1
        return Update(update_id=self.message_id, message=Message(
            message_id=message_id or self.message_id, date=DATE, chat=Chat(id=actor, type=chat_type),
            from_user=User(id=actor, is_bot=False, first_name='Fixture'), text=text))

    async def feed(self, text, actor=42, **kwargs):
        await self.dp.feed_update(self.bot, self.event(text, actor, **kwargs))

    def button(self, *, actor=None, callback_data=None, message=None):
        method, reply = next(item for item in reversed(self.sent) if item[0].reply_markup is not None)
        self.message_id += 1
        query = CallbackQuery(id=f'query-{self.message_id}', chat_instance='fixture',
                              from_user=User(id=actor or reply.chat.id, is_bot=False, first_name='Fixture'),
                              message=message or reply,
                              data=callback_data or method.reply_markup.inline_keyboard[0][0].callback_data)
        return Update(update_id=self.message_id, callback_query=query)

    async def ready(self, actor=42):
        for value in ('/apply', ' Python ', 'Учебный бот <text>'): await self.feed(value, actor)
        return self.button()

    async def context(self, actor=42):
        return self.dp.fsm.get_context(bot=self.bot, chat_id=actor, user_id=actor)

    async def test_success_review_confirmation_and_plain_text(self):
        update = await self.ready()
        self.assertEqual(self.submissions, [], 'Last field must not submit without confirmation')
        self.assertIn('Тема: python', self.sent[-1][0].text)
        self.assertIn('<text>', self.sent[-1][0].text)
        await self.dp.feed_update(self.bot, update)
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(dict(self.submissions[0].values), {'topic': 'python', 'brief': 'Учебный бот <text>'})
        self.assertEqual((self.submissions[0].bot_id, self.submissions[0].actor_id, self.submissions[0].chat_id), (100, 42, 42))
        context = await self.context()
        self.assertIsNone(await context.get_state())
        self.assertEqual(await context.get_data(), {})
        self.assertEqual(self.sent[-1][0].text, 'Заявка принята.')
        self.assertTrue(all(method.parse_mode is None for method, reply in self.sent))

    async def test_invalid_input_media_and_help_preserve_current_step(self):
        await self.feed('/apply')
        for value in ('bad', None, '😀' * 100): await self.feed(value)
        await self.feed('/help')
        self.assertEqual(self.sent[-1][0].text, 'Помощь проекта')
        await self.feed('python')
        self.assertIn('Шаг 2/2', self.sent[-1][0].text)
        await self.feed('Учебная задача')
        self.assertIn('Проверьте ответы', self.sent[-1][0].text)
        self.assertEqual(self.submissions, [])

    async def test_back_replaces_value_and_old_button_is_rejected(self):
        old = await self.ready()
        await self.feed('/back')
        await self.feed('Новое описание')
        new = self.button()
        await self.dp.feed_update(self.bot, old)
        self.assertEqual(self.submissions, [])
        await self.dp.feed_update(self.bot, new)
        self.assertEqual(self.submissions[0].values['brief'], 'Новое описание')

    async def test_cancel_and_back_at_first_step_preserve_unrelated_data(self):
        context = await self.context()
        await context.set_data({'host_preference': 'ru'})
        await self.feed('/apply')
        await self.feed('/back')
        self.assertIn('Шаг 1/2', self.sent[-1][0].text)
        await self.feed('/cancel')
        self.assertIsNone(await context.get_state())
        self.assertEqual(await context.get_data(), {'host_preference': 'ru'})
        self.assertEqual(self.submissions, [])

    async def test_two_users_do_not_share_answers(self):
        for value in ('/apply', 'python'): await self.feed(value, 42)
        for value in ('/apply', 'typescript', 'Вторая задача'): await self.feed(value, 43)
        await self.dp.feed_update(self.bot, self.button(actor=43))
        await self.feed('Первая задача', 42)
        await self.dp.feed_update(self.bot, self.button(actor=42))
        self.assertEqual([(item.actor_id, item.values['topic']) for item in self.submissions], [(43, 'typescript'), (42, 'python')])

    async def test_duplicate_text_does_not_fill_two_steps(self):
        await self.feed('/apply')
        update = self.event('python')
        await asyncio.gather(self.dp.feed_update(self.bot, update), self.dp.feed_update(self.bot, update))
        context = await self.context()
        form = (await context.get_data())['__telegram_patterns_form']
        self.assertEqual(form['index'], 1)
        self.assertEqual(form['values'], {'topic': 'python'})

    async def test_old_cancel_does_not_cancel_current_form(self):
        await self.feed('/apply')
        await self.feed('python')
        await self.feed('/cancel', message_id=1)
        self.assertIsNotNone(await (await self.context()).get_state())

    async def test_simultaneous_confirmations_have_one_service_call(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(submission):
            self.submissions.append(submission)
            entered.set()
            await release.wait()
            return 'Готово.'
        await self.dp.fsm.close()
        self.dp = self.app(delayed)
        update = await self.ready()
        first = asyncio.create_task(self.dp.feed_update(self.bot, update))
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(self.dp.feed_update(self.bot, self.button()))
        try:
            await asyncio.sleep(0)
            self.assertFalse(second.done(), 'Second update did not wait for event isolation')
        finally:
            release.set()
            await asyncio.gather(first, second)
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(len([item for item in self.session.calls if isinstance(item, AnswerCallbackQuery)]), 2)

    async def test_foreign_actor_bad_payload_and_inaccessible_callback_ack_without_effect(self):
        await self.ready()
        updates = [self.button(actor=99), self.button(callback_data='form:application:tampered:submit'),
                   self.button(message=InaccessibleMessage(message_id=1, chat=Chat(id=42, type='private'), date=0))]
        for update in updates: await self.dp.feed_update(self.bot, update)
        self.assertEqual(self.submissions, [])
        self.assertEqual(len([item for item in self.session.calls if isinstance(item, AnswerCallbackQuery)]), 3)

    async def test_failed_submit_keeps_retry_identity_and_freezes_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'requests.sqlite'
            once = SQLiteOnce(database)
            once.initialize()
            with closing(sqlite3.connect(database)) as db, db: db.execute('CREATE TABLE requests(id INTEGER PRIMARY KEY, topic TEXT)')
            attempts = []
            async def persist_then_lose_response(submission):
                attempts.append(submission.operation_id)
                result = once.run(f'actor:{submission.actor_id}', submission.operation_id, dict(submission.values),
                                  lambda db: {'id': db.execute('INSERT INTO requests(topic) VALUES (?)', (submission.values['topic'],)).lastrowid})
                if len(attempts) == 1: raise RuntimeError('fixture lost response after commit')
                self.assertTrue(result.replayed)
                return 'Заявка сохранена.'
            await self.dp.fsm.close()
            self.dp = self.app(persist_then_lose_response)
            update = await self.ready()
            with self.assertRaisesRegex(RuntimeError, 'lost response'): await self.dp.feed_update(self.bot, update)
            for command in ('/back', '/cancel', '/apply', 'new text'):
                await self.feed(command)
                self.assertIn('Отправка уже началась', self.sent[-1][0].text)
            await self.dp.feed_update(self.bot, self.button())
            self.assertEqual(attempts[0], attempts[1])
            with closing(sqlite3.connect(database)) as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 1)
            self.assertIsNone(await (await self.context()).get_state())

    async def test_invalid_feedback_after_effect_preserves_identity_for_reconciliation(self):
        identities = []
        async def persisted(submission):
            identities.append(submission.operation_id)
            return '' if len(identities) == 1 else 'Состояние существующей заявки подтверждено.'
        await self.dp.fsm.close()
        self.dp = self.app(persisted)
        update = await self.ready()
        with self.assertRaises(InvalidCompletion) as caught:
            await self.dp.feed_update(self.bot, update)
        self.assertEqual(safe_error_report(caught.exception, operation='write').recovery, 'reconcile')
        context = await self.context()
        self.assertEqual((await context.get_data())['__telegram_patterns_form']['operation_id'], identities[0])
        await self.feed('/apply')
        self.assertIn('Отправка уже началась', self.sent[-1][0].text)
        await self.dp.feed_update(self.bot, self.button())
        self.assertEqual(identities, [identities[0], identities[0]])
        self.assertIsNone(await context.get_state())

    async def test_feedback_failure_after_success_does_not_resubmit(self):
        update = await self.ready()
        def fail(method): raise RuntimeError('fixture feedback failure')
        self.session.respond(SendMessage, fail)
        with self.assertRaisesRegex(RuntimeError, 'feedback failure'): await self.dp.feed_update(self.bot, update)
        self.session.respond(SendMessage, self.response)
        await self.dp.feed_update(self.bot, update)
        self.assertEqual(len(self.submissions), 1)

    async def test_cancelled_submit_can_reconcile_with_same_identity(self):
        entered = asyncio.Event()
        identities = []
        async def delayed(submission):
            identities.append(submission.operation_id)
            if len(identities) == 1:
                entered.set()
                await asyncio.Future()
            return 'Результат подтверждён.'
        await self.dp.fsm.close()
        self.dp = self.app(delayed)
        update = await self.ready()
        task = asyncio.create_task(self.dp.feed_update(self.bot, update))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        await self.dp.feed_update(self.bot, self.button())
        self.assertEqual(identities[0], identities[1])
        self.assertIsNone(await (await self.context()).get_state())

    async def test_changed_schema_does_not_drop_pending_identity(self):
        await self.ready()
        context = await self.context()
        data = await context.get_data()
        data['__telegram_patterns_form'] = {**data['__telegram_patterns_form'], 'schema': ['previous_schema']}
        await context.set_data(data)
        with self.assertRaisesRegex(RuntimeError, 'schema migration'): await self.feed('/apply')
        self.assertEqual((await context.get_data())['__telegram_patterns_form']['operation_id'], data['__telegram_patterns_form']['operation_id'])

    async def test_default_isolation_and_disabled_fsm_fail_before_mutation(self):
        for dp in (Dispatcher(), Dispatcher(disable_fsm=True, events_isolation=SimpleEventIsolation())):
            dp.include_router(text_form_router([TextField('x', 'X', 'X?')], self.submit))
            try:
                with self.assertRaisesRegex(RuntimeError, 'enabled FSM'): await dp.feed_update(self.bot, self.event('/apply'))
                state = dp.fsm.get_context(bot=self.bot, chat_id=42, user_id=42)
                self.assertIsNone(await state.get_state())
            finally: await dp.fsm.close()

    async def test_unrelated_fsm_group_and_other_mention_are_preserved(self):
        context = await self.context()
        await context.set_state('Host:existing')
        for command in ('/apply', '/cancel', '/back'): await self.feed(command)
        self.assertEqual(await context.get_state(), 'Host:existing')
        await context.set_state(None)
        await self.feed('/apply', chat_type='group')
        await self.feed('/apply@other_bot')
        self.assertIsNone(await context.get_state())
        self.assertEqual(self.sent, [])


if __name__ == '__main__': unittest.main(verbosity=2)
