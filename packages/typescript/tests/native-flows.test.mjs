import test from 'node:test';
import assert from 'node:assert/strict';
import {NativeFlowScope,NativeActionButtons,NativePrompts,NativeAccountStorage,NativeSharing,ServerlessEndpointClient,ValidationFailure,AuthenticationRequired,UnknownOutcome,TelegramNativeAPI} from '../dist/index.js';
// Inline protocol fixture keeps the installed-package behavior suite self-contained.
/** Explicit local SDK fixture. No Telegram, Serverless, device permission or network calls. */
function createFakeNativeApp({version='9.6',platform='android',automatic=false,mode='completed'}={}){
  const calls=[],listeners=new Map(),queues=new Map(),timers=new Set();let failOff=0;
  const state={mode,qrOpen:false};
  const dispatch=(name,args)=>{const queue=queues.get(name)??[];const entry=queue.shift();if(!entry)throw Error('No pending fake callback: '+name);entry.before?.();return entry.callback?.(...(args??entry.args));};
  const push=(name,callback,args=[],before)=>{
    const queue=queues.get(name)??[];queue.push({callback,args,before});queues.set(name,queue);
    if(automatic&&state.mode!=='late'){const timer=setTimeout(()=>{timers.delete(timer);if(queue.length)dispatch(name);},10);timers.add(timer);}
  };
  const record=(name,...args)=>calls.push({name,args});
  const app={version,platform,initData:'PRIVATE_INIT_DATA_CANARY',
    isVersionAtLeast(required){const a=this.version.split('.').map(Number),b=required.split('.').map(Number);return a[0]>b[0]||a[0]===b[0]&&a[1]>=b[1];},
    ready(){record('ready');},
    onEvent(name,callback){const set=listeners.get(name)??new Set();set.add(callback);listeners.set(name,set);record('onEvent',name);},
    offEvent(name,callback){if(failOff>0){failOff--;throw Error('PRIVATE_OFF_ERROR');}listeners.get(name)?.delete(callback);record('offEvent',name);},
    showPopup(params,callback){record('showPopup',params);push('popup',callback,[state.mode==='cancelled'?null:params.buttons?.[0]?.id??'']);},
    showScanQrPopup(params,callback){record('showScanQrPopup',params);state.qrOpen=true;push('qr',callback,['untrusted://text-from-code']);},
    closeScanQrPopup(){record('closeScanQrPopup');state.qrOpen=false;emit('scanQrPopupClosed');},
    openInvoice(url,callback){record('openInvoice',url);push('invoice',callback,[state.mode==='cancelled'?'cancelled':'paid']);},
    requestContact(callback){record('requestContact');push('contact',callback,[state.mode!=='denied']);},
    shareMessage(id,callback){record('shareMessage',id);push('share',callback,[state.mode!=='denied']);},
    shareToStory(url,params){record('shareToStory',url,params);},
    downloadFile(params,callback){record('downloadFile',params);push('download',callback,[state.mode!=='denied']);},
  };
  const emit=(name,...args)=>{for(const callback of [...listeners.get(name)??[]])callback(...args);};
  for(const [prefix,event]of [['MainButton','mainButtonClicked'],['SecondaryButton','secondaryButtonClicked'],['BackButton','backButtonClicked']]){
    const button={visible:false,enabled:true,loading:false,text:'',show(){this.visible=true;record(prefix+'.show');return this;},hide(){this.visible=false;record(prefix+'.hide');return this;},onClick(callback){app.onEvent(event,callback);return this;},offClick(callback){app.offEvent(event,callback);return this;}};
    if(prefix!=='BackButton')Object.assign(button,{setText(value){this.text=value;record(prefix+'.setText',value);return this;},enable(){this.enabled=true;return this;},disable(){this.enabled=false;return this;},showProgress(active){this.loading=true;this.enabled=active;record(prefix+'.showProgress',active);return this;},hideProgress(){this.loading=false;record(prefix+'.hideProgress');return this;}});
    app[prefix]=button;
  }
  app.LocationManager={isInited:false,isLocationAvailable:true,isAccessRequested:false,isAccessGranted:false,
    init(callback){record('LocationManager.init');push('location-init',callback,[],()=>{this.isInited=true;});return this;},
    getLocation(callback){record('LocationManager.getLocation');push('location',callback,[state.mode==='denied'?null:{latitude:55,longitude:37,altitude:null,course:null,speed:null,horizontal_accuracy:10,vertical_accuracy:null,course_accuracy:null,speed_accuracy:null}],()=>{this.isAccessRequested=true;this.isAccessGranted=state.mode!=='denied';});return this;},
  };
  app.BiometricManager={isInited:false,isBiometricAvailable:true,isAccessRequested:false,isAccessGranted:false,
    init(callback){record('BiometricManager.init');push('biometric-init',callback,[],()=>{this.isInited=true;});return this;},
    requestAccess(params,callback){record('BiometricManager.requestAccess',params);push('biometric-access',callback,[state.mode!=='denied'],()=>{this.isAccessRequested=true;this.isAccessGranted=state.mode!=='denied';});return this;},
    authenticate(params,callback){record('BiometricManager.authenticate',params);push('biometric-auth',callback,[state.mode!=='denied','PRIVATE_BIOMETRIC_TOKEN']);return this;},
  };
  const storage={cloud:new Map(),device:new Map(),secure:new Map(),restore:new Map()};
  for(const [kind,prefix]of [['cloud','CloudStorage'],['device','DeviceStorage'],['secure','SecureStorage']]){
    app[prefix]={
      getItem(key,callback){record(prefix+'.getItem',key);push(kind+'-get',callback,[null,storage[kind].get(key)??(kind==='cloud'?'':null),kind==='secure'&&storage.restore.has(key)]);return this;},
      setItem(key,value,callback){record(prefix+'.setItem',key,value);storage[kind].set(key,value);push(kind+'-set',callback,[null,true]);return this;},
      removeItem(key,callback){record(prefix+'.removeItem',key);storage[kind].delete(key);push(kind+'-remove',callback,[null,true]);return this;},
    };
  }
  app.SecureStorage.restoreItem=function(key,callback){record('SecureStorage.restoreItem',key);push('secure-restore',callback,state.mode==='denied'?['PRIVATE_RESTORE_ERROR']:[null,storage.restore.get(key)??null]);return this;};
  app.Serverless={call(name,input,callback){if(typeof input==='function'){callback=input;input={};}record('Serverless.call',name,input);push('serverless',callback,state.mode==='error'?[{message:'PRIVATE_ENDPOINT_MESSAGE',type:'ENDPOINT_ERROR',status:409,parameters:{secret:'PRIVATE_ENDPOINT_PARAMETERS'}},null]:[null,{label:'Fixture endpoint result'}]);}};
  return {app,calls,state,storage,listeners,emit,
    flush(name){return dispatch(name);},reply(name,...args){return dispatch(name,args);},
    take(name){const entry=(queues.get(name)??[]).shift();if(!entry)throw Error('No fake callback: '+name);return (...args)=>{entry.before?.();return entry.callback?.(...args);};},
    failOff(count=1){failOff=count;},pending(name){return queues.get(name)?.length??0;},
    dispose(){for(const timer of timers)clearTimeout(timer);timers.clear();},
  };
}


