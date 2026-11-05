import {TelegramNativeAPI, ApiClient, ApiError, SelectionDraftStore} from '@awesome-telegram/patterns';
const api=new TelegramNativeAPI(undefined);api.call('HapticFeedback.impactOccurred','light');
new ApiClient({baseUrl:'https://api.example.test/api/v1/'});
new ApiError('network',undefined,'unknown');
new SelectionDraftStore(()=>localStorage,{namespace:'booking',scope:'verified-user:42',ttlMs:1000});
