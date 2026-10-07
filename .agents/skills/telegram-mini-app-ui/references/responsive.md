# Responsive, viewport и safe areas

Термины: **fallback** — запасной вариант, если основная возможность недоступна.

Проверено по [Telegram Mini Apps](https://core.telegram.org/bots/webapps) 2 октября 2026 года. Поля и version gates сверяйте с установленным bridge/SDK.

## Геометрия

Используйте ширину viewport/container, не screen.width, user agent или устройство. Breakpoint нужен там, где содержимое не помещается. У grid/flex children проверьте min-width, длинный текст и картинки; overflow-x: hidden не исправляет потерянный контент.

Не фиксируйте все приложение на 100vh без прокрутки. Для браузера проверьте dvh и fallback; Telegram предоставляет --tg-viewport-height и --tg-viewport-stable-height. Telegram предупреждает: частота viewportHeight недостаточна для плавного закрепления снизу. Для стабильной границы используйте stable height; клавиатура проверяется отдельно.

viewportChanged передает isStateStable. Resize сохраняет выбор и форму. VisualViewport при доступности помогает обеспечить достижимость focused input, но не является универсальным детектором клавиатуры.

## Insets и CTA

safeAreaInset / --tg-safe-area-inset-* описывают системные элементы, contentSafeAreaInset / --tg-content-safe-area-inset-* — элементы Telegram. Это разные области. CSS env(safe-area-inset-*) — возможный fallback системного inset вне bridge, а не еще одна копия того же отступа.

Вычисляйте safe area в одном shell с учетом контракта SDK: примененные insets и система координат. Не складывайте повторно env и Telegram system inset, не вкладывайте два контейнера с одинаковой компенсацией, не подменяйте разные области произвольным max без проверки геометрии. Проверьте bounds относительно обоих overlay в fullscreen/обычном режиме.

safeAreaChanged, contentSafeAreaChanged, viewportChanged и themeChanged подписываются по потребности; cleanup использует те же функции. Safe-area/fullscreen API зависят от версии; отсутствие поля дает fallback, а не NaN padding.

Выберите native MainButton или CTA страницы с доступным fallback. Fixed/sticky footer не перекрывает последние поля: его фактическая высота и соответствующие insets учтены в scrolling контенте. Проверьте длинную ошибку, landscape и клавиатуру; scrollIntoView не прыгает на каждый ввод.

## Проверка

Для нового пути: 320×568, 390×844, 768×1024, 1024×768, 1280×800, 480×720, плюс 390×420 как browser approximation клавиатуры. На планшете/ПК проверьте полезное использование ширины. Это критерии набора, не перечень проверенных физических устройств.

Измеряйте общий horizontal overflow и выполняйте действие. На форме проверьте длинные данные, focus, back, theme/resize, ошибку и черновик. Внутренний горизонтальный scroll допустим для действительно широких данных с доступной альтернативой по продукту.

Browser emulation и fake events проверяют собственный обработчик. Реальный bridge, клавиатура, zoom и fullscreen проверяются в целевых Telegram-клиентах; различайте эти результаты в отчете.
