# Подключить библиотеку как ИИ-агент

Задача этой инструкции — выбрать готовый компонент, подтвердить его публичный API и встроить его в существующий проект. Скиллы и пакеты устанавливаются отдельно. Не считайте репозиторий установкой Python/npm-пакета.

## Сначала определите, что вам передали

| Вход | Как начать |
| --- | --- |
| Полный репозиторий | Прочитайте `AGENTS.md`, `components.json` и README подходящего пакета. Канонические скиллы находятся в `.agents/skills/` |
| Каталог одного скилла | Прочитайте его `SKILL.md` и только нужные локальные references. Соседние скиллы не обязательны |
| Python wheel / npm tarball | Установите предоставленный файл в окружение проекта. Проверьте фактическую версию и exports; библиотека не опубликована в PyPI/npm |
| Только сайт документации | Найдите нужный API и пример. Для импорта получите исходный пакет или архив; HTML-страница не устанавливает библиотеку |

```powershell
python -c "from importlib.metadata import version; print(version('awesome-telegram-patterns'))"
npm.cmd ls @awesome-telegram/patterns
```

Ошибка первой команды или отсутствие пакета во второй означает, что импорт еще не подтвержден. Сначала выберите предоставленный источник установки. Не устанавливайте пакет по одному имени из публичного реестра.

## Выберите минимальную точку входа

| Задача | Где искать |
| --- | --- |
| Найти готовый код | `telegram-code-patterns`, каталог компонентов и CLI recipes |
| Строки кнопок, цвета, reply-ввод | `telegram-buttons`; `ActionButton`, `action_menu`, `KeyboardLayout`, `inline_layout`, `reply_layout` |
| Добавить поведение Python-бота | `telegram-bot-python`; подключите Router к текущему Dispatcher |
| Многошаговый ввод | `telegram-dialogs`; формы и storage-контракты текущего проекта |
| Mini App и серверная авторизация | `telegram-mini-app-architecture`, `telegram-mini-app-auth`; TypeScript bridge и backend-проверка `initData` |
| Другой SDK или готовый React/PostgreSQL-проект | Сохраните стек. Подключите только совместимый core/адаптер; aiogram и DOM shell не требуют миграции проекта |
| Чтение чатов пользовательского аккаунта | Отдельная задача `telegram-user-client` / MTProto, а не обычный Bot API |

## Найдите рецепт и проверьте его требования

После локальной установки Python-пакета команды работают из среды целевого проекта:

```powershell
python -m telegram_patterns recipes "две кнопки" --task keyboards --sdk aiogram --context private
python -m telegram_patterns recipes --show two-columns
python -m telegram_patterns run-recipe two-columns
python -m telegram_patterns run-recipe two-columns --offline
```

`recipes` ищет и показывает код. `run-recipe` без `--offline` выводит план: зависимости, данные, контекст и ограничения. `--offline` выполняет закрытую synthetic fixture, если она поставляется для этого рецепта. Не исполняйте произвольный `recipe.code` через `exec` и не подставляйте реальные credentials в sample-запросы.

Для конкретного символа используйте [справочник API](api-reference.md): индекс содержит полный import, вид runtime/type, пример и ограничения. `ref.*` — примеры справочника, а не IDs cookbook-команды `run-recipe`.

## Подтвердите установку и интеграцию

Python из checkout библиотеки, в отдельное окружение целевого проекта:

```powershell
python -m pip install "./packages/python[aiogram]"
python -c "from telegram_patterns.aiogram import ActionButton, action_menu; print(action_menu([ActionButton('Открыть', 'open')], columns=2).model_dump(exclude_none=True))"
```

Путь относится к checkout библиотеки: при запуске из другого проекта укажите его фактический абсолютный путь или предоставленный wheel. Для core без Bot SDK достаточно `./packages/python`. Для TypeScript из каталога целевого проекта:

```powershell
npm.cmd install "C:/path/to/awesome-telegram-patterns-0.24.0.tgz"
npm.cmd ls @awesome-telegram/patterns
```

```typescript
import { TelegramBridge, type BridgeSnapshot } from '@awesome-telegram/patterns';
import '@awesome-telegram/patterns/styles.css';
```

Замените путь на предоставленный архив и сверьте версию с документацией. Runtime и type exports различаются; CSS подключается отдельным export в frontend с bundler. Подробные команды: [первый запуск](quickstart.md) и [контракт поставки](distribution-contract.md).

Сначала выполните пример на synthetic данных, затем добавьте бизнес-логику проекта. Сохраняйте текущие Bot/session, Dispatcher/router, storage, frontend-фреймворк и способ сборки. Не закрывайте ресурсы, которыми владеет host-приложение.

## Проверьте смысл, а не только импорт

Кнопка строит разметку; callback handler проверяет автора, объект и текущие права. ACK не подтверждает бизнес-успех. `validate_init_data` проверяет подпись/freshness, но не ACL. `SQLiteOnce` покрывает эффект только на переданном SQLite connection. Потерянный ответ записи сохраняет прежний operation ID и требует сверки; новый ID не является безопасным retry.

Для бота проверьте основной путь и относящийся к нему отказ: чужой callback, устаревший шаг, повтор или неизвестный результат. Для Mini App — узкий/широкий viewport, обе темы, ввод, отмену запроса и восстановление формы. Browser-проверка не подтверждает физические устройства Telegram или live-платеж.

`maturity` и `verification` — разные свойства. `sdk`/`mock`/`browser` — способы проверки, а не обещание готовности к production. Для version-specific поведения сверяйте официальный Telegram/SDK источник из соответствующего reference.

В результате укажите выбранный API, подтвержденную версию, измененные файлы, выполненные проверки и оставшиеся обязанности приложения. Если нужного API в установленной версии нет, покажите этот факт и предложите совместимую композицию; не придумывайте export.

[Проверка этого пути подключения](internal/agent-onboarding-check.md) содержит выполненные сценарии и границы evidence.
