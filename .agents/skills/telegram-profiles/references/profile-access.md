# Доступность профиля

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

| Задача | API и условия |
| --- | --- |
| Базовые данные, включая доступный `is_premium` | [User](https://core.telegram.org/bots/api#user) из update или другого допустимого ответа |
| Фото и аудио профиля | [getUserProfilePhotos](https://core.telegram.org/bots/api#getuserprofilephotos), [getUserProfileAudios](https://core.telegram.org/bots/api#getuserprofileaudios) |
| Расширенный контекст private chat: доступные bio, дата рождения (`birthdate`), emoji status, personal chat | [getChat](https://core.telegram.org/bots/api#getchat), [ChatFullInfo](https://core.telegram.org/bots/api#chatfullinfo) |
| Последние сообщения чата, прикрепленного к профилю | [getUserPersonalChatMessages](https://core.telegram.org/bots/api#getuserpersonalchatmessages); это не произвольная личная переписка пользователя |
| MTProto-профиль | [users.getFullUser](https://core.telegram.org/method/users.getFullUser), [Telethon](https://docs.telethon.dev/en/stable/modules/client.html) с доступным peer |

`getChat` не является поиском любого private-пользователя по username. Для MTProto проверьте caller eligibility и privacy конкретного метода. Авторизация пользовательского клиента не отменяет ограничения Telegram.

## Изменение профиля

| Цель | Маршрут и права |
| --- | --- |
| Собственный бот: имя и описания | [setMyName](https://core.telegram.org/bots/api#setmyname), [setMyDescription](https://core.telegram.org/bots/api#setmydescription), [setMyShortDescription](https://core.telegram.org/bots/api#setmyshortdescription); учитывать локализацию |
| Собственный бот: фото | [setMyProfilePhoto](https://core.telegram.org/bots/api#setmyprofilephoto), [removeMyProfilePhoto](https://core.telegram.org/bots/api#removemyprofilephoto); формат InputProfilePhoto |
| Подключенный Business-аккаунт | [setBusinessAccountName](https://core.telegram.org/bots/api#setbusinessaccountname), [setBusinessAccountUsername](https://core.telegram.org/bots/api#setbusinessaccountusername), [setBusinessAccountBio](https://core.telegram.org/bots/api#setbusinessaccountbio), [setBusinessAccountProfilePhoto](https://core.telegram.org/bots/api#setbusinessaccountprofilephoto); business_connection_id и соответствующие `can_edit_name` / `can_edit_username` / `can_edit_bio` / `can_edit_profile_photo` |
| Пользовательский MTProto-клиент: собственные имя и bio | [account.updateProfile](https://core.telegram.org/method/account.updateProfile); собственная авторизованная user session. Обертка business connection требует отдельной проверки прав |

Не применяйте `setMy*` к профилю произвольного пользователя. Изменение username, фото или других полей через MTProto проверяйте по отдельному методу и схеме; `account.updateProfile` не является универсальным editor всех полей.

Для rights используйте поля [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights) и модели SDK. При сверке 3 октября 2026 года prose некоторых методов называла `can_change_name` / `can_change_username` / `can_change_bio`, но схема и проверенные Python SDK содержали `can_edit_*`. Не создавайте отсутствующие поля по тексту описания метода; отдельно проверяйте актуальность connection и нужное право.

Проверено 2 октября 2026 года. Для реализации проверяйте поля установленного SDK и актуальную схему; raw Bot API и MTProto используют разные объекты.

5 октября 2026 отдельно повторно прочитаны `User`, `getMe`, `getChat`, `ChatFullInfo`, `getUserProfilePhotos`, методы профиля своего бота (`setMyName`, `getMyName`, `setMyDescription`, `getMyDescription`, `setMyShortDescription`, `getMyShortDescription`, `setMyProfilePhoto`, `removeMyProfilePhoto`) и `InputProfilePhotoStatic`/`InputProfilePhotoAnimated`; сверены модели установленного aiogram 3.31.0. [Готовая локальная композиция](profiles.md) различает «неизвестно» и `false`, учитывает язык, пропуск и очистку значения и текущие права проекта. Эта дата не относится к Business, MTProto, аудио профиля, сообщениям личного канала и остальному API.
