/** Local fake-SDK composition. No real Telegram, Serverless endpoint, account, payment or permission. */
import {createAppShell,createUiButton,createUiField,createUiLink,NativeFlowScope,NativeActionButtons,NativePrompts,NativeAccountStorage,NativeSharing,createNativeFileInput,ServerlessEndpointClient} from '@awesome-telegram/patterns';
import {createFakeNativeApp} from './fake-sdk.mjs';

const shell=createAppShell(document.querySelector('#app'),'Native-возможности по ситуации');
const explanation=document.createElement('p');explanation.textContent='Это локальный fake SDK. Выбор платформы и версии проверяет наш adapter, а не реальный клиент, устройство, auth или платеж.';shell.content.append(explanation);
const config=document.createElement('div');config.className='tp-ui-grid';shell.content.append(config);
function select(label,values){const wrapper=document.createElement('div');wrapper.className='tp-field';const caption=document.createElement('label');caption.textContent=label;const input=document.createElement('select');input.id=`native-config-${config.children.length}`;caption.htmlFor=input.id;for(const value of values){const option=document.createElement('option');option.value=value;option.textContent=value;input.append(option);}wrapper.append(caption,input);config.append(wrapper);return input;}
const platform=select('Платформа fixture',['android','ios','tdesktop','web','unknown']);const version=select('Версия fixture',['9.6','8.0','7.2','6.4','6.0']);
const launch=select('Контекст запуска fixture',['direct','menu','keyboard','inline','attachment','unknown']);const mode=select('Ответ fake SDK',['completed','denied','cancelled','error','late']);
const result=document.createElement('p');result.id='result';result.setAttribute('role','status');result.textContent='Выберите нужное действие.';shell.summary.append(result);
const matrix=document.createElement('ul');matrix.setAttribute('aria-label','Capability matrix fixture');shell.summary.append(matrix);
const manualContact=createUiField(document,{label:'Контакт вручную',type:'tel',inputMode:'tel',hint:'Это ввод данных, не подтверждение личности.'});manualContact.root.hidden=true;shell.content.append(manualContact.root);
const manualCode=createUiField(document,{label:'Код вручную',hint:'Содержимое QR не открывается как ссылка автоматически.'});manualCode.root.hidden=true;shell.content.append(manualCode.root);
const manualAddress=createUiField(document,{label:'Адрес вручную',hint:'Доступ к объектам проверяет backend.'});manualAddress.root.hidden=true;shell.content.append(manualAddress.root);
const picker=createNativeFileInput(document,{label:'Выбрать изображение обычным file picker',accept:['image/*'],capture:'environment',maxBytes:1024*1024,
  onFiles:files=>{result.textContent=`Выбрано файлов: ${files.length}. Тип, размер и содержимое backend проверяет отдельно.`;},onError:report=>{result.textContent=report.message;}});shell.content.append(picker.element);
