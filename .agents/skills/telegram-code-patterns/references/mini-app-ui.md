# UI toolkit для Mini Apps

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **fallback** — запасной вариант, если основная возможность недоступна.

Набор дополняет существующие `createAppShell`, `createTextField` и `TelegramBridge`.
Это DOM API без обязательного React/Vue/Svelte, второго server state и внешних
ресурсов. Все компоненты импортируются из основного TypeScript-пакета; CSS
подключается явно в этом порядке:

```ts
import '@awesome-telegram/patterns/styles.css';
import '@awesome-telegram/patterns/tokens.css';
import {createUiButton, createUiField, validateUiFields} from '@awesome-telegram/patterns';

const name = createUiField(document, {
  label: 'Как к вам обращаться', required: true,
  value: savedName, autocomplete: 'name', inputMode: 'text',
});
const save = createUiButton(document, {
  label: 'Сохранить',
  onPress: async () => {
    if (!validateUiFields([name])) return;
    await projectService.save({name: name.input.value});
  },
  onError: report => showProjectRecovery(report),
});
host.append(name.root, save.element);
// Владелец снимает обработчики при настоящем unmount:
// save.dispose(); name.dispose();
```

## Токены и темы

`tokens.css` использует существующие роли `--tp-bg`, `--tp-surface`, `--tp-text`,
`--tp-muted`, `--tp-border`, `--tp-action`, `--tp-action-text`, `--tp-error`.
Добавлены парные success/warning/neutral/danger поверхности, focus и overlay,
семейство/размеры шрифта, line height, spacing 1–6, радиусы sm/md/lg и motion
duration/easing. Цвета определяются в палитрах, а не отдельно в каждом компоненте.
Дополнительные status-пары имеют согласованные light/dark defaults.

Плотность выбирает host: `shell.element.dataset.density = 'compact'` или удаление
атрибута для comfortable. Минимальная высота обычного control — 3rem, compact —
2.75rem. Это критерий набора 44 CSS px при базовом размере 16px; он не означает,
что WCAG требует 44px для любого элемента. Типографика и интервалы используют rem,
длинные строки переносятся, focus виден. `prefers-reduced-motion: reduce`
отключает skeleton и transitions. Смена цветовых пар происходит сразу: фон не
анимируется отдельно от текста через промежуточный недостаточный контраст.

```ts
const disconnect = connectUiShell(shell, bridge, {
  resolveInsets(snapshot) {
    // Только если host проверил именно эту систему координат клиента:
    return projectGeometry.resolve(snapshot);
  },
});
```

`connectUiShell` использует `applyTheme` и `setInsets` существующей оболочки.
При `snapshot.insideTelegram` Telegram theme имеет приоритет. Вне Telegram
используется системная тема через matchMedia; native themeParams из такого
snapshot не подставляются. Обновление темы не пересоздаёт input и не перехватывает
focus. Без connector CSS также поддерживает системный dark fallback на shell
без `data-theme`. Данные bridge не подтверждают auth/права пользователя.

Произвольные Telegram custom colors могут требовать собственной проверки
контраста: defaults и две проверенные темы не доказывают доступность любой
пользовательской палитры. Компоненты не исправляют серверные значения, цены или
права по внешнему виду и не читают `initDataUnsafe`.

## Компоненты и владение

| API | Существенный контракт |
| --- | --- |
| `createUiButton` | Подпись, основной/дополнительный/опасный вид, тип кнопки; ожидание блокирует повтор, запрет и освобождение задаются явно |
| `createUiField`, `validateUiFields` | Поле со связанной подписью, подсказкой и ошибкой; тип, режим ввода, автозаполнение, локальная проверка и фокус первой ошибки |
| `createUiCard`, `createUiList` | article/heading или семантический список, буквальные title/detail |
| `createUiBadge` | neutral/success/warning/danger с текстом, смысл не передаётся одним цветом |
| `createUiSkeleton` | 1–12 декоративных lines и status «Загрузка», без фальшивого прогресса операции |
| `createUiFeedback` | разные empty/error/success, сообщение и необязательное действие по смыслу сценария |
| `uiUrl`, `createUiLink` | Переход внутри своего origin либо HTTPS; без пароля, управляющих символов и исполняемых схем; внешняя ссылка изолирована от opener |
| `createUiTabs` | Смонтированные панели, один фокус в наборе, стрелки и клавиши Home/End, выбранное/скрытое состояние; ввод сохраняется |
| `createUiDialog` | Диалог или нижняя панель с доступным заголовком, начальным фокусом и циклом Tab; Escape и видимое закрытие возвращают фокус |
| `connectUiShell`, `bindUiFocusVisibility` | borrowed shell/bridge и достижимость активного поля; возвращают cleanup без удаления чужой оболочки |

