/** Type consumer, compiled against the installed tarball by distribution checks. */
import {
  ApiClient, TelegramBridge, createTextField,
  type AppShell, type BridgeSnapshot, type ClientOptions, type DraftOptions,
  type DraftRead, type FailureKind, type Insets, type RequestOptions,
  type SelectionDraft, type TelegramNativeEvent, type TelegramNativeMethod,
  type TelegramWebApp, type TextFieldControl,
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