let active,account='bot100_account42',displayGeneration=0,nativePresses=0;
const controls=[];
const action={purpose:'Выбрать данные для текущего шага формы',userInitiated:true};
function renderMatrix(){matrix.replaceChildren(...active.scope.capabilities().map(row=>{const item=document.createElement('li');item.textContent=`${row.flow}: ${row.state}; gates ${row.versions.join('/')}; fallback: ${row.fallback}`;return item;}));}
function bindButtons(){active.buttons=new NativeActionButtons(active.scope,{main:async()=>{nativePresses++;await new Promise(resolve=>setTimeout(resolve,60));},secondary:()=>{nativePresses++;},back:()=>{nativePresses++;},onError:report=>{result.textContent=report.message;}});active.buttons.render({main:{text:'Продолжить',visible:true},secondary:{text:'Изменить выбор',visible:true},backVisible:true});}
function configure(){
  displayGeneration++;if(active){active.buttons.dispose();active.scope.dispose();active.serverless.dispose();active.fake.dispose();}
  const fake=createFakeNativeApp({platform:platform.value,version:version.value,automatic:true,mode:mode.value});
  // This policy is a deployment choice, not a claim that every named platform supports hardware.
  const scope=new NativeFlowScope(fake.app,{accountTag:account,launch:launch.value,timeoutMs:250,platformPolicy:(_flow,_platform,context)=>context!=='unknown'});
  active={fake,scope,prompts:new NativePrompts(scope),storage:new NativeAccountStorage(scope),sharing:new NativeSharing(scope),serverless:new ServerlessEndpointClient(fake.app,{serverlessHosting:true,timeoutMs:250})};
  bindButtons();renderMatrix();result.textContent='Новая конфигурация fake SDK. Реальные возможности не проверены.';
}
for(const input of [platform,version,launch,mode])input.addEventListener('change',configure);
async function run(label,invoke,fallback){const generation=displayGeneration,owner=active;const response=await invoke(owner);if(owner!==active||generation!==displayGeneration||response.status==='stale')return;
  result.textContent=`${label}: ${response.status}.`;
  if(response.status==='completed'&&response.value?.requiresServerReconciliation)result.textContent+=' Native invoice status получен; оплату подтверждает серверная сверка.';
  if(response.status==='completed'&&response.value?.persisted===false)result.textContent+=' Принятие download не доказывает запись файла на диск.';
  if('error'in response)result.textContent+=` ${response.error.message} Recovery: ${response.error.recovery}.`;
  if(['unsupported','denied','cancelled','unknown'].includes(response.status))fallback?.();renderMatrix();
  // Never serialize raw initData, biometricToken, storage values or endpoint message/parameters.
}
function button(label,call){const control=createUiButton(document,{label,onPress:call,onError:report=>{result.textContent=report.message;}});controls.push(control);shell.actions.append(control.element);return control;}
button('Fake MainButton',async()=>{active.fake.emit('mainButtonClicked');await new Promise(resolve=>setTimeout(resolve,80));result.textContent=`Native action callbacks: ${nativePresses}`;});
button('Fake SecondaryButton',async()=>{active.fake.emit('secondaryButtonClicked');await new Promise(resolve=>setTimeout(resolve,0));result.textContent=`Native action callbacks: ${nativePresses}`;});
button('Fake BackButton',async()=>{active.fake.emit('backButtonClicked');await new Promise(resolve=>setTimeout(resolve,0));result.textContent=`Native action callbacks: ${nativePresses}`;});
button('Показать popup',()=>run('Popup',owner=>owner.prompts.popup({message:'Продолжить текущий шаг?',buttons:[{id:'confirm',type:'ok'},{id:'cancel',type:'cancel'}]})));
button('Сканировать QR',()=>run('QR',owner=>owner.prompts.qr({text:'Код услуги'},action),()=>{manualCode.root.hidden=false;manualCode.focus();}));
button('Открыть invoice fixture',()=>run('Invoice',owner=>owner.prompts.invoice('https://t.me/$fixture-invoice',action)));
button('Поделиться контактом',()=>run('Contact',owner=>owner.prompts.contact(action),()=>{manualContact.root.hidden=false;manualContact.focus();}));
button('Подготовить геолокацию',()=>run('Location init',owner=>owner.prompts.prepareLocation()));
button('Запросить геолокацию',()=>run('Location',owner=>owner.prompts.location(action),()=>{manualAddress.root.hidden=false;manualAddress.focus();}));
button('Подготовить биометрию',()=>run('Biometric init',owner=>owner.storage.prepareBiometric()));
button('Разрешить локальную биометрию',()=>run('Biometric permission',owner=>owner.storage.requestBiometricAccess(action)));
button('Локальная биометрия',()=>run('Local unlock',owner=>owner.storage.unlockBiometric(action)));
button('Сохранить device draft',()=>run('Device write',owner=>owner.storage.write('device','draft','non-secret-selection')));
button('Прочитать device draft',()=>run('Device read',owner=>owner.storage.read('device','draft')));
button('Прочитать secure item',()=>run('Secure read',owner=>owner.storage.read('secure','local_state')));
button('Восстановить secure item',()=>run('Secure restore',owner=>owner.storage.restoreSecure('local_state',action)));
button('Поделиться prepared message',()=>run('Share',owner=>owner.sharing.message('server-prepared-fixture-id',action)));
button('Открыть story editor',()=>run('Story editor',owner=>Promise.resolve(owner.sharing.story('https://example.org/approved.jpg',undefined,action))));
button('Запросить download',()=>run('Download',owner=>owner.sharing.download({url:'https://example.org/approved.pdf',file_name:'approved.pdf'},action)));
shell.content.append(createUiLink(document,'Альтернатива: разрешённая ссылка на файл','https://example.org/approved.pdf'));
button('Fake Serverless read',()=>run('Serverless',owner=>owner.serverless.call('getProfile',{},value=>{if(!value||typeof value.label!=='string')throw Error('Invalid DTO');return {label:value.label};},{operation:'read'})));
button('Сменить account scope fixture',()=>{displayGeneration++;active.buttons.dispose();active.serverless.invalidateAccount();account=account.endsWith('42')?'bot100_account77':'bot100_account42';active.scope.setAccount(account);for(const field of [manualContact,manualCode,manualAddress]){field.input.value='';field.root.hidden=true;}picker.input.value='';bindButtons();renderMatrix();result.textContent='Account scope переключён; поздние callbacks старого аккаунта не применяются.';});
configure();
window.addEventListener('pagehide',event=>{if(event.persisted)return;controls.forEach(control=>control.dispose());active.buttons.dispose();active.scope.dispose();active.serverless.dispose();active.fake.dispose();manualContact.dispose();manualCode.dispose();manualAddress.dispose();picker.dispose();shell.dispose();});
Object.assign(window,{nativePreview:{get active(){return active;},run,configure,picker,get account(){return account;},get nativePresses(){return nativePresses;}}});