const action={purpose:'Выбрать адрес для текущей записи',userInitiated:true};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function setup(t,options={},scopeOptions={}){
  const fake=createFakeNativeApp(options),scope=new NativeFlowScope(fake.app,{accountTag:'bot100_account42',launch:'direct',timeoutMs:1000,...scopeOptions});
  t.after(()=>{scope.dispose();fake.dispose();});return {...fake,scope,prompts:new NativePrompts(scope),storageFlow:new NativeAccountStorage(scope),sharing:new NativeSharing(scope)};
}
test('public native popup callback preserves null cancellation rather than fabricating an ID',t=>{
  const f=setup(t),api=new TelegramNativeAPI(f.app),seen=[];t.after(()=>api.dispose());
  api.call('showPopup',{message:'Close without button'},buttonId=>seen.push(buttonId));f.reply('popup',null);
  assert.deepEqual(seen,[null]);
});
test('capability matrix combines version presence platform launch hardware permission and account state',async t=>{
  for(const [version,main,secondary]of [['6.0',false,false],['6.1',true,false],['7.10',true,true]]){
    const f=setup(t,{version});const rows=f.scope.capabilities();assert.equal(rows.find(r=>r.flow==='main-button').available,main);assert.equal(rows.find(r=>r.flow==='secondary-button').available,secondary);assert.equal(rows[0].launch,'direct');
  }
  const f=setup(t,{}, {accountTag:null,launch:'keyboard',platformPolicy:(flow,platform,launch)=>flow!=='share-message'||platform!=='android'||launch!=='keyboard'});
  assert.equal(f.scope.capabilities().find(r=>r.flow==='device-storage').state,'needs-account');
  assert.equal(f.scope.capabilities().find(r=>r.flow==='location').state,'needs-init');assert.equal(f.scope.capabilities().find(r=>r.flow==='share-message').available,false);
  f.app.LocationManager.isLocationAvailable=false;const prepare=f.prompts.prepareLocation();f.flush('location-init');assert.equal((await prepare).value.available,false);assert.equal(f.scope.capabilities().find(r=>r.flow==='location').state,'unavailable');
  const outside=setup(t,{platform:'unknown'});assert.ok(outside.scope.capabilities().every(r=>!r.available));
  delete f.app.MainButton.enable;assert.equal(f.scope.capabilities().find(r=>r.flow==='main-button').available,false);
});
test('native buttons own all handlers visibility progress and duplicate activation',async t=>{
  const f=setup(t);let calls=0,release;const buttons=new NativeActionButtons(f.scope,{main:()=>{calls++;return new Promise(resolve=>{release=resolve;});},secondary:()=>{calls+=10;},back:()=>{calls+=100;}});t.after(()=>buttons.dispose());
  buttons.render({main:{text:'Подтвердить',visible:true},secondary:{text:'Назад',visible:true},backVisible:true});
  f.emit('mainButtonClicked');f.emit('mainButtonClicked');await tick();assert.equal(calls,1);assert.equal(f.app.MainButton.loading,true);assert.equal(f.app.MainButton.enabled,false);
  release();await tick();assert.equal(f.app.MainButton.loading,false);assert.equal(f.app.MainButton.enabled,true);
  f.emit('secondaryButtonClicked');f.emit('backButtonClicked');await tick();assert.equal(calls,111);
  buttons.render({main:{text:'Скрыто',visible:false},backVisible:false});assert.equal(f.app.MainButton.visible,false);f.emit('mainButtonClicked');f.emit('backButtonClicked');await tick();assert.equal(calls,111);
  buttons.dispose();assert.ok([...f.listeners.values()].every(set=>set.size===0));assert.equal(f.app.SecondaryButton.visible,false);f.emit('mainButtonClicked');assert.equal(calls,111);
});
test('queued button actions cannot start after disposal or account change and cleanup is retryable',async t=>{
  const f=setup(t);let calls=0;let buttons=new NativeActionButtons(f.scope,{main:()=>{calls++;}});buttons.render({main:{text:'Действие',visible:true}});
  f.emit('mainButtonClicked');buttons.dispose();await tick();assert.equal(calls,0);
  buttons=new NativeActionButtons(f.scope,{main:()=>{calls++;}});buttons.render({main:{text:'Действие',visible:true}});
  f.emit('mainButtonClicked');f.scope.setAccount('bot100_account77');await tick();assert.equal(calls,0);f.emit('mainButtonClicked');await tick();assert.equal(calls,0);
  f.failOff(1);assert.throws(()=>buttons.dispose(),UnknownOutcome);buttons.dispose();assert.ok([...f.listeners.values()].every(set=>set.size===0));
});
test('popup cancellation success validation and busy duplicate preserve the active owner',async t=>{
  const f=setup(t);assert.throws(()=>f.prompts.popup({message:'x',buttons:[]}),ValidationFailure);assert.throws(()=>f.prompts.popup({message:'x',buttons:[{type:'default'}]}),ValidationFailure);
  const first=f.prompts.popup({message:'Продолжить?',buttons:[{id:'confirm',type:'ok'}]});
  assert.equal((await f.prompts.popup({message:'Duplicate'})).status,'busy');assert.equal(f.pending('popup'),1);f.reply('popup','confirm');assert.deepEqual(await first,{status:'completed',value:{buttonId:'confirm'}});
  const cancel=f.prompts.popup({message:'Отмена',buttons:[{id:'cancel',type:'cancel'}]});f.reply('popup','cancel');assert.equal((await cancel).status,'cancelled');
  const close=f.prompts.popup({message:'Закрытие'});f.reply('popup',null);assert.equal((await close).status,'cancelled');
  const emptyClose=f.prompts.popup({message:'Default close'});f.reply('popup','');assert.equal((await emptyClose).status,'cancelled');
  const original={message:'Snapshot',buttons:[{id:'ok',type:'ok'}]};const snapshot=f.prompts.popup(original);original.buttons[0].id='changed';f.reply('popup','ok');assert.equal((await snapshot).value.buttonId,'ok');
  const unknown=f.prompts.popup({message:'Unknown response',buttons:[{id:'ok',type:'ok'}]});f.reply('popup','not-shown');assert.equal((await unknown).status,'failed');
});
test('timeout keeps native prompt occupied until real callback or fenced explicit closure',async t=>{
  const f=setup(t,{}, {timeoutMs:5});const request=f.prompts.popup({message:'Await native'});const late=f.take('popup');const unknown=await request;
  assert.equal(unknown.status,'unknown');assert.equal(unknown.error.recovery,'reconcile');assert.equal((await f.prompts.contact(action)).status,'busy');
  assert.equal(f.scope.confirmPromptClosed('wrong'),false);assert.equal(f.scope.confirmPromptClosed(unknown.recoveryId),true);
  const next=f.prompts.popup({message:'Next',buttons:[{id:'ok',type:'ok'}]});late('old');assert.equal((await f.prompts.contact(action)).status,'busy');f.reply('popup','ok');assert.equal((await next).status,'completed');
  assert.equal(f.scope.confirmPromptClosed(unknown.recoveryId),false);
});
test('QR rejects malformed data, preserves current scanner on duplicate and ignores late callbacks',async t=>{
  const f=setup(t);const request=f.prompts.qr({text:'Код услуги'},action);const callback=f.take('qr');
  assert.equal((await f.prompts.qr({},action)).status,'busy');assert.equal(f.calls.filter(c=>c.name==='closeScanQrPopup').length,0);
  assert.equal(callback(''),false);assert.equal(callback('untrusted://not-opened'),true);assert.deepEqual((await request).value,{text:'untrusted://not-opened'});
  assert.equal(f.calls.some(c=>c.name==='openLink'),false);
  const second=f.prompts.qr({},action);assert.equal(callback('late-old'),false);assert.equal(f.pending('qr'),1);f.reply('qr','current');assert.equal((await second).value.text,'current');
});
test('QR abort closes only its scanner; old clients require explicit closure recovery',async t=>{
  const f=setup(t,{version:'6.4'}, {timeoutMs:1000});const abort=new AbortController();const request=f.prompts.qr({},action,abort.signal);abort.abort();const result=await request;
  assert.equal(result.status,'unknown');assert.equal(f.calls.filter(c=>c.name==='closeScanQrPopup').length,1);assert.equal((await f.prompts.popup({message:'Still occupied'})).status,'busy');
  assert.equal(f.scope.confirmPromptClosed(result.recoveryId),true);
  const again=f.prompts.qr({},action);f.scope.dispose();assert.equal((await again).status,'stale');assert.equal(f.calls.filter(c=>c.name==='closeScanQrPopup').length,2);
});
test('invoice native paid pending cancelled failed never confirms backend payment',async t=>{
  const f=setup(t);assert.throws(()=>f.prompts.invoice('https://evil.example/pay',action),ValidationFailure);
  for(const nativeStatus of ['paid','pending','cancelled','failed']){const flow=f.prompts.invoice('https://t.me/$server-issued',action);f.reply('invoice',nativeStatus);const result=await flow;assert.equal(result.status,'completed');assert.deepEqual(result.value,{nativeStatus,requiresServerReconciliation:true});assert.equal('paid'in result.value,false);}
});
test('contextual contact consent differs from unsupported and ignores account-stale response',async t=>{
  const f=setup(t);assert.throws(()=>f.prompts.contact({purpose:'No user gesture'}),ValidationFailure);
  let request=f.prompts.contact(action);f.reply('contact',false);assert.equal((await request).status,'denied');
  request=f.prompts.contact(action);f.scope.setAccount('bot100_account77');const result=await request;assert.equal(result.status,'stale');f.reply('contact',true);
  request=f.prompts.contact(action);f.reply('contact',true);assert.deepEqual((await request).value,{shared:true});
  const old=setup(t,{version:'6.8'});assert.equal((await old.prompts.contact(action)).status,'unsupported');
});
test('location initializes hardware, handles denied and rejects invalid coordinates without identity claims',async t=>{
  const f=setup(t);assert.equal((await f.prompts.location(action)).status,'unsupported');
  const init=f.prompts.prepareLocation();f.flush('location-init');assert.equal((await init).value.available,true);
  let request=f.prompts.location(action);f.reply('location',null);assert.equal((await request).status,'denied');
  request=f.prompts.location(action);f.flush('location');const result=await request;assert.equal(result.value.latitude,55);assert.equal('actorId'in result.value,false);
  request=f.prompts.location(action);f.reply('location',{latitude:91,longitude:0});assert.equal((await request).status,'failed');
  request=f.prompts.location(action);f.reply('location',{latitude:55,longitude:37,actorId:1,role:'admin'});const untrusted=await request;assert.equal(untrusted.status,'completed');assert.equal('role'in untrusted.value,false);assert.equal('actorId'in untrusted.value,false);
});
test('biometric permission and local unlock are separate; account change ignores late token',async t=>{
  const f=setup(t);const init=f.storageFlow.prepareBiometric();f.flush('biometric-init');assert.equal((await init).value.available,true);
  assert.equal((await f.storageFlow.unlockBiometric(action)).status,'denied');
  let request=f.storageFlow.requestBiometricAccess(action);f.reply('biometric-access',false);assert.equal((await request).status,'denied');
  request=f.storageFlow.requestBiometricAccess(action);f.reply('biometric-access',true);f.app.BiometricManager.isAccessGranted=true;assert.equal((await request).status,'completed');
  const auth=f.storageFlow.unlockBiometric(action);const late=f.take('biometric-auth');f.scope.setAccount('bot100_account77');assert.equal((await auth).status,'stale');late(true,'PRIVATE_OLD_ACCOUNT_TOKEN');
  const current=f.storageFlow.unlockBiometric(action);f.reply('biometric-auth',false);assert.deepEqual((await current).value,{authenticated:false});
  assert.equal(f.calls.some(call=>call.name.includes('setItem')),false);
});
test('all native storage kinds isolate account keys and do not clear other accounts or downgrade',async t=>{
  const f=setup(t);for(const kind of ['cloud','device','secure']){
    let write=f.storageFlow.write(kind,'draft','account42');f.flush(kind+'-set');assert.equal((await write).value.stored,true);
    f.scope.setAccount('bot100_account77');write=f.storageFlow.write(kind,'draft','account77');f.flush(kind+'-set');await write;
    const read=f.storageFlow.read(kind,'draft');f.flush(kind+'-get');assert.equal((await read).value.value,'account77');
    assert.equal(f.storage[kind].get('tp_16_bot100_account42_draft'),'account42');
    const remove=f.storageFlow.remove(kind,'draft');f.flush(kind+'-remove');assert.equal((await remove).value.removed,true);assert.equal(f.storage[kind].get('tp_16_bot100_account42_draft'),'account42');
    f.scope.setAccount('bot100_account42');
  }
  assert.equal(f.calls.some(c=>c.name.endsWith('.clear')),false);f.scope.setAccount(null);assert.throws(()=>f.storageFlow.read('secure','draft'),AuthenticationRequired);
});
test('late storage callbacks cannot update a new account and unknown write keeps its key busy',async t=>{
  const f=setup(t,{}, {timeoutMs:5});const old=f.storageFlow.read('device','draft');const callback=f.take('device-get');f.scope.setAccount('bot100_account77');assert.equal((await old).status,'stale');callback(null,'PRIVATE_OLD_ACCOUNT_VALUE');
  const write=f.storageFlow.write('device','draft','persisted-before-response');const result=await write;assert.equal(result.status,'unknown');assert.equal((await f.storageFlow.read('device','draft')).status,'busy');
  f.flush('device-set');const current=f.storageFlow.read('device','draft');f.flush('device-get');assert.equal((await current).value.value,'persisted-before-response');
});
test('secure recovery is explicit contextual consent and does not fall back to plain storage',async t=>{
  const f=setup(t);f.storage.restore.set('tp_16_bot100_account42_secret','restored-local-value');const read=f.storageFlow.read('secure','secret');f.flush('secure-get');assert.deepEqual((await read).value,{value:null,canRestore:true});assert.equal(f.calls.some(c=>c.name==='SecureStorage.restoreItem'),false);
  let request=f.storageFlow.restoreSecure('secret',action);f.reply('secure-restore','PRIVATE_DENIED_ERROR');const denial=await request;assert.equal(denial.status,'failed');assert.equal(JSON.stringify(denial).includes('PRIVATE'),false);
  request=f.storageFlow.restoreSecure('secret',action);f.flush('secure-restore');assert.equal((await request).value.value,'restored-local-value');
  const unsupported=setup(t,{version:'8.0'});assert.equal((await unsupported.storageFlow.read('secure','secret')).status,'unsupported');assert.equal(unsupported.calls.some(c=>c.name.includes('Storage.')),false);
});
test('sharing prepared ID and file download report exact local meanings with validated URLs',async t=>{
  const f=setup(t);const share=f.sharing.message('server-prepared-id',action);f.reply('share',true);assert.deepEqual((await share).value,{sent:true});
  const download=f.sharing.download({url:'https://example.org/report.pdf',file_name:'report.pdf'},action);f.reply('download',true);assert.deepEqual((await download).value,{accepted:true,persisted:false});
  assert.deepEqual(f.sharing.story('https://example.org/story.jpg',{text:'Preview'},action).value,{editorRequested:true});
  assert.throws(()=>f.sharing.download({url:'http://example.org/report.pdf',file_name:'report.pdf'},action),ValidationFailure);assert.throws(()=>f.sharing.download({url:'https://example.org/',file_name:'../secret'},action),ValidationFailure);
});
test('Serverless presence uses explicit hosting and initData rather than invented minimum version',async t=>{
  const f=setup(t,{version:'6.0'});for(const [patch,hosted,available]of [[{},true,true],[{},false,false],[{platform:'unknown'},true,false],[{initData:''},true,false],[{Serverless:{}},true,false]]){
    const client=new ServerlessEndpointClient({...f.app,...patch},{serverlessHosting:hosted});t.after(()=>client.dispose());assert.equal(client.supports(),available);
  }
  const client=new ServerlessEndpointClient(f.app,{serverlessHosting:true});t.after(()=>client.dispose());const result=client.call('getProfile',{},value=>({label:value.label}),{operation:'read'});f.flush('serverless');assert.equal((await result).value.label,'Fixture endpoint result');
});
test('Serverless status0 endpoint errors decoder failures and timeouts never blindly retry writes',async t=>{
  const f=setup(t);const client=new ServerlessEndpointClient(f.app,{serverlessHosting:true,timeoutMs:5});t.after(()=>client.dispose());
  for(const error of [{message:'PRIVATE_MESSAGE',status:0,type:'UNAUTHORIZED'},{message:'PRIVATE_MESSAGE',status:409,type:'ENDPOINT_ERROR',parameters:{token:'PRIVATE_PARAMETER'}}]){
    const request=client.call('place_order',{operation_id:'same-stable-id'},value=>value,{operation:'write'});f.reply('serverless',error,null);const result=await request;assert.equal(result.status,'unknown');assert.equal(result.error.recovery,'reconcile');assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
  }
  let request=client.call('place_order',{},()=>{throw new ValidationFailure('PRIVATE_DECODE');},{operation:'write'});f.reply('serverless',null,{});let result=await request;assert.equal(result.status,'unknown');assert.equal(result.error.outcome,'unknown');
  request=client.call('place_order',{},value=>value);const late=f.take('serverless');result=await request;assert.equal(result.status,'unknown');late(null,{paid:true});assert.equal(f.calls.filter(c=>c.name==='Serverless.call').length,4);
});
test('Serverless unauthorized is pre-endpoint rejection; account invalidation and dispose fence replies',async t=>{
  const f=setup(t);const client=new ServerlessEndpointClient(f.app,{serverlessHosting:true});t.after(()=>client.dispose());
  let request=client.call('getProfile',{},value=>value,{operation:'read'});f.reply('serverless',{message:'PRIVATE_AUTH',type:'UNAUTHORIZED',status:401});const rejected=await request;assert.equal(rejected.error.code,'authentication-required');assert.equal(rejected.error.outcome,'rejected');
  let decodes=0;request=client.call('getProfile',{},value=>{decodes++;return value;});const old=f.take('serverless');client.invalidateAccount();assert.equal((await request).status,'stale');old(null,{secret:'PRIVATE_OLD_ACCOUNT'});assert.equal(decodes,0);
  request=client.call('getProfile',{},value=>value);client.dispose();assert.equal((await request).status,'stale');f.reply('serverless',null,{secret:'PRIVATE_AFTER_DISPOSE'});assert.equal((await client.call('getProfile',{},value=>value)).status,'unsupported');
});
test('Serverless validates endpoint names and finite plain JSON before any native call',async t=>{
  const f=setup(t),client=new ServerlessEndpointClient(f.app,{serverlessHosting:true});t.after(()=>client.dispose());
  const cyclic={};cyclic.self=cyclic;let getterRan=false;const accessor={get secret(){getterRan=true;return 'secret';}};
  const deep={};let nested=deep;for(let i=0;i<34;i++){nested.value={};nested=nested.value;}
  for(const input of [[],{value:NaN},{value:undefined},{value:new Date()},cyclic,accessor,deep,{value:'Ж'.repeat(40000)}])assert.throws(()=>client.call('getProfile',input,value=>value),ValidationFailure);
  assert.throws(()=>client.call('../unsafe',{},value=>value),ValidationFailure);assert.equal(getterRan,false);assert.equal(f.calls.filter(c=>c.name==='Serverless.call').length,0);
});
test('late button failure and finally cannot report or overwrite controls of a changed account',async t=>{
  const f=setup(t);let reject,reported=0;const old=new NativeActionButtons(f.scope,{main:()=>new Promise((_resolve,fail)=>{reject=fail;}),onError:()=>{reported++;}});
  old.render({main:{text:'Old account',visible:true}});f.emit('mainButtonClicked');await tick();f.scope.setAccount('bot100_account77');
  const current=new NativeActionButtons(f.scope,{main:()=>{}});current.render({main:{text:'New account',visible:true}});
  reject(new Error('PRIVATE_OLD_ACCOUNT_FAILURE'));await tick();assert.equal(reported,0);assert.equal(f.app.MainButton.text,'New account');old.dispose();assert.equal(f.app.MainButton.visible,true);current.dispose();
});

