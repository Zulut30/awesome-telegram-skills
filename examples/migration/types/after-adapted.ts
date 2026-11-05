import {TelegramNativeAPI,ApiError,SelectionDraftStore,TELEGRAM_NATIVE_METHODS,type SelectionDraft} from '@awesome-telegram/patterns';
type NativeMethodSpec=typeof TELEGRAM_NATIVE_METHODS[keyof typeof TELEGRAM_NATIVE_METHODS];
export function requiredVersion(method:NativeMethodSpec):string{return method.minVersion===null?'unknown minimum':method.minVersion;}
export function invoke(api:TelegramNativeAPI,style:unknown):void {if(style!=='light'&&style!=='medium'&&style!=='heavy'&&style!=='rigid'&&style!=='soft')throw Error('invalid style');api.call('HapticFeedback.impactOccurred',style);}
export function recovery(error:ApiError):string {switch(error.outcome){case 'unknown':return 'reconcile original ID';case 'read-failed':return 'read again';case 'rejected':return 'fix input/auth; explicit user retry';default:{const never:never=error.outcome;return never;}}}
function oldSelection(value:unknown):SelectionDraft {if(value===null||typeof value!=='object')throw Error('invalid draft');const v=value as Record<string,unknown>;if((v.serviceId!==null&&typeof v.serviceId!=='string')||(v.slotId!==null&&typeof v.slotId!=='string'))throw Error('invalid IDs');return {serviceId:v.serviceId,slotId:v.slotId};}
new SelectionDraftStore(()=>localStorage,{namespace:'booking',scope:'verified-user:42',ttlMs:1000,schemaVersion:2,migrateFrom:{1:oldSelection}});
