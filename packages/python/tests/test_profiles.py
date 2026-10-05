import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import unittest

from aiogram import Bot
from aiogram.methods import (GetMe, GetMyName, GetMyDescription, GetMyShortDescription,
                             GetUserProfilePhotos, SetMyName, SetMyDescription,
                             SetMyShortDescription, SetMyProfilePhoto, RemoveMyProfilePhoto)
from aiogram.types import User, ChatFullInfo, ChatPermissions, InputProfilePhotoAnimated, InputProfilePhotoStatic
from telegram_patterns import InvalidType, PermissionDenied, ValidationFailure, safe_error_report
from telegram_patterns.aiogram import (BotProfilePatch, ProfileEditIncomplete, ProfilePhotoSize,
                                      ProfilePhotos, MediaFile, chat_profile, user_profile,
                                      read_bot_profile, read_profile_photos, update_bot_profile)
from telegram_patterns.testing import StubSession


WHEN = datetime(2026, 10, 5, tzinfo=timezone.utc)
JPEG = b'\xff\xd8\xff\xe0fixture\xff\xd9'  # synthetic markers, deliberately no codec claim


def chat(**kwargs):
    return ChatFullInfo.model_validate({'id': 42, 'type': 'private', 'accent_color_id': 0,
                                       'max_reaction_count': 11, 'accepted_gift_types': {k: False for k in ('unlimited_gifts', 'limited_gifts', 'unique_gifts', 'premium_subscription', 'gifts_from_channels')}, **kwargs})


def session():
    s = StubSession()
    state = {'': {'name': 'Base', 'description': 'Default bio', 'short_description': 'Default short'},
             'ru': {'name': 'Русский', 'description': 'Описание', 'short_description': 'Кратко'}}
    s.respond(GetMe, {'id': 100, 'is_bot': True, 'first_name': 'Base', 'can_join_groups': True})
    for method, key in ((GetMyName, 'name'), (GetMyDescription, 'description'), (GetMyShortDescription, 'short_description')):
        s.respond(method, lambda request, key=key: {key: state.get(request.language_code, {}).get(key, state[''][key])})
    for method, key in ((SetMyName, 'name'), (SetMyDescription, 'description'), (SetMyShortDescription, 'short_description')):
        def write(request, key=key):
            locale = request.language_code
            value = getattr(request, key)
            if value == '' and locale:
                state.setdefault(locale, {}).pop(key, None)
            else:
                state.setdefault(locale, {})[key] = value
            return True
        s.respond(method, write)
    s.respond(GetUserProfilePhotos, {'total_count': 1, 'photos': [[{'file_id': 'opaque', 'file_unique_id': 'unique', 'width': 100, 'height': 100}]]})
    s.respond(SetMyProfilePhoto, True).respond(RemoveMyProfilePhoto, True)
    return s, state


async def allow(actor, bot_id, method):
    return actor == 42 and bot_id == 100