test('synchronous native open error retains unknown ownership and never exposes raw SDK text',async t=>{
  const f=setup(t);f.app.showPopup=()=>{throw new Error('PRIVATE_SDK_OPEN_ERROR');};
  const result=await f.prompts.popup({message:'May have opened'});assert.equal(result.status,'unknown');assert.equal(result.error.recovery,'reconcile');assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
  assert.equal((await f.prompts.contact(action)).status,'busy');assert.equal(f.scope.confirmPromptClosed(result.recoveryId),true);
  const contact=f.prompts.contact(action);f.reply('contact',false);assert.equal((await contact).status,'denied');
});

test('Serverless rejects asynchronous decoders without unhandled rejections and abort cannot cancel a started write',async t=>{
  const f=setup(t),client=new ServerlessEndpointClient(f.app,{serverlessHosting:true});t.after(()=>client.dispose());
  for(const operation of ['read','write']){
    const request=client.call('getProfile',{},async()=>{throw new Error('PRIVATE_ASYNC_DECODE');},{operation});f.reply('serverless',null,{});
    const result=await request;assert.equal(result.status,operation==='write'?'unknown':'failed');assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
  }
  const aborted=new AbortController();aborted.abort();assert.equal((await client.call('place_order',{},value=>value,{signal:aborted.signal})).status,'cancelled');assert.equal(f.pending('serverless'),0);
  const active=new AbortController();let decodes=0;const request=client.call('place_order',{operation_id:'same-operation'},value=>{decodes++;return value;},{signal:active.signal});
  const late=f.take('serverless');active.abort();const result=await request;assert.equal(result.status,'unknown');assert.equal(result.error.recovery,'reconcile');late(null,{committed:true});assert.equal(decodes,0);await tick();
});

