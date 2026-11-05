import {createUiButton, createUiField, createUiTabs, createUiDialog, connectUiShell, uiUrl, createAppShell, TelegramBridge} from '../../dist/index.js';
declare const document: Document;
const button=createUiButton(document,{label:'Подтвердить',onPress:async()=>{},onError:report=>{const recovery:string=report.recovery;void recovery;}});
button.setPending(true);button.setDisabled(false);const pending:boolean=button.pending;
// @ts-expect-error no arbitrary HTML injection option
createUiButton(document,{label:'Safe',html:'<script>'});
// @ts-expect-error pending is read-only
button.pending=false;
// @ts-expect-error variants are finite
createUiButton(document,{label:'Safe',variant:'unreviewed'});
createUiField(document,{label:'Телефон',type:'tel',inputMode:'tel',validate:value=>value?null:'Заполните поле'});
// @ts-expect-error validation is local and synchronous
createUiField(document,{label:'Safe',validate:async()=>null});
const panel=document.createElement('section');const tabs=createUiTabs(document,'Разделы',[{id:'profile',label:'Профиль',content:panel}]);tabs.select('profile');
const dialog=createUiDialog(document,'Обзор','sheet');dialog.open(button.element);dialog.close();dialog.dispose();
const shell=createAppShell(document.body,'Приложение');const bridge=new TelegramBridge(undefined);
const stop=connectUiShell(shell,bridge,{resolveInsets:snapshot=>snapshot.contentInsets});stop();
const href:string=uiUrl('/profile','https://app.example');void href;void pending;
