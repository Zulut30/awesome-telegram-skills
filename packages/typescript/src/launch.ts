/** One rule for "running inside Telegram", shared by TelegramBridge and TelegramNativeAPI. */
export function isInsideTelegram(app: unknown): boolean {
  // Outside a client the official script still creates Telegram.WebApp with platform 'unknown'.
  if (app === null || typeof app !== 'object') return false;
  const platform = (app as {platform?: unknown}).platform;
  return typeof platform === 'string' && platform !== '' && platform !== 'unknown';
}
