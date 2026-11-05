/** Telegram host boundary. Browser UI owns its listeners; this adapter owns SDK resources. */
import {TelegramBridge,TelegramNativeAPI,UnsupportedTelegramCapability,type BridgeSnapshot,type TelegramWebApp} from '@awesome-telegram/patterns';
export type ShopHost=TelegramWebApp&{initData?:string};
export class ShopTelegramAdapter {
  private readonly bridge:TelegramBridge;
  private readonly native:TelegramNativeAPI;
  constructor(private readonly host:ShopHost|undefined){this.bridge=new TelegramBridge(host);this.native=new TelegramNativeAPI(host);}
  get initData():string{return this.host?.initData??'';}
  get present():boolean{return this.bridge.snapshot().insideTelegram;}
  snapshot():BridgeSnapshot{return this.bridge.snapshot();}
  subscribe(listener:(snapshot:BridgeSnapshot)=>void):()=>void{return this.bridge.subscribe(listener);}
  start():void{this.bridge.start();}
  back(visible:boolean):void{const name=visible?'BackButton.show':'BackButton.hide';if(this.native.supports(name))this.native.call(name);}
  onBack(listener:()=>void):(()=>void)|undefined{return this.native.supports('BackButton.show')?this.native.listen('backButtonClicked',listener):undefined;}
  onResume(listener:()=>void):(()=>void)|undefined {
    if(!this.native.supports('onEvent')||!this.native.supports('offEvent'))return;
    try{return this.native.listen('activated',listener);}catch(error){if(!(error instanceof UnsupportedTelegramCapability))throw error;}
  }
  closing(enabled:boolean):void{const name=enabled?'enableClosingConfirmation':'disableClosingConfirmation';if(this.native.supports(name))this.native.call(name);}
  invoice(url:string,closed:()=>void):boolean{if(!this.native.supports('openInvoice'))return false;this.native.call('openInvoice',url,closed);return true;}
  dispose():void{this.back(false);this.closing(false);this.native.dispose();this.bridge.dispose();}
}
export function telegramFromWindow(window:Window):ShopTelegramAdapter{return new ShopTelegramAdapter((window as Window&{Telegram?:{WebApp?:ShopHost}}).Telegram?.WebApp);}
