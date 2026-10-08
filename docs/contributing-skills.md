# Добавить свой скилл или компонент

Эта страница ведет от идеи до pull request без помощи мейнтейнера. Общие правила — в [CONTRIBUTING.md](../CONTRIBUTING.md), формат сообщения коммита — там же.

## Скилл

Скилл — каталог `.agents/skills/telegram-<имя>/` с `SKILL.md` (инструкции агенту на русском, идентификаторы на английском), `agents/openai.yaml` (подпись для каталога) и при необходимости `references/` (длинные справки) и `scripts/`. Скилл самостоятелен: после копирования одного каталога все его ссылки работают, соседние скиллы не обязательны.

### 1. Каркас

```bash
python scripts/new_skill.py telegram-example --title "Пример" --short "Короткое описание для каталога" --not-for telegram-bot-api --next-steps
```

Команда создает `SKILL.md` по общему шаблону — разделы «Когда использовать», «Когда не использовать», «Алгоритм», «Проверка», «Типичные ошибки» (не меньше трех пунктов), «Источники» со строкой `Проверено: ГГГГ-ММ-ДД, …` — и `agents/openai.yaml` с текущей версией библиотеки. Каждое место для вашего текста помечено `[TODO: …]`: пока они есть, `validate_skills.py` сообщает «unfinished scaffold». `--not-for` — соседний скилл, куда описание отправляет агента, если задача не ваша: описание обязано сказать, когда скилл не применяется.

### 2. Текст скилла

- Описание (`description`) различимо по намерению пользователя: агент выбирает скилл только по имени и описанию.
- Алгоритм сохраняет стек проекта пользователя и не добавляет обязательных сервисов. Bot API не подменяется автоматизацией пользовательского аккаунта.
- Поведение, зависящее от версии, сверьте с официальной документацией и укажите источники с датой проверки.
- Термины из глоссария (неизвестный результат, ACK и другие) объясняются строкой «Термины:» — ее добавляет `python scripts/add_terms_lines.py`.

### 3. Регистрация

| Что | Где |
| --- | --- |
| Строка каталога | README.md, раздел «Скилл под вашу задачу», и такая же английская строка в README.en.md |
| Числа скиллов | README.md, README.en.md, `.claude-plugin/marketplace.json`: `python -m unittest tests.test_current_numbers tests.test_readme_status` называет каждое место |
| Источники | `python scripts/check_skill_sources.py --table docs/sources.md` пересобирает таблицу из разделов «Источники» скиллов; запись в журнал под таблицей добавьте сами |
| Оценки | три задачи с критериями в `evaluations/skill-value.json`, запросы на выбор в `evaluations/skill-selection.json` |

### 4. Оценки

Нужен Claude Code CLI (`claude`) с вашим входом; запросы расходуют лимит аккаунта. Порядок и пороги — в [evaluations/README.md](../evaluations/README.md).

```bash
python scripts/eval_skill_selection.py --cases evaluations/skill-selection.json --model haiku --output evaluations/reports/skill-selection-latest.json
python scripts/eval_skill_value.py --skill telegram-example --report evaluations/reports/skill-value-latest.json
python scripts/eval_skill_value.py --table evaluations/reports/skill-value-latest.json
```

Последняя команда печатает таблицу для `evaluations/README.md`. Выбор скилла должен оставаться не ниже 95%, а скилл — давать заметный прирост на своих задачах.

### 5. Проверка

```bash
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests
```

### Чек-лист pull request со скиллом

- [ ] Каркас заполнен, `[TODO: …]` не осталось, `validate_skills.py` проходит.
- [ ] Описание говорит, когда скилл применять и когда нет (`Не для … → telegram-…`).
- [ ] Источники со ссылками и датой; таблица `docs/sources.md` пересобрана, запись в журнале добавлена.
- [ ] Строки каталога в README.md и README.en.md, числа скиллов обновлены.
- [ ] Задачи и запросы оценки добавлены, отчеты пересчитаны.
- [ ] Корневые тесты проходят; сообщение коммита по шаблону `.gitmessage`.

Пример: коммит [excellence(040)](https://github.com/Zulut30/awesome-telegram-skills/commit/8140c0b02c47476055eb4e88d3db45794ce0782b) добавил `telegram-ai-bot` — скилл, справку в `references/`, строки каталога, источники, задачи оценки и отчеты (рецепт и пример в том же коммите необязательны для нового скилла).

## Компонент библиотеки

Компонент — публичный API в `packages/python` (Python, ботам) или `packages/typescript` (Mini Apps), описанный в `components.json`.

1. Код и тесты: модуль в `packages/python/src/telegram_patterns/` или `packages/typescript/src/`, тесты рядом с похожими в `packages/*/tests/`. Ядро Python не зависит от SDK; код для aiogram — в подпакете `telegram_patterns.aiogram`.
2. Экспорт: имя в `__all__` пакета или в `packages/typescript/src/index.ts`.
3. Каталог: запись в `components.json` (id, язык, точный import, назначение, границы, зрелость `experimental`), затем `python scripts/build_api_reference.py` и другие генераторы, которые требует задача CI `generated-files`.
4. Совместимость: `python scripts/check_api_compatibility.py --base auto` и строка в разделе «Не выпущено» CHANGELOG.
5. Полная проверка поставки: `npm ci`, затем `python scripts/verify_pattern_packages.py` (нужен Chrome или `CHROME_PATH`).

Пример: коммит [excellence(054)](https://github.com/Zulut30/awesome-telegram-skills/commit/9ca80057b5bc60251bd03250a08acf9f2d0db1e8) добавил rich-сообщения: компонент, экспорт, каталог, справочник, тесты и строку CHANGELOG.
