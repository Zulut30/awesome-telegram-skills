# Тексты компонентов: русский, английский и своя формулировка

Все фразы, которые компоненты библиотеки показывают пользователю бота, берутся из каталога `telegram_patterns.Texts`. Это шаги и ошибки форм, кнопки «Отправить» и «Назад», ответы навигации и составного выбора, названия месяцев, сообщения об ошибках для пользователя. Встроены два языка: `ru` (по умолчанию, те же строки, что и раньше) и `en`. Любую строку можно заменить своей.

```python
from telegram_patterns import Texts, default_texts
from telegram_patterns.aiogram import text_form_router

texts = Texts('en', {'form.submit': 'Send application'})  # один объект на язык, создается при запуске
router = text_form_router(fields, on_submit, texts=texts)
print(sorted(default_texts('en')))  # все ключи каталога
```

`texts('form.step', number=1, total=3, prompt='Your name?')` возвращает одну строку. Значения вставляются как обычный текст: фигурные скобки в имени пользователя не разбираются как шаблон.

## Правила замены

- Ключ должен существовать в каталоге. Опечатка (`form.sbmit`) вызывает `ValidationFailure` при создании `Texts`, а не в чате пользователя.
- Замена сохраняет плейсхолдеры исходной фразы. `form.step` обязан содержать `{number}`, `{total}` и `{prompt}`, иначе пользователь потеряет номер шага. Литеральные скобки пишутся как `{{` и `}}`.
- Пустая строка и строка длиннее 1024 символов отклоняются. Ограничения Telegram проверяет сам компонент: подпись кнопки навигации длиннее 64 символов будет отклонена при создании меню.
- `with_overrides({...})` возвращает копию с дополнительными заменами; исходный объект неизменяем.

## Где передать `texts`

| Компонент | Параметр | Ключи |
| --- | --- | --- |
| `text_form_router`, `dialog_form_router` | `texts=` | `form.*`, `dialog.*`, `field.*` |
| `InvalidField` встроенных полей | `error.text(texts)` | `field.*`; `str(error)` — русский текст |
| `MessageNavigation` | `texts=`; `back_text`/`refresh_text` имеют приоритет | `navigation.*` |
| `SelectionSpec` (меню, `selection_markup`, `selection_keyboard`) | `texts=` в спецификации; `selection_router(texts=)` для ответов до поиска меню | `selection.*` |
| `CalendarMonth.text`, `calendar_keyboard` | `texts=` | `calendar.*` |
| `paginated_menu`, `paginated_markup` | `texts=` | `page.previous`, `page.next` |
| `callback_router` | `texts=` | `action.stale` |
| `safe_error_report`, `PatternError.report` | `texts=` | `error.<code>` |
| `RichMessageBuilder` | `texts=` | `rich.document` |

У `SelectionSpec` фильтр «все» и текст подтверждения по умолчанию берутся из `texts`. Явно переданные `filters` и `confirm_text` проверяются как раньше: пустой словарь или пустая строка — ошибка.

## Язык пользователя

Язык выбирает проект. В [User](https://core.telegram.org/bots/api#user) поле `language_code` необязательно и содержит тег IETF (`en`, `en-US`, `pt-br`). Библиотека не определяет язык сама. Для бота на двух языках создайте два объекта при запуске и выбирайте по сохраненной настройке пользователя или по `language_code`:

```python
TEXTS = {'ru': Texts('ru'), 'en': Texts('en')}
texts = TEXTS['en' if (user.language_code or '').startswith('en') else 'ru']
```

Роутеры форм создаются один раз и говорят на одном языке. Для двух языков зарегистрируйте две формы с разными `name` и `command` (например, `/apply` и `/apply_en`) либо выберите язык при развертывании. Меню навигации и выбора создаются на сессию, поэтому язык можно выбрать для каждого пользователя.

## Что не входит в каталог

Сообщения CLI (`telegram-patterns recipes`, `init`, `doctor`), диагностики и шаблонов нового проекта адресованы разработчику и остаются русскими. Подписи, которые передает приложение (поля формы, экраны, варианты выбора, текст `on_submit`), остаются его ответственностью. Тест `test_handlers_hold_no_user_phrases` обходит AST модулей библиотеки и не пропускает кириллические строки вне каталога и инструментов разработчика.
