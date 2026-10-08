import asyncio
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, Update, User

from telegram_patterns import (
    ConflictFailure,
    FormattedText,
    InvalidCompletion,
    InvalidType,
    PermissionDenied,
    TextEntity,
    ValidationFailure,
)
from telegram_patterns.aiogram import (
    InlineCachePolicy,
    InlineItem,
    InlineSearch,
    inline_articles,
    inline_query_router,
)
from telegram_patterns.testing import StubSession

WHEN = datetime(2026, 10, 5, tzinfo=timezone.utc)
SECRET = b'host-persistent-test-secret-32bytes'


def query(actor=42, text='', offset='', context='sender', identity='q'):
    return InlineQuery(
        id=identity,
        from_user=User(id=actor, is_bot=False, first_name='Reader'),
        query=text,
        offset=offset,
        chat_type=context,
    )


def records():
    return [
        InlineItem('a', 'Alpha', 'first', shareable=True),
        InlineItem('private', 'DO_NOT_SHARE', 'PRIVATE_NOTE'),
        InlineItem('b', 'Bravo', 'second', shareable=True),
        InlineItem('c', 'Charlie', 'third', shareable=True),
    ]


async def allow(actor, item):
    return True


def search(items=None, **kwargs):
    return InlineSearch(records() if items is None else items, secret=SECRET, revision='catalog-v1', **kwargs)


