"""Server rules, stale/context boundaries, confirmation and actual SDK composition."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest
from unittest.mock import patch

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from aiogram.types import CallbackQuery, Update

from telegram_patterns import (ConflictFailure, SelectionContext, SelectionMenu, SelectionOption,
                               SelectionResult, SelectionSpec, SelectionState, UnknownOutcome, ValidationFailure)
from telegram_patterns.aiogram import KeyboardCapabilities, KeyboardLayout, selection_keyboard, selection_router
from telegram_patterns.testing import StubSession


def spec(**changes):
    return SelectionSpec([SelectionOption('a', '<Alpha>', ['first']), SelectionOption('b', 'Beta', ['second']),
                          SelectionOption('c', 'Unavailable', enabled=False)],
                         toggles={'notify': 'Уведомлять'}, filters={'all': 'Все', 'first': 'Первая', 'second': 'Вторая'},
                         quantity_min=1, quantity_max=3, max_selected=2, **changes)


CONTEXT = SelectionContext(100, 7, 7, 10)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.menu = SelectionMenu(spec(), CONTEXT)

    def act(self, action):
        return self.menu.apply(self.menu.state.callback(action), CONTEXT)

    def test_toggle_multiselect_quantity_and_deselect_are_server_owned(self):
        self.assertEqual(self.act('t:notify').state.toggles, (('notify', True),))
        self.act('s:b'); self.act('s:a')
        self.assertEqual(self.menu.state.selected, ('a', 'b'))
        self.assertEqual(self.act('q:inc').state.quantity, 2)
        self.assertEqual(self.act('s:a').state.selected, ('b',))
        self.assertEqual(self.act('t:notify').state.toggles, (('notify', False),))

    def test_filter_preserves_hidden_selection_but_rejects_invisible_option(self):
        self.act('s:a'); self.act('f:second')
        state = self.menu.state
        self.assertEqual(self.act('s:a').status, 'invalid')
        self.assertIs(self.menu.state, state)
        self.assertEqual(self.act('s:b').state.selected, ('a', 'b'))
        self.assertIn('<Alpha>', self.menu.state.text())

    def test_disabled_unknown_options_and_fields_do_not_mutate(self):
        for action in ('s:c', 's:missing', 't:missing', 'f:missing', 'q:dec'):
            with self.subTest(action=action):
                state = self.menu.state
                self.assertEqual(self.act(action).status, 'invalid')
                self.assertIs(self.menu.state, state)

    def test_selection_limit_and_quantity_bounds_are_enforced(self):
        self.menu = SelectionMenu(replace(spec(), max_selected=1), CONTEXT)
        self.act('s:a')
        self.assertEqual(self.act('s:b').status, 'invalid')
        self.act('q:inc'); self.act('q:inc')
        self.assertEqual(self.act('q:inc').status, 'invalid')
        self.assertEqual(self.menu.state.quantity, 3)

    def test_minimum_is_checked_before_confirmation(self):
        self.menu = SelectionMenu(spec(min_selected=1), CONTEXT)
        before = self.menu.state
        self.assertEqual(self.act('ask').status, 'invalid')
        self.assertIs(self.menu.state, before)
        self.act('s:a')
        self.assertEqual(self.act('ask').status, 'confirming')

    def test_snapshots_copy_mutable_inputs_and_are_immutable(self):
        tags = ['first']; labels = {'notify': 'Уведомлять'}
        option = SelectionOption('a', 'Alpha', tags)
        options = [option]
        rules = SelectionSpec(options, toggles=labels, filters={'all': 'Все', 'first': 'Первая'})
        tags.clear(); labels.clear(); options.clear()
        self.assertEqual(rules.options[0].filters, ('first',))
        self.assertEqual(rules.toggles['notify'], 'Уведомлять')
        with self.assertRaises(TypeError): rules.toggles['notify'] = 'Changed'
        old = self.menu.state
        self.act('s:a')
        self.assertEqual(old.selected, ())
        self.assertIsInstance(old, SelectionState)

    def test_owner_and_every_context_guard_hides_other_state(self):
        data = self.menu.state.callback('s:a')
        for change, status in [({'owner_id': 8}, 'denied'), ({'bot_id': 101}, 'stale'),
                               ({'chat_id': 8}, 'stale'), ({'message_id': 11}, 'stale'), ({'message_thread_id': 3}, 'stale')]:
            before = self.menu.state
            result = self.menu.apply(data, replace(CONTEXT, **change))
            self.assertEqual(result.status, status)
            self.assertIsNone(result.state)
            self.assertIs(self.menu.state, before)

    def test_malformed_forged_and_old_revision_callbacks_are_stale(self):
        old = self.menu.state.callback('s:a')
        self.menu.apply(old, CONTEXT)
        for data in (old, old.replace(':0:', ':01:'), old.replace('s:a', 'q:999'),
                     'sel:' + '0' * 16 + ':1:s:a', old + 'x' * 70, '', None):
            before = self.menu.state
            self.assertEqual(self.menu.apply(data, CONTEXT).status, 'stale')
            self.assertIs(self.menu.state, before)

    def test_confirmation_is_exact_revision_nonce_and_consumed_once(self):
        self.act('s:a'); self.act('t:notify'); self.act('q:inc')
        result = self.act('ask')
        self.assertEqual(result.status, 'confirming')
        self.assertEqual(self.act('y:' + '0' * 16).status, 'stale')
        data = self.menu.state.callback('y:' + result.state.confirmation_id)
        accepted = self.menu.apply(data, CONTEXT)
        self.assertEqual(accepted.status, 'confirmed')
        self.assertEqual((accepted.state.selected, accepted.state.quantity), (('a',), 2))
        self.assertIsNotNone(accepted.state.operation_id)
        self.assertEqual(self.menu.apply(data, CONTEXT).status, 'stale')
        self.assertEqual(self.act('refresh').status, 'stale')

    def test_back_and_edit_revoke_the_previous_confirmation(self):
        self.act('s:a'); self.act('ask')
        old = self.menu.state.callback('y:' + self.menu.state.confirmation_id)
        self.assertEqual(self.act('s:b').status, 'stale')
        self.act('back'); self.act('s:b'); self.act('ask')
        self.assertEqual(self.menu.apply(old, CONTEXT).status, 'stale')
        self.assertEqual(self.menu.state.selected, ('a', 'b'))

    def test_confirmation_expiry_and_refresh_do_not_extend_old_confirmation(self):
        with patch('telegram_patterns.selection.time.monotonic', return_value=100):
            self.menu = SelectionMenu(spec(), CONTEXT, confirmation_ttl_seconds=5)
            self.act('ask')
        state = self.menu.state
        with patch('telegram_patterns.selection.time.monotonic', return_value=105):
            self.assertEqual(self.act('y:' + state.confirmation_id).status, 'stale')
            self.assertIs(self.menu.state, state)
            self.act('refresh')
            self.assertEqual(self.menu.state.phase, 'editing')
            self.assertIsNone(self.menu.state.confirmation_id)

    def test_menu_expiry_is_not_implicitly_renewed_by_rule_refresh(self):
        with patch('telegram_patterns.selection.time.monotonic', return_value=100):
            self.menu = SelectionMenu(spec(), CONTEXT, ttl_seconds=1)
        with patch('telegram_patterns.selection.time.monotonic', return_value=102):
            self.menu.replace_spec(replace(spec(), resource_version='2'))
            self.assertEqual(self.act('s:a').status, 'stale')
        self.assertEqual(self.menu.state.expires_at, 101)

    def test_changed_server_rules_revoke_confirm_and_remove_invalid_values(self):
        self.act('s:a'); self.act('s:b'); self.act('q:inc'); self.act('t:notify'); self.act('ask')
        old = self.menu.state.callback('y:' + self.menu.state.confirmation_id)
        updated = replace(spec(), options=[SelectionOption('b', 'Beta', ['second'])], max_selected=1,
                          quantity_max=1, toggles={}, resource_version='2')
        state = self.menu.replace_spec(updated)
        self.assertEqual((state.selected, state.quantity, state.toggles, state.phase), (('b',), 1, (), 'editing'))
        self.assertEqual(self.menu.apply(old, CONTEXT).status, 'stale')
        same = self.menu.state
        self.assertIs(self.menu.replace_spec(updated), same)

    def test_cancel_is_terminal_and_no_operation_is_issued(self):
        self.act('ask')
        cancelled = self.act('cancel')
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertIsNone(cancelled.state.operation_id)
        self.assertEqual(self.act('ask').status, 'stale')
        with self.assertRaises(ConflictFailure): self.menu.replace_spec(replace(spec(), resource_version='2'))

    def test_thread_concurrent_same_revision_changes_draft_once(self):
        data = self.menu.state.callback('s:a')
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.menu.apply(data, CONTEXT), range(20)))
        self.assertEqual([r.status for r in results].count('accepted'), 1)
        self.assertEqual([r.status for r in results].count('stale'), 19)
        self.assertEqual(self.menu.state.selected, ('a',))

    def test_native_callback_budget_and_invalid_constructor_fields(self):
        menu = SelectionMenu(SelectionSpec([SelectionOption('a' * 24, 'A')]), CONTEXT, prefix='abcdefgh:')
        state = replace(menu.state, revision=9_999_999_999)
        self.assertEqual(len(state.callback('s:' + 'a' * 24).encode()), 63)
        for changes in ({'ttl_seconds': True}, {'ttl_seconds': float('nan')}, {'quantity': True},
                        {'selected': ['c']}, {'toggles': {'notify': 1}}, {'prefix': 'a:b:'}):
            with self.subTest(changes=changes), self.assertRaises((ValidationFailure, TypeError)):
                SelectionMenu(spec(), CONTEXT, **changes)
        for make in (lambda: SelectionOption('x', 'x\n'), lambda: SelectionOption('x', 'x', [['bad']]),
                     lambda: SelectionSpec([SelectionOption('x', 'x')], filters={}),
                     lambda: SelectionSpec([SelectionOption('x', 'x')], quantity_min=True),
                     lambda: SelectionSpec([SelectionOption('x', 'x')], min_selected=2),
                     lambda: SelectionContext(True, 7, 7, 10)):
            with self.assertRaises((ValidationFailure, TypeError)): make()


class SelectionRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.menu = SelectionMenu(spec(), CONTEXT)
        self.session = StubSession().respond(AnswerCallbackQuery, True)
        self.bot = Bot('100:SELECTION_FIXTURE', session=self.session, default=DefaultBotProperties(parse_mode='HTML'))
        self.results = []
        self.uid = 0
        self.chat_type = 'private'
        def response(method):
            return {'message_id': method.message_id, 'date': 1, 'chat': {'id': method.chat_id, 'type': 'private'},
                    'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}, 'text': method.text,
                    'reply_markup': method.reply_markup.model_dump(exclude_none=True)}
        self.response = response
        self.session.respond(EditMessageText, response)
        self.dp = Dispatcher()
        async def feedback(query, result): self.results.append(result)
        self.feedback = feedback
        self.dp.include_router(selection_router(self.menu, on_result=feedback))

    async def asyncTearDown(self):
        await self.dp.fsm.close()
        await self.bot.session.close()
        self.assertTrue(self.session.closed)

    def query(self, data, **changes):
        self.uid += 1
        payload = {'id':str(self.uid), 'from':{'id':7,'is_bot':False,'first_name':'Owner'}, 'data':data,
                   'chat_instance':'fixture', 'message':{'message_id':10,'date':1,'chat':{'id':7,'type':self.chat_type},
                   'from':{'id':100,'is_bot':True,'first_name':'Fixture'}}}
        for key, value in changes.items():
            if key == 'actor': payload['from']['id'] = value
            elif key == 'chat': payload['message']['chat']['id'] = value
            else: payload['message'][key] = value
        return CallbackQuery.model_validate(payload, context={'bot':self.bot})

    async def feed(self, data, **changes):
        query = self.query(data, **changes)
        await self.dp.feed_update(self.bot, Update(update_id=self.uid, callback_query=query))
        return self.results[-1]

    async def test_real_dispatcher_plain_text_and_selected_markup(self):
        result = await self.feed(self.menu.state.callback('s:a'))
        self.assertEqual(result.status, 'accepted')
        edit = self.session.calls[-1]
        self.assertIsInstance(edit, EditMessageText)
        self.assertIsNone(edit.parse_mode)
        self.assertIn('<Alpha>', edit.text)
        self.assertEqual(edit.message_id, 10)
        self.assertTrue(edit.reply_markup.inline_keyboard[0][0].text.startswith('✓'))

    async def test_foreign_wrong_message_inaccessible_and_business_ack_without_edit(self):
        data = self.menu.state.callback('s:a')
        for changes in ({'actor':8}, {'chat':8}, {'message_id':11}, {'message_thread_id':3},
                        {'date':0}, {'business_connection_id':'b'}, {'from':{'id':101,'is_bot':True,'first_name':'Other'}}):
            before = self.menu.state
            self.assertIn((await self.feed(data, **changes)).status, {'denied','stale'})
            self.assertIs(self.menu.state, before)
        self.assertFalse(any(isinstance(c, EditMessageText) for c in self.session.calls))
        self.assertEqual(len(self.session.calls), 7)

    async def test_concurrent_updates_ack_before_slow_edit_and_old_revision_is_stale(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def slow(method):
            started.set(); await release.wait(); return self.response(method)
        self.session.respond(EditMessageText, slow)
        data = self.menu.state.callback('s:a')
        first = asyncio.create_task(self.feed(data))
        await started.wait()
        second = asyncio.create_task(self.feed(data))
        for _ in range(50):
            if sum(isinstance(c,AnswerCallbackQuery) for c in self.session.calls)==2: break
            await asyncio.sleep(0)
        self.assertEqual(sum(isinstance(c,AnswerCallbackQuery) for c in self.session.calls), 2)
        release.set(); await asyncio.gather(first, second)
        self.assertEqual([r.status for r in self.results], ['accepted','stale'])
        self.assertEqual(sum(isinstance(c,EditMessageText) for c in self.session.calls), 1)

    async def test_host_refresh_rejects_old_confirmation_before_business_hook(self):
        self.menu.apply(self.menu.state.callback('s:a'), CONTEXT)
        self.menu.apply(self.menu.state.callback('ask'), CONTEXT)
        data = self.menu.state.callback('y:' + self.menu.state.confirmation_id)
        await self.dp.fsm.close()
        self.dp = Dispatcher()
        async def fresh(query, menu): return replace(spec(), resource_version='2')
        self.dp.include_router(selection_router(self.menu, load_spec=fresh, on_result=self.feedback))
        self.assertEqual((await self.feed(data)).status, 'stale')
        self.assertEqual(self.menu.state.phase, 'editing')
        self.assertIsNone(self.menu.state.operation_id)
        self.assertFalse(any(isinstance(c,EditMessageText) for c in self.session.calls))

    async def test_edit_timeout_retains_server_value_and_refresh_uses_same_message(self):
        def lost(method): raise TimeoutError('private transport detail')
        self.session.respond(EditMessageText, lost)
        old = self.menu.state.callback('s:a')
        with self.assertRaises(TimeoutError): await self.feed(old)
        self.assertEqual(self.menu.state.selected, ('a',))
        self.assertEqual((await self.feed(old)).status, 'stale')
        self.session.respond(EditMessageText, self.response)
        await self.feed(self.menu.state.callback('refresh'))
        self.assertEqual(self.session.calls[-1].message_id, 10)
        self.assertEqual(self.menu.state.selected, ('a',))

    async def test_cancel_during_edit_retains_state_and_releases_display_lock(self):
        started = asyncio.Event()
        async def slow(method): started.set(); await asyncio.Future()
        self.session.respond(EditMessageText, slow)
        task = asyncio.create_task(self.feed(self.menu.state.callback('s:a')))
        await started.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(self.menu.state.selected, ('a',))
        self.session.respond(EditMessageText, self.response)
        await self.feed(self.menu.state.callback('refresh'))
        self.assertEqual(self.menu.state.revision, 2)

    async def test_confirmation_hook_runs_once_before_display_and_unknown_hook_is_not_retried(self):
        await self.dp.fsm.close(); self.dp = Dispatcher()
        intents=[]
        async def effect(query, result):
            self.results.append(result)
            if result.status=='confirmed':
                intents.append(result.state.operation_id)
                raise UnknownOutcome('fixture business outcome unknown')
        self.dp.include_router(selection_router(self.menu, on_result=effect))
        await self.feed(self.menu.state.callback('s:a'))
        await self.feed(self.menu.state.callback('ask'))
        data=self.menu.state.callback('y:'+self.menu.state.confirmation_id)
        with self.assertRaises(UnknownOutcome): await self.feed(data)
        self.assertEqual((await self.feed(data)).status,'stale')
        self.assertEqual(len(intents),1)
        self.assertEqual(self.menu.state.phase,'confirmed')

    async def test_markup_filters_layout_styles_and_terminal_controls(self):
        self.menu.apply(self.menu.state.callback('s:a'), CONTEXT)
        state=self.menu.state
        unknown=selection_keyboard(state,layout=KeyboardLayout((1,)))
        self.assertTrue(all(b.style is None for row in unknown.inline_keyboard for b in row))
        shown=selection_keyboard(state,capabilities=KeyboardCapabilities(styles=True))
        self.assertEqual(shown.inline_keyboard[0][0].style,'success')
        self.assertFalse(any('Unavailable' in b.text for row in shown.inline_keyboard for b in row))
        self.menu.apply(state.callback('f:second'), CONTEXT)
        filtered=selection_keyboard(self.menu.state)
        self.assertFalse(any('<Alpha>' in b.text for row in filtered.inline_keyboard for b in row))
        self.menu.apply(self.menu.state.callback('cancel'), CONTEXT)
        self.assertEqual(selection_keyboard(self.menu.state).inline_keyboard,[])

    async def test_awaited_server_load_rechecks_revision_and_never_loads_foreign(self):
        await self.dp.fsm.close(); self.dp=Dispatcher()
        started, release=asyncio.Event(),asyncio.Event()
        loads=[]
        async def fresh(query,menu):
            loads.append(query.from_user.id)
            started.set(); await release.wait(); return spec()
        self.dp.include_router(selection_router(self.menu,load_spec=fresh,on_result=self.feedback))
        data=self.menu.state.callback('s:a')
        self.assertEqual((await self.feed(data,actor=8)).status,'denied')
        self.assertFalse(loads)
        task=asyncio.create_task(self.feed(data))
        await started.wait()
        self.menu.apply(self.menu.state.callback('t:notify'),CONTEXT)
        release.set(); await task
        self.assertEqual(self.results[-1].status,'stale')
        self.assertEqual(self.menu.state.selected,())
        self.assertFalse(any(isinstance(c,EditMessageText) for c in self.session.calls))

    async def test_static_router_inherits_custom_prefix_and_rejects_explicit_mismatch(self):
        await self.dp.fsm.close(); self.dp=Dispatcher()
        self.menu=SelectionMenu(spec(),CONTEXT,prefix='choose:')
        with self.assertRaises(ValidationFailure): selection_router(self.menu,prefix='other:')
        self.dp.include_router(selection_router(self.menu,on_result=self.feedback))
        self.assertEqual((await self.feed(self.menu.state.callback('s:a'))).status,'accepted')

    async def test_topic_context_and_wrong_edit_response_preserve_server_draft(self):
        await self.dp.fsm.close(); self.dp=Dispatcher()
        self.menu=SelectionMenu(spec(),SelectionContext(100,7,-70,10,3))
        self.chat_type='supergroup'
        self.dp.include_router(selection_router(lambda query:self.menu,capabilities=KeyboardCapabilities(chat_type='supergroup'),on_result=self.feedback))
        def reply(method):
            result=self.response(method)
            result['chat']['type']='supergroup'; result['message_thread_id']=3
            return result
        self.session.respond(EditMessageText,reply)
        query=self.query(self.menu.state.callback('s:a'),chat=-70,message_thread_id=3)
        await self.dp.feed_update(self.bot,Update(update_id=self.uid,callback_query=query))
        self.assertEqual(self.menu.state.selected,('a',))
        self.session.respond(EditMessageText,True)
        query=self.query(self.menu.state.callback('s:b'),chat=-70,message_thread_id=3)
        with self.assertRaises(UnknownOutcome):
            await self.dp.feed_update(self.bot,Update(update_id=self.uid,callback_query=query))
        self.assertEqual(self.menu.state.selected,('a','b'))
