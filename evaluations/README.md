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

## Польза скиллов: без скилла и со скиллом

`skill-value.json` — по три задачи на каждый из 41 скилла, 123 задачи и 435 критериев результата. Критерии взяты из правил самих скиллов и официальной документации: «проверяет подпись по сырому телу», «не выдает доступ до `successful_payment`», «отмечает недоступные устройства как not-run».

Решающая модель отвечает на каждую задачу дважды с одинаковыми инструментами `Read`, `Glob`, `Grep`: в пустом каталоге и в каталоге с копией скилла, который она читает сама, как агент в проекте. Ответ ограничен 500 словами в обоих случаях. Судья (sonnet) видит задачу, критерии и один ответ, не зная, из какого прогона он пришел, и отмечает каждый критерий. Задача пройдена, если выполнено не меньше 75% ее критериев.

```bash
python3 scripts/eval_skill_value.py --model haiku --workers 8 --output output/value-haiku.json --report evaluations/reports/skill-value-latest.json
python3 scripts/eval_skill_value.py --model sonnet --workers 8 --output output/value-sonnet.json --report evaluations/reports/skill-value-latest.json
python3 scripts/eval_skill_value.py --skill telegram-buttons --report evaluations/reports/skill-value-latest.json
python3 scripts/eval_skill_value.py --table evaluations/reports/skill-value-latest.json
```

`--output` сохраняет ответы целиком, а `--report` объединяет прогон с общим отчетом без текстов ответов: остаются вердикты и короткие обоснования судьи. С `--skill` заменяются результаты только указанных скиллов. Отчет хранит отпечаток каталога каждого скилла (`skills_sha256`), на котором получен результат. Тест `tests/test_skill_value.py` проверяет, что задачи покрывают все скиллы, отчет соответствует задачам и критериям, итоги пересчитываются из вердиктов, а таблица ниже совпадает с отчетом.

Отчет `reports/skill-value-latest.json`, 7 октября 2026 года, Claude Code CLI 2.1.292, судья sonnet:

- haiku: без скилла выполнено 91 из 435 критериев (21%), со скиллом — 256 (59%), прирост 38 процентных пунктов; пройдено задач: 2 → 47 из 123. Прирост есть у 39 из 41 скилла.
- sonnet: 236 из 435 (54%) → 390 (90%), прирост 35 пунктов; пройдено задач: 40 → 110. Прирост есть у 40 из 41 скилла.

Без скилла модели опираются на устаревшее или придуманное API. Для входа через Telegram на сайте обе модели описывают старый виджет с `hash` вместо текущего OIDC; неактивную кнопку не делает ни одна, хотя `DisabledButton` есть в Bot API 10.3; haiku задает цвет кнопки несуществующим полем `color` вместо `style`. Со скиллом модели находят нужный reference и следуют его правилам: проверяют подпись по сырому телу, не выдают доступ до `successful_payment`, отмечают недоступные устройства как not-run.

Что нужно улучшить:

- `telegram-dialogs`: задачи не различают условия — sonnet выполняет 10 из 10 критериев и без скилла, haiku — 6 из 10 в обоих случаях. Нужны задачи труднее.
- `telegram-mini-app-integration` (+9% у обеих моделей), `telegram-mini-app-ux` и `telegram-user-client` у haiku (+11% и +10%): даже со скиллом модель пропускает его ключевые правила — канал по способу запуска, итог до оплаты, разрыв между историей и live updates. Это кандидаты для пункта 48.
- Со скиллом sonnet выполняет меньше 75% критериев только у `telegram-cryptopay` и `telegram-mini-app-ux`.

В таблице прирост — разница долей выполненных критериев в процентных пунктах, «задач» — сколько задач скилла оценено.

Ограничения. На каждую задачу и условие получен один ответ, поэтому отдельная ячейка таблицы колеблется на 1–2 критерия; надежнее итоги и сравнение моделей. Судья не знает условия, но это модель того же поставщика. Сеть недоступна в обоих условиях, ответы ограничены 500 словами. Оценка показывает, следует ли ответ проверяемым правилам, а не качество кода в реальном проекте.