class InlineValidationTests(unittest.TestCase):
    def test_private_is_default_and_payload_hidden_from_repr(self):
        item = InlineItem('a', 'PRIVATE_TITLE', 'PRIVATE_TEXT')
        self.assertFalse(item.shareable)
        self.assertNotIn('PRIVATE', repr(item))
        self.assertNotIn(SECRET.decode(), repr(search()))

    def test_result_ids_use_utf8_byte_limit_and_text_character_limit(self):
        self.assertEqual(len(InlineItem('😀' * 16, 'Name', '😀' * 4096).content.text), 4096)
        for identity in ('', '😀' * 17, 'a' * 65):
            with self.assertRaises(ValidationFailure):
                InlineItem(identity, 'Name', 'Text')
        with self.assertRaises(ValidationFailure):
            InlineItem('a', 'Name', 'a' * 4097)
        with self.assertRaises(ValueError):
            InlineItem('a', 'Name', '\ud800')

    def test_strict_flags_and_configuration_bounds(self):
        for kwargs in (
            {'page_size': 0},
            {'page_size': 51},
            {'page_size': True},
            {'cursor_ttl': 0},
            {'cursor_ttl': 86401},
            {'allowed_chat_types': [[]]},
            {'allowed_chat_types': []},
            {'allowed_chat_types': ['sender', 'sender']},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                search(**kwargs)
        for kwargs in ({'cache_time': -1}, {'cache_time': True}, {'is_personal': 1}):
            with self.assertRaises((ValueError, TypeError)):
                InlineCachePolicy(**kwargs)
        with self.assertRaises(InvalidType):
            InlineItem('a', 'Title', 'Text', shareable=1)

    def test_duplicates_and_non_item_catalog_are_rejected(self):
        with self.assertRaises(ValidationFailure):
            search([records()[0]] * 2)
        with self.assertRaises(ValidationFailure):
            search([object()])
        with self.assertRaises(InvalidType):
            search('not-a-sequence-of-items')
        with self.assertRaises(ValidationFailure):
            InlineSearch([], secret=b'short', revision='v1')

    def test_shared_cache_requires_public_all_contexts_and_bounded_lifetime(self):
        with self.assertRaises(ValidationFailure):
            search(cache=InlineCachePolicy(10, False))
        with self.assertRaises(ValidationFailure):
            search(cache=InlineCachePolicy(301))
        with self.assertRaises(ValidationFailure):
            search(public_catalog=True, cache=InlineCachePolicy(10, False), allowed_chat_types=['sender'])

    def test_catalog_items_are_frozen_and_snapshot_sequence(self):
        original = records()
        catalog = search(original)
        original.clear()
        self.assertEqual(len(catalog.items), 4)
        with self.assertRaises(FrozenInstanceError):
            catalog.items[0].title = 'Changed'
        with self.assertRaises(AttributeError):
            catalog.items = ()
        with self.assertRaises(AttributeError):
            catalog.revision = 'new'

    def test_router_checks_hooks_and_deadline_before_registration(self):
        for timeout in (0, -1, float('nan'), float('inf'), True, 61):
            with self.assertRaises(ValidationFailure):
                inline_query_router(search(), search_timeout=timeout)
        for kwargs in ({'authorize': 1}, {'permission_revision': 1}, {'custom_emoji_entitlement_verified': 1}):
            with self.assertRaises(InvalidType):
                inline_query_router(search(), **kwargs)


class InlineSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_query_pages_stable_ids_and_terminal_offset(self):
        catalog = search(page_size=1)
        offset = ''
        found = []
        for index in range(3):
            page = await catalog.page(query(offset=offset, identity=str(index)), bot_id=100, authorize=allow, now=WHEN)
            found.extend(item.id for item in page.items)
            offset = page.next_offset
            self.assertLessEqual(len(offset.encode()), 64)
        self.assertEqual(found, ['a', 'b', 'c'])
        self.assertEqual(offset, '')

    async def test_casefold_and_whitespace_use_same_cursor_scope(self):
        items = [InlineItem(str(i), 'Straße', 'Shared', shareable=True) for i in range(3)]
        catalog = search(items, page_size=1)
        page = await catalog.page(query(text='  STRASSE '), bot_id=100, authorize=allow, now=WHEN)
        second = await catalog.page(
            query(text='straße', offset=page.next_offset), bot_id=100, authorize=allow, now=WHEN
        )
        self.assertEqual(second.items[0].id, '1')

    async def test_private_item_never_reaches_search_or_authorizer(self):
        seen = []

        async def authorized(actor, item):
            seen.append(item.id)
            return True

        page = await search().page(query(text='PRIVATE_NOTE'), bot_id=100, authorize=authorized, now=WHEN)
        self.assertEqual(page.items, ())
        self.assertEqual(seen, [])

    async def test_current_acl_is_per_actor_and_requires_literal_true(self):
        async def authorized(actor, item):
            return actor == 42 and item.id == 'b'

        for actor, expected in ((42, ['b']), (43, [])):
            page = await search().page(query(actor=actor), bot_id=100, authorize=authorized, now=WHEN)
            self.assertEqual([item.id for item in page.items], expected)

        async def truthy(actor, item):
            return 1

        self.assertEqual((await search().page(query(), bot_id=100, authorize=truthy, now=WHEN)).items, ())

    async def test_personal_search_requires_explicit_authorization_and_context(self):
        with self.assertRaises(PermissionDenied):
            await search().page(query(), bot_id=100, now=WHEN)
        for context in (None, 'private', 'group', 'supergroup', 'channel'):
            with self.assertRaises(PermissionDenied):
                await search().page(query(context=context), bot_id=100, authorize=allow, now=WHEN)

    async def test_personal_cursor_rejects_another_actor_bot_query_or_context(self):
        catalog = search(page_size=1, allowed_chat_types=['sender', 'group'])
        first = await catalog.page(query(), bot_id=100, authorize=allow, now=WHEN)
        for changed, bot_id in (
            (query(actor=43, offset=first.next_offset), 100),
            (query(text='different', offset=first.next_offset), 100),
            (query(context='group', offset=first.next_offset), 100),
            (query(offset=first.next_offset), 101),
        ):
            with self.assertRaises(ConflictFailure):
                await catalog.page(changed, bot_id=bot_id, authorize=allow, now=WHEN)

    async def test_cursor_invalidated_by_catalog_content_order_revision_page_and_permissions(self):
        catalog = search(page_size=1)
        first = await catalog.page(query(), bot_id=100, authorize=allow, now=WHEN)
        changed = records()
        changed[0] = InlineItem('a', 'Changed', 'first', shareable=True)
        variants = [
            search(changed, page_size=1),
            search(list(reversed(records())), page_size=1),
            search(page_size=2),
            InlineSearch(records(), secret=SECRET, revision='v2', page_size=1),
        ]
        for variant in variants:
            with self.assertRaises(ConflictFailure):
                await variant.page(query(offset=first.next_offset), bot_id=100, authorize=allow, now=WHEN)
        with self.assertRaises(ConflictFailure):
            await catalog.page(
                query(offset=first.next_offset), bot_id=100, authorize=allow, permission_revision='new-role', now=WHEN
            )

    async def test_cursor_expiry_does_not_slide_between_pages(self):
        catalog = search(page_size=1, cursor_ttl=10)
        first = await catalog.page(query(), bot_id=100, authorize=allow, now=WHEN)
        second = await catalog.page(
            query(offset=first.next_offset), bot_id=100, authorize=allow, now=WHEN + timedelta(seconds=9)
        )
        with self.assertRaises(ConflictFailure):
            await catalog.page(
                query(offset=second.next_offset), bot_id=100, authorize=allow, now=WHEN + timedelta(seconds=10)
            )

    async def test_forged_noncanonical_and_oversized_offsets_rejected(self):
        catalog = search(page_size=1)
        first = await catalog.page(query(), bot_id=100, authorize=allow, now=WHEN)
        for offset in (
            '0',
            'A' * 65,
            first.next_offset + '=',
            ('A' if first.next_offset[0] != 'A' else 'B') + first.next_offset[1:],
        ):
            with self.assertRaises(ConflictFailure):
                await catalog.page(query(offset=offset), bot_id=100, authorize=allow, now=WHEN)

    async def test_next_page_rechecks_acl_for_remaining_item(self):
        catalog = search(page_size=1)
        revoked = set()

        async def authorized(actor, item):
            return item.id not in revoked

        first = await catalog.page(query(), bot_id=100, authorize=authorized, now=WHEN)
        revoked.add('b')
        second = await catalog.page(query(offset=first.next_offset), bot_id=100, authorize=authorized, now=WHEN)
        self.assertEqual(second.items[0].id, 'c')

    async def test_shared_public_cache_pagination_can_be_replayed_to_another_actor(self):
        catalog = search(page_size=1, public_catalog=True, cache=InlineCachePolicy(10, False))
        first = await catalog.page(query(actor=42, context='group'), bot_id=100, now=WHEN)
        second = await catalog.page(query(actor=43, context=None, offset=first.next_offset), bot_id=100, now=WHEN)
        self.assertEqual(second.items[0].id, 'b')
        self.assertFalse(second.cache.is_personal)
        with self.assertRaises(ValidationFailure):
            await catalog.page(query(), bot_id=100, authorize=allow, now=WHEN)
        with self.assertRaises(ValidationFailure):
            await catalog.page(query(), bot_id=100, permission_revision='actor-role', now=WHEN)

    async def test_page_answer_is_bound_to_exact_query_and_keeps_literal_entities(self):
        content = FormattedText(
            '😀 <b>', (TextEntity('custom_emoji', 0, 2, custom_emoji_id='123'), TextEntity('bold', 3, 3))
        )
        catalog = search([InlineItem('x', 'Title', content, shareable=True)])
        original = query()
        page = await catalog.page(original, bot_id=100, authorize=allow, now=WHEN)
        for changed, bot_id in ((query(identity='other'), 100), (query(actor=43), 100), (original, 101)):
            with self.assertRaises(PermissionDenied):
                page.answer_request(changed, bot_id=bot_id)
        native = page.answer_request(original, bot_id=100)
        text = native.results[0].input_message_content
        self.assertIsNone(text.parse_mode)
        self.assertEqual(text.message_text, '😀 <b>')
        self.assertEqual([(e.type, e.offset, e.length) for e in text.entities], [('bold', 3, 3)])
        full = inline_articles(page, custom_emoji_entitlement_verified=True)
        self.assertEqual(full[0].input_message_content.entities[0].custom_emoji_id, '123')
        text.entities.clear()
        self.assertEqual(len(inline_articles(page)[0].input_message_content.entities), 1)

    async def test_bad_clock_or_query_context_rejected(self):
        for now in (0, datetime(2026, 10, 5)):
            with self.assertRaises(ValidationFailure):
                await search().page(query(), bot_id=100, authorize=allow, now=now)
        with self.assertRaises(ValidationFailure):
            await search().page(query(context='unknown'), bot_id=100, authorize=allow, now=WHEN)


class InlineRouterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = StubSession().respond(AnswerInlineQuery, True)
        self.bot = Bot('100:INLINE_FIXTURE', session=self.session, default=DefaultBotProperties(parse_mode='HTML'))
        self.dispatcher = Dispatcher()

    async def asyncTearDown(self):
        await self.dispatcher.fsm.close()
        await self.bot.session.close()

    async def feed(self, value=None):
        return await self.dispatcher.feed_update(self.bot, Update(update_id=1, inline_query=value or query()))

    async def test_actual_dispatcher_fresh_provider_and_personal_cache(self):
        called = []

        async def provider(value):
            called.append(value.from_user.id)
            return search()

        self.dispatcher.include_router(inline_query_router(provider, authorize=allow))
        await self.feed()
        await self.feed(query(actor=43))
        self.assertEqual(called, [42, 43])
        self.assertEqual(len(self.session.calls), 2)
        self.assertTrue(all(call.is_personal and call.cache_time == 0 for call in self.session.calls))
        self.assertFalse(self.session.closed)

    async def test_stale_cursor_answers_empty_instead_of_restarting_results(self):
        self.dispatcher.include_router(inline_query_router(search(), authorize=allow))
        await self.feed(query(offset='forged'))
        self.assertEqual(self.session.calls[-1].results, [])
        self.assertEqual(self.session.calls[-1].next_offset, '')

    async def test_missing_authorization_answers_empty_personal(self):
        self.dispatcher.include_router(inline_query_router(search()))
        await self.feed()
        self.assertEqual(self.session.calls[-1].results, [])

    async def test_permissions_changed_mid_search_answers_empty(self):
        revisions = iter(('v1', 'v2'))

        async def revision(actor):
            return next(revisions)

        self.dispatcher.include_router(inline_query_router(search(), authorize=allow, permission_revision=revision))
        await self.feed()
        self.assertEqual(self.session.calls[-1].results, [])

    async def test_deadline_cancels_provider_then_answers_empty(self):
        cancelled = asyncio.Event()

        async def provider(value):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.dispatcher.include_router(inline_query_router(provider, search_timeout=0.01))
        await self.feed()
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.session.calls[-1].results, [])

    async def test_external_cancellation_propagates_without_answer(self):
        async def provider(value):
            raise asyncio.CancelledError

        self.dispatcher.include_router(inline_query_router(provider))
        with self.assertRaises(asyncio.CancelledError):
            await self.feed()
        self.assertEqual(self.session.calls, [])

    async def test_deadline_also_cancels_slow_authorization(self):
        cancelled = asyncio.Event()

        async def authorization(actor, item):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.dispatcher.include_router(inline_query_router(search(), authorize=authorization, search_timeout=0.01))
        await self.feed()
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.session.calls[-1].results, [])

    async def test_host_storage_failure_is_not_masked_as_empty_success(self):
        async def failed(actor, item):
            raise RuntimeError('host ACL unavailable')

        self.dispatcher.include_router(inline_query_router(search(), authorize=failed))
        with self.assertRaises(RuntimeError):
            await self.feed()
        self.assertEqual(self.session.calls, [])

    async def test_shared_cache_rejects_actor_revision_hook(self):
        async def revision(actor):
            return 'role-v1'

        catalog = search(public_catalog=True, cache=InlineCachePolicy(10, False))
        self.dispatcher.include_router(inline_query_router(catalog, permission_revision=revision))
        with self.assertRaises(ValidationFailure):
            await self.feed()
        self.assertEqual(self.session.calls, [])

    async def test_unknown_native_answer_is_not_retried(self):
        def lost(value):
            raise TimeoutError('lost confirmation')

        self.session.respond(AnswerInlineQuery, lost)
        self.dispatcher.include_router(inline_query_router(search(), authorize=allow))
        with self.assertRaises(TimeoutError):
            await self.feed()
        self.assertEqual(len(self.session.calls), 1)

    async def test_false_native_confirmation_is_explicit_failure(self):
        self.session.respond(AnswerInlineQuery, False)
        self.dispatcher.include_router(inline_query_router(search(), authorize=allow))
        with self.assertRaises(InvalidCompletion):
            await self.feed()
        self.assertEqual(len(self.session.calls), 1)

    async def test_unrelated_host_help_handler_is_preserved(self):
        seen = []
        host = Router()

        async def help(message):
            seen.append(message.text)

        host.message.register(help, F.text == '/help')
        self.dispatcher.include_router(inline_query_router(search(), authorize=allow))
        self.dispatcher.include_router(host)
        await self.dispatcher.feed_update(
            self.bot,
            Update.model_validate(
                {
                    'update_id': 1,
                    'message': {
                        'message_id': 1,
                        'date': 1780000000,
                        'chat': {'id': 42, 'type': 'private'},
                        'text': '/help',
                    },
                }
            ),
        )
        self.assertEqual(seen, ['/help'])
        self.assertEqual(self.session.calls, [])
