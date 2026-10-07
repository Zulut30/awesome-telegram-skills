# Locale, время и сообщения

Термины: **fallback** — запасной вариант, если основная возможность недоступна.

## Выбор

Опишите приоритет явного предпочтения, сохраненной настройки, language_code и default locale. Ограничьте выбор поддерживаемыми locale; malformed/неизвестный код приводит к fallback, а не падению formatter. При необходимости подбирайте базовый язык из regional locale, сохраняя явный выбор пользователя.

Предпочтение синхронизируется по контракту backend, если нужно общее значение для бота и Mini App. Отсутствие language_code не означает конкретный язык; доверенный язык профиля не является авторизацией или геолокацией.

## Форматирование

Для TypeScript используйте установленную i18n библиотеку/Intl; для Python — существующий formatter, gettext/Babel по стеку. В plural messages есть необходимая ветка fallback/other. Покройте значимые категории выбранного языка: для русского, например, 1/2/5/11/21 и ноль. Decimal counts требуют своих правил.

Backend передает канонические значения и семантику: instant с timezone/offset, локальный день услуги либо сумма в точных units/decimal и currency. Frontend не пытается угадать тип по произвольной строке. Formatting не пересчитывает валюту и не округляет сумму иначе, чем контракт оплаты.

Язык не определяет timezone. Для записи укажите timezone услуги и то, какой день видит пользователь; не парсите date-only как UTC instant с последующим неявным переносом дня. Повторяемое локальное время требует политики ambiguous/nonexistent DST; при неоднозначности запрашивайте выбор или отклоняйте ввод по контракту.

## Строки и безопасные вставки

Стабильные translation keys/error codes не меняются от языка. Не сохраняйте отформатированный текст как идентификатор услуги, сумму или дату. Parametrized message позволяет переводчику менять порядок слов; escaped values не должны экранироваться повторно другим слоем без проверки.

Для Bot API entities учитывайте offsets по его контракту, если меняете текст и вставки. HTML/Markdown escaping выбирается по конкретному parse mode, а не универсальным regex. В Web UI обычные text nodes предпочтительны для пользовательских вставок.

После смены языка и RTL проверьте длинную кнопку, label/error, карточку, даты/цены и навигацию. Не обрезайте единственное действие многоточием ради прохождения overflow test. Native UI и сообщения бота могут иметь свой набор доступных локализуемых настроек; проверяйте конкретный API.

Источники: [Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat), [Intl.PluralRules](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules), [Telegram formatting](https://core.telegram.org/bots/api#formatting-options).
