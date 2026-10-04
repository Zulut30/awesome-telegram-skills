# Движение и assistive technology

## Переходы

Выбирай движение по смыслу: раскрытие деталей, переход шага, подтверждение локального изменения. Сохраняй существующую motion систему и бюджет; анимационная библиотека не обязательна. Не задерживай выполнение/показ результата ради эффекта.

Учитывай prefers-reduced-motion при первом рендере и изменении настройки. Сокращай/убирай несущественное движение, сохраняя смысл через статичное состояние. Выбранное пользователем уменьшение движения не должно отключать действие или обратную связь.

Для простых переходов transform/opacity часто дешевле layout изменений, но измерение важнее предположения. Не анимируй геометрию keyboard/safe area так, чтобы CTA оставалось вне доступной области. Отмена/быстрое повторное действие не оставляют transition в промежуточном состоянии.

Не полагайся только на animationend/transitionend: событие может не возникнуть при removed element, reduced motion или отмене. Жизненный цикл операции и cleanup независимы от декоративной анимации.

## Focus и объявления

Используй HTML семантику и связанный label/error. Для custom control выбирай подходящий APG pattern и проверяй клавиатуру; наличие role без поведения не делает его доступным.

Modal dialog получает имя, подходящий initial focus, замкнутый keyboard focus и недоступный background. Escape/back закрывают по одному переходу, затем focus возвращается к существующему инициатору или следующему логичному элементу. В длинном dialog initial focus может быть на заголовке; не прокручивай важное начало к последней кнопке.

При смене маршрута обозначай новый заголовок/контекст без перехвата focus на каждом resize/theme/refetch. Pending/success/error сообщаются подходящим status/live region, без повторных объявлений каждую секунду. Для валидации связаны поле и текст ошибки; summary дает путь исправления.

Native Telegram CTA имеет иной доступный контекст, чем DOM. Предусмотри доступный page action по возможностям клиента и не создавай два расходящихся submit handler.

## Проверка

Пройди Tab/Shift+Tab, активацию, dialog/back и ошибку формы. Повтори с reduced motion и увеличенным текстом. DOM accessibility tree и automated scan выявляют часть проблем, но не доказывают работу screen reader.

Если доступны VoiceOver/TalkBack/NVDA либо другой целевой reader, запиши конкретную версию, клиент, путь и наблюдаемое объявление/порядок focus. Без такой среды сохрани not-run и инструкцию ручной приемки; не заявляй соответствие WCAG по одному коэффициенту контраста.

Источники сверены 3 октября 2026 года: [APG Modal dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/), [WAI Forms notifications](https://www.w3.org/WAI/tutorials/forms/notifications/), [Animation from Interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html), [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion). Метод приемки выбирается по затронутому сценарию.
