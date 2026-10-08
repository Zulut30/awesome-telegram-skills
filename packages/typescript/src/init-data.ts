import {PatternError, UnsupportedCapability, ValidationFailure} from './errors.js';

/** Telegram's Ed25519 keys for third-party initData validation, hex (core.telegram.org/bots/webapps). */
export const TELEGRAM_PUBLIC_KEYS = Object.freeze({
  production: 'e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d',
  test: '40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec',
} as const);

/** Untrusted launch data was rejected; messages never include the raw input. */
export class InvalidInitData extends PatternError {
  constructor(message?: string) { super('invalid-init-data', 'rejected', message); }
}

export type SignedObject = Readonly<Record<string, unknown>>;

/** Signed launch fields after verification; nested JSON is frozen. */
export interface SignedLaunch {
  readonly userId: number;
  readonly authDate: number;
  readonly user: SignedObject;
  readonly queryId?: string;
  readonly chatType?: string;
  readonly chatInstance?: string;
  readonly startParam?: string;
  readonly canSendAfter?: number;
  readonly chat?: SignedObject;
  readonly receiver?: SignedObject;
}

export interface InitDataSignatureOptions {
  /** Which published key to use; default production. */
  readonly environment?: keyof typeof TELEGRAM_PUBLIC_KEYS;
  /** 32 raw bytes replacing the published key, e.g. after a key change announced by Telegram. */
  readonly publicKey?: Uint8Array;
  /** Current Unix time in seconds; default the system clock. */
  readonly now?: number;
  readonly maxAgeSeconds?: number;
  readonly futureToleranceSeconds?: number;
  readonly maxLength?: number;
  /** WebCrypto implementation; default globalThis.crypto.subtle (browsers, Node 20+). */
  readonly subtle?: SubtleCrypto;
}

const SIGNATURE = /^[A-Za-z0-9_-]{86}(?:==)?$/;

function integer(value: unknown, minimum: number, name: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum) throw new ValidationFailure(`Invalid ${name}`);
  return value;
}

function decode(part: string): string {
  try {
    return decodeURIComponent(part.replace(/\+/g, ' '));
  } catch {
    throw new InvalidInitData('Invalid launch encoding');
  }
}

function fields(raw: string, maxLength: number): Map<string, string> {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > maxLength) throw new InvalidInitData('Invalid launch data size');
  if (/%(?![0-9a-fA-F]{2})/.test(raw)) throw new InvalidInitData('Invalid URL encoding');
  const parts = raw.split('&');
  if (parts.length > 64) throw new InvalidInitData('Invalid launch encoding');
  const result = new Map<string, string>();
  for (const part of parts) {
    const separator = part.indexOf('=');
    if (separator < 0) throw new InvalidInitData('Invalid launch encoding');
    const key = decode(part.slice(0, separator));
    if (!key || result.has(key)) throw new InvalidInitData('Ambiguous launch fields');
    result.set(key, decode(part.slice(separator + 1)));
  }
  return result;
}

function hexBytes(hex: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(hex.match(/../g) ?? [], (pair) => Number.parseInt(pair, 16));
}

function base64url(value: string): Uint8Array<ArrayBuffer> {
  const text = atob(value.replace(/=+$/, '').replace(/-/g, '+').replace(/_/g, '/') + '==');
  return Uint8Array.from(text, (character) => character.charCodeAt(0));
}

function frozen(value: unknown): unknown {
  if (value !== null && typeof value === 'object') {
    for (const item of Object.values(value)) frozen(item);
    Object.freeze(value);
  }
  return value;
}

function object(data: Map<string, string>, name: string): SignedObject | undefined {
  const text = data.get(name);
  if (text === undefined) return undefined;
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new InvalidInitData(`Invalid ${name}`);
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new InvalidInitData(`Invalid ${name}`);
  return frozen(value) as SignedObject;
}

