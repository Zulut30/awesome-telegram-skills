/** Scoped native workflows over existing version/presence gates; no transport, auth or automatic retries. */
import {TelegramNativeAPI} from './native-api.js';
import {TELEGRAM_NATIVE_METHODS} from './native-catalog.js';
import type {TelegramNativeMethod} from './native-catalog.js';
import type {TelegramNativeArguments, LocationData, InvoiceStatus, NativeServerlessError} from './native-signatures.js';
import {isInsideTelegram} from './launch.js';
import {AuthenticationRequired, InvalidType, PatternError, UnknownOutcome, ValidationFailure, safeErrorReport} from './errors.js';
import type {ErrorReport, OperationKind} from './errors.js';

export type NativeFlowResult<T> = Readonly<{status:'completed';value:T} |
  {status:'denied'|'cancelled'|'unsupported'|'busy'} | {status:'stale';recoveryId?:string} |
  {status:'unknown'|'failed';error:ErrorReport;recoveryId?:string}>;
export type NativeLaunch = 'keyboard'|'inline'|'menu'|'direct'|'attachment'|'unknown';
export interface NativeInteraction {readonly purpose:string;readonly userInitiated:true}
export type NativeFlowKind = 'main-button'|'secondary-button'|'back-button'|'popup'|'qr'|'invoice'|'contact'|'location'|'biometric'|'cloud-storage'|'device-storage'|'secure-storage'|'share-message'|'story'|'download';
export interface NativeScopeOptions {
  accountTag:string|null; launch:NativeLaunch; timeoutMs?:number;
  platformPolicy?:(flow:NativeFlowKind,platform:string,launch:NativeLaunch)=>boolean;
}
export interface NativeCapability {
  readonly flow:NativeFlowKind;readonly versions:readonly string[];readonly platform:string;readonly launch:NativeLaunch;
  readonly available:boolean;readonly permission:'contextual-action'|'manager-state'|'account-scope'|'none';readonly fallback:string;
  readonly state:'ready-to-attempt'|'unavailable'|'needs-init'|'needs-account'|'permission-needed';
}
const DEFINITIONS:ReadonlyArray<{flow:NativeFlowKind;methods:readonly TelegramNativeMethod[];permission:NativeCapability['permission'];fallback:string}> = [
  {flow:'main-button',methods:['onEvent','offEvent','MainButton.setText','MainButton.onClick','MainButton.offClick','MainButton.show','MainButton.hide','MainButton.enable','MainButton.disable','MainButton.showProgress','MainButton.hideProgress'],permission:'none',fallback:'DOM action'},
  {flow:'secondary-button',methods:['onEvent','offEvent','SecondaryButton.setText','SecondaryButton.onClick','SecondaryButton.offClick','SecondaryButton.show','SecondaryButton.hide','SecondaryButton.enable','SecondaryButton.disable','SecondaryButton.showProgress','SecondaryButton.hideProgress'],permission:'none',fallback:'DOM secondary action'},
  {flow:'back-button',methods:['onEvent','offEvent','BackButton.show','BackButton.hide','BackButton.onClick','BackButton.offClick'],permission:'none',fallback:'DOM navigation'},
  {flow:'popup',methods:['showPopup'],permission:'none',fallback:'DOM dialog'},
  {flow:'qr',methods:['showScanQrPopup','closeScanQrPopup'],permission:'contextual-action',fallback:'manual code field'},
  {flow:'invoice',methods:['openInvoice'],permission:'contextual-action',fallback:'server-issued invoice link'},
  {flow:'contact',methods:['requestContact'],permission:'contextual-action',fallback:'manual contact field'},
  {flow:'location',methods:['LocationManager.init','LocationManager.getLocation'],permission:'manager-state',fallback:'manual address'},
  {flow:'biometric',methods:['BiometricManager.init','BiometricManager.requestAccess','BiometricManager.authenticate'],permission:'manager-state',fallback:'server confirmation'},
  {flow:'cloud-storage',methods:['CloudStorage.getItem','CloudStorage.setItem','CloudStorage.removeItem'],permission:'account-scope',fallback:'server-owned draft'},
  {flow:'device-storage',methods:['DeviceStorage.getItem','DeviceStorage.setItem','DeviceStorage.removeItem'],permission:'account-scope',fallback:'server-owned draft'},
  {flow:'secure-storage',methods:['SecureStorage.getItem','SecureStorage.setItem','SecureStorage.removeItem','SecureStorage.restoreItem'],permission:'account-scope',fallback:'explicit server recovery; no downgrade'},
  {flow:'share-message',methods:['shareMessage'],permission:'contextual-action',fallback:'copyable approved link'},
  {flow:'story',methods:['shareToStory'],permission:'contextual-action',fallback:'downloadable approved media'},
  {flow:'download',methods:['downloadFile'],permission:'contextual-action',fallback:'HTTPS download link'},
];
type ObjectLike=Record<string,unknown>;
const object=(value:unknown):value is ObjectLike=>value!==null&&typeof value==='object';
const completed=<T>(value:T):NativeFlowResult<T>=>Object.freeze({status:'completed',value});
const status=<T>(value:'denied'|'cancelled'|'unsupported'|'busy'|'stale'):NativeFlowResult<T>=>Object.freeze({status:value});
function bounded(value:unknown,max:number,min=1):asserts value is string {
  if(typeof value!=='string'||value.length<min||value.length>max)throw new ValidationFailure('Use bounded native parameters');
}
function interaction(value:NativeInteraction):void {
  if(!value||value.userInitiated!==true)throw new ValidationFailure('Request native permission from an explicit user action');bounded(value.purpose,128);
}
function https(value:string):string {
  bounded(value,2048);let url:URL;try{url=new URL(value);}catch{throw new ValidationFailure('Use an HTTPS URL');}
  if(url.protocol!=='https:'||url.username||url.password||/[\u0000-\u0020\u007f]/.test(value))throw new ValidationFailure('Use an HTTPS URL without credentials');return url.href;
}
function account(value:string|null):void {
  if(value!==null&&(typeof value!=='string'||!/^[-_A-Za-z0-9]{1,48}$/.test(value)))throw new ValidationFailure('Use a server-verified opaque bot/account tag');
}
function endpointInput(input:Readonly<Record<string,unknown>>):string {
  const seen=new WeakSet<object>();let nodes=10000,units=0;
  const visit=(value:unknown,depth:number):void=>{
    if(--nodes<0||depth>32)throw new ValidationFailure('Endpoint JSON exceeds local bounds');
    if(typeof value==='string'){units+=value.length;if(units>65536)throw new ValidationFailure('Endpoint input exceeds local bounds');return;}
    if(value===null||typeof value==='boolean'||typeof value==='number'&&Number.isFinite(value))return;
    if(!object(value)||seen.has(value))throw new ValidationFailure('Use finite plain endpoint JSON');
    const array=Array.isArray(value),prototype=Object.getPrototypeOf(value);
    if(!array&&prototype!==Object.prototype&&prototype!==null||Object.getOwnPropertySymbols(value).length)throw new ValidationFailure('Use finite plain endpoint JSON');
    seen.add(value);const descriptors=Object.getOwnPropertyDescriptors(value);
    if(array&&Object.keys(value).length!==(value as unknown[]).length)throw new ValidationFailure('Use dense endpoint arrays');
    for(const [key,descriptor]of Object.entries(descriptors)){if(array&&key==='length')continue;units+=key.length;if(units>65536)throw new ValidationFailure('Endpoint input exceeds local bounds');if(!descriptor.enumerable||!('value'in descriptor))throw new ValidationFailure('Endpoint JSON cannot contain accessors');visit(descriptor.value,depth+1);}
    seen.delete(value);
  };
  visit(input,0);const result=JSON.stringify(input);if(new TextEncoder().encode(result).length>65536)throw new ValidationFailure('Endpoint input exceeds local UTF-8 byte limit');return result;
}
interface Ticket {id:string;generation:number;settled:boolean;retained:boolean;finish:(value:NativeFlowResult<unknown>)=>void;cleanups:Array<()=>void>;cancelNative?:()=>void}
interface RequestOptions {signal?:AbortSignal;retain?:boolean;operation?:OperationKind}
class Core {
  readonly api:TelegramNativeAPI;readonly pending=new Map<string,Ticket>();generation=0;disposed=false;counter=0;
  constructor(readonly app:unknown,readonly options:NativeScopeOptions){this.api=new TelegramNativeAPI(app);}
  platform():string{return object(this.app)&&typeof this.app.platform==='string'?this.app.platform:'unknown';}
  supports(flow:NativeFlowKind):boolean {
    if(this.disposed||this.options.platformPolicy?.(flow,this.platform(),this.options.launch)===false)return false;
    const definition=DEFINITIONS.find(value=>value.flow===flow)!;return definition.methods.every(method=>this.api.supports(method));
  }
  release(facility:string,ticket:Ticket):void {
    if(this.pending.get(facility)!==ticket)return;
    this.pending.delete(facility);for(const cleanup of ticket.cleanups.splice(0)){try{cleanup();}catch{/* stale callbacks remain fenced */}}
  }
  request<T>(facility:string,start:(reply:(value:NativeFlowResult<T>)=>void,ticket:Ticket)=>void,options:RequestOptions={}):Promise<NativeFlowResult<T>> {
    if(this.disposed)return Promise.resolve(status('stale'));
    if(this.pending.has(facility)||this.pending.size>=16)return Promise.resolve(status('busy'));
    if(options.signal?.aborted)return Promise.resolve(status('cancelled'));
    return new Promise(resolve=>{
      const ticket:Ticket={id:String(++this.counter),generation:this.generation,settled:false,retained:options.retain??false,cleanups:[],finish:value=>{
        if(ticket.settled)return;ticket.settled=true;clearTimeout(timer);options.signal?.removeEventListener('abort',abort);resolve(value as NativeFlowResult<T>);
      }};
      const unresolved=()=>{
        const error=safeErrorReport(new UnknownOutcome(),options.operation??'write');
        ticket.finish(Object.freeze({status:'unknown',error,...(ticket.retained?{recoveryId:ticket.id}:{})}));
        try{ticket.cancelNative?.();}catch{/* keep occupancy unless a real close reply arrives */}
        if(!ticket.retained)this.release(facility,ticket);
      };
      const abort=()=>unresolved();
      const timer=setTimeout(unresolved,this.options.timeoutMs??15000);
      this.pending.set(facility,ticket);options.signal?.addEventListener('abort',abort,{once:true});
      const reply=(value:NativeFlowResult<T>)=>{
        if(this.pending.get(facility)!==ticket)return;
        if(!ticket.settled)ticket.finish(ticket.generation===this.generation&&!this.disposed?value:status('stale'));
        this.release(facility,ticket);
      };
      try{start(reply,ticket);}catch(error){
        if(ticket.retained)ticket.finish(Object.freeze({status:'unknown',error:safeErrorReport(new UnknownOutcome(),'write'),recoveryId:ticket.id}));
        else reply(Object.freeze({status:'failed',error:safeErrorReport(error,options.operation??'write')}));
      }
    });
  }
  invalidate():void {this.generation++;for(const [facility,ticket]of this.pending){ticket.finish(Object.freeze({status:'stale',...ticket.retained?{recoveryId:ticket.id}:{}}));try{ticket.cancelNative?.();}catch{/* retained until closure */}if(!ticket.retained)this.release(facility,ticket);}}
  manager(kind:'LocationManager'|'BiometricManager'):{initialized:boolean;available:boolean;requested:boolean;granted:boolean} {
    const manager=object(this.app)&&object(this.app[kind])?this.app[kind]:{};
    return {initialized:manager.isInited===true,available:manager[kind==='LocationManager'?'isLocationAvailable':'isBiometricAvailable']===true,requested:manager.isAccessRequested===true,granted:manager.isAccessGranted===true};
  }
}
const owners=new WeakMap<NativeFlowScope,Core>();
function core(scope:NativeFlowScope):Core {const value=owners.get(scope);if(!value)throw new InvalidType('Use a NativeFlowScope');return value;}

