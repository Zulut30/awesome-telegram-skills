/** Framework-neutral view of a TelegramBridge: one bridge subscription and a stable latest snapshot. */
import type {BridgeSnapshot, TelegramBridge} from '../bridge.js';

export interface BridgeSource {
  /** The latest snapshot; the same object until a visible field changes, as React's external store requires. */
  current(): BridgeSnapshot;
  /** Calls onChange after each visible change; the last unsubscribe releases the bridge subscription. */
  subscribe(onChange: () => void): () => void;
}

const sources = new WeakMap<TelegramBridge, BridgeSource>();

export function bridgeSource(bridge: TelegramBridge): BridgeSource {
  const known = sources.get(bridge);
  if (known) return known;
  let current = bridge.snapshot();
  let currentKey = JSON.stringify(current);
  let detach: (() => void) | undefined;
  const listeners = new Set<() => void>();
  const update = (next: BridgeSnapshot): boolean => {
    const nextKey = JSON.stringify(next);
    if (nextKey === currentKey) return false;
    current = next;
    currentKey = nextKey;
    return true;
  };
  const source: BridgeSource = {
    // Without subscribers nothing tracks the bridge, so read it; the object stays the same if nothing changed.
    current: () => {
      if (!detach) update(bridge.snapshot());
      return current;
    },
    subscribe(onChange) {
      listeners.add(onChange);
      if (!detach) {
        detach = bridge.subscribe(next => {
          if (!update(next)) return;
          const failures: unknown[] = [];
          for (const listener of listeners) {
            try { listener(); } catch (error) { failures.push(error); }
          }
          if (failures.length === 1) throw failures[0];
          if (failures.length > 1) throw new AggregateError(failures, `${failures.length} framework listeners failed`);
        });
      }
      return () => {
        listeners.delete(onChange);
        if (listeners.size === 0 && detach) {
          const stop = detach;
          detach = undefined;
          stop();
        }
      };
    },
  };
  sources.set(bridge, source);
  return source;
}
