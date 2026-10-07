/** Type consumer, compiled against the installed tarball by distribution checks. */
import {
  ApiClient, TelegramBridge, createTextField, safeErrorReport, SelectionDraftStore,
  type AppShell, type BridgeSnapshot, type ClientOptions, type DraftOptions,
  type DraftRead, type FailureKind, type Insets, type RequestOptions,
  type SelectionDraft, type TelegramNativeEvent, type TelegramNativeMethod,
  type TelegramWebApp, type TextFieldControl, type ErrorReport, type OperationKind,
  type KeyValueStorage, type StorageFactory, type FetchTransport,
} from '@awesome-telegram/patterns';

export function connect(app: TelegramWebApp | undefined, document: Document): TextFieldControl {
  const bridge = new TelegramBridge(app);
  const snapshot: BridgeSnapshot = bridge.snapshot();
  const field: TextFieldControl = createTextField(document, 'Name');
  field.setError(snapshot.insideTelegram ? null : 'Open Telegram');
  bridge.dispose();
  return field;
}

export async function load(options: ClientOptions, request: RequestOptions): Promise<number> {
  return new ApiClient(options).request('/count', value => {
    if (typeof value !== 'number') throw Error('Bad count');
    return value;
  }, request);
}

// These are deliberate negative type assertions: the compiler must reject
// accidental broadening of documented literal unions and error value shapes.
// @ts-expect-error not a Telegram method path
export const badMethod: TelegramNativeMethod = 'invented.call';
// @ts-expect-error not a documented native event
export const badEvent: TelegramNativeEvent = 'copiedMessage';
// @ts-expect-error outcome is not a failure kind
export const badKind: FailureKind = 'unknown';
// @ts-expect-error draft contains identifiers, not numbers
export const badDraft: SelectionDraft = {serviceId: 42, slotId: null};

export type ConsumerTypes = AppShell | DraftOptions | DraftRead | Insets;
export const operation: OperationKind = 'write';
export const report: ErrorReport = safeErrorReport(new Error(), operation);
// @ts-expect-error operation kind must describe read or write
export const badOperation: OperationKind = 'retry';
// @ts-expect-error public report is immutable
report.message = 'Override';

export function projectAdapters(): SelectionDraftStore {
  const values = new Map<string,string>();
  const storage: KeyValueStorage = {getItem:key=>values.get(key)??null,
    setItem:(key,value)=>{values.set(key,value);}, removeItem:key=>{values.delete(key);}};
  const factory: StorageFactory = ()=>storage;
  const transport: FetchTransport = async()=>Response.json({fixture:true});
  new ApiClient({baseUrl:'https://fixture.test',fetch:transport});
  return new SelectionDraftStore(factory,{namespace:'fixture',scope:'verified-actor:42',ttlMs:1000});
}
// @ts-expect-error async CloudStorage is not the synchronous selection storage interface
export const asyncStorage: KeyValueStorage = {getItem:async()=>null,setItem:()=>{},removeItem:()=>{}};

import {verifyInitDataSignature, InvalidInitData, TELEGRAM_PUBLIC_KEYS,
  type SignedLaunch, type InitDataSignatureOptions} from '@awesome-telegram/patterns';

export async function thirdPartyLaunch(raw: string, botId: number): Promise<number> {
  const options: InitDataSignatureOptions = {environment: 'test', maxAgeSeconds: 300};
  try {
    const launch: SignedLaunch = await verifyInitDataSignature(raw, botId, options);
    return launch.userId + TELEGRAM_PUBLIC_KEYS.production.length;
  } catch (error) {
    if (error instanceof InvalidInitData) return 0;
    throw error;
  }
}

// @ts-expect-error environment is a closed set of published keys
export const unknownEnvironment: InitDataSignatureOptions = {environment: 'staging'};
