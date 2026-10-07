import asyncio
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import BufferedInputFile, InputMediaPhoto, Message, Poll, PollAnswer, Update

from telegram_patterns import FormattedText, InvalidType, PermissionDenied, TextEntity, ValidationFailure
from telegram_patterns.aiogram import (
    PollBinding,
    PollChoice,
    PollEvent,
    PollLocator,
    PollSpec,
    PollState,
    PollVote,
    poll_events_router,
    poll_option_added,
    poll_request,
    poll_state,
    poll_vote,
)
from telegram_patterns.testing import StubSession

WHEN = datetime(2026, 10, 5, tzinfo=timezone.utc)


def native_poll(**kwargs):
    return Poll.model_validate(
        {
            'id': 'poll-a',
            'question': 'Private question',
            'options': [
                {'text': 'A', 'voter_count': 0, 'persistent_id': 'stable-a'},
                {'text': 'B', 'voter_count': 0, 'persistent_id': 'stable-b'},
            ],
            'total_voter_count': 3,
            'is_closed': False,
            'is_anonymous': False,
            'type': 'regular',
            'allows_multiple_answers': True,
            'allows_revoting': True,
            'members_only': False,
            **kwargs,
        }
    )


def message(**kwargs):
    return Message.model_validate(
        {
            'message_id': 10,
            'date': 1780000000,
            'chat': {'id': -100, 'type': 'supergroup', 'title': 'Group'},
            'from': {'id': 100, 'is_bot': True, 'first_name': 'Bot'},
            'poll': native_poll(),
            **kwargs,
        }
    )


def vote(**kwargs):
    return PollAnswer.model_validate(
        {
            'poll_id': 'poll-a',
            'option_ids': [1],
            'option_persistent_ids': ['stable-b'],
            'user': {'id': 42, 'is_bot': False, 'first_name': 'Voter'},
            **kwargs,
        }
    )


def addition(original=None, **kwargs):
    service = {
        'option_persistent_id': 'stable-new',
        'option_text': 'Added',
        'poll_message': original if original is not None else message(),
        'option_text_entities': [{'type': 'custom_emoji', 'offset': 0, 'length': 1, 'custom_emoji_id': '123'}],
    }
    service.update(kwargs)
    return message(poll=None, poll_option_added=service)


