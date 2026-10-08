# Я делаю Mini App

Цель за 10 минут: увидеть готовый экран Mini App локально, подключить мост к Telegram во frontend и проверить `initData` на backend. Нужны Node.js 22+ и Python 3.11+.

## 1. Посмотрите демо

Из клона репозитория:

```bash
npm ci && npm run demo
```

```powershell
npm.cmd ci; npm.cmd run demo
```

Откройте http://127.0.0.1:4173: темы, safe areas, форма и восстановление запросов работают без Telegram.

## 2. Подключите пакет к своему frontend

```bash
npm install https://github.com/Zulut30/awesome-telegram-skills/releases/download/v0.24.0/awesome-telegram-patterns-0.24.0.tgz
```

<!-- start:mini-app -->
```typescript
import { ApiClient, TelegramBridge, type TelegramWebApp } from '@awesome-telegram/patterns';
import '@awesome-telegram/patterns/styles.css';

// Официальный telegram-web-app.js создает window.Telegram.WebApp.
const webApp = (window as { Telegram?: { WebApp?: TelegramWebApp & { initData?: string } } }).Telegram?.WebApp;
const bridge = new TelegramBridge(webApp);
bridge.subscribe(state => { document.documentElement.dataset.theme = state.colorScheme; });
bridge.start();  // ready(), тема, viewport и safe areas
export const api = new ApiClient({ baseUrl: location.origin, headers: () => ({ 'X-Init-Data': webApp?.initData ?? '' }) });
```

Вне Telegram мост сообщает `insideTelegram: false`, и экран работает как обычная страница.

## 3. Проверяйте пользователя только на сервере

```python
from telegram_patterns import validate_init_data

launch = validate_init_data(raw_init_data, bot_token, max_age_seconds=300)  # raw строка из заголовка
print(launch.user_id, launch.start_param)  # дальше: сессия и права на объекты
```

`initDataUnsafe` во frontend не подтверждает личность. Неверная подпись или устаревшие данные дают `InvalidInitData`.

## Что дальше

- Архитектура и экраны для телефона, планшета и ПК: скилл `telegram-mini-app-architecture`.
- Сессия и права: `telegram-mini-app-auth`; оформление: `telegram-mini-app-ui`.
- Полный пример с backend, корзиной и Stars — [магазин](../shop-example.md).
