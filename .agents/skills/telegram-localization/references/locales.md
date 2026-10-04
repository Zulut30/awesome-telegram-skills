# Locale, время и сообщения

## Выбор

Опиши приоритет явного предпочтения, сохраненной настройки, language_code и default locale. Ограничь выбор поддерживаемыми locale; malformed/неизвестный код приводит к fallback, а не падению formatter. При необходимости подбирай базовый язык из regional locale, сохраняя явный выбор пользователя.

Предпочтение синхронизируется по контракту backend, если нужно общее значение для бота и Mini App. Отсутствие language_code не означает конкретный язык; доверенный язык профиля не является авторизацией или геолокацией.

## Форматирование

Для TypeScript используй установленную i18n библиотеку/Intl; для Python — существующий formatter, gettext/Babel по стеку. В plural messages есть необходимая ветка fallback/other. Покрой значимые категории выбранного языка: для русского, например, 1/2/5/11/21 и ноль. Decimal counts требуют своих правил.

Backend передает канонические значения и семантику: instant с timezone/offset, локальный день услуги либо сумма в точных units/decimal и currency. Frontend не пытается угадать тип по произвольной строке. Formatting не пересчитывает валюту и не округляет сумму иначе, чем контракт оплаты.

Язык не определяет timezone. Для записи укажи timezone услуги и то, какой день видит пользователь; не парси date-only как UTC instant с последующим неявным переносом дня. Повторяемое локальное время требует политики ambiguous/nonexistent DST; при неоднозначности запрашивай выбор или отклоняй ввод по контракту.

## Строки и безопасные вставки

Стабильные translation keys/error codes не меняются от языка. Не сохраняй отформатированный текст как идентификатор услуги, сумму или дату. Parametrized message позволяет переводчику менять порядок слов; escaped values не должны экранироваться повторно другим слоем без проверки.

Для Bot API entities учитывай offsets по его контракту, если меняешь текст и вставки. HTML/Markdown escaping выбирается по конкретному parse mode, а не универсальным regex. В Web UI обычные text nodes предпочтительны для пользовательских вставок.

После смены языка и RTL проверь длинную кнопку, label/error, карточку, даты/цены и навигацию. Не обрезай единственное действие многоточием ради прохождения overflow test. Native UI и сообщения бота могут иметь свой набор доступных локализуемых настроек; проверяй конкретный API.

Источники: [Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat), [Intl.PluralRules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules), [Telegram formatting](https://core.telegram.org/bots/api#formatting-options).
