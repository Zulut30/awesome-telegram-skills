# Проверка сценариев навыка для пункта 031

Проверен узкий маршрут `telegram-dialogs` → самостоятельный `references/dialog-restart.md`, а при явном переиспользовании библиотеки — `telegram-code-patterns` и тот же guide. Ни один соседний навык не является обязательным. Все 100 требований roadmap сохраняются; это приемка восстановления форм, не приемка следующих workers/inbox/outbox.

| Задача разработчика | Решение и исполняемое доказательство |
| --- | --- |
| Сохранить существующий Dispatcher/SDK и storage проекта | Добавить optional AtomicFSMStorage или supplied SnapshotStore; attach_dialog сохраняет Router, storage/isolation и help. SDK fixture в трех отдельных процессах |
| Продолжить введенный email после рестарта | Согласованный snapshot state/data/revision, schema_version и оригинальный deadline; отдельные draft/unknown/reconcile процессы, accepted values сохраняются |
| Просроченный черновик | Lazy cleanup только собственного marker/state, host data сохраняются; отдельный actor draft в restarted process и focused text test |
| Таймаут после записи заявки | submission_started хранится до service; SQLite effect/replay под тем же operation_id после рестарта и expiry, одна бизнес-запись |
| Новая версия формы или испорченный payload | Explicit migration/reconciliation; никакого reset даже после expiry. File record и snapshot сравниваются до/после отказа |
| Контакт ожидает подтверждения | Сохранены candidate/nonce/message, owner/step; restored candidate подтверждается существующей кнопкой после нового Dispatcher |
| Диск/старая revision/отмена записи | Ошибка до prompt/service; callback ACK не означает effect. Cancelled writer завершается до выхода из event isolation; CAS не повторяется автоматически |
| Чужой bot/chat/user/topic/Business/destiny | Все шесть SDK StorageKey полей раздельны в project SQLite; обычные формы не расширяются на группы/Business |
| Проект уже использует другой backend | Сохранить backend; реализовать транзакционный read/CAS, не устанавливать обязательный Redis/SQLite и не называть MemoryStorage durable |
| Несколько workers, remote exactly-once или настоящие Telegram-клиенты | Отдельная приемка и архитектура следующих пунктов; текущие локальные проверки не являются их доказательством |

`verify_dialog_restart_recipe.py` исполняет точный Python block скопированного guide через установленный SDK и temporary files. Проверены exact/missing/tampered/duplicate blocks и побайтовая сохранность caller files. Offline runner изолирует argv примера и восстанавливает caller argv: отдельный subprocess regression исполняет полный restart recipe при лишних служебных аргументах, сохраняя файл проекта. Галерея и public API examples отдельно исполняются из matching wheel. Root/skill static checks подтверждают структуру и ссылки; таблица фиксирует авторские решения и behavioral evidence, **не независимый AI rollout или человеческое исследование**. Пункт 020 остается pending.
