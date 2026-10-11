# Авторская проверка навыков для пункта 032

Узкий запрос о повторе подтверждения или нескольких workers направляется в самостоятельный `references/concurrent-actions.md` навыка `telegram-code-patterns`; подтверждение FSM дополнительно доступно из `telegram-dialogs` без обязательного соседнего навыка. Backend/SDK/Dispatcher не заменяется ради примера. Таблица фиксирует авторские решения и исполняемые пробы, а не независимый agent rollout или человеческое исследование.

| Запрос разработчика | Решение и проверяемое поведение |
| --- | --- |
| Два worker получили одну кнопку | Серверный persistent intent, original operation ID, current checks/effect/receipt в одной транзакции. Два отдельных SDK Dispatcher процесса дают new/replay и одну business row |
| Разные операции подтвердили одну revision | Исходная domain revision входит в payload; current revision проверяется внутри writer transaction, одна операция accepted, вторая stale |
| Права отозваны после первого успеха | Current ACL проверяется до replay; сохраненный receipt не раскрывается, effect не вызывается |
| Чужой автор, bot/chat/topic/message | Native authenticated origin сравнивается с persistent binding; callback не задает actor/target/revision. Native/private/group/topic source probes и exact denied feedback |
| Потерян feedback после записи | Сверить исходный intent и ID; второй независимый процесс возвращает receipt, повторная запись отсутствует. Cancelled waiter дожидается owned work |
| Кнопка в группе или конкретном topic | Positive ordinary group и forum supergroup scenario, exact topic binding и неверный topic отказ; native rights/live clients не выводятся из mock |
| SDK считает date=0 обычным Message | Проверять и доступность, и date, и sender. Наблюдавшийся synthetic regression отклонил date=0 только после явной проверки; Bot API source подтверждает маркер |
| Старый run/OnceStore или другая БД проекта | Legacy API сохраняется; optional GuardedOnceStore выражает host contract, его atomicity доказывает сам backend. SQLite не является обязательной миграцией |
| Guard пытается commit/update/pragma | Read-only guard authorizer отклоняет операцию; effect/receipt/revision остаются неизменными. Apply commit/rollback/executescript и invalid result полностью откатываются |
| Русская клавиатура или pending feedback | SDK behavior проверяет читаемые «Подтвердить», «Отправить», contact label, review и unknown/frozen feedback; исправлена существовавшая двойная кодировка |

Полная проверка установленного wheel/tarball, автономного copied guide, gallery export и matching first run фиксируется отдельно в приемке 032. Source/core probes не подменяют ее. `verify_concurrent_actions_recipe.py` выполняет exact guide, проверяет missing/tampered/duplicate blocks до исполнения и сохраняет caller files побайтово. Это trusted package helper, не OS sandbox. Telegram HTTP, реальные клиентские устройства, удаленные платежные эффекты и независимая usability пока не приняты; пункт 020 остается pending.
