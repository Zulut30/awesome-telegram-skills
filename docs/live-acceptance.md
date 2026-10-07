# Живая приемка в тестовом окружении Telegram

Перед каждым тегом `vX.Y.Z`, начиная с 0.25.0, три примера репозитория проходят в настоящем Telegram, в тестовом окружении: [сервисный бот](service-bot.md), [групповой бот](group-bot.md) и [магазин](shop-example.md) с оплатой тестовыми Telegram Stars. Отчет с датой лежит в `docs/live-checks/<версия>/report.json` и входит в тег. Workflow Release проверяет его (`scripts/live_acceptance.py bundle`), прикладывает к релизу `live-report-<версия>.zip` и добавляет таблицу в описание. Без корректного отчета релиз 0.25.0 и новее не публикуется.

Офлайн-проверки CI (тестовый транспорт, браузер) это не заменяют: они не видят серверов Telegram, доставку обновлений, права в настоящих группах и платежный экран.

## Подготовка

1. Войдите в тестовое окружение ([Testing your bot](https://core.telegram.org/bots/features#testing-your-bot)): iOS — 10 нажатий на Settings → Accounts → Login to another account → Test; Telegram Desktop — ☰ Settings → Shift+Alt+правый клик по «Add Account» → Test Server; macOS — 10 нажатий на Settings, затем ⌘+клик по «Add Account».
2. В тестовом @BotFather создайте три бота (`/newbot`). Токены храните только в переменных окружения.
3. Запустите каждый пример по его странице с токеном тестового бота и переключателем тестового окружения (`TELEGRAM_TEST_ENVIRONMENT=1`; см. [тестовое окружение](test-environment.md)). Для магазина нужен HTTPS-адрес Mini App или HTTP-адрес, который тестовое окружение принимает.
4. `python scripts/live_acceptance.py new --version X.Y.Z` создает `docs/live-checks/X.Y.Z/report.json`, где все случаи `not-run`.

## Автоматическая проба

Для каждого бота:

```bash
TELEGRAM_TEST_BOT_TOKEN=<токен тестового бота> python scripts/live_acceptance.py probe --version X.Y.Z --scenario shop
```

Проба обращается к `https://api.telegram.org/bot<token>/test/METHOD` и записывает в отчет то, что бот подтверждает сам: имя бота (`getMe`), состояние webhook и число ожидающих обновлений, число команд и для магазина — что `createInvoiceLink` в валюте `XTR` возвращает ссылку на счет. Токен в отчет не попадает. Нажатия кнопок проба не заменяет: Bot API не может действовать от имени пользователя.

## Случаи

| Сценарий | ID | Ожидание |
| --- | --- | --- |
| service-bot | `start` | /start показывает меню записи |
| service-bot | `book-slot` | Запись на свободное время подтверждается одним сообщением |
| service-bot | `double-press` | Двойное нажатие «Подтвердить» создает одну запись |
| service-bot | `reminder` | Напоминание приходит в назначенное время |
| service-bot | `cancel` | Отмена записи освобождает время |
| group-bot | `topic` | Бот отвечает в теме форума, где его вызвали |
| group-bot | `missing-rights` | Без прав администратора бот называет недостающее право |
| group-bot | `join-request` | Заявка на вступление одобряется после подтверждения модератора |
| group-bot | `moderation` | Команда модерации действует только для администратора |
| shop | `open-mini-app` | Mini App открывается кнопкой меню, сервер принимает initData |
| shop | `order` | Заказ создается один раз на операцию |
| shop | `stars-invoice` | Счет в Stars открывается в тестовом окружении |
| shop | `payment` | Оплата тестовыми Stars подтверждается, материал открывается |
| shop | `refund` | Возврат через refundStarPayment закрывает доступ |

Статусы: `passed`, `failed`, `blocked` (проверить нельзя, причина в заметке), `not-run`. Для всего, кроме `passed`, нужна заметка. Статус сценария вычисляется из случаев так же, как в [проверке на устройствах](device-qa-checklist.md). `checked_by` — имя или ник без e-mail и телефона; `bot` — публичное имя вида `@example_bot`.

## Проверка и релиз

```bash
python scripts/live_acceptance.py check docs/live-checks/X.Y.Z --version X.Y.Z
```

Закоммитьте отчет до тега. Найденные дефекты остаются в отчете как `failed` с заметкой. Отчет подтверждает поведение конкретной сборки в тестовом окружении; основное окружение, настоящие платежи и другие версии клиентов он не проверяет.