class PollRequestTests(unittest.TestCase):
    def test_current_one_and_twelve_option_limits_and_character_bounds(self):
        self.assertEqual(len(poll_request(PollSpec('😀' * 300, ['😀' * 100]), chat_id=42).options), 1)
        self.assertEqual(len(poll_request(PollSpec('Question', [str(i) for i in range(12)]), chat_id=42).options), 12)
        for options in ([], ['a'] * 13, ['a' * 101]):
            with self.assertRaises(ValidationFailure):
                PollSpec('Question', options)
        with self.assertRaises(ValidationFailure):
            PollSpec('a' * 301, ['A'])

    def test_modern_multi_correct_quiz_preserves_revoting_and_shuffle(self):
        request = poll_request(
            PollSpec(
                'Quiz',
                ['A', 'B', 'C'],
                kind='quiz',
                correct_option_ids=[0, 2],
                allows_multiple_answers=True,
                allows_revoting=True,
                shuffle_options=True,
                hide_results_until_closes=True,
            ),
            chat_id=42,
        )
        self.assertEqual(request.correct_option_ids, [0, 2])
        self.assertIsNone(request.correct_option_id)
        self.assertTrue(request.allows_multiple_answers)
        self.assertTrue(request.allows_revoting)
        self.assertTrue(request.shuffle_options)

    def test_invalid_quiz_indices_and_regular_correct_answers_rejected(self):
        for indices in (None, [], [1, 0], [0, 0], [-1], [2], [True], ['0']):
            with self.subTest(indices=indices), self.assertRaises(ValidationFailure):
                PollSpec('Quiz', ['A', 'B'], kind='quiz', correct_option_ids=indices)
        with self.assertRaises(ValidationFailure):
            PollSpec('Regular', ['A'], correct_option_ids=[0])

    def test_adding_options_requires_nonanonymous_regular_poll(self):
        request = poll_request(PollSpec('Q', ['A'], is_anonymous=False, allow_adding_options=True), chat_id=42)
        self.assertTrue(request.allow_adding_options)
        for kwargs in ({'is_anonymous': True}, {'kind': 'quiz', 'correct_option_ids': [0], 'is_anonymous': False}):
            with self.assertRaises(ValidationFailure):
                PollSpec('Q', ['A'], allow_adding_options=True, **kwargs)

    def test_omission_keeps_native_revoting_default_and_literals(self):
        request = poll_request(PollSpec('<b>literal</b>', ['*literal*']), chat_id=42)
        self.assertIsNone(request.allows_revoting)
        self.assertIsNone(request.question_parse_mode)
        self.assertIsNone(request.options[0].text_parse_mode)
        self.assertEqual(request.question, '<b>literal</b>')

    def test_custom_emoji_fallback_and_utf16_entities(self):
        formatted = FormattedText('😀?', (TextEntity('custom_emoji', 0, 2, custom_emoji_id='123'),))
        spec = PollSpec(formatted, [formatted])
        request = poll_request(spec, chat_id=42)
        self.assertEqual(request.question, '😀?')
        self.assertEqual(request.question_entities, [])
        enriched = poll_request(spec, chat_id=42, custom_emoji_entitlement_verified=True)
        self.assertEqual(enriched.question_entities[0].length, 2)
        with self.assertRaises(ValidationFailure):
            PollSpec(FormattedText('Q', (TextEntity('bold', 0, 1),)), ['A'])

    def test_explanation_description_bounds_and_entity_modes(self):
        spec = PollSpec('Q', ['A'], kind='quiz', correct_option_ids=[0], explanation='a\nb\nc', description='😀' * 1024)
        request = poll_request(spec, chat_id=42)
        self.assertIsNone(request.explanation_parse_mode)
        self.assertIsNone(request.description_parse_mode)
        for explanation in ('a' * 201, 'a\nb\nc\nd'):
            with self.assertRaises(ValidationFailure):
                PollSpec('Q', ['A'], kind='quiz', correct_option_ids=[0], explanation=explanation)
        with self.assertRaises(ValidationFailure):
            PollSpec('Q', ['A'], explanation='Only quiz')
        with self.assertRaises(ValidationFailure):
            PollSpec('Q', ['A'], description='a' * 1025)

    def test_current_schedule_bounds_and_timezone(self):
        for period in (5, 600, 2628000):
            self.assertEqual(poll_request(PollSpec('Q', ['A'], open_period=period), chat_id=42).open_period, period)
        for period in (4, 2628001, True):
            with self.assertRaises(ValidationFailure):
                PollSpec('Q', ['A'], open_period=period)
        spec = PollSpec('Q', ['A'], close_date=WHEN + timedelta(seconds=5))
        self.assertEqual(poll_request(spec, chat_id=42, now=WHEN).close_date, spec.close_date)
        with self.assertRaises(ValidationFailure):
            poll_request(spec, chat_id=42, now=WHEN + timedelta(seconds=1))
        with self.assertRaises(ValidationFailure):
            poll_request(spec, chat_id=42, now=0)
        with self.assertRaises(ValidationFailure):
            PollSpec('Q', ['A'], close_date=datetime(2026, 10, 5))
        with self.assertRaises(ValidationFailure):
            PollSpec('Q', ['A'], open_period=5, close_date=WHEN)

    def test_channel_country_and_member_restrictions(self):
        spec = PollSpec('Q', ['A'], members_only=True, country_codes=['US', 'FT'])
        request = poll_request(spec, chat_id='@channel_name', chat_type='channel')
        self.assertEqual(request.country_codes, ['US', 'FT'])
        self.assertTrue(request.members_only)
        for restricted in (spec, PollSpec('Q', ['A'], country_codes=[])):
            with self.assertRaises(ValidationFailure):
                poll_request(restricted, chat_id=42)
        for codes in (['us'], ['USA'], ['US', 'US'], ['A1'], list('ABCDEFGHIJKLM')):
            with self.assertRaises(ValidationFailure):
                PollSpec('Q', ['A'], country_codes=codes)

    def test_chat_topic_business_and_strict_bool_validation(self):
        spec = PollSpec('Q', ['A'])
        self.assertEqual(
            poll_request(
                spec, chat_id=-100, chat_type='supergroup', message_thread_id=7, business_connection_id='conn'
            ).message_thread_id,
            7,
        )
        for kwargs in (
            {'chat_id': 0},
            {'chat_id': True},
            {'chat_id': 'not-address'},
            {'chat_id': -100, 'chat_type': 'channel', 'message_thread_id': 1},
        ):
            with self.assertRaises(ValidationFailure):
                poll_request(spec, **kwargs)
        with self.assertRaises(InvalidType):
            PollSpec('Q', ['A'], is_anonymous=1)

    def test_rich_media_is_copied_and_constructor_performs_no_io(self):
        original = InputMediaPhoto(media=BufferedInputFile(b'host-file', filename='photo.jpg'))
        choice = PollChoice('A', media=original)
        original.media.data = b'changed'
        request = poll_request(
            PollSpec('Q', [choice], kind='quiz', correct_option_ids=[0]),
            chat_id=42,
            media=InputMediaPhoto(media='https://example.com/photo.jpg'),
            explanation_media=choice.media,
        )
        self.assertEqual(request.options[0].media.media.data, b'host-file')
        request.options[0].media.media.data = b'consumer-change'
        self.assertEqual(choice.media.media.data, b'host-file')
        with self.assertRaises(ValidationFailure):
            poll_request(PollSpec('Q', ['A']), chat_id=42, explanation_media=choice.media)
        with self.assertRaises(ValueError):
            poll_request(PollSpec('Q', ['A']), chat_id=42, media='not-a-native-model')

    def test_explicit_parse_modes_survive_global_html_defaults(self):
        from aiogram.client.default import DefaultBotProperties

        session = StubSession()
        bot = Bot('100:POLL_FORMAT_FIXTURE', session=session, default=DefaultBotProperties(parse_mode='HTML'))
        request = poll_request(
            PollSpec(
                '<b>Q</b>',
                ['<i>A</i>'],
                kind='quiz',
                correct_option_ids=[0],
                explanation='<script>',
                description='<b>Literal</b>',
            ),
            chat_id=42,
        )
        for value in (
            request.question_parse_mode,
            request.explanation_parse_mode,
            request.description_parse_mode,
            request.options[0].text_parse_mode,
        ):
            self.assertIsNone(session.prepare_value(value, bot=bot, files={}))
        wire = session.prepare_value(request.options, bot=bot, files={})
        import json

        self.assertEqual(json.loads(wire)[0]['text'], '<i>A</i>')

    def test_spec_snapshots_sequences_and_hides_payload(self):
        options = ['PRIVATE_OPTION']
        correct = [0]
        spec = PollSpec('PRIVATE_QUESTION', options, kind='quiz', correct_option_ids=correct)
        options.clear()
        correct.clear()
        self.assertEqual(spec.correct_option_ids, (0,))
        self.assertEqual(len(spec.options), 1)
        self.assertNotIn('PRIVATE', repr(spec))
        with self.assertRaises(FrozenInstanceError):
            spec.question = 'Changed'