function launch(data: Map<string, string>, now: number, maxAge: number, tolerance: number): SignedLaunch {
  const auth = data.get('auth_date') ?? '';
  if (!/^[0-9]{1,20}$/.test(auth) || !Number.isSafeInteger(Number(auth))) throw new InvalidInitData('Invalid auth_date');
  const authDate = Number(auth);
  const age = now - authDate;
  if (age < -tolerance || age >= maxAge) throw new InvalidInitData('Launch data outside freshness policy');
  const user = object(data, 'user');
  const chat = object(data, 'chat');
  const receiver = object(data, 'receiver');
  const id = user?.['id'];
  if (user === undefined || typeof id !== 'number' || !Number.isSafeInteger(id) || id <= 0) {
    throw new InvalidInitData('Missing signed user identity');
  }
  const canSendAfter = data.get('can_send_after');
  if (canSendAfter !== undefined && !/^[0-9]{1,10}$/.test(canSendAfter)) throw new InvalidInitData('Invalid can_send_after');
  const result: Record<string, unknown> = {userId: id, authDate, user};
  const optional: Array<[string, string]> = [['queryId', 'query_id'], ['chatType', 'chat_type'], ['chatInstance', 'chat_instance'], ['startParam', 'start_param']];
  for (const [property, field] of optional) {
    const value = data.get(field);
    if (value !== undefined) result[property] = value;
  }
  if (canSendAfter !== undefined) result['canSendAfter'] = Number(canSendAfter);
  if (chat !== undefined) result['chat'] = chat;
  if (receiver !== undefined) result['receiver'] = receiver;
  return Object.freeze(result) as unknown as SignedLaunch;
}

/**
 * Third-party validation of raw initData without the bot token: the Ed25519 `signature` field
 * checked with Telegram's public key. The signed string is "<botId>:WebAppData" and every field except
 * hash and signature, sorted, one per line. A result authenticates launch data only: sessions,
 * object permissions and replay protection stay with the service.
 */
export async function verifyInitDataSignature(raw: string, botId: number, options: InitDataSignatureOptions = {}): Promise<SignedLaunch> {
  integer(botId, 1, 'botId');
  const maxAge = integer(options.maxAgeSeconds ?? 3600, 1, 'maxAgeSeconds');
  const tolerance = integer(options.futureToleranceSeconds ?? 30, 0, 'futureToleranceSeconds');
  const maxLength = integer(options.maxLength ?? 16384, 1, 'maxLength');
  const now = options.now === undefined ? Math.floor(Date.now() / 1000) : integer(options.now, 0, 'now');
  let key: Uint8Array;
  if (options.publicKey !== undefined) {
    if (!(options.publicKey instanceof Uint8Array) || options.publicKey.length !== 32) throw new ValidationFailure('publicKey must be 32 raw bytes');
    key = options.publicKey;
  } else {
    const environment = options.environment ?? 'production';
    if (environment !== 'production' && environment !== 'test') throw new ValidationFailure("environment must be 'production' or 'test'");
    key = hexBytes(TELEGRAM_PUBLIC_KEYS[environment]);
  }
  const subtle = options.subtle ?? globalThis.crypto?.subtle;
  if (subtle === undefined) throw new UnsupportedCapability('WebCrypto is not available');
  const data = fields(raw, maxLength);
  const signature = data.get('signature') ?? '';
  if (!SIGNATURE.test(signature)) throw new InvalidInitData('Invalid signature');
  data.delete('signature');
  data.delete('hash');
  const check = `${botId}:WebAppData\n` + [...data.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
    .map((name) => `${name}=${data.get(name)}`).join('\n');
  let verified: boolean;
  try {
    const imported = await subtle.importKey('raw', new Uint8Array(key), {name: 'Ed25519'}, false, ['verify']);
    verified = await subtle.verify({name: 'Ed25519'}, imported, base64url(signature), new TextEncoder().encode(check));
  } catch {
    throw new UnsupportedCapability('Ed25519 is not supported by this WebCrypto');
  }
  if (!verified) throw new InvalidInitData('Invalid signature');
  return launch(data, now, maxAge, tolerance);
}
