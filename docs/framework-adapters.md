# Адаптеры React, Vue и Svelte для TelegramBridge

`TelegramBridge` из `@awesome-telegram/patterns` не зависит от фреймворков: он подписывается на события клиента Telegram (тема, высота, безопасные отступы) и отдает неизменяемый снимок `BridgeSnapshot`. Тонкие адаптеры подключают этот снимок к компонентам. Каждый адаптер — отдельный подпуть пакета, поэтому основной импорт по-прежнему не тянет React или Vue.

| Фреймворк | Импорт | Что возвращает |
| --- | --- | --- |
| React 18+ | `import {useTelegramBridge} from '@awesome-telegram/patterns/react'` | `BridgeSnapshot`; компонент перерисовывается при видимом изменении (через `useSyncExternalStore`) |
| Vue 3.3+ | `import {useTelegramBridge} from '@awesome-telegram/patterns/vue'` | `ComputedRef<BridgeSnapshot>`; подписка снимается вместе с областью `setup()` или `effectScope` |
| Svelte 4 и 5 | `import {telegramBridgeStore} from '@awesome-telegram/patterns/svelte'` | store по контракту Svelte; `$snapshot` подписывается и отписывается вместе с компонентом |

React и Vue — необязательные peer-зависимости: устанавливает их сам проект. Адаптер Svelte реализует контракт store без импорта `svelte`.

```tsx
// main.tsx: проект владеет bridge — один на приложение, start() один раз, dispose() при выходе.
const bridge = new TelegramBridge(window.Telegram?.WebApp);
bridge.start();

function App() {
  const snapshot = useTelegramBridge(bridge);
  return <main style={{background: snapshot.theme.bg_color}}>{snapshot.colorScheme}</main>;
}
```

## Как это устроено

Все три адаптера используют общий источник: одна подписка на `TelegramBridge` на любое число компонентов, снимок меняется только при видимом изменении (тот же объект, пока тема, высота и отступы прежние — этого требует `useSyncExternalStore`). Когда отписывается последний компонент, источник снимает подписку с bridge. Ошибка в одном компоненте не мешает обновить остальные: bridge и источник уведомляют всех и только потом сообщают об ошибке.

Адаптеры не вызывают `bridge.start()` и `bridge.dispose()`, не проверяют `initData` и не устанавливают личность пользователя: `insideTelegram` означает только «открыто в клиенте Telegram». Проверка подписи остается на сервере (`validate_init_data`) или в `verifyInitDataSignature`.

## Примеры

`examples/frameworks` содержит одно и то же представление на React (TSX), Vue (render-функция) и Svelte (компонент `.svelte`). `npm run test:frameworks` собирает их (tsc и компилятор Svelte) и проверяет серверный рендер каждого, а также то, что Vue и Svelte обновляются при смене темы и отписываются. CI запускает эту команду в задаче TypeScript.