class SnapshotTests(unittest.TestCase):
    def test_missing_premium_is_unknown_and_false_is_preserved(self):
        for premium in (None, False, True):
            p = user_profile(User(id=42, is_bot=False, first_name='Private', is_premium=premium), observed_at=WHEN)
            self.assertIs(p.is_premium, premium)
            self.assertIsNone(p.username)
            self.assertIsNone(p.capabilities['can_join_groups'])

    def test_all_optional_sdk_bool_fields_are_preserved(self):
        u = User(id=100, is_bot=True, first_name='Bot', can_join_groups=False, supports_join_request_queries=True)
        p = user_profile(u, source='getMe', observed_at=WHEN)
        names = {name for name, f in User.model_fields.items() if f.annotation == (bool | None)} - {'is_premium'}
        self.assertEqual(set(p.capabilities), names)
        self.assertIs(p.capabilities['can_join_groups'], False)
        self.assertIs(p.capabilities['supports_join_request_queries'], True)

    def test_user_snapshot_has_no_mutable_sdk_aliases(self):
        u = User(id=42, is_bot=False, first_name='Private', is_premium=True)
        p = user_profile(u, observed_at=WHEN)
        object.__setattr__(u, 'first_name', 'Changed'); object.__setattr__(u, 'is_premium', False)
        self.assertEqual(p.first_name, 'Private')
        self.assertIs(p.is_premium, True)
        with self.assertRaises(TypeError): p.capabilities['can_join_groups'] = True
        with self.assertRaises(FrozenInstanceError): p.first_name = 'Other'
        self.assertNotIn('Private', repr(p))

    def test_observation_time_is_aware_and_normalized(self):
        u = User(id=42, is_bot=False, first_name='Name')
        self.assertEqual(user_profile(u, observed_at=WHEN.astimezone(timezone(timedelta(hours=3)))).observed_at, WHEN)
        with self.assertRaises(ValidationFailure): user_profile(u, observed_at=datetime(2026, 1, 1))

    def test_invalid_source_or_mutated_bool_rejected(self):
        u = User(id=42, is_bot=False, first_name='Name')
        with self.assertRaises(ValidationFailure): user_profile(u, source='untrusted')
        object.__setattr__(u, 'is_premium', 'false')
        with self.assertRaises(InvalidType): user_profile(u)

    def test_chat_unknown_permissions_are_not_empty_or_false(self):
        p = chat_profile(chat(), observed_at=WHEN)
        self.assertIsNone(p.permissions)
        self.assertIsNone(p.photo)
        self.assertIsNone(p.bio)
        self.assertIsNone(p.facts['has_private_forwards'])

    def test_chat_snapshot_copies_permissions_birthdate_photo_and_personal_chat(self):
        c = chat(bio='Private bio', birthdate={'day': 5, 'month': 10},
                 personal_chat={'id': -100, 'type': 'channel', 'title': 'Personal'},
                 photo={'small_file_id': 'small', 'small_file_unique_id': 'us', 'big_file_id': 'big', 'big_file_unique_id': 'ub'},
                 permissions=ChatPermissions(can_send_messages=False))
        p = chat_profile(c, observed_at=WHEN)
        object.__setattr__(c, 'bio', 'Changed'); object.__setattr__(c.photo, 'big_file_id', 'Changed'); object.__setattr__(c.permissions, 'can_send_messages', True)
        self.assertEqual(p.bio, 'Private bio'); self.assertEqual(p.birthdate, (5, 10, None))
        self.assertEqual(p.personal_chat_id, -100)
        self.assertEqual(p.photo['big_file_id'], 'big'); self.assertIs(p.permissions['can_send_messages'], False)
        self.assertIsNone(p.permissions['can_send_audios'])
        with self.assertRaises(TypeError): p.photo['big_file_id'] = 'Other'
        self.assertNotIn('Private bio', repr(p))

    def test_photo_identifiers_are_bot_scoped_for_message_reuse(self):
        p = ProfilePhotoSize(100, 42, 'opaque', 'unique', 100, 100)
        self.assertEqual(p.as_media().as_input(100), 'opaque')
        with self.assertRaises(ValidationFailure): p.as_media().as_input(101)
        self.assertNotIn('opaque', repr(p)); self.assertNotIn('unique', repr(p))

    def test_photo_page_snapshots_nested_input(self):
        size = ProfilePhotoSize(100, 42, 'opaque', 'unique', 100, 100)
        groups = [[size]]
        p = ProfilePhotos(100, 42, 1, 0, 1, groups, WHEN)
        groups.clear()
        self.assertEqual(p.photos, ((size,),))
        with self.assertRaises(ValidationFailure): ProfilePhotos(101, 42, 1, 0, 1, [[size]], WHEN)

    def test_patch_distinguishes_omission_and_explicit_clear(self):
        p = BotProfilePatch(description='')
        self.assertIsNone(p.name); self.assertEqual(p.description, '')
        with self.assertRaises(ValidationFailure): BotProfilePatch()
        with self.assertRaises(InvalidType): BotProfilePatch(description=False)

    def test_patch_character_bounds_and_unicode(self):
        self.assertEqual(len(BotProfilePatch(name='😀'*64).name), 64)
        for kwargs in ({'name': 'a'*65}, {'description': 'a'*513}, {'short_description': 'a'*121}, {'name': '\ud800'}):
            with self.assertRaises(ValidationFailure): BotProfilePatch(**kwargs)

    def test_photo_upload_requires_new_bytes_and_declared_format(self):
        for file in (MediaFile('photo', 'opaque', bot_id=100), MediaFile('photo', b'PNG', filename='image.png'), MediaFile('document', b'bytes', filename='document.jpg')):
            with self.assertRaises(ValidationFailure): BotProfilePatch(photo=file)
        with self.assertRaises(ValidationFailure): BotProfilePatch(photo=MediaFile('photo', JPEG, filename='avatar.jpg'), remove_photo=True)
        with self.assertRaises(InvalidType): BotProfilePatch(remove_photo=1)

    def test_animated_timestamp_requires_video_and_finite_nonnegative_value(self):
        animated = MediaFile('video', b'synthetic MPEG4 fixture', filename='avatar.mp4')
        for timestamp in (-1, float('nan'), float('inf'), True):
            with self.assertRaises(ValidationFailure): BotProfilePatch(photo=animated, main_frame_timestamp=timestamp)
        with self.assertRaises(ValidationFailure): BotProfilePatch(name='Name', main_frame_timestamp=0)
        with self.assertRaises(ValidationFailure): BotProfilePatch(photo=MediaFile('photo', JPEG, filename='avatar.jpg'), main_frame_timestamp=0)


class AsyncProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session, self.state = session()
        self.bot = Bot('100:PROFILE_FIXTURE', session=self.session)

    async def asyncTearDown(self):
        await self.bot.session.close()

    async def test_read_bot_uses_fresh_identity_and_exact_locale(self):
        p = await read_bot_profile(self.bot, language_code='ru')
        self.assertEqual(p.name, 'Русский'); self.assertEqual(p.description, 'Описание')
        self.assertEqual(p.user.id, 100); self.assertEqual(p.user.source, 'getMe')
        self.assertIsNone(p.user.is_premium)
        self.assertEqual([type(c).__name__ for c in self.session.calls], ['GetMe', 'GetMyName', 'GetMyDescription', 'GetMyShortDescription'])
        self.assertTrue(all(c.language_code == 'ru' for c in self.session.calls[1:]))
        self.assertIsNone(p.photos)

    async def test_bot_photo_read_is_explicit_and_scoped(self):
        p = await read_bot_profile(self.bot, include_photos=True)
        self.assertIsNotNone(p.photos)
        self.assertEqual((p.photos.bot_id, p.photos.user_id, p.photos.total_count), (100, 100, 1))
        self.assertIsInstance(self.session.calls[-1], GetUserProfilePhotos)

    async def test_invalid_bot_photo_switch_rejected_before_io(self):
        with self.assertRaises(InvalidType): await read_bot_profile(self.bot, include_photos='true')
        self.assertEqual(self.session.calls, [])

    async def test_read_rejects_mismatched_or_non_bot_identity(self):
        for changes in ({'id': 101}, {'is_bot': False}):
            self.session.calls.clear()
            self.session.respond(GetMe, {'id': 100, 'is_bot': True, 'first_name': 'Other', **changes})
            with self.assertRaises(PermissionDenied): await read_bot_profile(self.bot)
            self.assertEqual(len(self.session.calls), 1)

    async def test_read_photos_returns_immutable_sizes_and_one_request(self):
        photos = await read_profile_photos(self.bot, 42)
        self.assertEqual((photos.bot_id, photos.user_id, photos.total_count, photos.limit), (100, 42, 1, 1))
        self.assertIsNone(photos.photos[0][0].file_size)
        self.assertEqual(photos.photos[0][0].as_media().as_input(100), 'opaque')
        self.assertEqual(len(self.session.calls), 1)

    async def test_empty_visible_page_does_not_invent_absence(self):
        self.session.respond(GetUserProfilePhotos, {'total_count': 3, 'photos': []})
        p = await read_profile_photos(self.bot, 42, offset=4, limit=100)
        self.assertEqual(p.total_count, 3); self.assertEqual(p.photos, ())
        self.session.respond(GetUserProfilePhotos, {'total_count': 0, 'photos': []})
        self.assertEqual((await read_profile_photos(self.bot, 42)).total_count, 0)

    async def test_invalid_photo_page_rejected(self):
        self.session.respond(GetUserProfilePhotos, {'total_count': 0, 'photos': [[{'file_id': 'opaque', 'file_unique_id': 'unique', 'width': 100, 'height': 100}]]})
        with self.assertRaises(ValidationFailure): await read_profile_photos(self.bot, 42)

    async def test_photo_read_error_is_not_negative_result_or_retry(self):
        def timeout(request): raise TimeoutError('PRIVATE_PAYLOAD')
        self.session.respond(GetUserProfilePhotos, timeout)
        with self.assertRaises(TimeoutError): await read_profile_photos(self.bot, 42)
        self.assertEqual(len(self.session.calls), 1)

    async def test_invalid_inputs_rejected_before_acl_and_io(self):
        for value in ('RU', 'ru-RU', 'eng', None):
            with self.assertRaises(ValidationFailure): await read_bot_profile(self.bot, language_code=value)
            with self.assertRaises(ValidationFailure): await update_bot_profile(self.bot, BotProfilePatch(name='Name'), actor_id=42, authorize=allow, language_code=value)
        for kwargs in ({'offset': -1}, {'offset': True}, {'limit': 0}, {'limit': 101}, {'limit': True}):
            with self.assertRaises(ValidationFailure): await read_profile_photos(self.bot, 42, **kwargs)
        self.assertEqual(self.session.calls, [])

    async def test_read_denial_has_no_io(self):
        with self.assertRaises(PermissionDenied):
            await update_bot_profile(self.bot, BotProfilePatch(name='Name'), actor_id=99, authorize=allow)
        self.assertEqual(self.session.calls, [])

    async def test_method_specific_denial_has_no_write(self):
        async def authorize(actor, bot_id, method): return method == 'read'
        with self.assertRaises(PermissionDenied):
            await update_bot_profile(self.bot, BotProfilePatch(name='Name'), actor_id=42, authorize=authorize)
        self.assertEqual([type(c).__name__ for c in self.session.calls], ['GetMe'])

    async def test_truthy_unknown_authorization_never_grants_access(self):
        for result in ('true', 1, None):
            async def authorize(actor, bot_id, method): return result
            with self.assertRaises(PermissionDenied):
                await update_bot_profile(self.bot, BotProfilePatch(name='Name'), actor_id=42, authorize=authorize)
        self.assertEqual(self.session.calls, [])

    async def test_update_identity_mismatch_never_writes(self):
        self.session.respond(GetMe, {'id': 101, 'is_bot': True, 'first_name': 'Other'})
        with self.assertRaises(PermissionDenied):
            await update_bot_profile(self.bot, BotProfilePatch(name='Name'), actor_id=42, authorize=allow)
        self.assertEqual([type(c).__name__ for c in self.session.calls], ['GetMe'])

    async def test_localized_patch_preserves_omitted_fields_and_default_locale(self):
        p = await update_bot_profile(self.bot, BotProfilePatch(description='Новое'), actor_id=42, authorize=allow, language_code='ru')
        self.assertEqual(p.name, 'Русский'); self.assertEqual(p.short_description, 'Кратко'); self.assertEqual(p.description, 'Новое')
        self.assertEqual(self.state['']['description'], 'Default bio')
        self.assertEqual([type(c).__name__ for c in self.session.calls if type(c).__name__.startswith('Set')], ['SetMyDescription'])

    async def test_clear_localization_reads_fallback_without_claiming_empty_profile(self):
        p = await update_bot_profile(self.bot, BotProfilePatch(description=''), actor_id=42, authorize=allow, language_code='ru')
        self.assertEqual(p.description, 'Default bio'); self.assertNotIn('description', self.state['ru'])
        request = next(c for c in self.session.calls if isinstance(c, SetMyDescription))
        self.assertEqual((request.description, request.language_code), ('', 'ru'))

    async def test_authorization_rechecked_per_write_and_readback(self):
        checked = []
        async def authorize(actor, bot_id, method):
            checked.append((actor, bot_id, method)); return True
        await update_bot_profile(self.bot, BotProfilePatch(name='Name', description='Bio', short_description='Short', remove_photo=True), actor_id=42, authorize=authorize)
        self.assertEqual(checked, [(42, 100, m) for m in ('read', 'setMyName', 'setMyDescription', 'setMyShortDescription', 'removeMyProfilePhoto', 'read')])
        self.assertEqual(sum(isinstance(c, GetMe) for c in self.session.calls), 2)

    async def test_revoked_permission_after_prefix_requires_reconciliation(self):
        async def authorize(actor, bot_id, method): return method != 'setMyDescription'
        with self.assertRaises(ProfileEditIncomplete) as caught:
            await update_bot_profile(self.bot, BotProfilePatch(name='Changed', description='Denied'), actor_id=42, authorize=authorize)
        self.assertEqual(caught.exception.completed_methods, ('setMyName',))
        self.assertEqual(caught.exception.pending_method, 'authorize:setMyDescription')
        self.assertEqual(self.state['']['name'], 'Changed'); self.assertEqual(self.state['']['description'], 'Default bio')
        self.assertEqual(safe_error_report(caught.exception, operation='write').recovery, 'reconcile')

    async def test_lost_receipt_does_not_repeat_or_rollback_prefix(self):
        def write_and_lose(request):
            self.state['']['description'] = request.description
            raise TimeoutError('PRIVATE_TOKEN_AND_BIO')
        self.session.respond(SetMyDescription, write_and_lose)
        with self.assertRaises(ProfileEditIncomplete) as caught:
            await update_bot_profile(self.bot, BotProfilePatch(name='Changed', description='Applied', short_description='Never'), actor_id=42, authorize=allow)
        e = caught.exception
        self.assertEqual(e.completed_methods, ('setMyName',)); self.assertEqual(e.pending_method, 'setMyDescription')
        self.assertNotIn('PRIVATE_TOKEN_AND_BIO', str(e)); self.assertTrue(e.__suppress_context__)
        self.assertEqual(sum(isinstance(c, SetMyDescription) for c in self.session.calls), 1)
        self.assertFalse(any(isinstance(c, SetMyShortDescription) for c in self.session.calls))
        self.assertEqual((await read_bot_profile(self.bot)).description, 'Applied')

    async def test_false_native_confirmation_is_unknown(self):
        self.session.respond(SetMyName, False)
        with self.assertRaises(ProfileEditIncomplete) as caught:
            await update_bot_profile(self.bot, BotProfilePatch(name='Name'), actor_id=42, authorize=allow)
        self.assertEqual(caught.exception.completed_methods, ()); self.assertEqual(caught.exception.pending_method, 'setMyName')

    async def test_readback_failure_does_not_report_rejected_write(self):
        def fail(request): raise RuntimeError('PRIVATE_READBACK')
        self.session.respond(GetMyName, fail)
        with self.assertRaises(ProfileEditIncomplete) as caught:
            await update_bot_profile(self.bot, BotProfilePatch(name='Applied'), actor_id=42, authorize=allow)
        self.assertEqual(caught.exception.pending_method, 'read-back'); self.assertEqual(caught.exception.completed_methods, ('setMyName',))
        self.assertEqual(safe_error_report(caught.exception, operation='write').outcome, 'unknown')

    async def test_revoked_readback_access_exposes_no_profile(self):
        reads = 0
        async def authorize(actor, bot_id, method):
            nonlocal reads
            if method == 'read': reads += 1
            return reads <= 1
        with self.assertRaises(ProfileEditIncomplete) as caught:
            await update_bot_profile(self.bot, BotProfilePatch(name='Applied'), actor_id=42, authorize=authorize)
        self.assertEqual(caught.exception.pending_method, 'authorize:read-back')
        self.assertFalse(any(isinstance(c, GetMyName) for c in self.session.calls))

    async def test_static_avatar_is_new_buffered_upload(self):
        await update_bot_profile(self.bot, BotProfilePatch(photo=MediaFile('photo', JPEG, filename='avatar.jpg')), actor_id=42, authorize=allow)
        native = next(c for c in self.session.calls if isinstance(c, SetMyProfilePhoto)).photo
        self.assertIsInstance(native, InputProfilePhotoStatic)
        self.assertEqual(b''.join([part async for part in native.photo.read(self.bot)]), JPEG)
        self.assertFalse(any(isinstance(c, RemoveMyProfilePhoto) for c in self.session.calls))

    async def test_animated_avatar_has_native_frame_timestamp(self):
        data = b'synthetic MPEG4 fixture'
        await update_bot_profile(self.bot, BotProfilePatch(photo=MediaFile('video', data, filename='avatar.mp4'), main_frame_timestamp=1.25), actor_id=42, authorize=allow)
        native = next(c for c in self.session.calls if isinstance(c, SetMyProfilePhoto)).photo
        self.assertIsInstance(native, InputProfilePhotoAnimated); self.assertEqual(native.main_frame_timestamp, 1.25)
        self.assertEqual(b''.join([part async for part in native.animation.read(self.bot)]), data)

    async def test_cancelled_write_propagates_without_retry_or_close(self):
        async def cancel(request):
            self.state['']['name'] = request.name
            raise asyncio.CancelledError()
        self.session.respond(SetMyName, cancel)
        with self.assertRaises(asyncio.CancelledError):
            await update_bot_profile(self.bot, BotProfilePatch(name='May be applied'), actor_id=42, authorize=allow)
        self.assertEqual(sum(isinstance(c, SetMyName) for c in self.session.calls), 1)
        self.assertFalse(self.session.closed)