| Скилл | Задач | haiku: без → со | прирост | sonnet: без → со | прирост |
| --- | --- | --- | --- | --- | --- |
| telegram-admin-panel | 3 | 3/12 → 10/12 | +58% | 6/12 → 10/12 | +33% |
| telegram-bot-api | 3 | 2/12 → 8/12 | +50% | 7/12 → 10/12 | +25% |
| telegram-bot-python | 3 | 3/12 → 6/12 | +25% | 9/12 → 11/12 | +17% |
| telegram-business-bots | 3 | 1/11 → 8/11 | +64% | 7/11 → 11/11 | +36% |
| telegram-buttons | 3 | 1/12 → 7/12 | +50% | 6/12 → 10/12 | +33% |
| telegram-code-patterns | 3 | 2/10 → 5/10 | +30% | 2/10 → 9/10 | +70% |
| telegram-cryptopay | 3 | 2/11 → 5/11 | +27% | 7/11 → 8/11 | +9% |
| telegram-debugging | 3 | 4/11 → 7/11 | +27% | 8/11 → 10/11 | +18% |
| telegram-deploy | 3 | 3/12 → 8/12 | +42% | 8/12 → 10/12 | +17% |
| telegram-dialogs | 3 | 6/10 → 6/10 | +0% | 10/10 → 10/10 | +0% |
| telegram-groups | 3 | 1/10 → 7/10 | +60% | 5/10 → 10/10 | +50% |
| telegram-inline-mode | 3 | 1/11 → 7/11 | +55% | 6/11 → 9/11 | +27% |
| telegram-library-selection | 3 | 1/9 → 5/9 | +44% | 2/9 → 7/9 | +56% |
| telegram-localization | 3 | 3/11 → 8/11 | +46% | 7/11 → 9/11 | +18% |
| telegram-media-processing | 3 | 2/11 → 4/11 | +18% | 5/11 → 9/11 | +36% |
| telegram-mini-app-architecture | 3 | 1/11 → 6/11 | +46% | 5/11 → 10/11 | +46% |
| telegram-mini-app-auth | 3 | 5/11 → 9/11 | +36% | 9/11 → 11/11 | +18% |
| telegram-mini-app-design-system | 3 | 1/11 → 6/11 | +46% | 4/11 → 10/11 | +55% |
| telegram-mini-app-device-qa | 3 | 1/12 → 6/12 | +42% | 2/12 → 12/12 | +83% |
| telegram-mini-app-integration | 3 | 2/11 → 3/11 | +9% | 8/11 → 9/11 | +9% |
| telegram-mini-app-native-capabilities | 3 | 3/11 → 5/11 | +18% | 7/11 → 10/11 | +27% |
| telegram-mini-app-network-recovery | 3 | 1/10 → 6/10 | +50% | 2/10 → 10/10 | +80% |
| telegram-mini-app-performance | 3 | 2/10 → 5/10 | +30% | 4/10 → 8/10 | +40% |
| telegram-mini-app-typescript | 3 | 3/10 → 5/10 | +20% | 6/10 → 9/10 | +30% |
| telegram-mini-app-ui | 3 | 2/10 → 6/10 | +40% | 8/10 → 9/10 | +10% |
| telegram-mini-app-ux | 3 | 1/9 → 2/9 | +11% | 1/9 → 6/9 | +56% |
| telegram-mini-app-visual-regression | 3 | 3/10 → 3/10 | +0% | 2/10 → 10/10 | +80% |
| telegram-notifications | 3 | 2/11 → 7/11 | +46% | 5/11 → 11/11 | +55% |
| telegram-observability | 3 | 1/10 → 6/10 | +50% | 4/10 → 8/10 | +40% |
| telegram-payment-provider | 3 | 3/10 → 6/10 | +30% | 6/10 → 10/10 | +40% |
| telegram-payments | 3 | 0/12 → 6/12 | +50% | 6/12 → 10/12 | +33% |
| telegram-platega | 3 | 2/11 → 7/11 | +46% | 6/11 → 11/11 | +46% |
| telegram-profiles | 3 | 3/9 → 6/9 | +33% | 5/9 → 8/9 | +33% |
| telegram-project-planner | 3 | 1/10 → 7/10 | +60% | 7/10 → 10/10 | +30% |
| telegram-python-backend | 3 | 4/11 → 10/11 | +55% | 9/11 → 10/11 | +9% |
| telegram-security-review | 3 | 1/10 → 5/10 | +40% | 5/10 → 9/10 | +40% |
| telegram-subscription-access | 3 | 3/10 → 6/10 | +30% | 5/10 → 8/10 | +30% |
| telegram-testing | 3 | 3/10 → 8/10 | +50% | 6/10 → 9/10 | +30% |
| telegram-user-client | 3 | 4/10 → 5/10 | +10% | 6/10 → 9/10 | +30% |
| telegram-web-login | 3 | 2/10 → 6/10 | +40% | 5/10 → 10/10 | +50% |
| telegram-yookassa | 3 | 2/10 → 8/10 | +60% | 8/10 → 10/10 | +20% |
| **Всего** | 123 | 91/435 → 256/435 | +38% | 236/435 → 390/435 | +35% |
