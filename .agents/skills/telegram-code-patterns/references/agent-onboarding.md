# Когда агенту впервые передали библиотеку

Различайте исходный репозиторий, установленный пакет, архив и каталог одного скилла. Скилл не устанавливает runtime-зависимости. Пакеты пока локальные: используйте предоставленный wheel/tarball или явный путь к checkout, не предполагайте наличие в PyPI/npm.

1. Установите фактический стек и версию через `importlib.metadata.version('awesome-telegram-patterns')` / `npm ls @awesome-telegram/patterns`. Для одного предоставленного скилла нужны только его локальные references; полный репозиторий дает `components.json` и package README.
2. Выберите минимальный API по задаче. Python core не требует aiogram. Уже выбранные PTB/React/PostgreSQL сохраняйте; aiogram extra и DOM shell подходят только совместимому сценарию.
3. Найдите рецепт: `python -m telegram_patterns recipes "две кнопки" --sdk aiogram --context private`. `recipes --show two-columns` показывает код, `run-recipe two-columns` — требования, `run-recipe two-columns --offline` — закрытую fixture. Не выполняйте произвольный `recipe.code`; `ref.*` не является cookbook ID.
4. Подтвердите точный публичный import/тип по [справочнику API](api-reference.md) и установленному пакету. `ActionButton` / `action_menu` импортируются из `telegram_patterns.aiogram`; `validate_init_data` — из `telegram_patterns`. TypeScript type exports не являются runtime imports. Не придумывайте отсутствующий API.
5. Встройте компонент в текущий Dispatcher/router, storage или frontend и сохраните владение ресурсами. Разметка не проверяет ACL, подпись запуска не дает доступ к объекту, invoice не выдает товар. Unknown запись сверяется с прежним operation ID.
6. Выполните основной сценарий и существенный отказ на synthetic данных. Укажите версию и границы результата: SDK/mock/browser не доказывают live Telegram, платежи или физические устройства. Источники version-specific поведения находятся в нужном локальном reference.

При отсутствии пакета предложите установку из предоставленного источника в окружение проекта. Копирование всего набора навыков, смена SDK и новая инфраструктура не являются условием подключения одного helper.
