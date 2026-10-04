/** Host supplies its existing native SDK object; call only from an intended UI action. */
import { TelegramNativeAPI } from '@awesome-telegram/patterns';

export type ConfirmationResult = {status: 'unavailable' | 'confirmed' | 'cancelled' | 'error'};

export function showNativeConfirmation(nativeApp: unknown, onResult: (result: ConfirmationResult) => void): () => void {
  const api = new TelegramNativeAPI(nativeApp);
  let active = true, settled = false;
  const finish = (result: ConfirmationResult) => { if (active && !settled) { settled = true; onResult(result); } };
  if (!api.supports('showPopup')) { finish({status: 'unavailable'}); api.dispose(); return () => {}; }
  try {
    api.call('showPopup', {title: 'Подтверждение', message: 'Продолжить?', buttons: [
      {id: 'confirm', type: 'default', text: 'Продолжить'}, {id: 'cancel', type: 'cancel'},
    ]}, (id: unknown) => { finish({status: id === 'confirm' ? 'confirmed' : 'cancelled'}); });
  } catch { finish({status: 'error'}); }
  // Closing a screen suppresses its late callback. It does not close Telegram's popup.
  return () => { active = false; api.dispose(); };
}

export type LocationResult =
  | {status: 'unavailable' | 'denied' | 'error'}
  | {status: 'accepted'; latitude: number; longitude: number};

export function requestNativeLocation(nativeApp: unknown, onResult: (value: LocationResult) => void): () => void {
  const api = new TelegramNativeAPI(nativeApp);
  let active = true, requested = false, settled = false;
  const finish = (result: LocationResult) => { if (active && !settled) { settled = true; onResult(result); } };
  if (!api.supports('LocationManager.init') || !api.supports('LocationManager.getLocation')) {
    finish({status: 'unavailable'}); api.dispose(); return () => {};
  }
  try {
    api.call('LocationManager.init', () => {
      if (!active || requested) return;
      requested = true;
      try {
        api.call('LocationManager.getLocation', (value: unknown) => {
          if (value === null) { finish({status: 'denied'}); return; }
          if (typeof value !== 'object' || value === null || !('latitude' in value) || !('longitude' in value)
              || typeof value.latitude !== 'number' || !Number.isFinite(value.latitude) || Math.abs(value.latitude) > 90
              || typeof value.longitude !== 'number' || !Number.isFinite(value.longitude) || Math.abs(value.longitude) > 180) {
            finish({status: 'error'}); return;
          }
          finish({status: 'accepted', latitude: value.latitude, longitude: value.longitude});
        });
      } catch { finish({status: 'error'}); }
    });
  } catch { finish({status: 'error'}); }
  // The host cancels on navigation/account change and provides a manual address fallback.
  // No auto retry or permission loop; denied/unavailable are never accepted.
  return () => { active = false; api.dispose(); };
}
