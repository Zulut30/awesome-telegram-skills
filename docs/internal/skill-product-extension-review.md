# Семь новых навыков и расширение Mini App UI

Дата: 3 октября 2026 года, Europe/Warsaw. Набор расширен с 33 до 40 навыков. Стек сохранен: Python для ботов/backend и TypeScript для Mini Apps.

## Что добавлено

| Навык | Результат и граница |
| --- | --- |
| [telegram-mini-app-ux](../../.agents/skills/telegram-mini-app-ux/SKILL.md) | Понятный пользовательский путь, форма/checkout и восстановление ошибок. Walkthrough агента отделен от исследования с участниками. |
| [telegram-mini-app-visual-regression](../../.agents/skills/telegram-mini-app-visual-regression/SKILL.md) | Воспроизводимый baseline и expected/actual/diff. Pixel diff не является оценкой красоты или native клиента. |
| [telegram-mini-app-network-recovery](../../.agents/skills/telegram-mini-app-network-recovery/SKILL.md) | Допустимый scoped черновик, cache и сверка неизвестной записи. Backend authorization и dedup не подменены local storage. |
| [telegram-web-login](../../.agents/skills/telegram-web-login/SKILL.md) | OIDC ID token, login transaction и account linking. Протоколы Mini App initData, legacy widget и MTProto разделены. |
| [telegram-admin-panel](../../.agents/skills/telegram-admin-panel/SKILL.md) | Операторские списки/действия с capability, scope, revision и журналом. Frontend confirmation не дает серверного права. |
| [telegram-media-processing](../../.agents/skills/telegram-media-processing/SKILL.md) | Настоящие parser/output, ограничения process, job lifecycle и закрытая выдача. Transform и Telegram send имеют разные исходы. |
| [telegram-subscription-access](../../.agents/skills/telegram-subscription-access/SKILL.md) | Charge ledger, оплаченные интервалы и проверка доступа. Подписка/charge/grant различаются; отмена продления не является возвратом. |

У каждого нового навыка собственные SKILL.md, agents/openai.yaml и тематическая reference; соседние навыки не являются обязательной зависимостью. Всего добавлен 21 файл новых каталогов.

UI и design-system дополнены инструкциями по reduced motion, независимому от animationend cleanup, focus и объявлениям состояния. Отдельная [motion-accessibility.md](../../.agents/skills/telegram-mini-app-ui/references/motion-accessibility.md) содержит приемку с keyboard и границу настоящего screen reader. Это восемь новых references вместе с семью тематическими файлами.

Descriptions разделяют UX, реализацию экрана, библиотеку компонентов и сравнение снимков; OIDC сайта и initData Mini App; платежный protocol и продуктовые права доступа. Общие framework, global services и live actions не добавлены.

Всего изменены 24 файла навыков: 22 новых и два существующих входных файла UI/design-system. Diff (`output/quality-product-extension/skill-changes.diff`, локальный артефакт), hashes (`output/quality-product-extension/changes.json`, локальный артефакт).

## Структура и переносимость

- Валидатор коллекции: 40/40. Вывод (`output/quality-product-extension/collection-validation.txt`, локальный артефакт).
- Официальный quick_validate: 40/40. Результаты (`output/quality-product-extension/official-validation.json`, локальный артефакт).
- Тесты репозитория: 16/16 без пропусков, установщик/API parser. Вывод (`output/quality-product-extension/repository-tests.txt`, локальный артефакт).
- Реальный CLI roundtrip на временном проекте: 40 навыков/119 файлов побайтово совпали; dry run не создал каталоги; повтор не перезаписал файлы; standalone copy снова прошла validator. Roundtrip (`output/quality-product-extension/installer-roundtrip.json`, локальный артефакт), inventory (`output/quality-product-extension/inventory.json`, локальный артефакт).
- README содержит все 40 навыков. Packaging (`output/quality-product-extension/packaging.json`, локальный артефакт).

## Независимые поведенческие пробы

Три независимых оценщика получили реалистичные запросы, нужные навыки и отдельные временные каталоги. Они не читали прошлые отчеты и не редактировали canonical навыки. Примеры реализованы с fake Telegram/payment transport; их пределы указаны в исходных отчетах.

| Проба | Фактически выполнено |
| --- | --- |
| UX / network recovery / visual regression / motion | TypeScript typecheck и build; 27 behavior/API проверок + 26 screenshot comparisons = 53/53. Из снимков 6 относятся к адаптированному TypeScript примеру reference. Chrome window sizes/DOM/fake bridge не заменяют реальные клиенты. |
| Видимый дефект | Контролируемое изменение вызвало ожидаемый exit 1 и 38 248 diff pixels. После возврата кода 26/26 сравнений прошли без перезаписи baseline. Это проверка чувствительности, а не оставшийся дефект. |
| Login / admin backend | 25 unittest methods на реальном SQLite, все прошли. 15 отрицательных signed JWT вариантов входят в эти методы, не добавляются к 25. RS256 ключ искусственный и не принадлежит Telegram. |
| Login / admin transport и клиент | 13 сценариев через настоящий локальный HTTPS с fake provider; TypeScript typecheck/build и 3 Node contract tests прошли. Browser UI/Telegram code exchange не выполнялись. |
| Subscription / media | 36/36 checks на SQLite и настоящем FFmpeg 8.1: конкурирующие charge events, интервалы, cancel/refund, HTTP owner boundary, restart/fencing и реальное преобразование PCM16 WAV. |
| Timeout cleanup | После обнаруженной Windows process/cleanup гонки проведены 8/8 повторов одного targeted сценария. Это повторения, а не восемь дополнительных уникальных функций. |

