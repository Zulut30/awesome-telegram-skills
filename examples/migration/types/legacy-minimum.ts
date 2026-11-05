import {TELEGRAM_NATIVE_METHODS} from '@awesome-telegram/patterns';
type NativeMethodSpec=typeof TELEGRAM_NATIVE_METHODS[keyof typeof TELEGRAM_NATIVE_METHODS];
export function requiredVersion(method:NativeMethodSpec):string{return method.minVersion;}
