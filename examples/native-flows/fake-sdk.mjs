/** Explicit local SDK fixture. No Telegram, Serverless, device permission or network calls. */
export function createFakeNativeApp({version='9.6',platform='android',automatic=false,mode='completed'}={}){
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
