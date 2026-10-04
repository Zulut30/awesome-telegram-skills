import {ApiClient, ApiError, TelegramBridge, SelectionDraftStore, createAppShell, createTextField} from '@awesome-telegram/patterns';
import type {TelegramWebApp} from '@awesome-telegram/patterns';

declare global {interface Window {Telegram?: {WebApp?: TelegramWebApp}}}
const host = document.querySelector<HTMLElement>('#app');
if (!host) throw new Error('Application host missing');
const shell = createAppShell(host, 'Запись на консультацию');
const bridge = new TelegramBridge(window.Telegram?.WebApp);
let theme = bridge.snapshot().colorScheme;
const release = bridge.subscribe(snapshot => {theme = snapshot.colorScheme; shell.applyTheme(snapshot);});
bridge.start();
// Local browser demo has no Telegram identity. Production derives scope from its server session.
const drafts = new SelectionDraftStore(() => localStorage, {namespace:'booking-demo', scope:'local-demo', ttlMs:86400000});
const restored = drafts.read();
let serviceId = 'consultation';
let slotId: string | null = restored.status === 'restored' && ['10:00','14:30'].includes(restored.value.slotId ?? '') ? restored.value.slotId : null;
const intro = document.createElement('p'); intro.className='demo-badge'; intro.textContent='Локальный пример · оплата и запись в реальный календарь отключены';
const draftNotice=document.createElement('p');draftNotice.className='demo-badge';draftNotice.setAttribute('role','status');
if(restored.status==='unavailable') draftNotice.textContent='Сохранение выбора недоступно в этом браузере.';
if(restored.status==='restored' && slotId) draftNotice.textContent='Время восстановлено из черновика. Проверьте выбор.';
function saveChoice(){if(!drafts.write({serviceId,slotId})) draftNotice.textContent='Выбор не удалось сохранить. Не закрывайте страницу до завершения.';}
shell.content.append(intro,draftNotice);
const form = document.createElement('form'); form.noValidate=true;
const subtitle=document.createElement('h2'); subtitle.textContent='Выберите время';
const choices=document.createElement('div'); choices.className='demo-choices';
const slotButtons: HTMLButtonElement[]=[];
const updateChoices=()=>{for(const button of slotButtons) button.setAttribute('aria-pressed',String(button.dataset.slot===slotId)); summary.textContent=slotId ? `Консультация · ${slotId} · 30 минут` : 'Выберите удобное время для консультации.';};
for(const slot of ['10:00','14:30']) {
  const button=document.createElement('button'); button.type='button'; button.textContent=slot; button.dataset.slot=slot;
  button.addEventListener('click',()=>{slotId=slot; updateChoices(); saveChoice();}); slotButtons.push(button); choices.append(button);
}
const name=createTextField(document,'Ваше имя','Имя и контакт не сохраняются в локальном черновике.'); name.input.autocomplete='given-name'; name.input.name='name';
const phone=createTextField(document,'Телефон','Например: +7 900 123-45-67'); phone.input.type='tel'; phone.input.autocomplete='tel'; phone.input.name='phone';
name.input.maxLength=120;phone.input.maxLength=32;
name.input.addEventListener('input',()=>name.setError(null));phone.input.addEventListener('input',()=>phone.setError(null));
const submit=document.createElement('button'); submit.type='submit'; submit.textContent='Подтвердить запись'; submit.dataset.test='submit';
const checkbox=document.createElement('input'); checkbox.type='checkbox'; checkbox.dataset.test='drop';
const option=document.createElement('label'); option.className='demo-options'; option.append(checkbox,document.createTextNode('Симулировать потерянный ответ сервера'));
const status=document.createElement('p'); status.className='demo-state'; status.setAttribute('role','status');
const check=document.createElement('button'); check.type='button'; check.textContent='Проверить результат'; check.hidden=true; check.dataset.test='recover';
const summaryTitle=document.createElement('h2'); summaryTitle.textContent='Ваша запись';
const summary=document.createElement('p'); shell.summary.append(summaryTitle,summary); updateChoices();
form.append(subtitle,choices,name.root,phone.root,option,submit,status,check); shell.content.append(form);
const themeButton=document.createElement('button'); themeButton.type='button'; themeButton.textContent='Сменить тему'; themeButton.dataset.test='theme';
themeButton.addEventListener('click',()=>{theme=theme==='light'?'dark':'light';shell.applyTheme({...bridge.snapshot(),colorScheme:theme,theme:{}});}); shell.actions.append(themeButton);

interface Booking {id: number; slot: string}
function decodeBooking(value: unknown): Booking {
  if(!value || typeof value!=='object' || !('id' in value) || !Number.isInteger(value.id) || !('slot' in value) || typeof value.slot!=='string') throw new Error('Invalid booking');
  return {id: value.id as number,slot: value.slot};
}
const api=new ApiClient({baseUrl:location.origin});
let pending: string | null=null; let busy=false; let finished=false;
function success(booking: Booking) {finished=true;check.hidden=true;status.textContent=`Запись №${booking.id} подтверждена на ${booking.slot}.`;drafts.clear();}
form.addEventListener('submit', async event=>{
  event.preventDefault(); if(busy || pending || finished) return;
  name.setError(name.input.value.trim() ? null : 'Укажите имя.');
  const phoneText=phone.input.value.trim(),digits=phoneText.replace(/\D/g,'');
  phone.setError(/^\+?[\d ()-]{7,32}$/.test(phoneText) && digits.length>=7 && digits.length<=15 ? null : 'Проверьте номер телефона.');
  if(!slotId){status.textContent='Выберите время.'; slotButtons[0]?.focus(); return;}
  if(name.input.getAttribute('aria-invalid')==='true'){name.input.focus();return;}
  if(phone.input.getAttribute('aria-invalid')==='true'){phone.input.focus();return;}
  pending=crypto.randomUUID(); busy=true; submit.disabled=true; for(const button of slotButtons) button.disabled=true;
  status.textContent='Подтверждаем запись…';
  try {success(await api.request(`/api/bookings${checkbox.checked?'?drop=1':''}`,decodeBooking,{method:'POST',body:{operation:pending,serviceId,slotId},timeoutMs:3000}));}
  catch(error){status.textContent=error instanceof ApiError && error.outcome==='unknown' ? 'Ответ не получен. Проверьте результат, прежде чем повторять запись.' : 'Не удалось получить результат.';check.hidden=false;}
  finally{busy=false;}
});
check.addEventListener('click',async()=>{
  if(!pending || busy)return; busy=true;check.disabled=true;
  try{success(await api.request(`/api/bookings/${encodeURIComponent(pending)}`,decodeBooking));}
  catch{status.textContent='Результат пока не доступен. Попробуйте проверить позже.';}
  finally{busy=false;check.disabled=false;}
});
window.addEventListener('pagehide',()=>{if(!pending) saveChoice();});
// SPA host should call these at final unmount, not on a BFCache pagehide:
export function dispose(){release();bridge.dispose();shell.dispose();}