export class NativeFlowScope {
  constructor(app:unknown,options:NativeScopeOptions){
    account(options.accountTag);if(!['keyboard','inline','menu','direct','attachment','unknown'].includes(options.launch))throw new ValidationFailure('Declare the launch context');
    if(options.timeoutMs!==undefined&&(!Number.isFinite(options.timeoutMs)||options.timeoutMs<1||options.timeoutMs>120000))throw new ValidationFailure('Use native callback timeout 1..120000ms');
    owners.set(this,new Core(app,{...options}));
  }
  setAccount(accountTag:string|null):void {account(accountTag);const owner=core(this);if(owner.disposed)throw new ValidationFailure('Native scope disposed');if(owner.options.accountTag!==accountTag){owner.options.accountTag=accountTag;owner.invalidate();}}
  capabilities():readonly NativeCapability[] {
    const owner=core(this);return Object.freeze(DEFINITIONS.map(value=>{
      let available=owner.supports(value.flow),state:NativeCapability['state']=available?'ready-to-attempt':'unavailable';
      if(available&&(value.flow==='location'||value.flow==='biometric')){const manager=owner.manager(value.flow==='location'?'LocationManager':'BiometricManager');if(!manager.initialized){available=false;state='needs-init';}else if(!manager.available){available=false;state='unavailable';}else if(!manager.granted)state='permission-needed';}
      if(available&&value.permission==='account-scope'&&owner.options.accountTag===null){available=false;state='needs-account';}
      return Object.freeze({flow:value.flow,versions:Object.freeze([...new Set(value.methods.map(method=>TELEGRAM_NATIVE_METHODS[method].minVersion).filter(version=>version!==null))]),platform:owner.platform(),launch:owner.options.launch,available,state,permission:value.permission,fallback:value.fallback});
    }));
  }
  /** Only after the host actually observed native closure; token fences an older unknown prompt. */
  confirmPromptClosed(recoveryId:string):boolean {const owner=core(this),ticket=owner.pending.get('prompt');if(!ticket||!ticket.settled||ticket.id!==recoveryId)return false;owner.release('prompt',ticket);return true;}
  dispose():void {const owner=core(this);if(!owner.disposed){owner.disposed=true;owner.invalidate();for(const [facility,ticket]of owner.pending)owner.release(facility,ticket);}owner.api.dispose();}
}

