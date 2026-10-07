/** A stand-in for window.Telegram.WebApp so the views render in Node; a real Mini App passes the client's object. */
import type {TelegramWebApp} from '@awesome-telegram/patterns';

export interface DemoApp extends TelegramWebApp {
  colorScheme: string;
  /** Simulates the client firing an event the bridge listens to. */
  fire(event: string): void;
}

export function demoApp(): DemoApp {
  const listeners = new Map<string, Set<() => void>>();
  return {
    platform: 'tdesktop',
    colorScheme: 'light',
    themeParams: {bg_color: '#ffffff', text_color: '#222222', button_color: '#2481cc'},
    viewportStableHeight: 640,
    ready() {},
    onEvent(event, listener) { (listeners.get(event) ?? listeners.set(event, new Set()).get(event))?.add(listener); },
    offEvent(event, listener) { listeners.get(event)?.delete(listener); },
    fire(event) { for (const listener of listeners.get(event) ?? []) listener(); },
  };
}
