import {createAppShell, TelegramBridge, createUiButton, createUiField, validateUiFields,
  uiUrl, createUiLink, createUiBadge, createUiCard, createUiList, createUiSkeleton,
  createUiFeedback, createUiTabs, createUiDialog, connectUiShell, bindUiFocusVisibility,
  type UiControl, type UiTone, type UiButtonOptions, type UiButton, type UiFieldOptions,
  type UiField, type UiListItem, type UiFeedbackOptions, type UiTab, type UiTabs,
  type UiDialog, type UiShellOptions, type TelegramWebApp} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Installed-package DOM contract. No network, authenticated identity, payment or device claim. */
export async function referenceUi(document: Document): Promise<void> {
  const host=document.createElement('div');document.body.append(host);
  const shell=createAppShell(host,'UI consumer fixture');
  const events=new Map<string,Set<()=>void>>();let scheme='light';
  const app:TelegramWebApp={platform:'tdesktop',get colorScheme(){return scheme;},
    get themeParams(){return scheme==='dark'?{bg_color:'#101d27',text_color:'#edf4ff'}:{bg_color:'#ffffff',text_color:'#172f45'};},
    contentSafeAreaInset:{top:0,right:0,bottom:12,left:0},ready(){},
    onEvent(name,listener){const set=events.get(name)??new Set();set.add(listener);events.set(name,set);},
    offEvent(name,listener){events.get(name)?.delete(listener);}};
  const bridge=new TelegramBridge(app,new EventTarget());
  const options:UiShellOptions={resolveInsets:snapshot=>snapshot.contentInsets};
  const disconnect=connectUiShell(shell,bridge,options),focusCleanup=bindUiFocusVisibility(shell.element);
  bridge.start();
  const fieldOptions:UiFieldOptions={label:'Ваше имя',value:'Сохранённый ввод',required:true,inputMode:'text'};
  const field:UiField=createUiField(document,fieldOptions);shell.content.append(field.root);
  field.input.focus();field.input.setSelectionRange(2,4);field.setError('Ошибка сервера');
  check(field.input.value==='Сохранённый ввод'&&field.input.selectionStart===2);
  check(validateUiFields([field])&&field.input.getAttribute('aria-invalid')==='false');
  scheme='dark';for(const listener of events.get('themeChanged')??[])listener();
  check(shell.element.dataset.theme==='dark'&&field.input.value==='Сохранённый ввод');
  let presses=0;const buttonOptions:UiButtonOptions={label:'Продолжить',variant:'primary',onPress:async()=>{presses++;}};
  const button:UiButton=createUiButton(document,buttonOptions);shell.actions.append(button.element);
  button.setPending(true);button.element.click();check(presses===0);button.setPending(false);
  button.setDisabled(true);check(button.element.disabled);button.setDisabled(false);button.element.click();
  await new Promise<void>(resolve=>setTimeout(resolve,0));check(Number(presses)===1);
  const tone:UiTone='success';const card=createUiCard(document,'Карточка','<script>literal</script>');
  card.append(createUiBadge(document,'Подтверждённый локальный результат',tone));
  const rows:readonly UiListItem[]=[{title:'Сведения',detail:'Без персонального payload',badge:'Обзор'}];
  card.append(createUiList(document,rows,'Список'),createUiSkeleton(document,2));
  const safe=uiUrl('https://example.org/help',document.baseURI);card.append(createUiLink(document,'Справка',safe));
  let rejected=false;try{uiUrl('javascript:alert(1)',document.baseURI);}catch{rejected=true;}check(rejected);
  const feedbackOptions:UiFeedbackOptions={kind:'success',title:'Готово',message:'Это UI fixture, не оплата.'};
  const feedback:UiControl=createUiFeedback(document,feedbackOptions);card.append(feedback.element);
  const other=document.createElement('section');other.textContent='Второй раздел';
  const panels:readonly UiTab[]=[{id:'first',label:'Первый',content:card},{id:'second',label:'Второй',content:other}];
  const tabs:UiTabs=createUiTabs(document,'Разделы',panels);shell.content.append(tabs.element);tabs.select('second');
  check(tabs.selected==='second'&&card.hidden&&!other.hidden);
  const dialog:UiDialog=createUiDialog(document,'Подтверждение','sheet');shell.element.append(dialog.element);
  dialog.content.append(document.createTextNode('Без сетевого запроса'));button.element.focus();dialog.open(button.element);
  check(dialog.element.open&&dialog.element.contains(document.activeElement));dialog.close();
  check(!dialog.element.open&&document.activeElement===button.element);
  dialog.dispose();tabs.dispose();feedback.dispose();field.dispose();button.dispose();focusCleanup();disconnect();bridge.dispose();shell.dispose();
  check(host.children.length===0&&[...events.values()].every(set=>set.size===0));host.remove();
}