export interface NativeButtonsState {main?:{text:string;visible:boolean;enabled?:boolean};secondary?:{text:string;visible:boolean;enabled?:boolean};backVisible?:boolean}
export interface NativeButtonHandlers {main?:()=>void|Promise<void>;secondary?:()=>void|Promise<void>;back?:()=>void|Promise<void>;onError?:(report:ErrorReport)=>void}
export class NativeActionButtons {
  private readonly cleanups:Array<()=>void>=[];private readonly busy=new Set<'main'|'secondary'|'back'>();private disposed=false;private state:NativeButtonsState={};
  private readonly generation:number;private readonly bound=new Set<'main'|'secondary'|'back'>();
  constructor(private readonly scope:NativeFlowScope,private readonly handlers:NativeButtonHandlers){
    const owner=core(scope);this.generation=owner.generation;
    try{for(const [kind,path]of [['main','MainButton'],['secondary','SecondaryButton'],['back','BackButton']]as const){
      if(!owner.supports(kind==='back'?'back-button':`${kind}-button`))continue;
      const callback=()=>{
        if(this.disposed||owner.disposed||this.generation!==owner.generation||this.busy.has(kind))return;
        if(kind!=='back'&&(!this.state[kind]?.visible||this.state[kind]?.enabled===false))return;
        if(kind==='back'&&!this.state.backVisible)return;
        const call=this.handlers[kind];if(!call)return;this.setBusy(kind,true);
        void Promise.resolve().then(()=>this.disposed||owner.disposed||this.generation!==owner.generation?undefined:call()).catch((error:unknown)=>{if(!this.disposed&&!owner.disposed&&this.generation===owner.generation){try{this.handlers.onError?.(safeErrorReport(error,'write'));}catch{/* reporter failure never repeats the action */}}}).finally(()=>this.setBusy(kind,false));
      };
      this.cleanups.push(owner.api.listen(kind==='main'?'mainButtonClicked':kind==='secondary'?'secondaryButtonClicked':'backButtonClicked',callback));this.bound.add(kind);
    }}catch{try{this.dispose();}catch{/* scope.dispose retries retained native listener cleanups */}throw new UnknownOutcome('Native button binding failed');}
  }
  render(value:NativeButtonsState):void {
    if(this.disposed)return;if(core(this.scope).generation!==this.generation)throw new ValidationFailure('Recreate native buttons for the new account');for(const config of [value.main,value.secondary])if(config)bounded(config.text,64);
    this.state={...value,...value.main?{main:{...value.main}}:{},...value.secondary?{secondary:{...value.secondary}}:{}};this.refresh();
  }
  private refresh():void {
    if(this.disposed)return;const owner=core(this.scope);if(owner.disposed||owner.generation!==this.generation)return;
    for(const [kind,path]of [['main','MainButton'],['secondary','SecondaryButton']]as const){
      if(!owner.supports(`${kind}-button`))continue;const config=this.state[kind];
      if(!config?.visible){owner.api.call(`${path}.hide`);continue;}
      owner.api.call(`${path}.setText`,config.text);owner.api.call(`${path}.show`);
      if(this.busy.has(kind)){owner.api.call(`${path}.showProgress`,false);owner.api.call(`${path}.disable`);}
      else{owner.api.call(`${path}.hideProgress`);owner.api.call(config.enabled===false?`${path}.disable`:`${path}.enable`);}
    }
    if(owner.supports('back-button'))owner.api.call(this.state.backVisible?'BackButton.show':'BackButton.hide');
  }
  setBusy(kind:'main'|'secondary'|'back',value:boolean):void {if(value)this.busy.add(kind);else this.busy.delete(kind);this.refresh();}
  dispose():void {
    this.disposed=true;const owner=core(this.scope);let failed=false;
    for(const cleanup of this.cleanups.splice(0)){try{cleanup();}catch{this.cleanups.push(cleanup);failed=true;}}
    for(const [kind,path]of [['main','MainButton'],['secondary','SecondaryButton']]as const)if(this.generation===owner.generation&&this.bound.has(kind)&&owner.api.supports(`${path}.hide`)){owner.api.call(`${path}.hideProgress`);owner.api.call(`${path}.hide`);}
    if(this.generation===owner.generation&&this.bound.has('back')&&owner.api.supports('BackButton.hide'))owner.api.call('BackButton.hide');
    if(failed)throw new UnknownOutcome('Native listener cleanup needs retry');
  }
}

