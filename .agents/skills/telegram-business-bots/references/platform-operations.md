# Темы, реакции, заявки и специальные операции

Пункт 30 расширяет локальную Python-библиотеку; optional aiogram 3.31.0, Bot API 10.3. Публичные компоненты experimental. TypeScript Mini Apps и существующий Bot/Dispatcher/storage сохраняются. Этот слой выполняет 51 проверенную native-операцию, а не только создает SDK requests. Приемка общей поставки фиксируется отдельным отчетом; SDK/mock не подтверждают реальные права, расход Stars, содержимое медиа, доставку или устройства.

## Публичная композиция

Импортируйте из `telegram_patterns.aiogram`: `PlatformScope`, `PlatformPermit`, `PlatformAction`, `PlatformHooks`, `execute_platform_action`. Scope задается сервером: bot, actor, stable operation ID, revision и точные chat/thread/message, Business owner/connection, applicant/query или owner/child. `PlatformAction(scope, request)` принимает native aiogram request из закрытого allowlist, копирует его и дает fingerprint. `action.request` возвращает отдельную копию; изменение исходного запроса не меняет действие. Неизвестные SDK extras и подмена native класса отвергаются.

`platform_contracts()` перечисляет метод, семейство, right, read/write, финансовый/секретный характер, официальный URL, проверенную версию и уровень `sdk`. Статус experimental и способ проверки имеют разные значения. Отправитель callback, название кнопки, Premium, наблюдение Update и ручной DTO не дают прав.

Host реализует три async hooks. `authorize` проверяет текущие actor ACL, scope, revision, ресурс, сообщения, consent и quote. `claim` повторно проверяет прикладные ограничения в транзакции и сохраняет уникальное sending intent до native I/O; бюджет резервируется в той же транзакции. `record` сохраняет результат для этого fingerprint. При повторе claim возвращает False: даже подтвержденная операция явно сверяется; сервер не посылает ее заново и не возвращает чужой сохраненный секрет. Native проверка прав и host transaction не образуют атомарную транзакцию с Telegram.

`PlatformResult.value` сохраняет native SDK результат; `PlatformReceipt` содержит безопасные method/outcome/result ID. Repr скрывает private payloads. Для необратимых действий используйте подтверждение пользователя в интерфейсе проекта и текущую server policy. Секрет managed bot возвращается как `SecretToken`: `reveal()` нужен для явной передачи в secret store; `asdict`, произвольная сериализация или собственный logger автоматически безопасными не становятся.

## Семейства и условия

| Семейство | Операции | Перед выполнением |
| --- | --- | --- |
| Темы | Create/edit/close/reopen/delete, General hide/unhide и unpin, icon catalog | Свежий getChat; forum supergroup + нужный administrator right. Edit/close/reopen допускают проверенную host receipt создателя. Private поддерживается только методами, которые это явно допускают, при включенных bot topics. Icon проверяется по getForumTopicIconStickers |
| Реакции | Set/clear, удаление одной реакции или недавних реакций пользователя/чата | Свежий chat/membership; не более одной неплатной реакции бота. Custom emoji требует текущего chat catalog или подтвержденного наличия на сообщении. Delete требует can_delete_messages и ровно один user/chat actor |
| Заявки | Legacy approve/decline; query approve/decline/queue и HTTPS Mini App | Host подтверждает актуальность заявки и ее chat/applicant/query. Legacy требует can_invite_users. Query использует отдельный native путь, enabled capability и первоначальный receive time; первоначальный ответ — в пределах 10 секунд |
| Business | Connection, send/edit, read/delete, name/bio/username/photo/gift settings | Свежий enabled connection с правильным владельцем и конкретным right. Send/read/edit требует private chat и проверенной recent eligibility. Sent-only delete требует доказанного авторства и связи всех message IDs с одним чатом |
| Stories | Post/edit/delete/repost | can_manage_stories; допустимый active_period. Repost проверяет обе управляемые connection, право источника и собственную подтвержденную историю. New upload требует проверки host codec, dimensions, content/access и сохранения файла |
| Gifts | Catalog, user/chat/business gifts, balance, send, Premium, convert/upgrade/transfer/Stars | Current ACL/consent/quote и atomic host budget; точная цена Premium. Paid upgrade/transfer требует дополнительного can_transfer_stars; destination activity проверяется host. Send перечитывает доступный gift и цену; limited gift в channel отвергается |
| Managed bots | User-confirmed link, token read/rotation, access read/set | Enabled manager capability, текущая server binding parent/child/owner. Native user_id — ID дочернего бота. Access разрешает до 10 дополнительных пользователей; owner сохраняет доступ. Ротация требует отдельного подтверждения и обработки неизвестного результата |

