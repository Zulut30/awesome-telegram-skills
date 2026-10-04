# Приемка Mini App

## Браузерный уровень

Для нового пути отправные размеры в CSS px: 320×568, 390×844, 768×1024, 1024×768, 1280×800, 480×720; 390×420 моделирует малую высоту. Размер не доказывает проверку физического устройства или клавиатуры Telegram.

1. Проверь typecheck и production build; desktop build не заменяет runtime.
2. Пройди главный путь в компактном и широком виде, обеих темах. Измерь общий horizontal overflow; проверь достижимость последнего поля/CTA.
3. Заполни форму, измени размер и тему, вернись назад/вперед. Проверь сохраненный ввод и отсутствие лишних подписок.
4. Для submit смоделируй два быстрых действия и сетевую ошибку: один прикладной запрос, явное pending/error, сохраненный черновик. Потерянный ответ записи требует серверной сверки, если она обещана контрактом.
5. Проверь keyboard-only путь, labels, visible focus, длинный текст и увеличение текста. Измерь контраст основных элементов обеих тем; automated scan не является полным accessibility audit.
6. Если есть viewport/safe-area handlers, передай разные insets и stable/unstable events через явно выбранный fake adapter. Проверь геометрию, missing capabilities и cleanup. Это проверка собственного кода, не совместимости Telegram.
7. При cleanup на pagehide проверь persisted=true → pageshow → resize/back. Восстановление из back/forward cache не запускает bootstrap заново; UI должен снова получать актуальную геометрию и callbacks. Synthetic lifecycle и реальная browser back/forward проверяются отдельно.

Сохрани команды, версии, размеры, измерения, failed cases и screenshots. Отдельно оцени иерархию, читаемость и полезное использование ширины. Дизайн не подтверждается отсутствием console errors.

## Telegram runtime

При доступном тестовом боте проверь фактически поддерживаемые Android/iOS/desktop/web клиенты и точки запуска. Особенно: клавиатура, safe/content-safe areas, native BackButton/MainButton, изменение темы, fullscreen по применимости, background/resume и вход на backend. Запиши client/version и не публикуй подписанную initData.

Для скорости сравнивай production bundle и наблюдаемую загрузку/взаимодействие на выбранном сетевом/CPU профиле. Не называй localhost timing скоростью мобильного приложения. Бюджет задается продуктом; performance emulation требует отдельной проверки на слабом физическом устройстве.

Если клиент недоступен, оставь воспроизводимый runtime checklist и явно назови непроверенный участок. Не заполняй таблицу статусом PASS за неисполненный сценарий.

Источники: [Telegram Mini Apps](https://core.telegram.org/bots/webapps), [Web Vitals](https://web.dev/articles/vitals), [W3C accessibility](https://www.w3.org/WAI/WCAG22/Understanding/).
