"""SDK-free component texts: English catalog, one replaced phrase, a localized selection and error report; no network."""
import json
from telegram_patterns import (SelectionContext, SelectionMenu, SelectionOption, SelectionSpec, TextLocale, Texts,
                               ValidationFailure, default_texts, safe_error_report, selection_markup)

locale: TextLocale = 'en'  # the project picks the language; nothing is guessed from language_code
texts = Texts(locale, {'selection.cancel': 'Never mind'})  # one Texts per user language, built once at startup
assert texts('form.step', number=1, total=3, prompt='Your name?') == 'Step 1/3. Your name?\n/back — go back · /cancel — cancel'
assert set(default_texts('ru')) == set(default_texts('en'))  # every key exists in both locales
try:
    Texts('en', {'form.step': 'Next question'})  # drops {number}, {total} and {prompt}
except ValidationFailure:
    pass  # a broken translation fails at startup, not in a user's chat
else:
    raise AssertionError('Override without placeholders accepted')
menu = SelectionMenu(SelectionSpec([SelectionOption('tea', 'Tea')], texts=texts), SelectionContext(100, 7, 7, 1))
assert menu.state.text() == 'Choose options.\nSelected: nothing\nQuantity: 1\nFilter: All'
assert selection_markup(menu.state)['inline_keyboard'][-1][-1]['text'] == 'Never mind'
assert safe_error_report(ValidationFailure('detail'), texts=texts).message == 'Check the input data.'
# aiogram routers take the same object: text_form_router(..., texts=texts), dialog_form_router(..., texts=texts).
print(json.dumps({'case': 'core_texts', 'passed': True, 'network': False}))