class PollObservationTests(unittest.TestCase):
    def test_optional_correct_answers_and_ambiguous_zero_are_preserved(self):
        observed = poll_state(native_poll(type='quiz'))
        self.assertIsNone(observed.correct_option_ids)
        self.assertEqual(observed.options[0].reported_voter_count, 0)
        self.assertEqual(observed.reported_total_voter_count, 3)
        self.assertIsNone(observed.details['explanation'])

    def test_snapshot_preserves_unknown_fields_without_aliases(self):
        native = native_poll(future={'items': [{'value': 'Private'}]})
        observed = poll_state(native)
        native.future['items'][0]['value'] = 'Changed'
        native.options.clear()
        self.assertEqual(observed.details['future']['items'][0]['value'], 'Private')
        self.assertEqual(len(observed.options), 2)
        with self.assertRaises(TypeError):
            observed.details['future']['items'][0]['value'] = 'Other'
        self.assertNotIn('Private', repr(observed))
        self.assertNotIn('Private', repr(observed.options[0]))

    def test_manual_detail_mappings_and_tuples_are_deep_snapshotted(self):
        nested = {'items': ({'value': 'Old'},)}
        observed = replace(poll_state(native_poll()), details=MappingProxyType(nested))
        nested['items'][0]['value'] = 'Changed'
        self.assertEqual(observed.details['items'][0]['value'], 'Old')
        with self.assertRaises(InvalidType):
            replace(observed, details={'mutable': object()})

    def test_votes_keep_persistent_ids_when_ordinals_change(self):
        before = poll_vote(vote(option_ids=[1]))
        after = poll_vote(vote(option_ids=[0]))
        self.assertEqual(before.option_persistent_ids, after.option_persistent_ids)
        self.assertNotEqual(before.option_ids, after.option_ids)

    def test_retraction_and_chat_identity_are_not_inferred_as_user(self):
        retracted = poll_vote(vote(option_ids=[], option_persistent_ids=[]))
        self.assertTrue(retracted.retracted)
        anonymous_voter = poll_vote(vote(user=None, voter_chat={'id': -200, 'type': 'channel', 'title': 'Voter chat'}))
        self.assertEqual(anonymous_voter.voter_chat_id, -200)
        self.assertIsNone(anonymous_voter.voter_user_id)

    def test_vote_identity_and_arrays_reject_inconsistent_input(self):
        for kwargs in (
            {'voter_user_id': None},
            {'voter_chat_id': -100},
            {'option_ids': (1, 1), 'option_persistent_ids': ('a', 'b')},
            {'option_ids': (True,)},
            {'option_ids': ([],)},
            {'option_persistent_ids': ([],)},
        ):
            base = {'poll_id': 'p', 'option_ids': (0,), 'option_persistent_ids': ('a',), 'voter_user_id': 42}
            base.update(kwargs)
            with self.assertRaises((ValueError, TypeError)):
                PollVote(**base)

    def test_addition_preserves_entities_and_unknown_fields(self):
        added = poll_option_added(addition(future_flag={'value': True}))
        self.assertEqual(added.poll_id, 'poll-a')
        self.assertEqual((added.chat_id, added.message_id), (-100, 10))
        self.assertEqual(added.details['option_text_entities'][0]['custom_emoji_id'], '123')
        self.assertTrue(added.details['future_flag']['value'])

    def test_inaccessible_and_omitted_poll_messages_do_not_invent_poll_id(self):
        inaccessible = {'chat': {'id': -100, 'type': 'supergroup', 'title': 'Group'}, 'message_id': 10, 'date': 0}
        added = poll_option_added(addition(original=inaccessible))
        self.assertIsNone(added.poll_id)
        self.assertEqual((added.chat_id, added.message_id), (-100, 10))
        omitted = poll_option_added(addition(poll_message=None))
        self.assertIsNone(omitted.poll_id)
        self.assertIsNone(omitted.chat_id)
        self.assertIsNone(omitted.message_id)

    def test_own_poll_registration_rejects_wrong_sender_and_forward(self):
        binding = PollBinding.from_message(message(), bot_id=100)
        self.assertEqual(binding.poll_id, 'poll-a')
        for native in (
            message(**{'from': {'id': 101, 'is_bot': True, 'first_name': 'Other'}}),
            message(poll=None),
            message(
                forward_origin={
                    'type': 'user',
                    'date': 1780000000,
                    'sender_user': {'id': 42, 'is_bot': False, 'first_name': 'U'},
                }
            ),
        ):
            with self.assertRaises(PermissionDenied):
                PollBinding.from_message(native, bot_id=100)

    def test_channel_and_business_response_registration_preserves_scope(self):
        channel = message(chat={'id': -100, 'type': 'channel', 'title': 'Channel'}, **{'from': None})
        self.assertEqual(PollBinding.from_message(channel, bot_id=100).chat_id, -100)
        business = message(
            business_connection_id='conn',
            sender_business_bot={'id': 100, 'is_bot': True, 'first_name': 'Bot'},
            message_thread_id=7,
        )
        bound = PollBinding.from_message(business, bot_id=100)
        self.assertEqual((bound.business_connection_id, bound.message_thread_id), ('conn', 7))

    def test_bad_locator_or_mismatching_event_rejected(self):
        for kwargs in ({}, {'chat_id': -100}, {'message_id': 10}, {'bot_id': True, 'poll_id': 'p'}):
            parameters = {'bot_id': 100}
            parameters.update(kwargs)
            with self.assertRaises(ValidationFailure):
                PollLocator(**parameters)
        with self.assertRaises(PermissionDenied):
            PollEvent(1, PollBinding.from_message(message(), bot_id=100), poll_state(native_poll(id='other')))


class PollRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = StubSession()
        self.bot = Bot('100:POLL_FIXTURE', session=self.session)
        self.dispatcher = Dispatcher()
        self.binding = PollBinding.from_message(message(), bot_id=100)
        self.lookups = []
        self.events = []
        self.return_binding = self.binding

        async def lookup(locator):
            self.lookups.append(locator)
            return self.return_binding

        async def observe(event):
            self.events.append(event)

        self.dispatcher.include_router(poll_events_router(lookup, observe))

    async def asyncTearDown(self):
        await self.dispatcher.fsm.close()
        await self.bot.session.close()

    async def feed(self, **kwargs):
        return await self.dispatcher.feed_update(self.bot, Update(update_id=77, **kwargs))

    async def test_actual_poll_and_poll_answer_dispatcher_updates_preserve_update_id(self):
        await self.feed(poll=native_poll())
        await self.feed(poll_answer=vote())
        self.assertEqual([type(event.observation) for event in self.events], [PollState, PollVote])
        self.assertEqual([event.update_id for event in self.events], [77, 77])
        self.assertEqual(self.session.calls, [])
        self.assertFalse(self.session.closed)

    async def test_current_binding_rechecked_and_unknown_poll_ignored(self):
        await self.feed(poll_answer=vote())
        self.return_binding = None
        await self.feed(poll_answer=vote())
        self.assertEqual(len(self.lookups), 2)
        self.assertEqual(len(self.events), 1)
        self.return_binding = self.binding
        await self.feed(poll_answer=vote(poll_id='other'))
        self.assertEqual(len(self.events), 1)

    async def test_wrong_bot_anonymous_and_mismatching_poll_kind_are_dropped(self):
        self.return_binding = replace(self.binding, bot_id=101)
        await self.feed(poll_answer=vote())
        self.return_binding = replace(self.binding, is_anonymous=True)
        await self.feed(poll_answer=vote())
        self.return_binding = self.binding
        await self.feed(poll=native_poll(type='quiz'))
        self.assertEqual(self.events, [])

    async def test_added_option_resolves_inaccessible_exact_address_and_omitted_is_ignored(self):
        inaccessible = {'chat': {'id': -100, 'type': 'supergroup', 'title': 'G'}, 'message_id': 10, 'date': 0}
        await self.feed(message=addition(original=inaccessible))
        self.assertEqual(len(self.events), 1)
        self.assertIsNone(self.lookups[-1].poll_id)
        self.assertEqual(self.lookups[-1].message_id, 10)
        count = len(self.lookups)
        await self.feed(message=addition(poll_message=None))
        self.assertEqual(len(self.lookups), count)

    async def test_added_option_rejects_wrong_outer_chat_thread_and_business(self):
        for changed in (
            addition().model_copy(
                update={'chat': message(chat={'id': -101, 'type': 'supergroup', 'title': 'Other'}).chat}
            ),
            addition().model_copy(update={'message_thread_id': 7}),
            addition().model_copy(update={'business_connection_id': 'other'}),
        ):
            await self.feed(message=changed)
        self.assertEqual(self.events, [])

    async def test_business_service_event_uses_binding_business_and_topic_scope(self):
        self.return_binding = replace(self.binding, business_connection_id='conn', message_thread_id=7)
        service = addition().model_copy(update={'business_connection_id': 'conn', 'message_thread_id': 7})
        await self.feed(business_message=service)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[-1].binding.business_connection_id, 'conn')

    async def test_wrong_exact_message_binding_is_dropped(self):
        self.return_binding = replace(self.binding, message_id=999)
        await self.feed(message=addition())
        self.assertEqual(self.events, [])

    async def test_repeated_updates_are_observations_not_double_counted_totals(self):
        await self.feed(poll_answer=vote())
        await self.feed(poll_answer=vote())
        await self.feed(poll=native_poll())
        self.assertEqual(len(self.events), 3)
        self.assertEqual(self.events[-1].observation.reported_total_voter_count, 3)
        self.assertEqual(self.events[0].update_id, self.events[1].update_id)

    async def test_host_observer_failures_and_cancellation_propagate(self):
        await self.dispatcher.fsm.close()
        self.dispatcher = Dispatcher()

        async def lookup(locator):
            return self.binding

        async def failed(event):
            raise RuntimeError('host storage failure')

        self.dispatcher.include_router(poll_events_router(lookup, failed))
        with self.assertRaises(RuntimeError):
            await self.feed(poll_answer=vote())
        self.assertEqual(self.session.calls, [])
        await self.dispatcher.fsm.close()
        self.dispatcher = Dispatcher()

        async def cancelled(event):
            raise asyncio.CancelledError

        self.dispatcher.include_router(poll_events_router(lookup, cancelled))
        with self.assertRaises(asyncio.CancelledError):
            await self.feed(poll_answer=vote())

    async def test_unrelated_host_message_handler_is_preserved(self):
        host = Router()
        seen = []

        async def handle(value):
            seen.append(value.text)

        host.message.register(handle, F.text == '/help')
        self.dispatcher.include_router(host)
        await self.feed(message=message(poll=None, text='/help'))
        self.assertEqual(seen, ['/help'])
        self.assertEqual(self.lookups, [])
