# Обоснование плана библиотеки 1.0

Исследование от 4 октября 2026 года. Применен `product-design:research`. Задача — определить приоритеты библиотеки готовых Python/TypeScript компонентов и навыков Telegram, а не перепроектировать существующую галерею или публиковать пакеты. Горизонт — путь от локальной версии 0.5.0 до стабильного 1.0, без предположений о календаре и размере команды.

## Краткий вывод

У проекта уже есть хорошая основа для переиспользования: импортируемые пакеты, 24 группы компонентов, 41 навык, CLI, 298 рецептов и пройденная проверка поставки 0.5.0. Дальнейшее качество определяется тем, насколько легко разработчик или ИИ подключают компонент и получают устойчивый пользовательский сценарий. Локальные проверки пока не дают live evidence Telegram, а mock Mini App/backend и transient FSM нельзя считать production-подтверждением. Свежие первичные отчеты пользователей описывают проблемы iOS viewport/клавиатуры и декодирования Update в конкретных версиях, поэтому проверки отказов и реальных клиентов имеют высокий приоритет. Это отдельные наблюдения, а не измеренная частота проблем нашего продукта. Версия 1.0 должна закреплять публичные контракты и проверенный stable scope, при этом новые native/провайдерские возможности могут оставаться experimental. Из этого следует [план из 100 пунктов](library-roadmap-100.md), где архитектура, безопасность, качество интерфейса и доказательства приемки предшествуют обещанию широкого покрытия.

## Метод и границы доказательств

Проверены локальные README, package manifests, каталог, предыдущий roadmap, evaluation-сценарии и distribution report 0.5.0. Выполнен публичный поиск по GitHub issues, Stack Overflow, Reddit, Hacker News и X; технические ограничения сверены с первичной документацией Telegram, aiogram, W3C, SemVer, PyPA и npm. Сохраненного product-design user context нет; аудитория и стек взяты из задачи и AGENTS.md.

В распоряжении нет интервью, support tickets и telemetry использования этой библиотеки. Поиск по X не дал пригодного доступного первичного материала. Reddit/HN дали слабые или рекламные сигналы; они не используются для вывода о частоте или величине спроса. Кросспосты одного автора считаются одним наблюдением. Отчеты GitHub не воспроизведены в нашей среде и не доказывают дефект текущего установленного SDK или всех клиентов.

## Приоритетные проблемы и возможности

Severity ниже — оценка риска для пользовательского сценария, а не найденная уязвимость нашего кода. Confidence относится к наличию свидетельства; распространенность отдельно неизвестна.