Родитель отдельно повторил 53 browser tests, 25 backend methods, 36 subscription/media checks и 3 Node tests; все прошли. Эти повторения не суммируются с независимыми счетчиками. Также просмотрены три screenshot baseline. Browser (`output/quality-product-extension/parent-browser-results.json`, локальный артефакт), login/backend (`output/quality-product-extension/parent-login-results.json`, локальный артефакт), media (`output/quality-product-extension/parent-media-results.json`, локальный артефакт), visual review (`output/quality-product-extension/parent-visual-review.json`, локальный артефакт).

Исходные отчеты: frontend (`output/quality-product-extension/frontend-audit.json`, локальный артефакт), login/admin (`output/quality-product-extension/login-admin-audit.json`, локальный артефакт), media/access (`output/quality-product-extension/media-access-audit.json`, локальный артефакт). Первые неудачные попытки реализации сохранены отдельно; они не выданы за финальные passed.

## Исправления по наблюдаемому поведению

Подтвержденное P2 уточнение: удаление всего expired form record потеряло ID уже отправленной неизвестной операции; повторное заполнение создало две fake bookings. В network-recovery разделены TTL личных полей и recovery pointer/серверный путь. Retention ссылки не продлевает backend/provider dedup, невозможная сверка оставляет explicit unresolved. После исправления контакты удалены, прежний ID сохранен, результат найден, `effects=1/postCount=1`. Этот сценарий входит в 27 behavior tests.

Initial detector (`output/quality-product-extension/edge-expiry.json`, локальный артефакт) имеет exit 0, потому что утверждал наблюдаемый плохой результат `effects=2`; он не подтверждает правильность первоначального поведения. Final regression (`output/quality-product-extension/edge-expiry-final.json`, локальный артефакт) проверяет однократный эффект. Оценщик перечитал обновленные инструкции и подтвердил достаточность исправления.

Необязательное P3 замечание о том, кто принимает временный baseline, уточнено в visual-regression reference: автор изолированной пробы может визуально просмотреть временный эталон и записать это; продукт использует свой процесс review, дополнительное разрешение пользователю не вводится.

Родитель также смягчил обязательную «собственную сессию» в web-login до защищенной сессии сервиса по существующей модели. Auth-аудит относится к сохраненному начальному snapshot и отмечает изменение hash; отдельное перечитывание текущей формулировки (`output/quality-product-extension/login-admin-post-review.json`, локальный артефакт) подтвердило совместимость без повторного запуска тестов.

SQL-опечатки, focus rerender и process cleanup в самостоятельных примерах исправлены оценщиками. Они не превращены в универсальные требования новых навыков; порядок stop/wait/cleanup уже описывался в media reference.

## Материалы и воспроизведение

Архив примеров и доказательств (`output/quality-product-extension/forward-evidence.zip`, локальный артефакт) содержит исходники трех проб, dependency locks, README с командами, результаты и snapshots. Текущий снимок навыков (`output/quality-product-extension/skills-final.zip`, локальный артефакт) содержит все 40 каталогов. Summary (`output/quality-product-extension/summary.json`, локальный артефакт) и проверка ZIP (`output/quality-product-extension/archive-integrity.json`, локальный артефакт) дают счетчики и hashes.

Архив не включает node_modules, venv, скачанные runtime binaries или реальные credentials. RSA/TLS fixtures — явно обозначенные искусственные локальные тестовые ключи; их нельзя применять в production. Для истекшего TLS fixture README описывает генерацию новой пары в свежем каталоге. Абсолютные пути в исходных отчетах относятся к исходной Windows-среде; backend tests создают новые тестовые данные при запуске.

Основные команды после установки указанных в README зависимостей:

```powershell
# frontend: текущие baseline, без --update-snapshots
node node_modules/@playwright/test/cli.js test functional.spec.mjs supplementary.spec.mjs edge-expiry.spec.mjs visual.spec.mjs example-adapted.spec.ts
# login-admin: из его каталога и изолированного venv
& .venv/Scripts/python.exe run_tests.py
& .venv/Scripts/python.exe socket_probe.py
# media-access: FFmpeg должен быть доступен в PATH
python -X utf8 run_checks.py
```

Эталонные screenshots зависят от ОС/Chrome/fonts. Реальные devices, native keyboard/storage, screen reader, user research, Telegram Login/Stars/provider sandbox и production load не испытывались. Media probe охватывает только короткий PCM16 WAV, не произвольный MP3/Opus/video; frontend fake ledger хранится в памяти процесса, а настоящие SQLite проверки относятся к двум backend примерам. Полные ограничения доступны в исходных JSON.

## Источники и границы

Использованы текущие первичные источники Telegram, OpenID, W3C/MDN, Playwright, OWASP и FFmpeg. Конкретные проверенные инварианты и даты перечислены в [sources.md](../sources.md); локальные ledger, UX flow и матрица снимков являются решениями продукта.

Эта поставка содержит навыки и материалы проверки. Она не является развернутым Telegram-ботом, регистрацией merchant account или production приложением. Реальные Telegram аккаунты, платежные среды, физические устройства и screen reader требуют отдельного запуска в соответствующей среде.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](../v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
