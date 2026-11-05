import {ApiError} from '@awesome-telegram/patterns';
export function recovery(error:ApiError):string {
 switch(error.outcome){case 'unknown':return 'reconcile original ID';case 'read-failed':return 'read again';default:{const never:never=error.outcome;return never;}}
}
