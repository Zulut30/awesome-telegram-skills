/** Svelte store over TelegramBridge: import from '@awesome-telegram/patterns/svelte'; implements the store contract
 * without importing svelte, so `$snapshot` works in Svelte 4 and 5 components. */
import type {BridgeSnapshot, TelegramBridge} from '../bridge.js';
import {bridgeSource} from './source.js';

export interface BridgeReadable {
  subscribe(run: (value: BridgeSnapshot) => void): () => void;
}

/** A readable store of the bridge snapshot. The host still calls bridge.start() once and bridge.dispose() on exit. */
export function telegramBridgeStore(bridge: TelegramBridge): BridgeReadable {
  const source = bridgeSource(bridge);
  return {
    subscribe(run) {
      run(source.current());
      return source.subscribe(() => run(source.current()));
    },
  };
}
