/** Synchronous selection storage. Caller retains resource/lifecycle ownership. */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
export type StorageFactory = () => KeyValueStorage;

/** Existing Fetch-compatible transport. No retry or connection is supplied. */
export type FetchTransport = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
