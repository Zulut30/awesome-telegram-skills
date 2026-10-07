# Границы, состояние и восстановление

## Минимальная структура

Это роли компонентов, а не обязательные каталоги или архитектурный framework:

| Роль | Владеет | Не принимает за источник истины |
| --- | --- | --- |
| Shell/platform adapter | Capabilities, события, theme/viewport, cleanup | Серверную личность из initDataUnsafe |
| Экран/feature | Ввод и отображение действия | Цену, права и итог оплаты из frontend |
| API/session boundary | HTTP-контракт, проверенный ответ, cancellation, истечение сессии | TypeScript-тип как runtime-валидацию JSON |
| Прикладная операция Python | Права, правила, переходы, однократный эффект | Payload кнопки как полномочие |
| Storage | Долговечные записи и атомарные ограничения | Состояние одного WebView |

Для небольшого сценария хватает нескольких модулей. Выделяйте feature boundary там, где есть собственный lifecycle; не создавайте транзитные слои ради схемы. Проверяйте направление импортов и отсутствие window.Telegram в прикладных правилах.

## Владельцы состояния

| Состояние | Время жизни и восстановление |
| --- | --- |
| Экран/объект | Router или модель переходов; прямую ссылку проверяет сервер |
| Черновик | Владелец выше сменяемого шага; сохраняется при back/resize/theme |
| Серверные данные | Один cache/API boundary; invalidation после изменения и смены личности |
| Отправка | idle → pending → succeeded/error/unknown outcome; общий handler CTA |
| Telegram callbacks | Один владелец, стабильные функции и симметричный cleanup |

Browser history использует стабильные routes/state; перезагрузка любого URL дает осмысленный результат. Не добавляйте новый popstate/back callback на каждый render. Для одного modal не нужен большой router.

Для отправки фиксируйте данные и логический request key. Повтор попытанного действия использует прежний ключ и параметры; новое действие — новый ключ. Потерянный ответ восстанавливайте по операции/заказу, если контракт позволяет. Disabled-кнопка не доказывает exactly-once.

Не сохраняйте initData, bearer tokens или чувствительный черновик в localStorage по умолчанию. Восстановление после перезапуска зависит от продукта и модели сессии. Demo adapter включается явно в dev и не подменяет production backend.

## Ошибки границ

Сеть, неверное поле, запрет доступа, истечение сессии и бизнес-конфликт дают разные действия восстановления. Временная ошибка не очищает форму. После смены пользователя cache и старые запросы не показывают чужие данные.

Для поиска отменяйте stale requests либо проверяйте request generation перед применением. Для записи cancellation HTTP-запроса не доказывает отмену серверной операции. Retries согласуйте с семантикой метода.

Background/frozen document и окончательный unmount — разные lifecycle. Если pagehide используется для teardown, поддержи восстановление pageshow при persisted=true: геометрия и подписки не должны оставаться выключенными после возврата без нового bootstrap.

Покажите один путь экран → действие → API → результат и отказную ветку. Проверьте back к заполненной форме, прямую загрузку route, повтор отправки, stale response и cleanup. Python-операция тестируется вне Telegram handler; framework выбирается по проекту.

Источники: [события Telegram](https://core.telegram.org/bots/webapps#events-available-for-mini-apps), [pagehide и persisted](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event), [pageshow](https://developer.mozilla.org/en-US/docs/Web/API/Window/pageshow_event), [back/forward cache](https://web.dev/articles/bfcache), [серверная проверка](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
