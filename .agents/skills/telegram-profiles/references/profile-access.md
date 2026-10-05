# Доступность профиля

| Задача | API и условия |
| --- | --- |
| Базовые данные, включая доступный `is_premium` | [User](https://core.telegram.org/bots/api#user) из update или другого допустимого ответа |
| Фото и аудио профиля | [getUserProfilePhotos](https://core.telegram.org/bots/api#getuserprofilephotos), [getUserProfileAudios](https://core.telegram.org/bots/api#getuserprofileaudios) |
| Расширенный контекст private chat: доступные bio, дата рождения (`birthdate`), emoji status, personal chat | [getChat](https://core.telegram.org/bots/api#getchat), [ChatFullInfo](https://core.telegram.org/bots/api#chatfullinfo) |
| Последние сообщения чата, прикрепленного к профилю | [getUserPersonalChatMessages](https://core.telegram.org/bots/api#getuserpersonalchatmessages); это не произвольная личная переписка пользователя |
| MTProto-профиль | [users.getFullUser](https://core.telegram.org/method/users.getFullUser), [Telethon](https://docs.telethon.dev/en/stable/modules/client.html) с доступным peer |

`getChat` не является поиском любого private-пользователя по username. Для MTProto проверь caller eligibility и privacy конкретного метода. Авторизация пользовательского клиента не отменяет ограничения Telegram.

## Изменение профиля

| Цель | Маршрут и права |
| --- | --- |
| Собственный бот: имя и описания | [setMyName](https://core.telegram.org/bots/api#setmyname), [setMyDescription](https://core.telegram.org/bots/api#setmydescription), [setMyShortDescription](https://core.telegram.org/bots/api#setmyshortdescription); учитывать локализацию |
| Собственный бот: фото | [setMyProfilePhoto](https://core.telegram.org/bots/api#setmyprofilephoto), [removeMyProfilePhoto](https://core.telegram.org/bots/api#removemyprofilephoto); формат InputProfilePhoto |
| Подключенный Business-аккаунт | [setBusinessAccountName](https://core.telegram.org/bots/api#setbusinessaccountname), [setBusinessAccountUsername](https://core.telegram.org/bots/api#setbusinessaccountusername), [setBusinessAccountBio](https://core.telegram.org/bots/api#setbusinessaccountbio), [setBusinessAccountProfilePhoto](https://core.telegram.org/bots/api#setbusinessaccountprofilephoto); business_connection_id и соответствующие `can_edit_name` / `can_edit_username` / `can_edit_bio` / `can_edit_profile_photo` |
| Пользовательский MTProto-клиент: собственные имя и bio | [account.updateProfile](https://core.telegram.org/method/account.updateProfile); собственная авторизованная user session. Обертка business connection требует отдельной проверки прав |

Не применяй `setMy*` к профилю произвольного пользователя. Изменение username, фото или других полей через MTProto проверяй по отдельному методу и схеме; `account.updateProfile` не является универсальным editor всех полей.

Для rights используй поля [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights) и модели SDK. При сверке 3 октября 2026 года prose некоторых методов называла `can_change_name` / `can_change_username` / `can_change_bio`, но схема и проверенные Python SDK содержали `can_edit_*`. Не создавай отсутствующие поля по тексту описания метода; отдельно проверяй актуальность connection и нужное право.

Проверено 2 октября 2026 года. Для реализации проверяй поля установленного SDK и актуальную схему; raw Bot API и MTProto используют разные объекты.

5 октября 2026 отдельно повторно прочитаны User, getMe/getChat/ChatFullInfo, getUserProfilePhotos, own-bot set/getMyName/Description/ShortDescription и set/removeMyProfilePhoto/InputProfilePhotoStatic/Animated; сверены native модели установленного aiogram 3.31.0. [Готовая локальная композиция](profiles.md) сохраняет unknown/false, язык, omission/clear и текущий host ACL. Эта дата не обновляет Business/MTProto, profile audio/personal chat messages либо весь API.
