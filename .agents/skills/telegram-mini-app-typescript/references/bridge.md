# Bridge и SDK

Термины: **fallback** — запасной вариант, если основная возможность недоступна.

Native bridge `Telegram.WebApp` описан в [Telegram Mini Apps](https://core.telegram.org/bots/webapps). TypeScript wrappers могут принадлежать сторонним разработчикам; не называйте их официальным SDK Telegram без подтверждения.

Перед выбором wrapper проверьте первичный репозиторий, опубликованный пакет, совместимость со стеком, актуальность поддержки и нужные методы. Не устанавливайте несколько поколений SDK одновременно. Сохраняйте lockfile и точные импорты выбранного пакета.

Adapter должен возвращать доступность возможности отдельно от ее типового описания. Наличие метода в declaration не доказывает, что текущий клиент Telegram его поддерживает. При недоступности используйте предусмотренное UX-состояние.

Каждая подписка должна иметь симметричную очистку. Инициализация при повторном mount не должна добавлять несколько отправок для одного пользовательского действия. В React, Vue или другом framework соблюдайте его lifecycle, не подменяя его SDK callbacks.

Browser mock предназначен для верстки и локальных тестов. Он не дает подписанную Telegram-личность. При проверке runtime зафиксируйте client, точку запуска и фактические bridge events.

Native script может создать Telegram.WebApp и вне Telegram. Разделяйте наличие объекта, launch context, client capability и авторизованную backend-сессию. Для запуска без подписанных данных не выводите автоматически ошибку подписи: контекст зависит от точки запуска, а режим доступа определяется продуктом.

Platform adapter предоставляет снимок геометрии/темы и unsubscribe, а не пересоздает приложение при каждом resize. Различайте viewportHeight и viewportStableHeight; stable state передается событием viewportChanged. Insets системы и Telegram контента имеют отдельные поля. Не пишите конкурирующие значения native --tg-* CSS variables из нескольких компонентов; нормализованные --app-* переменные принадлежат одному shell.

BackButton/MainButton callbacks используют те же ссылки при cleanup. При remount или смене экрана один click дает одно действие. Проверяйте capability и предусмотренный fallback, включая клиента без native-кнопки.

Если cleanup выполняется на pagehide, учитывайте event.persisted: документ может быть заморожен в back/forward cache, затем восстановлен без нового bootstrap. Безусловный destroy с одноразовым pagehide listener оставит восстановленный UI без resize/bridge callbacks. Сохраните необходимые подписки либо восстановите их и текущий snapshot на pageshow; фактическое закрытие/unmount очищает ресурсы. Проверьте resize и back после такого восстановления, не только первый mount.

Источники lifecycle: [pagehide и persisted](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event), [back/forward cache](https://web.dev/articles/bfcache).
