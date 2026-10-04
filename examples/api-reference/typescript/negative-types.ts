/** Deliberate compiler checks; never called by runtime examples. */
import type {SelectionDraft, TelegramNativeMethod, TelegramNativeEvent, OperationKind, ErrorReport,
  KeyValueStorage, RequestOptions} from '@awesome-telegram/patterns';
// @ts-expect-error arbitrary strings are not native paths
export const method: TelegramNativeMethod = 'invented.call';
// @ts-expect-error unsupported event
export const event: TelegramNativeEvent = 'invented.event';
// @ts-expect-error numeric ID is not a selection ID
export const draft: SelectionDraft = {serviceId: 42, slotId: null};
// @ts-expect-error recovery action is not operation kind
export const operation: OperationKind = 'retry';
// @ts-expect-error HTTP method unsupported
export const request: RequestOptions = {method: 'CONNECT'};
// @ts-expect-error async cloud storage is not sync local storage
export const storage: KeyValueStorage = {getItem: async () => null, setItem: () => {}, removeItem: () => {}};
export function cannotMutate(report: ErrorReport): void {
  // @ts-expect-error public metadata is immutable
  report.outcome = 'rejected';
}
