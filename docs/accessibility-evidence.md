# Доказательства доступности UI-композиций

Пункт 060 остается **pending**. Для шести композиций библиотеки 0.28.0 собраны
проверки DOM, клавиатуры, геометрии и отдельных цветов; прохождения с программой
чтения с экрана нет. Соответствие WCAG 2.2 AA не заявляется.

Машинная [матрица применимости и доказательств](../tools/mini-app-quality/accessibility-evidence.json)
содержит 23 выбранных критерия A/AA: применимость к текущим экранам, точные
JSON pointers/утверждения, SHA-256 отчетов и оставшиеся проверки. Это оценка
критических labels, contrast, focus, keyboard, reflow и сообщений, а не полный
список критериев WCAG. Остальные критерии имеют статус **not assessed**, а не
автоматический pass или «не применимо». Полное утверждение AA потребовало бы
всех применимых A/AA для заявленных страниц и процессов. Нормативный документ —
[WCAG 2.2 Recommendation](https://www.w3.org/TR/WCAG22/), просмотренная редакция
от 12 декабря 2024; материалы Understanding поясняют его и не заменяют.

## Что действительно исполнено

| Доказательство | Наблюдение | Граница |
| --- | --- | --- |
| Installed UI 0.28.0, `E028` | 35 contract/browser assertions, 24 axe scans, 96 измерений геометрии; Chrome 156.0.8078.80, axe 4.14.0 | Каталог, товар, корзина, профиль, настройки, запись; это не shop и не отдельное booking demo |
| Дополнение адаптивности, `E056` | 336 обычных pointer cases и 36 CDP scale cases, увеличение root/shell 16→32px | Достижимость действий и геометрия не доказывают семантику, чтение текста или native zoom |
| Keyboard/text-spacing, `E060` | 24/24 ready-state cases: шесть экранов × 320/1280px × обе темы; 47 хешей copied installed assets проверены | Дополнительный локальный probe, а не полная проверка страницы или screen reader |
| Историческое quality demo, `EQUALITY_OLD` | Восемь axe states и Lighthouse accessibility 1.0 | Другое приложение; старый report не сохранял `incomplete`, точный source commit в нем не записан |
| Исправление сохранения incomplete, `ESERIALIZER` | Настоящий axe/Chrome gradient fixture сохранил один `incomplete`, targets и `manual_review_required` | Проверяет serializer; не исправляет задним числом старый report и не принимает контраст UI |

В новом probe состояние и шрифты ожидаются по условиям. Затем одновременно
задаются line height 1.5, paragraph spacing 2em, letter spacing .12em и word
spacing .16em. Исполнены Home/arrows для tabs, Tab и Enter для основных действий,
keyboard ввод имени/email, Escape и возврат focus из dialog. Отказ сохранения
не теряет введенные значения. Для профиля, где нет действия, проверен доступ
к панели чтения. Начальный focus устанавливается программно как setup;
последующие измеренные действия вызываются реальными keyboard events.

Сохранены ширина документа, прямоугольники focus targets, пересечение viewport,
`elementFromPoint`, `:focus-visible`, computed outline и screenshots. Это полезные
наблюдения; они не доказывают, что человек различает индикатор, что весь текст
не обрезан или что reader произносит сообщение. Pixel comparison 144 снимков из
[visual regression](visual-regression.md) также не проверяет эти свойства.

## Применимость и остаток

| Группа / критерии | Что подтверждено в указанном scope | Что еще проверить |
| --- | --- | --- |
| Labels/structure: 1.3.1, 1.3.2, 1.3.5, 2.4.6, 2.5.3, 3.3.2, 4.1.2 | Связь label/error, обнаружение полей и действий по names/roles, выбранная панель и сохранение pending label | Порядок чтения, понятность headings/names, computed purposes и фактическое поведение reader; для 1.3.2/1.3.5 отдельного результата нет |
| Текст/цвет: 1.4.1, 1.4.3, 1.4.11 | Текст ошибки; axe observations и две фактические solid dialog text/background пары | Все значимые цветовые состояния, соседние цвета границ/focus, перекрытия; non-text contrast отдельно не измерен |
| Размер/поток: 1.3.4, 1.4.4, 1.4.10, 1.4.12 | Portrait/landscape browser sizes, текст 200%, отсутствие document overflow, выбранные действия при spacing stress | Ручное чтение всего содержимого, clipping и остальные состояния; нет переноса browser resize в физическую приемку |
| Keyboard/focus: 2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11 | Home/End/arrows, ограниченные Tab/Shift+Tab и Escape циклы, Enter, focus возврат/ошибка/достижимость | Полный осмысленный keyboard путь всех веток, визуальная различимость focus, overlays и reader transitions |
| Targets: 2.5.8 | Видимые compact controls одной выбранной панели и 20 primary action rectangles дополнительного probe | Остальные controls/states и применимость исключений; внутренние 44px не являются AA-формулировкой |
| Ошибки/status: 3.3.1, 3.3.3, 4.1.3 | Inline error association, перенос focus к ошибке, текст отказа и сохранение draft | Все подсказки исправления и фактические объявления; 3.3.3/4.1.3 не имеют исполненного критериального результата |

Для [1.4.10 Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)
эти экраны используют вертикальную прокрутку, поэтому значим эквивалент ширины
320 CSS px. Формула высоты 256 CSS px относится к горизонтально прокручиваемому
содержимому. Нулевой `scrollWidth` overflow не исключает скрытую обрезку текста.
Фактические 400% browser-menu zoom из теста CDP scale 2 не следуют.

[2.4.7 Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)
и [2.4.11 Focus Not Obscured](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)
различаются: видимый индикатор и отсутствие полного перекрытия component —
разные проверки. Полную незакрытость из AAA 2.4.12 и численный perimeter тест
AAA 2.4.13 не добавляем к AA как обязательные требования. Контраст значимых
состояний относительно соседних цветов отдельно рассматривает AA 1.4.11.

## Incomplete не равно pass

Installed six-composition report сохраняет два `color-contrast incomplete`:
светлый и темный bottom sheet, где axe не определил фон перекрывающегося элемента.
Дополнительное вычисление дает **13.7347:1** и **12.2787:1** для известной пары
solid dialog parent text/background. Оно подтверждает эти пары, а не любой
дочерний фон, перекрытие и все состояния. Исходные incomplete остаются в отчете.

Исторический отдельный quality report записывал только passes/violations:
отсутствующий ключ `incomplete` означает **not recorded**, а не ноль. Текущий
serializer уже сохраняет такие findings; новая root-проба с gradient воспроизвела
один настоящий incomplete и сохранила его. Это отдельный persistence witness.
Старые bytes/report не изменены, и новый serializer сам по себе не подтверждает
повторное прохождение старого UI-сценария. [W3C поясняет ограничения автоматических
инструментов](https://www.w3.org/WAI/test-evaluate/tools/selecting/).

## Внутренние 44px и WCAG

Внутренний критерий toolkit — 44 CSS px при базовых 16px (`2.75rem`). Canonical
assertion измерял текущие видимые compact controls, когда выбрана панель Настроек
при 390×844, а не все targets шести экранов и четырех состояний. Дополнительный
probe сохранил размеры 20 primary actions: минимальная высота 50px. Это конкретные
наблюдения ограниченного набора.

[AA 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
задает 24×24 CSS px с исключениями: достаточное расстояние между небольшими
targets, эквивалентный control, inline target, неизмененный user-agent control,
essential presentation. Для spacing рассматриваются круги диаметра 24 CSS px
в центрах bounding boxes небольших targets и их пересечения с другими targets.
Наличие исключения надо обосновать для конкретного случая. В
[AAA 2.5.5](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html)
используются 44 CSS px со своими исключениями; совпадение числа не принимает
весь AAA и не переопределяет AA.

## Оставшаяся проверка с reader

Narrator не запускался, настройки компьютера не менялись. Для scoped desktop
проверки не требуется придумывать дополнительное обязательное мобильное устройство.
При доступной среде запишите reader/browser/OS и версии, способ ввода, точный путь,
ожидаемый и фактически услышанный результат, замечание и повторную проверку.

Пройдите названия и чтение шести панелей; имя/email и обязательную/форматную ошибку;
исправление, отказ и сохранение draft; вход/выход dialog и возврат focus;
loading/empty/error и status без пропущенных или повторяющихся объявлений.
Наличие `role=status`, `role=alert` или `aria-busy` — исходный контракт, а не запись
произнесенного reader результата. Визуальный focus, non-text contrast и все
неразобранные incomplete также остаются в ручном остатке. Пункт 060 не закрывается
по Lighthouse score, axe violation count, screenshot или этой матрице.

Источники по каждому критерию и точные локальные SHA-256 — в JSON-матрице;
официальные W3C страницы просмотрены 6 ноября 2026. Матрица содержит результаты
проверки текущих артефактов и явно отмеченный остаток, а не сертификат доступности.
