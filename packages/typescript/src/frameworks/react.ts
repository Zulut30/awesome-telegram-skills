/** React hook over TelegramBridge: import from '@awesome-telegram/patterns/react'; React is an optional peer. */
import {useSyncExternalStore} from 'react';
import type {BridgeSnapshot, TelegramBridge} from '../bridge.js';
import {bridgeSource} from './source.js';

/** The bridge snapshot for rendering. The host still calls bridge.start() once and bridge.dispose() on exit. */
export function useTelegramBridge(bridge: TelegramBridge): BridgeSnapshot {
  const source = bridgeSource(bridge);
  return useSyncExternalStore(source.subscribe, source.current, source.current);
}
