# У меня уже есть бот на aiogram

Цель за 10 минут: добавить в свой бот меню из двух кнопок и обработчик нажатий из библиотеки, не меняя Dispatcher, хранилище и структуру проекта. Нужны Python 3.11+ и aiogram 3.31 или новее в пределах 3.x.

## 1. Установите пакет в окружение бота

Из файла релиза (или `"./packages/python[aiogram]"` из клона репозитория):

```bash
pip install "awesome-telegram-patterns[aiogram] @ https://github.com/Zulut30/awesome-telegram-skills/releases/download/v0.24.0/awesome_telegram_patterns-0.24.0-py3-none-any.whl"
```

## 2. Подключите Router к своему Dispatcher и проверьте без сети

Сохраните как `menu_check.py` рядом с ботом и выполните `python menu_check.py`. Блок `offline_check` прогоняет нажатие кнопки через ваш Dispatcher с тестовым транспортом: токен и Telegram не нужны.

<!-- start:existing-bot -->
```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from telegram_patterns.aiogram import ActionButton, ActionResult, action_menu, callback_router
from telegram_patterns.testing import StubSession

dp = Dispatcher()  # в своем проекте используйте существующий Dispatcher

async def execute(action):  # здесь ваша бизнес-логика и проверка прав пользователя
    return ActionResult('accepted', f'Выбрано: {action.key}')

async def notify(query, result):
    await query.message.answer(result.text, parse_mode=None)

dp.include_router(callback_router(execute, notify))
menu = action_menu([ActionButton('Каталог', 'catalog'), ActionButton('Помощь', 'help')], columns=2)
# В обработчике команды: await message.answer('Выберите действие', reply_markup=menu)

async def offline_check():
    session = StubSession().respond(AnswerCallbackQuery, True).respond(
        SendMessage, {'message_id': 2, 'date': 1, 'chat': {'id': 42, 'type': 'private'}})
    bot = Bot('100:OFFLINE', session=session)
    user, chat = User(id=42, is_bot=False, first_name='Test'), Chat(id=42, type='private')
    pressed = CallbackQuery(id='1', from_user=user, chat_instance='offline', data=menu.inline_keyboard[0][0].callback_data,
                            message=Message(message_id=1, date=1, chat=chat, text='Выберите действие'))
    await dp.feed_update(bot, Update(update_id=1, callback_query=pressed))
    await bot.session.close()
    print([type(call).__name__ for call in session.calls], session.calls[-1].text)

if __name__ == '__main__':
    asyncio.run(offline_check())
```

Ожидаемый вывод: `['AnswerCallbackQuery', 'SendMessage'] Выбрано: catalog`. Затем используйте `menu` в своем обработчике и `dp` как раньше.

## Что дальше

- Скиллы для агента: `telegram-bot-python`, `telegram-buttons`, `telegram-code-patterns` — установка в проект описана в [странице для ИИ-агента](ai-agent.md).
- Формы, календарь, навигация по сообщениям: `python -m telegram_patterns recipes "форма"` и [справочник API](../api-reference.md).
- Права, повторы и неизвестный результат проверяет ваш `execute`: кнопка только строит разметку.
