# Найти пример по задаче, контексту и версии — 0.12.0

Галерея содержит 302 запись: 11 keyboard/input builders, 185 Bot API requests, 99 native fragments, 5 bot fixtures и SQLite recovery fixture. Поиск и выбор не исполняют найденный код. Из них 18 experimental и 284 reference; 196 sdk, 7 mock, 99 not_run. Stable/live не заявлены.

Главный поиск понимает «две кнопки», «назад», «потерянный ответ»; результаты ранжируются по названию и keywords. Задача доступна сразу; контекст, SDK/снимок, версия API, раздел, зрелость и уровень проверки — в «Другие фильтры». На телефоне блок свернут при первом входе. Фильтры пересекаются; «Сбросить» очищает их и возвращает фокус в поиск. При смене SDK несовместимая выбранная версия сбрасывается. В версии API `mini:*` — минимум native документации, а не обещание работы клиента.

«Назад» находит разметку с callback и native BackButton fragments. Это не готовая история экранов: обработчик, state и права принадлежат приложению. «Потерянный ответ» находит полный локальный SQLite сценарий: effect уже сохранен, unknown outcome сверяется тем же authorized scoped key; второй заказ не создается. Actor fixture не доказывает реальную session/ACL.

Context tags обозначают проверенный поднабор подходящих вариантов примера/контракта. `unspecified` значит «уточнить контекст», а не «все чаты». Private helper defaults не доказывают права на отправку; Business tag не означает MTProto user session. У большинства request-only records контекст намеренно не обобщается. SDK version — конкретная установленная версия; WebApp использует явно названный snapshot, без придуманной версии SDK или Telegram-клиента.

## SDK-free Python и CLI

Предоставленный wheel работает без aiogram для поиска. Source/check links указывают на дерево репозитория или standalone export; wheel не требует наличия этих файлов при выполнении.

```python
from telegram_patterns import RecipeCatalog

catalog = RecipeCatalog()
rows = catalog.search("две кнопки", task="keyboards", context="private",
                      sdk="aiogram", sdk_version="3.31.0", api_version="bot:10.3")[0]
assert rows.id == "two-columns" and rows.source_files and rows.check_files
lost = catalog.search("потерянный ответ", task="recovery", context="backend")[0]
assert lost.id == "demo-recovery" and lost.sdk == "python-core"
assert catalog.search("потерянный ответ", context="private") == ()
```

```text
python -m telegram_patterns recipes "две кнопки" --task keyboards --context private --sdk aiogram --sdk-version 3.31.0
python -m telegram_patterns recipes "назад" --sdk telegram-webapp
python -m telegram_patterns recipes "потерянный ответ" --task recovery --context backend
```

Old schema 1 без новых metadata fields сохраняется: задачи/ссылки пусты, context/sdk/versions unspecified. Новые filters optional; прежние imports и CLI поля сохранены. Новые поля Recipe — immutable tuples и строки; source paths не принимают URL/traversal. Category остается разделом, task — пользовательским намерением.

## Исходники и проверка

Карточка показывает точную версию и ограничения, ссылки «Исходники» и «Код проверки». Последняя ведет к исполняемому проверяющему коду; это не ссылка на готовый production сервис или заявление о свежем live PASS. HTTPS docs остаются отдельными ссылками. Некорректные пути не становятся кликабельными ссылками.

При `build_recipe_gallery.py --output-dir <NEW_EXPORT>` экспорт копирует связанные source/check files byte-for-byte в files/, HTML указывает на них. Галерея работает с file URL без HTTP. Это статическое представление исходников, не runnable проект с установленными зависимостями. `--check` проверяет drift и не меняет существующие файлы; unrelated notes сохраняются. Известные symlink/junction paths отклоняются до записи.

Standalone skill достаточно этого reference и предоставленного wheel; соседние навыки и исходный репозиторий не обязательны для SDK-free search. Для конкретной композиции выбирайте соответствующий локальный API reference.

## Сверенные источники

4 октября 2026 проверены private/supergroup topics и ограничение restrictChatMember, channel subscription invite и Business gift rights в [официальном Bot API](https://core.telegram.org/bots/api). Private defaults проверены в native_keyboards.py; runtime generation сверяет установленный aiogram 3.31.0 с snapshot. Остальные context tags не выдаются за новую полную ревизию Telegram API. Полная public support matrix и реальные клиенты остаются отдельными задачами.

Поиск «календарь» с task=input/context=private/SDK=aiogram находит demo-calendar: date/time/back, timezone и transactional booking. Это mock Dispatcher/file SQLite evidence, не live device rendering.
