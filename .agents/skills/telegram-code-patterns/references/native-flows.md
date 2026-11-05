# Native-сценарии Mini App

Термины: **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **fallback** — запасной вариант, если основная возможность недоступна.

`NativeFlowScope` объединяет существующие version/presence gates `TelegramNativeAPI`
с жизненным циклом конкретного экрана и аккаунта. SDK, framework и новый backend
не требуются. Импорты — из `@awesome-telegram/patterns`; пакет устанавливается
локально, как описано в [инструкции подключения](https://github.com/Zulut30/awesome-telegram-skills/blob/main/docs/for-agents.md).

Один scope принадлежит одному активному Mini App client. `capabilities()` возвращает
15 сценариев с версией, наблюдаемой платформой, объявленным контекстом запуска,
состоянием permission/hardware/account и текстом fallback. `ready-to-attempt`
означает возможность попытки по проверенным признакам. Успешную работу на устройстве
подтверждает отдельная проверка в целевом Telegram-клиенте.

## Подключение и запасной путь

```ts
import {NativeFlowScope, NativePrompts} from '@awesome-telegram/patterns';

// accountTag получен из проверенной сервером сессии, включает bot/account scope.
const scope = new NativeFlowScope(window.Telegram?.WebApp, {
  accountTag: session.nativeAccountTag,
  launch: 'direct', // фактический проверенный приложением контекст запуска
  platformPolicy: (_flow, platform, launch) =>
    testedPlatforms.has(platform) && launch !== 'unknown',
});
const prompts = new NativePrompts(scope);
const onContact = async () => {
  const result = await prompts.contact({
    purpose: 'Контакт для этой доставки', userInitiated: true,
  });
  if (result.status === 'completed') {
    showContactAwaitingServerConfirmation();
  } else if (result.status === 'unsupported' || result.status === 'denied') {
    showManualContactField(); // сохраняет текущие значения формы
  } else if (result.status === 'unknown') {
    showWaitingForNativeClosure();
  }
};
contactButton.addEventListener('click', onContact);
// teardown экрана:
contactButton.removeEventListener('click', onContact);
scope.dispose();
```

`session`, `testedPlatforms` и UI-функции принадлежат приложению. Маркер
`userInitiated: true` фиксирует намерение вызывающего кода; он не доказывает
браузерный gesture, согласие или серверную авторизацию. Политику платформ и launch
задаёт host по своим проверкам. Имя `android` либо наличие метода сами по себе
не подтверждают доступность камеры, permission или аппаратной биометрии.

## Матрица сценариев

Версии ниже — gates используемых методов из текущего каталога библиотеки.
Для каждой строки дополнительно нужны presence gate и политика platform/launch
приложения. Неизвестный клиент получает явный запасной путь в локальном примере.

| Сценарий / API | Gate | Permission и локальный результат | Fallback приложения |
| --- | --- | --- | --- |
| `NativeActionButtons`: Main / Back | 6.1 | Свои listeners; visibility, enabled и progress | DOM action / navigation |
| Secondary button | 7.10 | Отдельный handler и mutex | DOM secondary action |
| `NativePrompts.popup` | 6.2 | `null`, close/cancel → `cancelled`; только известный ID → completed | DOM dialog |
| `qr` | 6.4; close event 7.7 | Контекстное действие; QR — непроверенный текст | Поле кода |
| `invoice` | 6.1 | Любой native status требует серверной сверки | Серверная invoice-ссылка и статус заказа |
| `contact` | 6.9 | `shared: true` либо denied; без присвоения личности | Ручной контакт с серверной проверкой |
| `prepareLocation` → `location` | 8.0 | Init, наличие hardware, действие пользователя; null → denied | Ручной адрес |
| `NativeAccountStorage`: cloud | 6.9 | Проверенный account scope; callback чтения/записи | Серверный черновик |
| device / secure | 9.0 | Scoped key; secure recovery вызывается отдельно | Серверное восстановление без plaintext downgrade |
| `prepareBiometric` → `requestBiometricAccess` → `unlockBiometric` | 7.2 | Init, hardware, consent, local authentication | Серверное подтверждение |
| `NativeSharing.message` | 8.0 | Prepared ID с backend; callback `sent` | Разрешённая копируемая ссылка |
| `story` | 8.0 | Только `editorRequested: true`; отправка не наблюдается | Разрешённый media download |
| `download` | 8.0 | `accepted`, всегда `persisted: false` | HTTPS download-ссылка |
| `createNativeFileInput` | Обычный HTML | File selection; accept/capture — hints | Выбор файла без обещания камеры |
| `ServerlessEndpointClient` | Минимальная версия не опубликована | Явный hosting opt-in + presence; результат endpoint | Существующий HTTP backend |

Native invoice callback не подтверждает оплату: даже `nativeStatus: 'paid'`
возвращается с `requiresServerReconciliation: true`. Право на товар/доступ выдаёт
backend после собственной проверки. Download callback не доказывает запись файла;
story request не доказывает публикацию. Для download сервер должен корректно
обслуживать файл и необходимые Telegram Web CORS/Content-Disposition заголовки.
[Официальные методы клиента](https://core.telegram.org/bots/webapps#initializing-mini-apps).

## Pending, отмена и поздние ответы

`NativeFlowResult<T>` различает completed, denied, cancelled, unsupported, busy,
stale, unknown и failed. Ошибки используют общий безопасный `ErrorReport`.
Валидация параметров может синхронно выбросить `ValidationFailure` до native-вызова.
Методы возвращают завершённый Promise; pending наблюдается как текущая операция
вызывающего кода. Ограничение scope — 16 одновременных facilities без очереди.

Окна, QR, счета, контакт, разрешения, передача и загрузка владеют общим prompt
слотом. Повторное нажатие возвращает busy и не удаляет listener первой операции.
Таймаут/abort после начала запроса означает unknown. Слот сохраняется до реального
terminal callback, поэтому таймаут не открывает второй native prompt поверх первого.
`AbortSignal` не обещает отменить уже начатый внешний эффект. Для QR вызывается
закрытие только своего сканера; на старом клиенте без close event слот остаётся занят.

Если host действительно наблюдал закрытие, он может вызвать
`scope.confirmPromptClosed(result.recoveryId)`. Не используйте этот метод по таймеру
или ради повторной попытки записи. Поздний callback освобождает только свой слот,
не меняет уже полученный результат и не применяется к новому аккаунту. QR-текст
никогда не открывается автоматически как URL. Ошибка SDK при открытии prompt
сохраняет unknown: окно могло уже открыться.

`NativeActionButtons` владеет своими Main/Secondary/Back listeners и видимостью.
Показывайте DOM альтернативу при неподдерживаемой поверхности. На время async handler
сохраняется label, включается progress и блокируется повторная активация этой кнопки.
Queued handler не стартует после dispose. После его старта dispose не отменяет
удалённую бизнес-операцию; host использует её operation ID и серверную сверку.
Вызывайте `buttons.dispose()` перед `scope.setAccount(...)` либо `scope.dispose()`;
для нового аккаунта создавайте новый `NativeActionButtons`. При ошибке снятия listener
cleanup можно повторить; ошибка не содержит исходный SDK message.

## Хранилища, аккаунт и восстановление

`NativeAccountStorage` создаёт ключи `tp_<длина accountTag>_<accountTag>_<key>`.
Длина в префиксе не дает разным парам аккаунта и ключа совпасть при наличии `_`.
`accountTag` — непрозрачное
значение проверенной backend-сессии с bot/account scope, а не доверенный клиентом
Telegram ID. Локальные пределы: tag/key до 48 символов `A-Z a-z 0-9 _ -`, value до
4096 символов. Секреты бота, provider keys и bearer-сессия сюда не помещаются.
`completed` означает полученный корректный callback: обязательно проверьте
`value.stored` / `value.removed`. Значение false не подтверждает сохранение/удаление
и не запускает fallback или повтор автоматически. `canRestore` у чтения проверяется
отдельно от `value`.

`scope.setAccount(newTag)` инвалидирует старые callbacks. Host одновременно очищает
private DOM/cache/drafts и пересоздаёт owned controls. Данные других аккаунтов
автоматически не удаляются. Чтение SecureStorage может вернуть `value: null` с
`canRestore: true`: `restoreSecure` вызывается отдельно по понятному действию
пользователя. Ошибка/недоступность secure storage не вызывает запись в cloud/device.
Unknown write сохраняет занятым свой key до terminal callback; повтор не выполняется
автоматически. Биометрический token не кешируется компонентом, local unlock
не авторизует запрос к backend.

HTML picker проверяет локальный maxBytes и удаляет свой listener при dispose.
Host проверяет содержимое, MIME и доступ на сервере. `capture` — только hint;
камера, OS picker и получение разрешений требуют отдельной проверки на устройстве.

## Необязательный Serverless adapter

`ServerlessEndpointClient(app, {serverlessHosting: true})` предназначен только для
явно выбранного Telegram Serverless hosting. `supports()` требует native presence,
непустой initData и функцию `Serverless.call`; минимальная версия не выдумывается.
Обычный Python/backend не мигрирует автоматически.
[Официальные Serverless.call](https://core.telegram.org/bots/webapps#serverless),
[hosting и проверка initData](https://core.telegram.org/bots/serverless).

```ts
import {ServerlessEndpointClient} from '@awesome-telegram/patterns';

const client = new ServerlessEndpointClient(app, {serverlessHosting: true});
const result = await client.call('place_order', {
  operation_id: orderOperationId, // durable ID создал host до первой попытки
  product_id: selectedProductId,
}, decodeOrder, {operation: 'write'});
if (result.status === 'unknown') await reconcileOrder(orderOperationId);
```

`decodeOrder` — синхронный decoder, `orderOperationId` и reconciliation принадлежат
приложению. Endpoint проверяет object ACL и idempotency по тому же ID. Серверная
проверка Telegram initData не заменяет эти проверки. Для обычного backend используйте
его существующий клиент при unsupported.

Raw typed bridge повторяет `call(name[, input][, callback]): void`; raw error содержит
message/type/status/parameters. Wrapper не раскрывает эти сообщения/parameters/initData
в ErrorReport. Имена endpoint ограничены идентификатором до 128 символов. Input —
обычный JSON-объект с конечными числами: без геттеров, циклов, undefined и экземпляров классов;
пределы 32 уровня, 10000 узлов и 64 KiB UTF-8. Decoder не должен возвращать Promise.
`operation` по умолчанию write. Сетевая ошибка status 0, timeout/abort либо ошибка
endpoint после возможной записи → unknown/reconcile без автоматического retry.
UNAUTHORIZED с status 401 распознаётся как отказ до endpoint. `invalidateAccount()`
и dispose отсекают поздние результаты; они не отменяют серверную запись.

## Проверка и проверенные источники

Локальный `examples/native-flows/README.md` и
`examples/api-reference/typescript/flows.ts` используют
основные импорты пакета. Node-проверки охватывают занятость, поздние ответы,
неизвестный исход, согласие и изоляцию аккаунтов,
storage isolation, безопасные ошибки, JSON bounds и callback null. Реальный локальный
Chrome исполняет fake SDK, DOM fallback и 20 комбинаций platform/launch. Это
не native/device acceptance; реальные Telegram/Serverless/платежи не вызываются.

2026-11-05 проверены Serverless presence/overloads/errors из
[source-watch #7](https://github.com/Zulut30/awesome-telegram-skills/issues/7)
и дополнительно nullable popup callback. Официальный
[JavaScript SDK](https://telegram.org/js/telegram-web-app.js) snapshot имеет SHA-256
`124BDFF7BA3FE86C8BA5143467AFEC21E020405E74ABDB92CFDDA6C0EE3B5908`.
В [popupClosed](https://core.telegram.org/bots/webapps#events-available-for-mini-apps)
отсутствие нажатой кнопки даёт null. Канонический `showPopup` callback уточнён до
`string | null` и штатно сгенерирован; общая дата проверки каталога не обновлялась.
Полный native catalog и реальные устройства этим изменением не переаттестованы.