| Приоритет | Цель пользователя / поверхность | Где возникает затруднение | Доказательство и границы | Severity / частота / confidence | Что делать |
| --- | --- | --- | --- | --- | --- |
| 1 | Закончить ввод и подтвердить действие в Mini App | Viewport и клавиатура при первом входе/resume | [iOS #2235](https://github.com/TelegramMessenger/Telegram-iOS/issues/2235), 16.07.2026: автор сообщает collapse viewport с Yandex keyboard, iOS 26.5.1 / Telegram 12.9; штатная клавиатура не подтверждена. Наша репродукция отсутствует | High / один отчет, частота неизвестна / medium | 56–58, 67: реальные клиенты, launch/resume/keyboard matrix, фиксировать ограничения, а не обещать универсальный JS workaround |
| 2 | Получать события без зависания бота | SDK decode и polling recovery | [aiogram #1840](https://github.com/aiogram/aiogram/issues/1840), 25.06.2026: автор на aiogram 3.26.0 описывает блокирование polling из-за неожиданного forwarded payload. Это не подтверждение дефекта нашей 3.31.0 | High / один отчет / medium | 34/39/81–83: версии SDK, входная совместимость, обнаружение остановки, воспроизводимые проверки отказов без молчаливого пропуска событий |
| 3 | Авторизовать пользователя и отправить результат Mini App | Launch context, initData, sendData | Исторические вопросы SO [о пустом initData](https://stackoverflow.com/questions/74843361/telegram-bot-webapp-initdata-is-empty-on-google-app-script-and-mainbutton-oncl), [валидации](https://stackoverflow.com/questions/72044314/how-to-validate-data-received-via-the-telegrams-web-app/76091807), [sendData](https://stackoverflow.com/questions/78114696/python-telegram-bot-does-not-receive-data-from-the-web-mini-app), 2022–2025. Ответы сообщества не принимаются за API-контракт; наш starter пока frontend-only | High / несколько разных старых вопросов, текущая частота неизвестна / high для локального пробела, medium для внешнего friction | 41–45/61: полноценный серверный пример и таблица launch contexts по официальным docs |
| 4 | Продолжить диалог после перезапуска | FSM/storage | Наш пример использует MemoryStorage. [aiogram storage docs](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html) предупреждают об отсутствии сохранения после остановки | High / локальная воспроизводимая граница, пользовательская частота неизвестна / high | 31–32/38–39: durable state, concurrency и restart, не вводя обязательный Redis/Postgres |
| 5 | Быстро вставить рабочий код | Документация, DI, примеры | [aiogram #1759](https://github.com/aiogram/aiogram/issues/1759), 01.02.2026, aiogram 3.24.0: пользователь получает missing argument после переноса callback example. Причина и переносимость на другие версии не установлены | Medium / один отчет / medium | 11/14/16/20: полные runnable примеры и consumer-проверки вместо оторванных фрагментов |
| 6 | Доверять обещанию «поддерживается» | Каталог, галерея, выпуск | Локально 298 recipes и SDK/mock/reference статусы, live evidence отсутствует; в корне отсутствуют Git/CI/LICENSE/SECURITY.md | High для широкого выпуска / локальные факты / high | 1–9/81–86/91–100: отделить покрытие имен API от зрелости сценария и привязать доказательства к артефакту |
| 7 | Получить качественный UI и оплату на своем устройстве | Компоненты, интеграция, ошибки | Требования владельца; [Telegram Mini Apps](https://core.telegram.org/bots/webapps), [WCAG 2.2](https://www.w3.org/WAI/WCAG22/quickref/) и [Stars](https://core.telegram.org/bots/payments-stars) задают контекст. Готовой внешней оценки нашего UX нет | High для критических действий / частота не измерена / high для требований, низкая для предполагаемого спроса на конкретный widget | 46–80/89–90: система компонентов, usability/real-device проверки, подтверждение платежей сервером |

## Карта источников

| Источник | Для чего использован | Ограничение |
| --- | --- | --- |
| Локальные [component-library.md](component-library.md), [developer-tools-review.md](developer-tools-review.md), [roadmap-25](library-roadmap-25.md), [evaluation.md](evaluation.md), manifests и report 0.5.0 | Исходная архитектура, выполненные функции, scope evidence | Отчет поставки не заменяет live acceptance |
| [Telegram Mini Apps](https://core.telegram.org/bots/webapps) | Launch/auth, темы, native возможности и платформенные ограничения | При реализации каждого модуля заново сверять конкретное поле и SDK; этот просмотр не обновляет даты всего каталога |
| [Telegram Bot API](https://core.telegram.org/bots/api) | Границы API, клавиатур и событий | Перечень методов не доказывает реализацию workflow |
| [Telegram Stars](https://core.telegram.org/bots/payments-stars) | Цифровые товары, XTR, pre-checkout и подтверждение/refund | Внешние провайдеры требуют отдельного актуального первичного контракта и допустимого сценария |
| [aiogram FSM storages](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html) | Ограничения MemoryStorage | Выбор production storage остается за проектом |
| [iOS #2235](https://github.com/TelegramMessenger/Telegram-iOS/issues/2235), [aiogram #1840](https://github.com/aiogram/aiogram/issues/1840), [aiogram #1759](https://github.com/aiogram/aiogram/issues/1759) | Первичные свежие пользовательские сообщения о затруднениях | Разные версии; не воспроизведено локально, нельзя экстраполировать частоту |
| [iOS #1410](https://github.com/TelegramMessenger/Telegram-iOS/issues/1410), 03.06.2024 | Исторический сигнал проблем fixed inputs/keyboard | Старые версии iOS/Telegram; не утверждение текущего дефекта |
| Три SO вопроса из таблицы приоритетов | Историческое непонимание initData/launch/sendData | Не источник безопасной реализации и не доказательство современного массового спроса |
| [Reddit: camera на разных платформах](https://www.reddit.com/r/Telegram/comments/1wg00ce/telegram_mini_app_camera_works_on_ios_but_android/), [Reddit: fullscreen и launch](https://www.reddit.com/r/node/comments/1qg4ofb/telegram_mini_app_fullscreen_works_via_main_app/) | Discovery leads для будущих device-задач | Доступны поисковые сигналы, полного первичного воспроизведения нет; кросспосты не суммируются |
| [HN: builder](https://news.ycombinator.com/item?id=46461121) | Discovery идеи onboarding | Публикация автора продукта и слабое обсуждение; не независимое подтверждение спроса |
| X | Поиск viewport/keyboard feedback | Пригодных доступных первичных материалов не найдено |
| [WCAG 2.2 quick reference](https://www.w3.org/WAI/WCAG22/quickref/) | Доступность интерфейсов | Применимость критериев проверяется по компоненту; внутренний touch target budget не объявляется требованием WCAG |
| [SemVer](https://semver.org/) | Значение 1.0 и публичного API | Не сертификат production-ready |
| [PyPA release workflows](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/), [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/) | План воспроизводимой и защищенной поставки | Пакеты сейчас локальные; фактическая публикация требует решения владельца |

Контракты Crypto Pay, Platega и ЮКассы в этом исследовании полностью не перепроверялись. Пункты 75–77 требуют свежей доступной первичной документации и provider-specific тестового контура до заявления о stable. Отсутствие источника или sandbox оформляется как явное ограничение, не заполняется догадками.

## Наблюдения и выводы

**Наблюдается:** локальная поставка проверена; есть каталог, CLI и переносимые навыки; live evidence не заявлено; starter без production auth и mock server имеет ограниченный scope. Во внешних первичных отчетах есть конкретные затруднения на определенных версиях.

**Предлагается на основании этих данных:** выпускать стабильные контракты и сценарии с честным evidence, повысить качество устройств и восстановления раньше широких обещаний покрытия. Приоритет удобства Mini Apps дополнительно задан владельцем проекта. Рекомендации о количестве интервью, этапах релизов и времени первого запуска — будущие цели исследования, а не измеренные показатели.

## Возможности по горизонту

| Горизонт | Полезное действие | Что должно стать известно |
| --- | --- | --- |
| Первый цикл / условная неделя | Stable scope, maturity/evidence, support matrix, first-run маршрут и 2–3 пробных onboarding-сессии | Какие компоненты входят в контракт 1.0 и где потребитель реально застревает |
| Несколько циклов / условный квартал | Backend/auth, durable state, UI-композиции, native adapters, device matrix и pilots | Какие критические пути надежны на целевых клиентах и текущем storage |
| Более глубокое исследование | 5–8 developer sessions, независимые задачи ИИ, проверка tablet/low-end/IME, спрос на дополнительные payment providers | Какие новые компоненты нужны чаще всего и какие UX проблемы имеют наблюдаемую частоту |

Эти горизонты не обещают календарный срок при неизвестных ресурсах. Предлагаемый следующий рабочий этап — закрепить контракты и критерии стабильности из пунктов 1–10 плана, параллельно подготовив исходный onboarding-замер.
