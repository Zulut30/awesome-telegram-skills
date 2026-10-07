"""User-facing component texts: Russian and English catalogs, and any string replaceable by the application.

Components take `texts=Texts(...)` (selection takes it through `SelectionSpec.texts`) and render every word a
user sees through it. Without it they use `Texts()`: the Russian catalog, the same strings as before. An override
must keep the placeholders of the text it replaces, so a translation cannot drop a step number or a command.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias

from .errors import InvalidType, ValidationFailure

__all__ = ['TextLocale', 'Texts', 'default_texts']

TextLocale: TypeAlias = Literal['ru', 'en']

_RU: dict[str, str] = {
    # Text forms (forms) and mixed dialogs (dialog_forms).
    'form.invalid_value': 'Проверьте значение и попробуйте ещё раз.',
    'form.length': 'Введите от 1 до {maximum} символов.',
    'form.submit_started': 'Отправка уже началась. Нажмите «Отправить» в последней форме, чтобы проверить результат.',
    'form.stale_button': 'Кнопка устарела. Откройте актуальную форму командой /{command}.',
    'form.expired': 'Срок черновика истёк. Начать заново: /{command}.',
    'form.step': 'Шаг {number}/{total}. {prompt}\n/back — назад · /cancel — отмена',
    'form.review': 'Проверьте ответы:\n{answers}\n/back — исправить · /cancel — отмена',
    'form.submit': 'Отправить',
    'form.cancelled': 'Форма отменена. Начать заново: /{command}.',
    'form.unconfirmed': (
        'Результат отправки пока не подтверждён. Нажмите «Отправить» ещё раз для проверки той же заявки.'
    ),
    'dialog.stale_action': 'Действие устарело. Откройте текущий вопрос командой /{command}.',
    'dialog.confirm': 'Подтвердить',
    'dialog.keyboard_closed': 'Клавиатура ввода закрыта.',
    'dialog.share_contact': 'Поделиться контактом',
    'dialog.share_location': 'Поделиться геопозицией',
    'dialog.reply_to_question': 'Ответьте на текущий вопрос бота.',
    'dialog.confirm_value': '{label}: {value}\nПодтвердите значение для текущего вопроса.',
    # Dialog fields (dialog_fields).
    'field.invalid_text': 'Введите значение без управляющих символов в указанном формате.',
    'field.corrupted': 'Данные поля повреждены. Повторите ввод.',
    'field.number_format': 'Введите число без экспоненты; разделитель — точка или запятая.',
    'field.decimal_places': 'Допустимо до {places} знаков после разделителя.',
    'field.number_range': 'Число вне разрешенного диапазона.',
    'field.email_format': 'Введите email в формате name@example.com.',
    'field.email_invalid': 'Введите email без пробелов, с корректным именем и доменом.',
    'field.phone_format': 'Укажите международный номер с + и кодом страны.',
    'field.phone_digits': 'Укажите от 7 до 15 цифр, начиная с кода страны.',
    'field.date_format': 'Введите существующую дату в формате ГГГГ-ММ-ДД.',
    'field.date_range': 'Дата вне разрешенного диапазона.',
    'field.file_size': 'Размер файла неизвестен или превышает разрешенный лимит.',
    'field.file_type': 'Этот тип файла не разрешен.',
    'field.file_single': 'Отправьте один документ ответом на текущий вопрос.',
    'field.file_display': '{name} ({size} байт)',
    'field.file_unnamed': 'Документ',
    'field.contact_user_id': 'Контакт имеет некорректный user_id.',
    'field.contact_own': 'Поделитесь своим контактом через кнопку.',
    'field.contact_not_forwarded': 'Отправьте контакт без пересылки.',
    'field.location_range': 'Координаты вне разрешенного диапазона.',
    'field.location_accuracy': 'Некорректная точность геопозиции.',
    'field.location_static': 'Отправьте обычную статичную геопозицию без пересылки.',
    # Message navigation (navigation).
    'navigation.back': 'Назад',
    'navigation.refresh': 'Обновить',
    'navigation.foreign': 'Это меню другого пользователя.',
    'navigation.other_message': 'Это сообщение не относится к активному меню.',
    'navigation.stale': 'Кнопка устарела. Откройте меню командой /menu.',
    'navigation.recover': 'Экран требует восстановления. Откройте /menu.',
    'navigation.invalid': 'Некорректная кнопка. Откройте /menu.',
    'navigation.closed': 'Меню уже закрыто. Откройте /menu.',
    'navigation.no_previous': 'Предыдущего экрана нет.',
    'navigation.no_transition': 'Такого перехода на текущем экране нет.',
    'navigation.history_full': 'История заполнена. Вернитесь назад или откройте /menu.',
    'navigation.edit_rejected': 'Telegram отклонил редактирование. Откройте /menu.',
    'navigation.unavailable': 'Переход недоступен. Откройте новое меню.',
    'navigation.unconfirmed': 'Ответ не подтвержден. Откройте /menu для восстановления.',
    'navigation.updated': 'Экран обновлен.',
    # Composite selection (selection, selection_aiogram).
    'selection.filter_all': 'Все',
    'selection.confirm': 'Подтвердить действие',
    'selection.nothing': 'ничего',
    'selection.yes': 'да',
    'selection.no': 'нет',
    'selection.choose': 'Выберите варианты.',
    'selection.check': 'Проверьте выбор: {action}.',
    'selection.confirmed': 'Выбор подтвержден.',
    'selection.cancelled': 'Выбор отменен.',
    'selection.selected': 'Выбрано: {items}',
    'selection.quantity': 'Количество: {quantity}',
    'selection.filter': 'Фильтр: {filter}',
    'selection.foreign': 'Это выбор другого пользователя.',
    'selection.other_context': 'Кнопка относится к другому сообщению или контексту.',
    'selection.stale': 'Кнопка устарела. Откройте актуальный выбор.',
    'selection.back_to_editing': 'Сначала вернитесь к редактированию выбора.',
    'selection.option_unavailable': 'Этот вариант сейчас недоступен.',
    'selection.limit_reached': 'Достигнуто допустимое число вариантов.',
    'selection.no_toggle': 'Такого переключателя нет.',
    'selection.no_filter': 'Такого фильтра нет.',
    'selection.quantity_range': 'Количество вне допустимого диапазона.',
    'selection.need_more': 'Выберите необходимое число вариантов.',
    'selection.confirmation_expired': 'Подтверждение истекло или относится к другому выбору.',
    'selection.confirmation_closed': 'Подтверждение еще не открыто.',
    'selection.updated': 'Выбор обновлен.',
    'selection.review': 'Проверьте выбор перед подтверждением.',
    'selection.confirm_button': 'Да: {action}',
    'selection.change': 'Изменить выбор',
    'selection.cancel': 'Отмена',
    'selection.unsupported_message': 'Это сообщение не поддерживает такой выбор.',
    'selection.closed': 'Выбор уже закрыт.',
    # Calendar (calendar_core, calendar_aiogram).
    'calendar.month_1': 'Январь',
    'calendar.month_2': 'Февраль',
    'calendar.month_3': 'Март',
    'calendar.month_4': 'Апрель',
    'calendar.month_5': 'Май',
    'calendar.month_6': 'Июнь',
    'calendar.month_7': 'Июль',
    'calendar.month_8': 'Август',
    'calendar.month_9': 'Сентябрь',
    'calendar.month_10': 'Октябрь',
    'calendar.month_11': 'Ноябрь',
    'calendar.month_12': 'Декабрь',
    'calendar.weekday_1': 'Пн',
    'calendar.weekday_2': 'Вт',
    'calendar.weekday_3': 'Ср',
    'calendar.weekday_4': 'Чт',
    'calendar.weekday_5': 'Пт',
    'calendar.weekday_6': 'Сб',
    'calendar.weekday_7': 'Вс',
    'calendar.legend': '· — недоступно. Дату выбирайте кнопкой ниже.',
    'calendar.no_dates': 'Нет доступных дат.',
    'calendar.previous_month': 'Предыдущий месяц',
    'calendar.next_month': 'Следующий месяц',
    # Paginated menus (keyboards, markup), action buttons (aiogram.callback_router), rich message fallback.
    'page.previous': '← Назад',
    'page.next': 'Далее →',
    'action.stale': 'Кнопка недействительна. Откройте актуальное меню.',
    'rich.document': 'Документ',
    # Public error reports (errors.safe_error_report).
    'error.validation-failed': 'Проверьте входные данные.',
    'error.invalid-init-data': 'Откройте приложение заново для входа.',
    'error.invalid-api-request': 'Проверьте параметры запроса.',
    'error.invalid-field': 'Проверьте значение поля.',
    'error.authentication-required': 'Требуется вход в приложение.',
    'error.permission-denied': 'Недостаточно прав для действия.',
    'error.unsupported-capability': 'Функция недоступна в текущем окружении.',
    'error.timeout': 'Ответ не получен вовремя.',
    'error.network': 'Не удалось получить ответ.',
    'error.operation-conflict': 'Проверьте состояние существующей операции.',
    'error.cancelled': 'Ожидание ответа отменено.',
    'error.internal': 'Не удалось обработать действие.',
    'error.unknown-outcome': 'Результат операции пока не подтвержден.',
    'error.invalid-response': 'Получен неподдерживаемый ответ сервера.',
    'error.rate-limited': 'Слишком много запросов. Повторите позже.',
    'error.server-error': 'Сервер временно не смог обработать запрос.',
    'error.unknown-outcome-write': 'Результат операции пока не подтвержден. Проверьте ее статус.',
}

_EN: dict[str, str] = {
    'form.invalid_value': 'Check the value and try again.',
    'form.length': 'Enter 1 to {maximum} characters.',
    'form.submit_started': 'Submission has already started. Press “Submit” in the latest form to check the result.',
    'form.stale_button': 'This button is outdated. Open the current form with /{command}.',
    'form.expired': 'The draft has expired. Start again: /{command}.',
    'form.step': 'Step {number}/{total}. {prompt}\n/back — go back · /cancel — cancel',
    'form.review': 'Check your answers:\n{answers}\n/back — edit · /cancel — cancel',
    'form.submit': 'Submit',
    'form.cancelled': 'The form is cancelled. Start again: /{command}.',
    'form.unconfirmed': 'The submission result is not confirmed yet. Press “Submit” again to check the same request.',
    'dialog.stale_action': 'This action is outdated. Open the current question with /{command}.',
    'dialog.confirm': 'Confirm',
    'dialog.keyboard_closed': 'The input keyboard is closed.',
    'dialog.share_contact': 'Share contact',
    'dialog.share_location': 'Share location',
    'dialog.reply_to_question': 'Reply to the bot’s current question.',
    'dialog.confirm_value': '{label}: {value}\nConfirm the value for the current question.',
    'field.invalid_text': 'Enter a value without control characters in the requested format.',
    'field.corrupted': 'The field data is corrupted. Enter it again.',
    'field.number_format': 'Enter a number without an exponent; use a dot or a comma as the separator.',
    'field.decimal_places': 'Up to {places} digits are allowed after the separator.',
    'field.number_range': 'The number is outside the allowed range.',
    'field.email_format': 'Enter an email like name@example.com.',
    'field.email_invalid': 'Enter an email without spaces, with a valid name and domain.',
    'field.phone_format': 'Enter an international number with + and the country code.',
    'field.phone_digits': 'Enter 7 to 15 digits starting with the country code.',
    'field.date_format': 'Enter an existing date as YYYY-MM-DD.',
    'field.date_range': 'The date is outside the allowed range.',
    'field.file_size': 'The file size is unknown or exceeds the allowed limit.',
    'field.file_type': 'This file type is not allowed.',
    'field.file_single': 'Send one document in reply to the current question.',
    'field.file_display': '{name} ({size} bytes)',
    'field.file_unnamed': 'Document',
    'field.contact_user_id': 'The contact has an invalid user_id.',
    'field.contact_own': 'Share your own contact with the button.',
    'field.contact_not_forwarded': 'Send the contact without forwarding it.',
    'field.location_range': 'The coordinates are outside the allowed range.',
    'field.location_accuracy': 'The location accuracy is invalid.',
    'field.location_static': 'Send a regular static location without forwarding it.',
    'navigation.back': 'Back',
    'navigation.refresh': 'Refresh',
    'navigation.foreign': 'This menu belongs to another user.',
    'navigation.other_message': 'This message is not part of the active menu.',
    'navigation.stale': 'This button is outdated. Open the menu with /menu.',
    'navigation.recover': 'The screen needs recovery. Open /menu.',
    'navigation.invalid': 'Invalid button. Open /menu.',
    'navigation.closed': 'The menu is already closed. Open /menu.',
    'navigation.no_previous': 'There is no previous screen.',
    'navigation.no_transition': 'This screen has no such transition.',
    'navigation.history_full': 'The history is full. Go back or open /menu.',
    'navigation.edit_rejected': 'Telegram rejected the edit. Open /menu.',
    'navigation.unavailable': 'This transition is unavailable. Open a new menu.',
    'navigation.unconfirmed': 'The response is not confirmed. Open /menu to recover.',
    'navigation.updated': 'The screen is updated.',
    'selection.filter_all': 'All',
    'selection.confirm': 'Confirm action',
    'selection.nothing': 'nothing',
    'selection.yes': 'yes',
    'selection.no': 'no',
    'selection.choose': 'Choose options.',
    'selection.check': 'Check your choice: {action}.',
    'selection.confirmed': 'The choice is confirmed.',
    'selection.cancelled': 'The choice is cancelled.',
    'selection.selected': 'Selected: {items}',
    'selection.quantity': 'Quantity: {quantity}',
    'selection.filter': 'Filter: {filter}',
    'selection.foreign': 'This choice belongs to another user.',
    'selection.other_context': 'This button belongs to another message or context.',
    'selection.stale': 'This button is outdated. Open the current choice.',
    'selection.back_to_editing': 'Return to editing the choice first.',
    'selection.option_unavailable': 'This option is unavailable right now.',
    'selection.limit_reached': 'The maximum number of options is selected.',
    'selection.no_toggle': 'There is no such switch.',
    'selection.no_filter': 'There is no such filter.',
    'selection.quantity_range': 'The quantity is outside the allowed range.',
    'selection.need_more': 'Choose the required number of options.',
    'selection.confirmation_expired': 'The confirmation has expired or belongs to another choice.',
    'selection.confirmation_closed': 'The confirmation is not open yet.',
    'selection.updated': 'The choice is updated.',
    'selection.review': 'Check your choice before confirming.',
    'selection.confirm_button': 'Yes: {action}',
    'selection.change': 'Change choice',
    'selection.cancel': 'Cancel',
    'selection.unsupported_message': 'This message does not support this choice.',
    'selection.closed': 'The choice is already closed.',
    'calendar.month_1': 'January',
    'calendar.month_2': 'February',
    'calendar.month_3': 'March',
    'calendar.month_4': 'April',
    'calendar.month_5': 'May',
    'calendar.month_6': 'June',
    'calendar.month_7': 'July',
    'calendar.month_8': 'August',
    'calendar.month_9': 'September',
    'calendar.month_10': 'October',
    'calendar.month_11': 'November',
    'calendar.month_12': 'December',
    'calendar.weekday_1': 'Mo',
    'calendar.weekday_2': 'Tu',
    'calendar.weekday_3': 'We',
    'calendar.weekday_4': 'Th',
    'calendar.weekday_5': 'Fr',
    'calendar.weekday_6': 'Sa',
    'calendar.weekday_7': 'Su',
    'calendar.legend': '· — unavailable. Pick a date with the buttons below.',
    'calendar.no_dates': 'No dates are available.',
    'calendar.previous_month': 'Previous month',
    'calendar.next_month': 'Next month',
    'page.previous': '← Back',
    'page.next': 'Next →',
    'action.stale': 'This button is no longer valid. Open the current menu.',
    'rich.document': 'Document',
    'error.validation-failed': 'Check the input data.',
    'error.invalid-init-data': 'Open the app again to sign in.',
    'error.invalid-api-request': 'Check the request parameters.',
    'error.invalid-field': 'Check the field value.',
    'error.authentication-required': 'Sign in to the app first.',
    'error.permission-denied': 'You do not have permission for this action.',
    'error.unsupported-capability': 'This feature is unavailable in the current environment.',
    'error.timeout': 'No response arrived in time.',
    'error.network': 'Could not get a response.',
    'error.operation-conflict': 'Check the state of the existing operation.',
    'error.cancelled': 'Waiting for the response was cancelled.',
    'error.internal': 'Could not process the action.',
    'error.unknown-outcome': 'The operation result is not confirmed yet.',
    'error.invalid-response': 'Received an unsupported server response.',
    'error.rate-limited': 'Too many requests. Try again later.',
    'error.server-error': 'The server could not process the request right now.',
    'error.unknown-outcome-write': 'The operation result is not confirmed yet. Check its status.',
}

_CATALOGS: dict[str, Mapping[str, str]] = {'ru': MappingProxyType(_RU), 'en': MappingProxyType(_EN)}
_MAX_OVERRIDE = 1024


def _placeholders(template: str) -> frozenset[str]:
    try:
        return frozenset(name for _, name, _, _ in string.Formatter().parse(template) if name is not None)
    except ValueError:
        raise ValidationFailure('Text has unbalanced braces; write literal braces as {{ and }}') from None


def default_texts(locale: TextLocale = 'ru') -> Mapping[str, str]:
    """The built-in catalog of a locale: key -> template with {placeholders}. Read-only."""
    if locale not in _CATALOGS:
        raise ValidationFailure('Use locale ru or en')
    return _CATALOGS[locale]


@dataclass(frozen=True, slots=True)
class Texts:
    """Locale catalog plus overrides; texts(key, **values) renders one string.

    Unknown keys, empty values and overrides that change the placeholder set are rejected at construction,
    so a typo fails at startup rather than in a user's chat. Values are inserted as plain text.
    """

    locale: TextLocale = 'ru'
    overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        catalog = default_texts(self.locale)
        if not isinstance(self.overrides, Mapping):
            raise InvalidType('Use a mapping of text key to replacement')
        checked: dict[str, str] = {}
        for key, value in self.overrides.items():
            if not isinstance(key, str) or key not in catalog:
                raise ValidationFailure(f'Unknown text key {str(key)[:64]!r}; see default_texts()')
            if not isinstance(value, str) or not value.strip() or len(value) > _MAX_OVERRIDE:
                raise ValidationFailure(f'Text {key} must be nonempty and at most {_MAX_OVERRIDE} characters')
            expected = _placeholders(catalog[key])
            if _placeholders(value) != expected:
                names = ', '.join('{' + name + '}' for name in sorted(expected)) or 'no placeholders'
                raise ValidationFailure(f'Text {key} must use exactly {names}')
            checked[key] = value
        object.__setattr__(self, 'overrides', MappingProxyType(checked))

    def __call__(self, key: str, /, **values: object) -> str:
        catalog = default_texts(self.locale)
        if key not in catalog:
            raise ValidationFailure(f'Unknown text key {str(key)[:64]!r}; see default_texts()')
        try:
            return (self.overrides.get(key) or catalog[key]).format_map(values)
        except KeyError as missing:
            raise ValidationFailure(f'Text {key} needs the value {missing}') from None

    def with_overrides(self, overrides: Mapping[str, str]) -> Texts:
        """A copy with more overrides; later values win."""
        if not isinstance(overrides, Mapping):
            raise InvalidType('Use a mapping of text key to replacement')
        return Texts(self.locale, {**self.overrides, **overrides})

    def month(self, number: int) -> str:
        """Month name for 1..12."""
        if type(number) is not int or not 1 <= number <= 12:
            raise ValidationFailure('Use month 1..12')
        return self(f'calendar.month_{number}')

    def weekdays(self) -> tuple[str, ...]:
        """Short weekday names, Monday first."""
        return tuple(self(f'calendar.weekday_{number}') for number in range(1, 8))