test('storage completed false is a reply to inspect and account key limits stay within portable bounds',async t=>{
  const f=setup(t);
  for(const kind of ['cloud','device','secure']){
    const write=f.storageFlow.write(kind,'draft','value');f.reply(kind+'-set',null,false);assert.deepEqual(await write,{status:'completed',value:{stored:false}});
    const remove=f.storageFlow.remove(kind,'draft');f.reply(kind+'-remove',null,false);assert.deepEqual(await remove,{status:'completed',value:{removed:false}});
  }
  assert.throws(()=>new NativeFlowScope(f.app,{accountTag:'x'.repeat(49),launch:'direct'}),ValidationFailure);
  f.scope.setAccount('x'.repeat(48));const key='k'.repeat(48);const read=f.storageFlow.read('cloud',key);f.flush('cloud-get');await read;
  assert.equal(f.calls.at(-1).args[0].length,103);
  for(const bad of ['', 'k'.repeat(49),'unsafe/key'])assert.throws(()=>f.storageFlow.read('cloud',bad),ValidationFailure);
  assert.throws(()=>f.storageFlow.write('cloud',key,'x'.repeat(4097)),ValidationFailure);
  const empty=f.storageFlow.write('cloud',key,'');f.reply('cloud-set',null,true);assert.equal((await empty).value.stored,true);
});


test('storage namespace cannot alias another account when both tags and field keys contain underscores',async t=>{
  const f=setup(t);
  for(const kind of ['cloud','device','secure']){
    f.scope.setAccount('a_b');let write=f.storageFlow.write(kind,'c','first-account');f.flush(kind+'-set');assert.equal((await write).value.stored,true);
    f.scope.setAccount('a');const foreign=f.storageFlow.read(kind,'b_c');f.flush(kind+'-get');assert.notEqual((await foreign).value.value,'first-account');
    write=f.storageFlow.write(kind,'b_c','second-account');f.flush(kind+'-set');await write;
    f.scope.setAccount('a_b');const original=f.storageFlow.read(kind,'c');f.flush(kind+'-get');assert.equal((await original).value.value,'first-account');
    const remove=f.storageFlow.remove(kind,'c');f.flush(kind+'-remove');await remove;
    f.scope.setAccount('a');const retained=f.storageFlow.read(kind,'b_c');f.flush(kind+'-get');assert.equal((await retained).value.value,'second-account');
  }
});