Строки отображаются через textContent, не innerHTML. Переданный в tabs/dialog
готовый DOM принадлежит host и не является HTML sanitizer. Control `.dispose()`
удаляет принадлежащий ему DOM и listeners; статические card/list/badge/skeleton
возвращают обычный HTMLElement и удаляются своим контейнером.

Pending кнопки блокирует повторную активацию и ставит aria-busy/aria-disabled,
сохраняя текущую подпись и focus. Настоящий disabled использует native disabled.
Managed `type=submit` с onPress не выполняет дополнительно browser form submit.
Без onPress остаётся обычная HTML submit-семантика. Одна обработка запроса должна
быть общей для DOM и native MainButton; toolkit не регистрирует native CTA сам.

Если control удалён до первого action microtask, действие не начинается. После
начала dispose не отменяет удалённый эффект и не сообщает «отменено». Host
хранит stable operation ID и unknown/reconciliation отдельно от жизни экрана.
onError получает safe error report для write; exception str и payload не
превращаются в пользовательский текст. UI mutex не заменяет серверную дедупликацию.

Validator поля синхронный: `(value) => string | null`. Он не делает HTTP.
Required видно в label; после blur выполняется локальная проверка. Серверная
ошибка устанавливается через setError и не стирает значение/selection. Поля не
пересоздаются при theme/resize. После отказа save экран сохраняет ввод; новый
успех относится к отправленным значениям, а не к последующим правкам пользователя.

## Навигация и модальные окна

Tab panels передаются один раз и переключаются через hidden; это не router и
не новая история приложения. ID табов/панели должны быть различными. Для
удалённой загрузки используйте отдельный service state, не делайте медленный
network request условием перемещения focus между вкладками.

Dialog надо добавить в DOM до `open(opener)`. Модальность, top layer и inert
предоставляет `showModal`; в неподдерживаемом engine выбрасывается
`UnsupportedCapability`, а не рисуется псевдомодальное окно. Начальный focus —
на heading, локальный Tab/Shift+Tab цикл удерживает его в light-DOM controls.
Escape, visible «Закрыть» и backdrop закрывают окно; focus возвращается к
существующему opener. Dispose открытого окна также восстанавливает focus.
Custom shadow widgets требуют отдельной интеграционной проверки их focus-порядка.

## Insets, viewport и клавиатура

Host — единственный владелец системы координат. Raw `systemInsets` и
`contentInsets` не суммируются и не объединяются произвольным max. Resolver
возвращает уже проверенный итог; при отсутствии resolver connector вообще не
угадывает padding. Shell использует resolved `--tp-inset-*`, а без них — CSS
env fallback. Card/field/list не добавляют второй inset. Dialog в top layer
позиционируется в том же resolved rectangle, а не вкладывает повторный safe padding.

Стабильная высота приходит из существующего `BridgeSnapshot.stableHeight`.
Нижнее действие остаётся в document flow, не закрепляется к быстро меняющемуся
viewportHeight. `bindUiFocusVisibility` слушает focusin, VisualViewport resize и
pageshow; при выходе активного поля за видимую границу планирует один
scrollIntoView(nearest). Это не детектор клавиатуры и не доказательство поведения
сторонней клавиатуры. Данные формы не сбрасываются при resize/resume. Для bfcache
пример не уничтожает UI на `pagehide.persisted`; при настоящем unmount выполняет
cleanup. Host выбирает lifecycle своего приложения.

## Композиции экранов и сервисы

