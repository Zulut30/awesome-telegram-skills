# Native Mini App API

Каталог функций текущего официального client API. `TelegramNativeAPI` проверяет version gate и наличие метода; permissions, параметры, результат callback и жизненный цикл экрана проверяет вызывающий код. Сигнатуры здесь справочные; wrapper не подменяет их полной TypeScript схемой SDK.

```typescript
import { TelegramNativeAPI } from "@awesome-telegram/patterns";
declare const nativeApp: unknown; // Host передает свой Telegram.WebApp.
const api = new TelegramNativeAPI(nativeApp);
if (api.supports("HapticFeedback.selectionChanged")) {
  api.call("HapticFeedback.selectionChanged");
}
const unsubscribe = api.supports("onEvent") && api.supports("offEvent")
  ? api.listen("themeChanged", () => { /* перечитать тему */ }) : () => {};
// При уходе с экрана:
unsubscribe();
api.dispose();
```

| Путь | Native сигнатура | Минимальная версия | Документация |
| --- | --- | --- | --- |
| `Accelerometer.start` | `start(params[, callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#accelerometer) |
| `Accelerometer.stop` | `stop([callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#accelerometer) |
| `BackButton.hide` | `hide()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#backbutton) |
| `BackButton.offClick` | `offClick(callback)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#backbutton) |
| `BackButton.onClick` | `onClick(callback)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#backbutton) |
| `BackButton.show` | `show()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#backbutton) |
| `BiometricManager.authenticate` | `authenticate(params[, callback])` | 7.2 | [Telegram](https://core.telegram.org/bots/webapps#biometricmanager) |
| `BiometricManager.init` | `init([callback])` | 7.2 | [Telegram](https://core.telegram.org/bots/webapps#biometricmanager) |
| `BiometricManager.openSettings` | `openSettings()` | 7.2 | [Telegram](https://core.telegram.org/bots/webapps#biometricmanager) |
| `BiometricManager.requestAccess` | `requestAccess(params[, callback])` | 7.2 | [Telegram](https://core.telegram.org/bots/webapps#biometricmanager) |
| `BiometricManager.updateBiometricToken` | `updateBiometricToken(token, [callback])` | 7.2 | [Telegram](https://core.telegram.org/bots/webapps#biometricmanager) |
| `CloudStorage.getItem` | `getItem(key, callback)` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#cloudstorage) |
| `CloudStorage.getItems` | `getItems(keys, callback)` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#cloudstorage) |
| `CloudStorage.getKeys` | `getKeys(callback)` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#cloudstorage) |
| `CloudStorage.removeItem` | `removeItem(key[, callback])` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#cloudstorage) |
| `CloudStorage.removeItems` | `removeItems(keys[, callback])` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#cloudstorage) |
| `CloudStorage.setItem` | `setItem(key, value[, callback])` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#cloudstorage) |
| `DeviceOrientation.start` | `start(params[, callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#deviceorientation) |
| `DeviceOrientation.stop` | `stop([callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#deviceorientation) |
| `DeviceStorage.clear` | `clear([callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#devicestorage) |
| `DeviceStorage.getItem` | `getItem(key, callback)` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#devicestorage) |
| `DeviceStorage.removeItem` | `removeItem(key[, callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#devicestorage) |
| `DeviceStorage.setItem` | `setItem(key, value[, callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#devicestorage) |
| `Gyroscope.start` | `start(params[, callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#gyroscope) |
| `Gyroscope.stop` | `stop([callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#gyroscope) |
| `HapticFeedback.impactOccurred` | `impactOccurred(style)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#hapticfeedback) |
| `HapticFeedback.notificationOccurred` | `notificationOccurred(type)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#hapticfeedback) |
| `HapticFeedback.selectionChanged` | `selectionChanged()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#hapticfeedback) |
| `LocationManager.getLocation` | `getLocation(callback)` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#locationmanager) |
| `LocationManager.init` | `init([callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#locationmanager) |
| `LocationManager.openSettings` | `openSettings()` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#locationmanager) |
| `MainButton.disable` | `disable()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.enable` | `enable()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.hide` | `hide()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.hideProgress` | `hideProgress()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.offClick` | `offClick(callback)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.onClick` | `onClick(callback)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.setParams` | `setParams(params)` | 9.5 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.setText` | `setText(text)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.show` | `show()` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `MainButton.showProgress` | `showProgress(leaveActive)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.disable` | `disable()` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.enable` | `enable()` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.hide` | `hide()` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.hideProgress` | `hideProgress()` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.offClick` | `offClick(callback)` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.onClick` | `onClick(callback)` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.setParams` | `setParams(params)` | 9.5 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.setText` | `setText(text)` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.show` | `show()` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecondaryButton.showProgress` | `showProgress(leaveActive)` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#bottombutton) |
| `SecureStorage.clear` | `clear([callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#securestorage) |
| `SecureStorage.getItem` | `getItem(key, callback)` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#securestorage) |
| `SecureStorage.removeItem` | `removeItem(key[, callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#securestorage) |
| `SecureStorage.restoreItem` | `restoreItem(key[, callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#securestorage) |
| `SecureStorage.setItem` | `setItem(key, value[, callback])` | 9.0 | [Telegram](https://core.telegram.org/bots/webapps#securestorage) |
| `SettingsButton.hide` | `hide()` | 7.0 | [Telegram](https://core.telegram.org/bots/webapps#settingsbutton) |
| `SettingsButton.offClick` | `offClick(callback)` | 7.0 | [Telegram](https://core.telegram.org/bots/webapps#settingsbutton) |
| `SettingsButton.onClick` | `onClick(callback)` | 7.0 | [Telegram](https://core.telegram.org/bots/webapps#settingsbutton) |
| `SettingsButton.show` | `show()` | 7.0 | [Telegram](https://core.telegram.org/bots/webapps#settingsbutton) |
| `addToHomeScreen` | `addToHomeScreen()` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `checkHomeScreenStatus` | `checkHomeScreenStatus([callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `close` | `close()` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `closeScanQrPopup` | `closeScanQrPopup()` | 6.4 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `disableClosingConfirmation` | `disableClosingConfirmation()` | 6.2 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `disableVerticalSwipes` | `disableVerticalSwipes()` | 7.7 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `downloadFile` | `downloadFile(params[, callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `enableClosingConfirmation` | `enableClosingConfirmation()` | 6.2 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `enableVerticalSwipes` | `enableVerticalSwipes()` | 7.7 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `exitFullscreen` | `exitFullscreen()` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `expand` | `expand()` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `hideKeyboard` | `hideKeyboard()` | 9.1 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `isVersionAtLeast` | `isVersionAtLeast(version)` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `lockOrientation` | `lockOrientation()` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `offEvent` | `offEvent(eventType, eventHandler)` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `onEvent` | `onEvent(eventType, eventHandler)` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `openInvoice` | `openInvoice(url[, callback])` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `openLink` | `openLink(url[, options])` | 6.4 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `openTelegramLink` | `openTelegramLink(url)` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `readTextFromClipboard` | `readTextFromClipboard([callback])` | 6.4 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `ready` | `ready()` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `requestChat` | `requestChat(req_id[, callback])` | 9.6 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `requestContact` | `requestContact([callback])` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `requestEmojiStatusAccess` | `requestEmojiStatusAccess([callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `requestFullscreen` | `requestFullscreen()` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `requestWriteAccess` | `requestWriteAccess([callback])` | 6.9 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `sendData` | `sendData(data)` | 6.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `setBackgroundColor` | `setBackgroundColor(color)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `setBottomBarColor` | `setBottomBarColor(color)` | 7.10 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `setEmojiStatus` | `setEmojiStatus(custom_emoji_id[, params, callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `setHeaderColor` | `setHeaderColor(color)` | 6.1 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `shareMessage` | `shareMessage(msg_id[, callback])` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `shareToStory` | `shareToStory(media_url[, params])` | 7.8 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `showAlert` | `showAlert(message[, callback])` | 6.2 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `showConfirm` | `showConfirm(message[, callback])` | 6.2 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `showPopup` | `showPopup(params[, callback])` | 6.2 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `showScanQrPopup` | `showScanQrPopup(params[, callback])` | 6.4 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `switchInlineQuery` | `switchInlineQuery(query[, choose_chat_types])` | 6.7 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |
| `unlockOrientation` | `unlockOrientation()` | 8.0 | [Telegram](https://core.telegram.org/bots/webapps#initializing-mini-apps) |

## События

`accelerometerChanged`, `accelerometerFailed`, `accelerometerStarted`, `accelerometerStopped`, `activated`, `backButtonClicked`, `biometricAuthRequested`, `biometricManagerUpdated`, `biometricTokenUpdated`, `clipboardTextReceived`, `contactRequested`, `contentSafeAreaChanged`, `deactivated`, `deviceOrientationChanged`, `deviceOrientationFailed`, `deviceOrientationStarted`, `deviceOrientationStopped`, `emojiStatusAccessRequested`, `emojiStatusFailed`, `emojiStatusSet`, `fileDownloadRequested`, `fullscreenChanged`, `fullscreenFailed`, `gyroscopeChanged`, `gyroscopeFailed`, `gyroscopeStarted`, `gyroscopeStopped`, `homeScreenAdded`, `homeScreenChecked`, `invoiceClosed`, `locationManagerUpdated`, `locationRequested`, `mainButtonClicked`, `popupClosed`, `qrTextReceived`, `safeAreaChanged`, `scanQrPopupClosed`, `secondaryButtonClicked`, `settingsButtonClicked`, `shareMessageFailed`, `shareMessageSent`, `themeChanged`, `viewportChanged`, `writeAccessRequested`.

Обычный браузер и mock не подтверждают поддержку настоящим Telegram-клиентом. Методы с user interaction / init / permissions вызывайте в указанном документацией порядке; callback может означать отказ или отмену, а отсутствие синхронной ошибки не означает успех. Отписки для `onClick`/`onEvent`, вызванных напрямую через call, принадлежат вам; listen управляет только своими подписками.
