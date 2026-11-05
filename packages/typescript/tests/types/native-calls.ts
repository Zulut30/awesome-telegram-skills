/** Type test: tsc must accept documented native calls and reject wrong arguments (npm run test:types). */
import {
  TelegramNativeAPI,
  type TelegramNativeArguments,
  type TelegramNativeResult,
  type TelegramNativeSignatures,
  type TelegramServerlessError,
} from '@awesome-telegram/patterns';

/** These signatures typecheck; the universal facade rejects their unknown version at runtime. */
export function documentedServerlessArguments(api:TelegramNativeAPI):void {
  const callback=(error:TelegramServerlessError|null,result?:unknown)=>{
    if(error){const code:number=error.status;const type:string|undefined=error.type;const details:Readonly<Record<string,unknown>>|undefined=error.parameters;void code;void type;void details;}
    void result;
  };
  const second:TelegramNativeArguments<'Serverless.call'>=['getProfile',callback];
  const third:TelegramNativeArguments<'Serverless.call'>=['getProfile',{lang:'ru'},callback];void second;void third;
  const raw:TelegramNativeSignatures['Serverless.call']=(...args)=>{const name:string=args[0];void name;};
  raw('getProfile');raw('getProfile',callback);raw('getProfile',{lang:'ru'},callback);raw('getProfile',undefined,callback);
  const returned:TelegramNativeResult<'Serverless.call'>=api.call('Serverless.call','getProfile',{lang:'ru'},callback);const noPromise:void=returned;void noPromise;
  api.call('Serverless.call','getProfile',callback);
  // @ts-expect-error an endpoint name is required
  api.call('Serverless.call');
  // @ts-expect-error endpoint name is a string
  api.call('Serverless.call',42);
  // @ts-expect-error input is an object, never an array
  api.call('Serverless.call','getProfile',[],callback);
  // @ts-expect-error callback receives an error object or null, never a string
  api.call('Serverless.call','getProfile',(error:string)=>{void error;});
  // @ts-expect-error native SDK return is void; callback carries the result
  const promise:Promise<unknown>=api.call('Serverless.call','getProfile');void promise;
  // @ts-expect-error HTTP status is numeric, including zero for network failure
  const error:TelegramServerlessError={message:'Fixture',status:'0'};void error;
}

export function documentedCalls(api: TelegramNativeAPI): boolean {
  api.call('showPopup', {message: 'Continue?', buttons: [{id: 'ok', type: 'ok'}]}, buttonId => { buttonId?.toUpperCase(); });
  api.call('showConfirm', 'Delete?', confirmed => { if (confirmed) api.call('HapticFeedback.notificationOccurred', 'success'); });
  api.call('HapticFeedback.impactOccurred', 'light');
  api.call('setHeaderColor', '#112233');
  api.call('setBottomBarColor', 'bottom_bar_bg_color');
  api.call('CloudStorage.getItem', 'draft', (error, value) => { if (error === null) void value?.length; });
  api.call('LocationManager.getLocation', location => { if (location) void location.latitude.toFixed(4); });
  api.call('MainButton.setParams', {text: 'Pay', position: 'left', has_shine_effect: true});
  api.call('switchInlineQuery', 'query', ['users', 'groups']);
  api.call('openLink', 'https://telegram.org', {try_instant_view: true});
  const popup: TelegramNativeArguments<'showPopup'>[0] = {message: 'Typed parameters are reusable'};
  const chained: TelegramNativeResult<'BackButton.show'> = api.call('BackButton.show');
  void popup; void chained;
  return api.call('isVersionAtLeast', '8.0');
}

export const documented: keyof TelegramNativeSignatures = 'showScanQrPopup';
// Each line below must fail to compile; an unused @ts-expect-error fails the test as well.
// @ts-expect-error showPopup needs a message
export const missingMessage = (api: TelegramNativeAPI) => api.call('showPopup', {title: 'No message'});
// @ts-expect-error impact styles are a closed set
export const loudHaptic = (api: TelegramNativeAPI) => api.call('HapticFeedback.impactOccurred', 'loud');
// @ts-expect-error the version is a string such as '8.0'
export const numericVersion = (api: TelegramNativeAPI) => api.call('isVersionAtLeast', 8);
// @ts-expect-error header colors are #RRGGBB or a theme keyword
export const namedColor = (api: TelegramNativeAPI) => api.call('setHeaderColor', 'red');
// @ts-expect-error ready takes no arguments
export const extraArgument = (api: TelegramNativeAPI) => api.call('ready', true);
// @ts-expect-error CloudStorage.getItem needs its callback
export const missingCallback = (api: TelegramNativeAPI) => api.call('CloudStorage.getItem', 'draft');
// @ts-expect-error the showConfirm callback receives a boolean
export const wrongCallback = (api: TelegramNativeAPI) => api.call('showConfirm', 'Sure?', (answer: string) => answer);
// @ts-expect-error showPopup returns nothing
export const popupResult: boolean = new TelegramNativeAPI(undefined).call('showPopup', {message: 'x'});
// @ts-expect-error not a documented native method
export const invented = (api: TelegramNativeAPI) => api.call('invented.method');