Права различаются по методу: can_reply не заменяет can_read_messages, can_delete_sent_messages не разрешает удаление чужих сообщений. Business не дает историю всех чатов аккаунта и не подменяет MTProto. Premium не требуется по устаревшему примеру: проверяется доступная текущему аккаунту возможность.

Проверенная quote и локальная бюджетная резервация не означают атомарного ограничения удаленного расхода. У sendGift нет параметра expected price/max debit: стоимость может измениться между чтением и запросом. Host определяет согласие на этот риск и сверку фактических транзакций. Owned gift eligibility, принадлежность, prepaid/transfer price и сроки проверяются current host policy; библиотека не считает отсутствие поля бесплатной операцией и требует явный star_count для upgrade/transfer.

## Новые загрузки stories

`StoryPhotoUpload(photo=BufferedInputFile(...))` и `StoryVideoUpload(video=BufferedInputFile(...), duration=...)` — валидируемые адаптеры к string-only полям сгенерированного SDK. Они используют обычную вложенную multipart-сериализацию session и создают совпадающие attach references/file parts. Здесь не отключается валидация через model_construct и не заменяется transport проекта. SDK serialize/wire проверяется отдельно от пригодности фото/видео для Telegram. Photo: 1080×1920, до 10 MB; video: 720×1280, H.265 MPEG4, key frames each second, до 30 MB и 60 секунд — host обязан проверить реальный файл, включая byte bound при FSInputFile. Literal captions и gift/business text используют explicit parse_mode=None/entities. FSInputFile fingerprint связывает locator, а не изменяемые bytes: host сохраняет неизменяемый проверенный файл до окончания отправки; buffered upload включает SHA-256 содержимого.

## Отказы, время и секреты

До native write требуется успешный claim. Явный API rejection записывается отдельно. Потерянный ответ, неизвестная ошибка или неудачная запись подтверждения требуют сверки прежнего intent; retry отсутствует. Sending row после аварии рассматривается как unknown. Cancellation сохраняется и пытается записать unknown; если storage недоступен, durable intent уже существует. Deadline охватывает preflight/claim/native await; для join query остаток исходных 10 секунд перепроверяется перед отправкой. Первоначальный timestamp нельзя обновлять при повторе. Если Mini App уже открыто, дальнейшее решение требует собственного актуального host состояния и native query contract.

Secret read не создает write intent. Rotate создает его и никогда не повторяется автоматически. После известной ротации сохраняйте новый token через `PlatformResult.value.reveal()` в secret store. При ошибке secret sink сверяйте/read token, а не вращайте снова. Claim fingerprint и receipts не хранят возвращенный токен. Не запускайте второй polling consumer дочернего бота как часть диагностики.

## События и хранилище

`platform_event` сохраняет native facts и raw JSON, включая None и неизвестные дополнительные поля; payload скрыт в repr. Анонимный chat actor не превращается в пользователя. ManagedBotUpdated использует реальное SDK поле `bot_user`; service ManagedBotCreated не выдумывает owner. Reaction count не восстанавливает индивидуальные действия или историю.

