# Зрелость API и доказательства проверки

Пункт 2 плана 1.0. Политика действует в исходниках 0.6.0; это еще не опубликованный stable релиз. `components.json` — канонический статус каждой группы и всех ее публичных символов. API вне зарегистрированной группы не получает обещания стабильности; при добавлении экспорта его группа и статус должны быть определены. Python ошибки, DTO/protocols и TypeScript types наследуют статус API, к которому относятся.

| Maturity | Что обещает | Условие изменения |
| --- | --- | --- |
| `stable` | Документированное поведение в заявленном scope, support matrix и правила совместимости | Контракт, consumer artifact checks, negative/failure cases и необходимые live/device/provider проверки выполнены; ограничения явно приняты |
| `experimental` | Реализованный компонент с ограничениями; стабильность 1.0 пока не обещается | Stable только после приемки; изменения требуют changelog и миграции при несовместимости |
| `reference` | Справочный запрос/фрагмент, требующий прикладной композиции | Experimental после runnable workflow и существенных проверок; автоматического повышения при генерации нет |

В 0.6.0 все 24 группы компонентов имеют experimental. Это относится и к публичным errors/models, CLI, тестовому transport и CSS subpath соответствующих групп. Ни один символ не объявляется stable только потому, что импортируется или успешно собирается.

## Независимые уровни evidence

| Уровень | Что подтверждает | Чего не подтверждает |
| --- | --- | --- |
| `sdk` | Конкретный native request/model построен установленным SDK | HTTP, права, доставка, полный business workflow |
| `mock` | Композиция исполнена с synthetic transport | Сервер Telegram, реальные клиентские особенности, provider operations |
| `browser` | Конкретное browser взаимодействие и окружение | Физическое устройство, Telegram WebView и серверное подтверждение оплаты |
| `live` | Сценарий выполнен на указанном настоящем клиенте/сервисе | Другие версии, все платформы, полный стабильный контракт |
| `not_run` | Фрагмент не исполнен | Любой runtime успех |

Evidence присваивается сценарию и версии. Проверка отрисовки галереи не превращает все ее рецепты в browser/live workflows. Stable request builder может требовать локальных проверок его узкого контракта, но это не гарантия полного платежного/Telegram-сценария.

## Реализация и совместимость

`Recipe.maturity` доступен через Python API и JSON CLI. `RecipeCatalog.search(maturity=...)`, `telegram-patterns recipes --maturity ...` и filter галереи выбирают зрелость независимо от verification. Schema 1 сохраняется: field добавлен без удаления существующих; старые records без maturity принимаются с conservative default. Неверное явное значение отклоняется, evidence никогда автоматически не дает stable.

Snapshot 0.6.0: 14 experimental рецептов (11 keyboard builders + 3 mock compositions), 284 reference (185 request-only + 99 native fragments), 0 stable. Исполнение остается 196 sdk / 3 mock / 99 not_run / 0 live. Browser evidence галереи записывается в отдельный отчет о ее UI.

Контракт RecipeCatalog, bundled JSON, generator, CLI, gallery и копируемый навык согласованы. Версии Python/TypeScript/catalog/example совпадают. После обновления проверяются wheel/tarball consumer и Chrome, без переноса статуса старого артефакта на новые байты.
