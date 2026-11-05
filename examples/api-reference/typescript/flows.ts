import {NativeFlowScope,NativeActionButtons,NativePrompts,NativeAccountStorage,NativeSharing,createNativeFileInput,ServerlessEndpointClient,
  type NativeFlowResult,type NativeLaunch,type NativeInteraction,type NativeFlowKind,type NativeScopeOptions,type NativeCapability,
  type NativeButtonsState,type NativeButtonHandlers,type NativeStorageKind,type NativeStoredValue,type NativeFileInputOptions,
  type TelegramServerlessError,type TelegramServerlessBridge,type ServerlessCallOptions} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Installed-package fake callbacks + real DOM, not Telegram/backend authentication. */
export async function referenceFlows(document:Document):Promise<void>{
  const host=document.createElement('section');document.body.append(host);
  const listeners=new Map<string,Set<()=>void>>(),records=new Map<string,string>();
  const replies:{popup?:(id:string|null)=>void;share?:(sent:boolean)=>void}={};let presses=0,visible=false;
  const endpointError:TelegramServerlessError={message:'PRIVATE_SERVERLESS_MESSAGE',type:'ENDPOINT_ERROR',status:0,parameters:{secret:'PRIVATE_PARAMETERS'}};
  const raw:TelegramServerlessBridge={call(_name:string,input?:Readonly<Record<string,unknown>>|((error:TelegramServerlessError|null,result?:unknown)=>void),callback?:(error:TelegramServerlessError|null,result?:unknown)=>void){const reply=typeof input==='function'?input:callback;reply?.(endpointError,null);}};
  const app={platform:'tdesktop',version:'9.6',initData:'PRIVATE_INITDATA_CANARY',Serverless:raw,isVersionAtLeast:()=>true,
    onEvent(name:string,callback:()=>void){const set=listeners.get(name)??new Set();set.add(callback);listeners.set(name,set);},
    offEvent(name:string,callback:()=>void){listeners.get(name)?.delete(callback);},
    MainButton:{setText(){return {};},show(){visible=true;return {};},hide(){visible=false;return {};},enable(){return {};},disable(){return {};},showProgress(){return {};},hideProgress(){return {};},onClick(){return {};},offClick(){return {};}},
    showPopup(_params:unknown,callback?:(id:string|null)=>void){if(callback)replies.popup=callback;},
    shareMessage(_id:string,callback?:(sent:boolean)=>void){if(callback)replies.share=callback;},
    DeviceStorage:{getItem(key:string,callback:(error:string|null,value?:string|null)=>void){callback(null,records.get(key)??null);return {};},setItem(key:string,value:string,callback?:(error:string|null,stored?:boolean)=>void){records.set(key,value);callback?.(null,true);return {};},removeItem(key:string,callback?:(error:string|null,removed?:boolean)=>void){records.delete(key);callback?.(null,true);return {};}},
  };
  const launch:NativeLaunch='direct',options:NativeScopeOptions={accountTag:'bot100_account42',launch,timeoutMs:5};
  const scope=new NativeFlowScope(app,options),flow:NativeFlowKind='popup';
  const capability:NativeCapability|undefined=scope.capabilities().find(value=>value.flow===flow);check(capability?.available&&capability.launch===launch);
  const handlers:NativeButtonHandlers={main:async()=>{presses++;}};const buttons=new NativeActionButtons(scope,handlers);
  const state:NativeButtonsState={main:{text:'Продолжить',visible:true}};buttons.render(state);check(visible);
  for(const listener of listeners.get('mainButtonClicked')??[])listener();await new Promise<void>(resolve=>setTimeout(resolve,0));check(presses===1);
  const prompts=new NativePrompts(scope);const popup:Promise<NativeFlowResult<{buttonId:string}>>=prompts.popup({message:'Продолжить?',buttons:[{id:'ok',type:'ok'}]});
  check((await prompts.popup({message:'Duplicate'})).status==='busy');check(replies.popup);const late=replies.popup;late(null);check((await popup).status==='cancelled');late('old');
  const storage=new NativeAccountStorage(scope),kind:NativeStorageKind='device';check((await storage.write(kind,'draft','account42')).status==='completed');
  buttons.dispose();scope.setAccount('bot100_account77');const read=await storage.read(kind,'draft');check(read.status==='completed');
  const stored:NativeStoredValue=read.value;check(stored.value===null&&records.get('tp_16_bot100_account42_draft')==='account42');
  const action:NativeInteraction={purpose:'Поделиться результатом текущего шага',userInitiated:true};const sharing=new NativeSharing(scope);
  const share=await sharing.message('server-prepared-id',action);check(share.status==='unknown'&&share.error.recovery==='reconcile');replies.share?.(false);
  check(sharing.story('https://example.org/approved.jpg',undefined,action).status==='unsupported');
  let selected=-1;const fileOptions:NativeFileInputOptions={label:'Файл без OS dialog',accept:['image/*'],capture:'environment',maxBytes:1024,onFiles:files=>{selected=files.length;}};
  const picker=createNativeFileInput(document,fileOptions);host.append(picker.element);picker.input.dispatchEvent(new Event('change'));check(selected===0&&picker.input.type==='file');
  const disabled=new ServerlessEndpointClient(app,{serverlessHosting:false});check((await disabled.call('getProfile',{},value=>value)).status==='unsupported');
  const serverless=new ServerlessEndpointClient(app,{serverlessHosting:true});const callOptions:ServerlessCallOptions={operation:'write'};
  const response=await serverless.call('place_order',{operation_id:'fixture-stable-operation'},value=>value,callOptions);
  check(response.status==='unknown'&&response.error.recovery==='reconcile'&&!JSON.stringify(response).includes('PRIVATE'));
  serverless.dispose();disabled.dispose();picker.dispose();scope.dispose();check(host.children.length===0&&[...listeners.values()].every(set=>set.size===0));host.remove();
}
