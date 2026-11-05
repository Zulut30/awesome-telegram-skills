# Доступность внешней приемки

5 ноября 2026 владелец проекта сообщил, что сейчас недоступны реальные устройства, тестовый Telegram-бот, платежные кабинеты и участники пилота; поручил продолжать доступную реализацию и проверки. Дополнительный платежный провайдер помимо четырех предусмотренных маршрутов ему не нужен.

Продолжаются исходный код, SDK construction, HTTP/SQLite/process-restart tests, browser/consumer/package checks, инструкции и подготовка воспроизводимых внешних сценариев. Данные настоящих пользователей, платежные операции и live/device/human/pilot результаты не создаются искусственно. Незавершенная внешняя приемка сохраняется в исходном регистре; готовность 1.0 из локальных результатов не выводится.

| Требование | Доступная работа | Недоступное доказательство |
| --- | --- | --- |
| 20, 88–89 | Воспроизводимые tasks, hashes, scoring и инструменты наблюдений | Независимый human+AI baseline и разработчики двух раундов |
| 45, 58, 60–70 | Browser/SDK/fallback/listener проверки и device scripts | Настоящий Telegram launch, системная клавиатура, physical tablet/iOS/Android, screen reader и weak-device замеры |
| 74–79 | Provider-specific contracts, authentic-fixture negatives, ledger/reconcile | Настоящий invoice/payment/refund и кабинеты трех провайдеров |
| 80 | Сохранить optional extension contract; не вводить случайный сервис | Дополнительный provider/use case не выбран и владельцу не требуется |
| 90, 96 | Готовый runtime, инструкции deploy/backup/restore/rollback | Пользовательский pilot и эксплуатация на выбранной инфраструктуре |
| 93–100 | Package metadata, license inventory, SBOM/provenance preparation, CI и release gates | Owner registry publishing setup, независимая приемка, production evidence и выпуск |

Этот документ фиксирует доступность ресурсов и решение продолжать работу. Он не помечает пункты выполненными и не понижает обязательные release gates.
