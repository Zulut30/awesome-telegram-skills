# Файловые границы и worker

## Источник

Telegram getFile дает путь загрузки; URL содержит bot token, поэтому его нельзя отдавать frontend или записывать в логи. Скачивание имеет deadline и счетчик фактически полученных bytes, даже если metadata/Content-Length отсутствуют. Для Mini App upload личность и object access определяет backend.

Произвольный внешне переданный URL требует отдельного контракта загрузки: разрешенные destinations, redirect проверка, DNS/IP и лимиты. Не используйте media parser как сетевой downloader пользовательского URL. Локальный Bot API может вернуть локальный file_path; не разрешайте клиенту подставить свой путь вместо результата доверенного API.

## Process и результат

Для subprocess используйте массив аргументов и server-owned пути. Ограничьте протоколы/файловую область и сеть parser по задаче; для FFmpeg/ffprobe сверьте protocol_whitelist и возможности установленной сборки. Whitelist не заменяет filesystem/process isolation и ограничение ресурсов.

Файл с заголовком допустимого media может все равно вызвать ошибку/нагрузку parser. Probe также требует timeout и лимиты. Ограничивайте decoded dimensions/frames/duration и растущий output; shell=False сам по себе не защищает от чтения внешних ресурсов media parser.

При timeout/cancel заверши запущенные процессы, дождитесь завершения и очистите temp. Публикуйте результат после успешного exit и проверки фактического output; partial файл не равен ready. Для атомарной публикации полезен rename внутри одного filesystem или контракт object storage.

## Идентичность и повтор

Dedup преобразования зависит от владельца/прав, input hash и transform version/options. Совпадение файла не дает чужому пользователю доступ к приватному output. Lease/fencing предотвращает публикацию устаревшего worker после отмены/restart.

file_id применяется для скачивания/повторной отправки в контексте соответствующего бота; не переносится между ботами. file_unique_id не является usable file_id и не служит доказательством владения. Сохраняйте тип результата; ограничения thumbnail и media format проверяются у конкретного метода.

Успех send и успех transform — разные состояния. Потерянный ответ отправки может означать доставленное сообщение: повтор определяется политикой продукта, не обещанием exactly-once Bot API.

Источники сверены 3 октября 2026 года: [File](https://core.telegram.org/bots/api#file), [getFile](https://core.telegram.org/bots/api#getfile), [Local Bot API](https://core.telegram.org/bots/api#using-a-local-bot-api-server), [FFmpeg protocols](https://ffmpeg.org/ffmpeg-protocols.html), [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html). Числовые лимиты конкретного пути сверяйте при реализации.