`platform_events_router(lookup, observe)` добавляется к текущему Dispatcher. Lookup каждый раз возвращает current host binding, затем сверяются bot/chat/thread/message/connection/owner/child/query доступные поля. Host транзакционно дедуплицирует `(bot_id, update_id)`, задает order/migration policy, отзываемые bindings и retention. Полученный connection/managed update надо сохранять и применять к будущим действиям; observer сам не назначает роли и не запускает эффекты. Выберите необходимые allowed_updates; Telegram может не доставлять отдельные события без нужных настроек/прав.

Полный пример содержит host-owned file SQLite actor revision/budget/intent и router. Это небольшая синхронная композиция; distributed inbox/outbox, очереди, массовая модерация, Telegram live и полная история аккаунта не заявлены. Сохраняйте инфраструктуру проекта и проверяйте разные чаты, темы, владельцев и отзыв доступа.

## Полный пример

Следующий блок — точная композиция `platform_bot.py`; host передает resolver, hooks, текущие bindings/observer и sink результатов. Offline fixture использует искусственные права и медиа и не подходит для отправки с настоящим токеном.

```python
"""Host-owned SQLite intents and native platform composition; no live startup."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from telegram_patterns import ConflictFailure, PermissionDenied, safe_error_report
from telegram_patterns.aiogram import (PlatformAction, PlatformHooks, PlatformLookup, PlatformObserver,
    PlatformPermit, PlatformReceipt, PlatformResult, execute_platform_action, platform_events_router)

Policy = Callable[[PlatformAction], Awaitable[PlatformPermit]]
Resolve = Callable[[Message], Awaitable[PlatformAction | None]]
ResultSink = Callable[[PlatformAction, PlatformResult], Awaitable[None]]


class PlatformJournal:
    """Example host storage. ACL/revision/budget are authoritative SQL rows.

    Only the host provisions actors and budgets. Native eligibility, message/gift
    ownership, media and child bindings come from its current policy callback.
    A sending intent recovered after crash is unknown; it is never auto-retried.
    This small synchronous file-SQLite example is not a distributed job queue.
    """
    def __init__(self, connection: sqlite3.Connection, policy: Policy) -> None:
        if connection.in_transaction:
            raise ConflictFailure('Host must finish its transaction before initializing the journal')
        self.connection, self.policy = connection, policy
        connection.executescript('''
          CREATE TABLE IF NOT EXISTS platform_actors (
            bot_id INTEGER, actor_id INTEGER, revision INTEGER, enabled INTEGER,
            PRIMARY KEY(bot_id, actor_id));
          CREATE TABLE IF NOT EXISTS platform_budgets (
            bot_id INTEGER, actor_id INTEGER, remaining INTEGER CHECK(remaining >= 0),
            PRIMARY KEY(bot_id, actor_id));
          CREATE TABLE IF NOT EXISTS platform_intents (
            bot_id INTEGER, operation_id TEXT, actor_id INTEGER, fingerprint TEXT,
            method TEXT, status TEXT, result_id INTEGER,
            PRIMARY KEY(bot_id, operation_id));
        ''')

    def _allowed(self, action: PlatformAction) -> bool:
        row = self.connection.execute('SELECT revision,enabled FROM platform_actors WHERE bot_id=? AND actor_id=?',
            (action.scope.bot_id, action.scope.actor_id)).fetchone()
        return row == (action.scope.revision, 1)

    async def authorize(self, action: PlatformAction) -> PlatformPermit:
        permit = await self.policy(action)
        return replace(permit, allowed=permit.allowed and self._allowed(action))

    async def claim(self, action: PlatformAction, permit: PlatformPermit) -> bool:
        db, scope = self.connection, action.scope
        if db.in_transaction: raise ConflictFailure('Host must end its transaction before claiming an external intent')
        db.execute('BEGIN IMMEDIATE')
        try:
            if not self._allowed(action):
                raise PermissionDenied('Current host ACL/revision changed before claim')
            existing = db.execute('SELECT fingerprint FROM platform_intents WHERE bot_id=? AND operation_id=?',
                (scope.bot_id, scope.operation_id)).fetchone()
            if existing is not None:
                db.rollback()
                return False
            if action.contract.financial:
                cost = permit.star_cost
                if cost is None or permit.max_stars is None or not permit.financial_authorized or cost > permit.max_stars:
                    raise PermissionDenied('No current financial authorization')
                result = db.execute('UPDATE platform_budgets SET remaining=remaining-? WHERE bot_id=? AND actor_id=? AND remaining>=?',
                                    (cost, scope.bot_id, scope.actor_id, cost))
                if result.rowcount != 1: raise PermissionDenied('Atomic host budget is unavailable')
            db.execute('INSERT INTO platform_intents VALUES (?,?,?,?,?,?,NULL)',
                       (scope.bot_id, scope.operation_id, scope.actor_id, action.fingerprint, action.contract.method, 'sending'))
            db.commit()
            return True
        except BaseException:
            db.rollback()
            raise

    async def record(self, action: PlatformAction, receipt: PlatformReceipt) -> None:
        if self.connection.in_transaction:
            raise ConflictFailure('Host must finish its transaction before recording a native receipt')
        if (receipt.operation_id,receipt.fingerprint,receipt.method) != (action.scope.operation_id,action.fingerprint,action.contract.method):
            raise ConflictFailure('Receipt does not match its claimed intent')
        with self.connection:
            result = self.connection.execute('UPDATE platform_intents SET status=?,result_id=? WHERE bot_id=? AND operation_id=? AND fingerprint=? AND status=?',
                (receipt.outcome,receipt.result_id,action.scope.bot_id,action.scope.operation_id,action.fingerprint,'sending'))
            if result.rowcount != 1: raise ConflictFailure('Receipt requires the original sending intent')


def platform_router(resolve: Resolve, hooks: PlatformHooks, lookup: PlatformLookup, observe: PlatformObserver,
                    on_result: ResultSink) -> Router:
    """Mount into the current Dispatcher; host resolves configured targets and consent."""
    router = Router(name='platform-composition')
    commands = Router(name='platform-commands')
    commands.message.filter(F.chat.type == 'private', F.from_user.is_bot == False)

    @commands.message(Command('topic','reaction','join','business','story','gift','managed'))
    async def handle(message: Message) -> None:
        if message.from_user is None or message.bot is None: return
        action = await resolve(message)
        if action is None: return
        try:
            if (action.scope.bot_id,action.scope.actor_id) != (message.bot.id,message.from_user.id):
                raise PermissionDenied('Command actor does not match the host operation')
            result = await execute_platform_action(message.bot,action,hooks)
            # The host stores returned secrets explicitly; results never become
            # command replies. A vault integration belongs to the application.
            await on_result(action,result)
            await message.answer('Действие подтверждено.' if result.receipt.outcome=='succeeded' else 'Проверьте состояние действия.',parse_mode=None)
        except Exception as error:
            await message.answer(safe_error_report(error,operation='write').message,parse_mode=None)

    router.include_router(commands)
    router.include_router(platform_events_router(lookup,observe))
    return router
```

## Источники и проверка

5 октября 2026 года проверены соответствующие методы [Bot API](https://core.telegram.org/bots/api), [Business](https://core.telegram.org/bots/features#business-bots), [managed bots](https://core.telegram.org/bots/features#managed-bots), [join requests](https://core.telegram.org/bots/api#chatjoinrequest), [story photo](https://core.telegram.org/bots/api#inputstorycontentphoto), [story video](https://core.telegram.org/bots/api#inputstorycontentvideo) и installed aiogram 3.31.0 models/session multipart. Дата относится к этим контрактам, не всему Telegram API.

Локальный путь: предоставить wheel, установить optional aiogram и выполнить bundled `demo-platform` offline. Unit tests проверяют каждый из 51 методов, server binding, права, дедлайны, бюджет, анонимные события и unknown outcomes; actual SDK multipart содержит связанные attach references и bytes. Полная поставка, чистый consumer, перенос guide и browser catalog принимаются отдельным отчетом. Live permissions, допустимость реальных медиа, финансовый settlement, реальные устройства и независимые human/AI проверки остаются отдельными приемками.
