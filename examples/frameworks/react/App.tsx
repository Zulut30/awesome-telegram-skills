/** React view: useTelegramBridge re-renders on theme and viewport changes; the host owns the bridge lifecycle. */
import type {TelegramBridge} from '@awesome-telegram/patterns';
import {useTelegramBridge} from '@awesome-telegram/patterns/react';

export function App({bridge}: {bridge: TelegramBridge}) {
  const snapshot = useTelegramBridge(bridge);
  return (
    <main data-scheme={snapshot.colorScheme} style={{background: snapshot.theme['bg_color'], color: snapshot.theme['text_color']}}>
      <h1>{snapshot.insideTelegram ? 'Telegram' : 'Browser'}</h1>
      <p>Scheme: {snapshot.colorScheme}; height: {snapshot.stableHeight ?? 'unknown'}</p>
    </main>
  );
}
