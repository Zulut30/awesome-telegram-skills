/** Vue composable over TelegramBridge: import from '@awesome-telegram/patterns/vue'; Vue is an optional peer. */
import {computed, getCurrentScope, onScopeDispose, shallowRef, type ComputedRef} from 'vue';
import type {BridgeSnapshot, TelegramBridge} from '../bridge.js';
import {bridgeSource} from './source.js';

/**
 * A read-only ref with the bridge snapshot. Call it in setup() or an effectScope: the subscription ends with the
 * scope. The host still calls bridge.start() once and bridge.dispose() on exit.
 */
export function useTelegramBridge(bridge: TelegramBridge): ComputedRef<BridgeSnapshot> {
  const source = bridgeSource(bridge);
  const snapshot = shallowRef(source.current());
  const stop = source.subscribe(() => { snapshot.value = source.current(); });
  if (getCurrentScope()) onScopeDispose(stop);
  return computed(() => snapshot.value);
}
