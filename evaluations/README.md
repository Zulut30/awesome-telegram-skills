# Оценки скиллов

Здесь лежат наборы запросов и отчеты, которые проверяют поведение агента на настоящей модели, а не только формат файлов.

## Выбор reference в `telegram-code-patterns`

`telegram-code-patterns-routing.json` — 40 запросов с ожидаемыми references, `telegram-code-patterns-routing-holdout.json` — 12 запросов, написанных уже после настройки таблицы, чтобы проверить, что результат не подогнан под первый набор. Скрипт показывает агенту `SKILL.md` и запрос, отключает инструменты и сравнивает первый названный файл с ожидаемыми:

```bash
python3 scripts/eval_reference_routing.py --skill .agents/skills/telegram-code-patterns/SKILL.md --cases evaluations/telegram-code-patterns-routing.json --model haiku --output output/routing-haiku.json
```

Нужен Claude Code CLI (`claude`) с вашим входом; запросы расходуют лимит аккаунта. Порог — 90% правильных выборов. Повторяйте оценку при каждом изменении таблицы «намерение → reference».

Отчет 2026-10-07 (`reports/telegram-code-patterns-routing-2026-10-07.json`), Claude Code CLI 2.1.292:

| Версия `SKILL.md` | Слов | Основной набор, haiku / sonnet | Отложенный набор, haiku / sonnet |
| --- | --- | --- | --- |
| До пункта 35 | 1332 | 38/40 / 39/40 | 11/12 / 12/12 |
| После пункта 35 | 398 | 39/40 / 40/40 | 12/12 / 12/12 |

Слова считаются как в `wc -w` с UTF-8: все токены между пробелами, включая ссылки.

Промежуточная версия таблицы давала у sonnet 50%: он понимал «видишь скилл впервые» как условие открыть onboarding для любой задачи. Условие сужено до «неясно, что за пакет передан и какая версия установлена».

## Границы между похожими скиллами

`skill-boundaries.json` — 40 запросов на границах пар, которые легко спутать: bot-api и buttons, mini-app-ui, design-system и ux, testing, device-qa и visual-regression, payments, subscription-access и yookassa, project-planner и mini-app-architecture, mini-app-auth и web-login, debugging и observability, а также кнопки Mini App и клавиатуры бота, review и реализация initData, Business и пользовательский аккаунт. Поле `not` называет скилл, который выбирать нельзя. Агент видит только список `name: description`, как при старте сессии:

```bash
python3 scripts/eval_skill_selection.py --cases evaluations/skill-boundaries.json --model haiku
python3 scripts/eval_skill_selection.py --cases evaluations/skill-boundaries.json --ref <commit> --model haiku
```

Отчет 2026-10-07 (`reports/skill-boundaries-2026-10-07.json`): 40/40 у haiku и sonnet и с границами «Не для … → telegram-…», и с прежними описаниями. На этих запросах явные границы не изменили точность; они нужны, чтобы агент и человек видели, куда уходит соседняя задача, и проверяются `validate_skills.py`.

## Выбор скилла: полный набор

`skill-selection.json` — 245 запросов: 205 позитивных (по 5 на каждый из 41 скилла; у 37 двусмысленных заранее записаны допустимые альтернативы) и 40 негативных из `skill-boundaries.json`. Порог — 95%.

```bash
python3 scripts/eval_skill_selection.py --cases evaluations/skill-selection.json --model haiku --workers 6 --output output/selection-haiku.json
python3 scripts/eval_skill_selection.py --cases evaluations/skill-selection.json --model sonnet --workers 6 --output output/selection-sonnet.json
```

Отчет `reports/skill-selection-latest.json` хранит отпечаток списка описаний (`descriptions_sha256`). Тест `tests/test_skill_selection_report.py` падает, как только меняется любое description: прогон нужно повторить и обновить отчет.

2026-10-07, Claude Code CLI 2.1.292: haiku 240/245 (98%), sonnet 240/245 (98%); негативные 40/40 у обеих моделей. Промахи — пограничные запросы вроде «сверка платежей провайдера раз в сутки» или «администратор вручную продлевает доступ». Второй агент (Codex, Gemini CLI, Copilot) в этой среде без входа недоступен, поэтому прогон выполнен на двух моделях одного агента.