export class NativePrompts {
  constructor(private readonly scope:NativeFlowScope){}
  popup(params:TelegramNativeArguments<'showPopup'>[0],signal?:AbortSignal):Promise<NativeFlowResult<{buttonId:string}>> {
    bounded(params.message,256);if(params.title!==undefined)bounded(params.title,64,0);
    if(params.buttons&&(params.buttons.length<1||params.buttons.length>3))throw new ValidationFailure('Use 1..3 popup buttons');
    for(const button of params.buttons??[]){if(button.id!==undefined)bounded(button.id,64,0);if(button.text!==undefined)bounded(button.text,64,0);if(!['default','ok','close','cancel','destructive'].includes(button.type??'default'))throw new ValidationFailure('Invalid popup button');if(['default','destructive'].includes(button.type??'default')&&!button.text)throw new ValidationFailure('Button text required');}
    const snapshot={message:params.message,...params.title!==undefined?{title:params.title}:{},...params.buttons?{buttons:params.buttons.map(button=>({...button}))}:{}};
    if(snapshot.buttons&&new Set(snapshot.buttons.map(button=>button.id??'')).size!==snapshot.buttons.length)throw new ValidationFailure('Use distinct popup button IDs');
    const owner=core(this.scope);if(!owner.supports('popup'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('showPopup',snapshot,buttonId=>{
      const button=snapshot.buttons?.find(value=>(value.id??'')===buttonId);
      reply(typeof buttonId!=='string'||!snapshot.buttons||button?.type==='close'||button?.type==='cancel'?status('cancelled'):!button?{status:'failed',error:safeErrorReport(new PatternError('invalid-response','read-failed'))}:completed({buttonId}));
    }),{...signal?{signal}:{},retain:true});
  }
  qr(params:TelegramNativeArguments<'showScanQrPopup'>[0],action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{text:string}>> {
    interaction(action);if(params.text!==undefined)bounded(params.text,64,0);const owner=core(this.scope);if(!owner.supports('qr'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',(reply,ticket)=>{
      try{ticket.cleanups.push(owner.api.listen('scanQrPopupClosed',()=>reply(status('cancelled'))));}catch{/* <7.7 lacks a close event; retain unknown until observed/manual closure */}
      owner.api.call('showScanQrPopup',params,text=>{if(owner.disposed||ticket.settled||ticket.generation!==owner.generation||owner.pending.get('prompt')!==ticket||typeof text!=='string'||!text||text.length>4096)return false;reply(completed({text}));return true;});
      ticket.cancelNative=()=>owner.api.call('closeScanQrPopup');
    },{...signal?{signal}:{},retain:true});
  }
  invoice(url:string,action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{nativeStatus:InvoiceStatus;requiresServerReconciliation:true}>> {
    interaction(action);const normalized=https(url),parsed=new URL(normalized);
    if(parsed.hostname!=='t.me'||!/^\/(?:\$|invoice\/)[A-Za-z0-9_=-]+$/.test(parsed.pathname)||parsed.port)throw new ValidationFailure('Use a server-issued Telegram invoice link');
    const owner=core(this.scope);if(!owner.supports('invoice'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('openInvoice',normalized,nativeStatus=>reply(['paid','cancelled','failed','pending'].includes(nativeStatus)?completed({nativeStatus,requiresServerReconciliation:true}):{status:'unknown',error:safeErrorReport(new UnknownOutcome(),'write')})),{...signal?{signal}:{},retain:true});
  }
  contact(action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{shared:true}>> {
    interaction(action);const owner=core(this.scope);if(!owner.supports('contact'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('requestContact',shared=>reply(shared===true?completed({shared:true}):status('denied'))),{...signal?{signal}:{},retain:true});
  }
  prepareLocation(signal?:AbortSignal):Promise<NativeFlowResult<{available:boolean;granted:boolean}>> {
    const owner=core(this.scope);if(!owner.supports('location'))return Promise.resolve(status('unsupported'));
    return owner.request('location-init',reply=>owner.api.call('LocationManager.init',()=>{const value=owner.manager('LocationManager');reply(completed({available:value.available,granted:value.granted}));}),{...signal?{signal}:{}});
  }
  location(action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<LocationData>> {
    interaction(action);const owner=core(this.scope),manager=owner.manager('LocationManager');
    if(!owner.supports('location')||!manager.initialized||!manager.available)return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('LocationManager.getLocation',value=>{
      if(value===null){reply(status('denied'));return;}
      if(!object(value)||!Number.isFinite(value.latitude)||!Number.isFinite(value.longitude)||Math.abs(value.latitude)>90||Math.abs(value.longitude)>180){reply({status:'failed',error:safeErrorReport(new ValidationFailure())});return;}
      const optionalKeys=['altitude','course','speed','horizontal_accuracy','vertical_accuracy','course_accuracy','speed_accuracy']as const;
      if(optionalKeys.some(key=>value[key]!==null&&value[key]!==undefined&&!Number.isFinite(value[key]))){reply({status:'failed',error:safeErrorReport(new PatternError('invalid-response','read-failed'))});return;}
      reply(completed({latitude:value.latitude,longitude:value.longitude,altitude:value.altitude??null,course:value.course??null,speed:value.speed??null,horizontal_accuracy:value.horizontal_accuracy??null,vertical_accuracy:value.vertical_accuracy??null,course_accuracy:value.course_accuracy??null,speed_accuracy:value.speed_accuracy??null}));
    }),{...signal?{signal}:{},retain:true});
  }
}

export type NativeStorageKind='cloud'|'device'|'secure';
export interface NativeStoredValue {readonly value:string|null;readonly canRestore:boolean}
export class NativeAccountStorage {
  constructor(private readonly scope:NativeFlowScope){}
  private key(key:string):string {bounded(key,48);if(!/^[-_A-Za-z0-9]+$/.test(key))throw new ValidationFailure('Use an opaque storage key');const tag=core(this.scope).options.accountTag;if(tag===null)throw new AuthenticationRequired('Establish server account scope before native storage');return `tp_${tag.length}_${tag}_${key}`;}
  read(kind:NativeStorageKind,key:string,signal?:AbortSignal):Promise<NativeFlowResult<NativeStoredValue>> {
    const owner=core(this.scope),scoped=this.key(key);if(!owner.supports(`${kind}-storage`))return Promise.resolve(status('unsupported'));
    return owner.request(`storage:${kind}:${scoped}` ,reply=>{
      const callback=(error:string|null,value?:string|null,canRestore?:boolean)=>reply(error!==null||value!==null&&typeof value!=='string'?{status:'failed',error:safeErrorReport(new PatternError('invalid-response','read-failed'))}:completed({value,canRestore:canRestore===true}));
      if(kind==='secure')owner.api.call('SecureStorage.getItem',scoped,callback);else if(kind==='device')owner.api.call('DeviceStorage.getItem',scoped,callback);else owner.api.call('CloudStorage.getItem',scoped,callback);
    },{...signal?{signal}:{},operation:'read'});
  }
  write(kind:NativeStorageKind,key:string,value:string,signal?:AbortSignal):Promise<NativeFlowResult<{stored:boolean}>> {
    bounded(value,4096,0);const owner=core(this.scope),scoped=this.key(key);if(!owner.supports(`${kind}-storage`))return Promise.resolve(status('unsupported'));
    return owner.request(`storage:${kind}:${scoped}`,reply=>{
      const callback=(error:string|null,stored?:boolean)=>reply(error!==null||typeof stored!=='boolean'?{status:'unknown',error:safeErrorReport(new UnknownOutcome(),'write')}:completed({stored}));
      if(kind==='secure')owner.api.call('SecureStorage.setItem',scoped,value,callback);else if(kind==='device')owner.api.call('DeviceStorage.setItem',scoped,value,callback);else owner.api.call('CloudStorage.setItem',scoped,value,callback);
    },{...signal?{signal}:{},retain:true});
  }
  remove(kind:NativeStorageKind,key:string,signal?:AbortSignal):Promise<NativeFlowResult<{removed:boolean}>> {
    const owner=core(this.scope),scoped=this.key(key);if(!owner.supports(`${kind}-storage`))return Promise.resolve(status('unsupported'));
    return owner.request(`storage:${kind}:${scoped}`,reply=>{
      const callback=(error:string|null,removed?:boolean)=>reply(error!==null||typeof removed!=='boolean'?{status:'unknown',error:safeErrorReport(new UnknownOutcome(),'write')}:completed({removed}));
      if(kind==='secure')owner.api.call('SecureStorage.removeItem',scoped,callback);else if(kind==='device')owner.api.call('DeviceStorage.removeItem',scoped,callback);else owner.api.call('CloudStorage.removeItem',scoped,callback);
    },{...signal?{signal}:{},retain:true});
  }
  restoreSecure(key:string,action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<NativeStoredValue>> {
    interaction(action);const owner=core(this.scope),scoped=this.key(key);if(!owner.supports('secure-storage'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('SecureStorage.restoreItem',scoped,(error,value)=>reply(error!==null||value!==null&&typeof value!=='string'?{status:'failed',error:safeErrorReport(new PatternError('invalid-response','read-failed'))}:completed({value,canRestore:false}))),{...signal?{signal}:{},retain:true});
  }
  prepareBiometric(signal?:AbortSignal):Promise<NativeFlowResult<{available:boolean;granted:boolean}>> {
    const owner=core(this.scope);if(!owner.supports('biometric'))return Promise.resolve(status('unsupported'));
    return owner.request('biometric-init',reply=>owner.api.call('BiometricManager.init',()=>{const manager=owner.manager('BiometricManager');reply(completed({available:manager.available,granted:manager.granted}));}),{...signal?{signal}:{}});
  }
  requestBiometricAccess(action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{granted:true}>> {
    interaction(action);const owner=core(this.scope),manager=owner.manager('BiometricManager');
    if(!owner.supports('biometric')||!manager.initialized||!manager.available)return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('BiometricManager.requestAccess',{reason:action.purpose},granted=>reply(granted===true?completed({granted:true}):status('denied'))),{...signal?{signal}:{},retain:true});
  }
  unlockBiometric(action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{authenticated:boolean;biometricToken?:string}>> {
    interaction(action);const owner=core(this.scope),manager=owner.manager('BiometricManager');
    if(!owner.supports('biometric')||!manager.initialized||!manager.available)return Promise.resolve(status('unsupported'));
    if(!manager.granted)return Promise.resolve(status('denied'));
    return owner.request('prompt',reply=>owner.api.call('BiometricManager.authenticate',{reason:action.purpose},(authenticated,token)=>reply(completed({authenticated:authenticated===true,...authenticated===true&&typeof token==='string'?{biometricToken:token}:{}}))),{...signal?{signal}:{},retain:true});
  }
}

export class NativeSharing {
  constructor(private readonly scope:NativeFlowScope){}
  message(preparedMessageId:string,action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{sent:boolean}>> {
    interaction(action);bounded(preparedMessageId,512);const owner=core(this.scope);if(!owner.supports('share-message'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('shareMessage',preparedMessageId,sent=>reply(completed({sent:sent===true}))),{...signal?{signal}:{},retain:true});
  }
  story(mediaUrl:string,params:TelegramNativeArguments<'shareToStory'>[1],action:NativeInteraction):NativeFlowResult<{editorRequested:true}> {
    interaction(action);const url=https(mediaUrl);if(params?.text!==undefined)bounded(params.text,2048,0);if(params?.widget_link){https(params.widget_link.url);if(params.widget_link.name!==undefined)bounded(params.widget_link.name,48,0);}
    const owner=core(this.scope);if(!owner.supports('story'))return status('unsupported');
    try{owner.api.call('shareToStory',url,params);return completed({editorRequested:true});}catch(error){return {status:'failed',error:safeErrorReport(error,'write')};}
  }
  download(params:TelegramNativeArguments<'downloadFile'>[0],action:NativeInteraction,signal?:AbortSignal):Promise<NativeFlowResult<{accepted:boolean;persisted:false}>> {
    interaction(action);const url=https(params.url);bounded(params.file_name,255);if(/[\\/\u0000-\u001f\u007f]/.test(params.file_name))throw new ValidationFailure('Use a file name without path/control characters');
    const owner=core(this.scope);if(!owner.supports('download'))return Promise.resolve(status('unsupported'));
    return owner.request('prompt',reply=>owner.api.call('downloadFile',{url,file_name:params.file_name},accepted=>reply(completed({accepted:accepted===true,persisted:false}))),{...signal?{signal}:{},retain:true});
  }
}

export interface NativeFileInputOptions {label:string;accept?:readonly string[];capture?:'user'|'environment';maxBytes:number;onFiles:(files:readonly File[])=>void;onError?:(report:ErrorReport)=>void}
/** HTML picker fallback; accept/capture are hints, never proof of camera support or safe file content. */
export function createNativeFileInput(document:Document,options:NativeFileInputOptions):{element:HTMLLabelElement;input:HTMLInputElement;dispose():void} {
  bounded(options.label,256);if(!Number.isSafeInteger(options.maxBytes)||options.maxBytes<1)throw new ValidationFailure('Use a finite file-size policy');
  if(typeof options.onFiles!=='function'||options.capture!==undefined&&!['user','environment'].includes(options.capture))throw new ValidationFailure('Use a file callback and supported capture hint');
  const element=document.createElement('label');element.textContent=options.label;const input=document.createElement('input');input.type='file';
  if(options.accept){if(options.accept.some(value=>typeof value!=='string'||!/^(?:[a-z]+\/[a-z0-9.+*-]+|\.[a-z0-9]+)$/i.test(value)))throw new ValidationFailure('Use MIME or extension accept hints');input.accept=options.accept.join(',');}
  if(options.capture)input.setAttribute('capture',options.capture);element.append(input);
  const change=()=>{const files=Array.from(input.files??[]);if(files.some(file=>file.size>options.maxBytes)){options.onError?.(safeErrorReport(new ValidationFailure()));return;}options.onFiles(Object.freeze(files));};
  input.addEventListener('change',change);return {element,input,dispose(){input.removeEventListener('change',change);element.remove();}};
}

export interface TelegramServerlessError extends NativeServerlessError {}
export interface TelegramServerlessBridge {
  call(name:string,callback?:(error:TelegramServerlessError|null,result?:unknown)=>void):void;
  call(name:string,input:Readonly<Record<string,unknown>>,callback?:(error:TelegramServerlessError|null,result?:unknown)=>void):void;
}
export interface ServerlessCallOptions {operation?:OperationKind;signal?:AbortSignal}
/** Optional hosting-specific presence adapter: official docs publish NO minimum client version. */
export class ServerlessEndpointClient {
  private disposed=false;private generation=0;private readonly pending=new Set<()=>void>();
  private readonly options:Readonly<{serverlessHosting:boolean;timeoutMs?:number}>;
  constructor(private readonly app:unknown,options:{serverlessHosting:boolean;timeoutMs?:number}){
    if(typeof options.serverlessHosting!=='boolean'||options.timeoutMs!==undefined&&(!Number.isFinite(options.timeoutMs)||options.timeoutMs<1||options.timeoutMs>120000))throw new ValidationFailure('Explicitly opt into Serverless hosting and bounded timeout');
    this.options={...options};
  }
  supports():boolean{try{return !this.disposed&&this.options.serverlessHosting&&isInsideTelegram(this.app)&&object(this.app)&&typeof this.app.initData==='string'&&this.app.initData.length>0&&object(this.app.Serverless)&&typeof this.app.Serverless.call==='function';}catch{return false;}}
  invalidateAccount():void {this.generation++;for(const cancel of [...this.pending])cancel();}
  call<T>(name:string,input:Readonly<Record<string,unknown>>,decode:(value:unknown)=>T,options:ServerlessCallOptions={}):Promise<NativeFlowResult<T>> {
    if(options.operation!==undefined&&!['read','write'].includes(options.operation))throw new ValidationFailure('Use read or write endpoint operation');
    if(!/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(name))throw new ValidationFailure('Use a bounded documented endpoint identifier');
    if(!object(input)||Array.isArray(input)||Object.getPrototypeOf(input)!==Object.prototype&&Object.getPrototypeOf(input)!==null||typeof decode!=='function')throw new ValidationFailure('Use a plain JSON object and a decoder');
    const serialized=endpointInput(input),operation=options.operation??'write';
    if(!this.supports())return Promise.resolve(status('unsupported'));if(this.pending.size>=16)return Promise.resolve(status('busy'));
    if(options.signal?.aborted)return Promise.resolve(status('cancelled'));const generation=this.generation;
    return new Promise(resolve=>{
      let done=false;const finish=(value:NativeFlowResult<T>)=>{if(done)return;done=true;clearTimeout(timer);options.signal?.removeEventListener('abort',abort);this.pending.delete(stale);resolve(value);};
      const unknown=()=>finish({status:'unknown',error:safeErrorReport(new UnknownOutcome(),operation)});
      const stale=()=>finish(status('stale'));const abort=()=>unknown();const timer=setTimeout(unknown,this.options.timeoutMs??15000);this.pending.add(stale);options.signal?.addEventListener('abort',abort,{once:true});
      const callback=(error:TelegramServerlessError|null,value?:unknown)=>{
        if(done)return;if(this.disposed||generation!==this.generation){stale();return;}
        if(error!==null){const raw=object(error)?error:undefined,rejected=raw?.type==='UNAUTHORIZED'&&raw.status===401,uncertain=raw?.status===0||operation==='write'&&!rejected;const failure=rejected?new AuthenticationRequired():uncertain?new UnknownOutcome():new PatternError('invalid-response','read-failed');finish({status:uncertain?'unknown':'failed',error:safeErrorReport(failure,operation)});return;}
        try{const decoded=decode(value);if(object(decoded)&&typeof decoded.then==='function'){void Promise.resolve(decoded).catch(()=>undefined);throw new InvalidType('Use a synchronous endpoint decoder');}finish(completed(decoded));}catch{finish({status:operation==='write'?'unknown':'failed',error:safeErrorReport(operation==='write'?new UnknownOutcome():new PatternError('invalid-response','read-failed'),operation)});}
      };
      try{const app=this.app as {Serverless:TelegramServerlessBridge};app.Serverless.call(name,JSON.parse(serialized) as Record<string,unknown>,callback);}catch(error){finish({status:operation==='write'?'unknown':'failed',error:safeErrorReport(operation==='write'?new UnknownOutcome():error,operation)});}
    });
  }
  dispose():void {if(this.disposed)return;this.disposed=true;this.invalidateAccount();}
}
