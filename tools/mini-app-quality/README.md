# Качество демо Mini App

Проверка скорости, доступности и размера бандла [демо Mini App](../../examples/mini-app). Задача CI `mini-app-quality` валит сборку, если нарушен любой бюджет из [budgets.json](budgets.json):

- Lighthouse, мобильный профиль по умолчанию с симуляцией медленной сети и CPU: медиана трех прогонов performance не ниже 0.9, accessibility не ниже 0.95;
- axe-core по тегам WCAG 2.0–2.2 A/AA: ноль нарушений на телефоне (320 px) и ПК (1440 px), в светлой и темной теме, до и после ошибки формы;
- бюджет первой загрузки: не больше 72 КиБ скриптов, 4 КиБ стилей и 16 запросов (несжатые байты: демо-сервер не использует gzip).

```bash
npm ci && npm run build
npm ci --prefix tools/mini-app-quality
npm test --prefix tools/mini-app-quality
node tools/mini-app-quality/check.mjs output/mini-app-quality
```

Нужен Node.js 22.19+ (требование Lighthouse 13) и установленный Chrome; другой браузер задается `CHROME_PATH`. В `output/mini-app-quality` сохраняются `report.json` (оценки всех прогонов, метрики, файлы бандла, результаты axe) и полный отчет Lighthouse выбранного прогона. Lighthouse и axe ставятся отдельным lockfile, чтобы остальные задачи CI их не устанавливали.

Порог проверен мутацией: блокирующий скрипт на 1.5 с и светло-серый текст снизили performance до 0.66 и дали нарушения `color-contrast`, проверка завершилась с кодом 1. Это лабораторная оценка локального сервера, а не замер на реальных устройствах или в WebView Telegram.