`examples/ui-kit/screens.ts` содержит каталог,
товар, корзину, профиль, настройки и запись. Они используют одни controls и
существующий `ScopedAsyncState`, принимая injected `ScreenService<T>` с
подтверждённым scope и loader, которому передаётся AbortSignal. Поздняя read
response не перезаписывает актуальную. Null/empty DTO дают empty, read failure —
санитизированный error с повторной загрузкой, ожидание — loading. Dispose
отписывает UI и прекращает принятие результата; он не обещает отмену сервера.
При смене подтверждённой сессии host удаляет прежний view и создаёт новый с
новым service/scope; приватный draft не переносится между аккаунтами.

SettingsService.save — граница настоящего доменного сервиса; после ошибки
draft остаётся. Backend проверяет DTO, права и operation ID. Цена и итог
приходят из модели сервиса. Корзина показывает путь обзора заказа, а не
фальшивый статус paid. Booking передаёт выбранный slot владельцу сценария;
успешная запись возникает только по фактическому backend result.

`examples/ui-kit/README.md` явно использует локальные учебные DTO,
не выдаёт их за Telegram auth/платёж и не обращается к внешним ресурсам.
В ней переключаются ready/loading/empty/error, обе темы, формы и sheet.
`examples/api-reference/typescript/ui.ts` отдельно выполняет
контракт всех public runtime/types через установленный пакет.

## Автоматическая и ручная приёмка

```sh
npm run build -w @awesome-telegram/patterns
node node_modules/typescript/bin/tsc -p examples/ui-kit/tsconfig.json
node node_modules/typescript/bin/tsc --strict --target ES2022 --module NodeNext --moduleResolution NodeNext --outDir output/production-run-2026-11-05/ui-kit/reference --rootDir examples/api-reference/typescript examples/api-reference/typescript/ui.ts
node --test packages/typescript/tests/ui.test.mjs
node node_modules/typescript/bin/tsc --noEmit --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess --target ES2022 --module NodeNext --moduleResolution NodeNext packages/typescript/tests/types/ui.ts
npm ci --prefix tools/mini-app-quality --ignore-scripts --no-audit --no-fund
node packages/typescript/tests/ui-browser.mjs
```

Browser runner использует настоящий локальный Chrome и axe из существующего
dev-only tooling. Проверяются: буквальный текст/URL, pending/dispose, сохранение
формы, focus/keyboard/touch закрытие modal, tabs, theme priority/insets, 96
измерений композиции (шесть экранов × две темы × восемь размеров), root text
200%, приближение масштабирования страницы в Chrome, компактные элементы,
уменьшенное движение и применимые правила axe для готового экрана, модального окна,
проверки формы, отказа сервера, загрузки, пустого результата и ошибки.
Для solid dialog surface дополнительно рассчитывается контраст фактических
computed text/background colors: это узкая проверка пары для axe overlap
incomplete, а не утверждение о контрасте любого перекрывающегося содержимого.
Окончательные команды, версии, violations и incomplete findings — в
`output/production-run-2026-11-05/ui-kit/report.json`.

320×568, 390×844, 844×390, 768×1024, 1024×768, 1280×800, 480×720 и 390×420 —
browser viewports, не список физических устройств. 390×300 после focus и
synthetic persisted pageshow проверяют наш обработчик, а не реальную native
клавиатуру. Screenshots — synthetic review artifacts, не утверждённые visual
baselines. CDP page scale не заменяет native zoom клиента. Automated axe scan,
focus assertions и DOM semantics не являются общим утверждением WCAG conformance.

Перед production отдельно пройдите Android/iOS/Desktop Telegram: холодный старт
и первый focus, возврат после background, обе ориентации, системную и стороннюю
клавиатуру, последнее поле и подтверждение, полноэкранные нативные отступы и выбранную программу чтения с экрана
(например TalkBack/VoiceOver/NVDA). Запишите версии клиента/ОС/reader и фактические
объявления. Эти device/native-keyboard/screen-reader сценарии здесь **not run**.

Источники фактически проверены 2026-11-05:
[Telegram theme/viewport](https://core.telegram.org/bots/webapps#initializing-mini-apps),
[ThemeParams](https://core.telegram.org/bots/webapps#themeparams),
[APG modal dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/),
[APG tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/).
[WCAG contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
Новые native keyboard/fullscreen API не добавляются. Safe/content inset fields
и их события — optional Bot API 8.0+, источник значений уже существует в bridge.
