import {TelegramNativeAPI,type TelegramNativeSignatures,type TelegramNativeArguments,type TelegramNativeResult,
  NativeFlowScope,NativeActionButtons,NativePrompts,NativeAccountStorage,NativeSharing,createNativeFileInput,ServerlessEndpointClient,
  type NativeFlowResult,type NativeLaunch,type NativeInteraction,type NativeFlowKind,type NativeScopeOptions,
  type NativeCapability,type NativeButtonsState,type NativeButtonHandlers,type NativeStorageKind,type NativeStoredValue,
  type NativeFileInputOptions,type TelegramServerlessError,type TelegramServerlessBridge,type ServerlessCallOptions} from '../../dist/index.js';

export async function typedNativeWorkflows(api:TelegramNativeAPI,app:unknown,document:Document,raw:TelegramServerlessBridge):Promise<void>{
  const launch:NativeLaunch='direct';const options:NativeScopeOptions={accountTag:'bot100_account42',launch};
  const scope=new NativeFlowScope(app,options);const capability:NativeCapability|undefined=scope.capabilities()[0];
  const flow:NativeFlowKind='contact';void capability;void flow;
  const action:NativeInteraction={purpose:'Показать доступные услуги рядом',userInitiated:true};
  const handlers:NativeButtonHandlers={main:async()=>{},onError:report=>{const message:string=report.message;void message;}};
  const buttons=new NativeActionButtons(scope,handlers);const state:NativeButtonsState={main:{text:'Продолжить',visible:true},backVisible:true};buttons.render(state);
  const prompts=new NativePrompts(scope);const result:NativeFlowResult<{shared:true}>=await prompts.contact(action);void result;
  const storage=new NativeAccountStorage(scope);const kind:NativeStorageKind='secure';const read=await storage.read(kind,'local_draft');
  if(read.status==='completed'){const value:NativeStoredValue=read.value;void value.canRestore;}
  const sharing=new NativeSharing(scope);await sharing.message('server-prepared-message',action);
  const fileOptions:NativeFileInputOptions={label:'Файл',accept:['image/*'],capture:'environment',maxBytes:1024,onFiles:files=>{const first:File|undefined=files[0];void first;}};
  const picker=createNativeFileInput(document,fileOptions);picker.dispose();
  const callback:NonNullable<TelegramNativeArguments<'showPopup'>[1]>=buttonId=>{const selected:string|null=buttonId;if(selected!==null)selected.toUpperCase();};
  callback(null);callback('confirm');
  const signature:TelegramNativeSignatures['showPopup']=(_params,reply)=>{reply?.(null);};signature({message:'Nullable'},callback);
  const returned:TelegramNativeResult<'showPopup'>=api.call('showPopup',{message:'Cancel is null'},callback);void returned;
  // @ts-expect-error a string-only callback cannot handle native cancellation
  api.call('showPopup',{message:'Nullable'},(buttonId:string)=>buttonId.toUpperCase());
  // @ts-expect-error callback ID is string|null, never boolean
  callback(false);
  // @ts-expect-error permission intent must be explicitly user initiated
  prompts.contact({purpose:'No user action'});
  // @ts-expect-error storage kinds are finite
  storage.read('cookies','draft');
  const onEndpoint=(error:TelegramServerlessError|null,value?:unknown)=>{if(error){const status:number=error.status;void status;}void value;};
  raw.call('getProfile',onEndpoint);raw.call('getProfile',{lang:'ru'},onEndpoint);
  // @ts-expect-error input is a JSON object, not an array
  raw.call('getProfile',[],onEndpoint);
  const client=new ServerlessEndpointClient(app,{serverlessHosting:true});const callOptions:ServerlessCallOptions={operation:'read'};
  await client.call('getProfile',{},value=>({value}),callOptions);client.invalidateAccount();client.dispose();buttons.dispose();scope.dispose();
}
