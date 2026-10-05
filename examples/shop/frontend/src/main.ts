import {ApiClient,ApiError,createAppShell,TelegramBridge,TelegramNativeAPI,type TelegramWebApp} from '@awesome-telegram/patterns';
type Product={id:string;title:string;description:string;stars:number;category:string};
type Order={id:string;operation:string;items:string[];total:number;currency:'XTR';status:'awaiting'|'paid'|'review';invoice_state:'none'|'creating'|'ready'|'unknown'};
type Pending={operation:string;items:string[];terms:string};
type Host=TelegramWebApp & {initData?:string};
const host=(window as Window & {Telegram?:{WebApp?:Host}}).Telegram?.WebApp;
const bridge=new TelegramBridge(host),native=new TelegramNativeAPI(host);
const shell=createAppShell(document.getElementById('app')!,'Материалы для Telegram');
const node=<K extends keyof HTMLElementTagNameMap>(tag:K,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
const button=(text:string,action:()=>void)=>{const b=node('button',text);b.type='button';b.addEventListener('click',action);return b;};
const record=(v:unknown):Record<string,unknown>=>{if(!v||typeof v!=='object'||Array.isArray(v))throw Error('Invalid response');return v as Record<string,unknown>;};
const string=(v:unknown)=>{if(typeof v!=='string')throw Error('Invalid response');return v;};
const strings=(v:unknown)=>{if(!Array.isArray(v)||v.some(s=>typeof s!=='string'))throw Error('Invalid response');return v as string[];};
const integer=(v:unknown)=>{if(typeof v!=='number'||!Number.isSafeInteger(v)||v<=0)throw Error('Invalid response');return v;};
function order(v:unknown):Order{const o=record(v);if(o.currency!=='XTR'||!['awaiting','paid','review'].includes(string(o.status))||!['none','creating','ready','unknown'].includes(string(o.invoice_state)))throw Error('Invalid order');return {id:string(o.id),operation:string(o.operation),items:strings(o.items),total:integer(o.total),currency:'XTR',status:o.status as Order['status'],invoice_state:o.invoice_state as Order['invoice_state']};}
let csrf='',scope='',products:Product[]=[],termsVersion='',pending:Pending|null=null,current:Order|null=null,busy=false,blocked=false,mode='catalog';
const cart=new Set<string>();
const api=new ApiClient({baseUrl:location.origin,headers:()=>({'X-Shop-CSRF':csrf})});
const nav=node('nav');nav.className='shop-nav';nav.setAttribute('aria-label','Разделы магазина');
const catalogButton=button('Каталог',()=>show('catalog')),purchasesButton=button('Мои покупки',()=>{show('orders');void purchases();});
nav.append(catalogButton,purchasesButton);shell.content.append(nav);
const intro=node('p','Две практичные памятки для ваших Telegram-проектов. Одноразовая покупка, доступ в этом магазине.');intro.className='shop-intro';shell.content.append(intro);
const catalog=node('section'),orders=node('section');catalog.setAttribute('aria-label','Каталог материалов');orders.setAttribute('aria-label','Мои покупки');shell.content.append(catalog,orders);
const title=node('h2','Корзина'),list=node('ul');list.className='shop-list';
const total=node('p');total.className='shop-total';
const consentBox=node('div');consentBox.className='shop-terms';const consent=node('input');consent.type='checkbox';consent.id='terms';const consentLabel=node('label','Я прочитал(а) условия покупки ниже и согласен(на) с ними.');consentLabel.htmlFor='terms';consentBox.append(consent,consentLabel);
const status=node('p','Загружаем каталог…');status.className='shop-status';status.setAttribute('role','status');
const controls=node('div');controls.className='shop-controls';
const checkout=button('Создать заказ',()=>{void submit();}),pay=button('Оплатить Stars',()=>{void payInvoice();}),check=button('Проверить заказ',()=>{void reconcile();}),again=button('Продолжить выбор',()=>{current=null;cart.clear();consent.checked=false;status.textContent='Выберите материалы.';render();show('catalog');});
const external=node('a','Открыть счёт в Telegram');external.target='_blank';external.rel='noopener noreferrer';external.hidden=true;
controls.append(checkout,pay,check,again,external);
const policy=node('details'),policyTitle=node('summary','Условия и поддержка'),policyText=node('p'),support=node('p');policy.append(policyTitle,policyText,support);
shell.summary.append(title,list,total,consentBox,controls,status,policy);
const release=bridge.subscribe(snapshot=>{const scheme=host?snapshot.colorScheme:(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');shell.applyTheme({...snapshot,colorScheme:scheme});shell.setInsets(snapshot.contentInsets??snapshot.systemInsets??{top:0,right:0,bottom:0,left:0});});
const media=matchMedia('(prefers-color-scheme:dark)');const systemTheme=()=>{if(!host)shell.applyTheme({...bridge.snapshot(),colorScheme:media.matches?'dark':'light'});};media.addEventListener('change',systemTheme);
let releaseBack:(()=>void)|undefined;
function connectBack(){if(!releaseBack&&native.supports('BackButton.show'))releaseBack=native.listen('backButtonClicked',()=>show('catalog'));}
function show(next:string){mode=next;catalog.hidden=mode!=='catalog';orders.hidden=mode!=='orders';catalogButton.setAttribute('aria-pressed',String(mode==='catalog'));purchasesButton.setAttribute('aria-pressed',String(mode==='orders'));if(native.supports('BackButton.show'))native.call(mode==='orders'?'BackButton.show':'BackButton.hide');}
function key(){return `telegram-shop:pending:${scope}:v1`;}
function save():boolean{try{if(pending)localStorage.setItem(key(),JSON.stringify(pending));else localStorage.removeItem(key());return true;}catch{return false;}}
function render(){
  catalog.replaceChildren();const heading=node('h2','Каталог'),grid=node('div');grid.className='shop-products';catalog.append(heading,grid);
  for(const product of products){const card=node('article');card.className='shop-card';const kind=node('span',product.category);kind.className='shop-category';const price=node('p',`${product.stars} ★`);price.className='shop-price';const add=button(cart.has(product.id)?`Убрать ${product.title}`:`Добавить ${product.title}`,()=>{if(cart.has(product.id))cart.delete(product.id);else cart.add(product.id);render();});add.setAttribute('aria-pressed',String(cart.has(product.id)));add.disabled=busy||pending!==null||current!==null;card.append(kind,node('h3',product.title),node('p',product.description),price,add);grid.append(card);}
  list.replaceChildren();for(const id of current?.items??[...cart])list.append(node('li',products.find(p=>p.id===id)?.title??id));
  if(!list.children.length)list.append(node('li','Пока пусто. Добавьте материал из каталога.'));
  const sum=current?.total??products.filter(p=>cart.has(p.id)).reduce((s,p)=>s+p.stars,0);total.replaceChildren(node('span',current?'Заказ':'Итого'),node('span',`${sum} ★`));
  checkout.hidden=pending!==null||current!==null;checkout.disabled=blocked||busy||cart.size===0||!csrf||!consent.checked;
  consent.disabled=busy||pending!==null||current!==null;
  pay.hidden=!current||current.status!=='awaiting'||current.invoice_state==='unknown'||current.invoice_state==='creating';pay.disabled=busy;
  check.hidden=!pending&&!current;check.disabled=busy;again.hidden=current?.status!=='paid';again.disabled=busy;
}
consent.addEventListener('change',()=>{checkout.disabled=blocked||busy||!csrf||cart.size===0||!consent.checked;});
async function purchases(){if(!csrf){orders.replaceChildren(node('h2','Мои покупки'),node('p','Откройте магазин из Telegram, чтобы войти.'));return;}
  orders.replaceChildren(node('h2','Мои покупки'),node('p','Проверяем покупки…'));
  try{const values=await api.request('/api/orders',v=>{const a=record(v).orders;if(!Array.isArray(a))throw Error();return a.map(order);});orders.replaceChildren(node('h2','Мои покупки'));if(!values.length)orders.append(node('p','Покупок пока нет. Выберите материал в каталоге.'));
    for(const o of values){const card=node('article');card.className='shop-card';card.append(node('h3',`Заказ ${o.id.slice(0,8)}`),node('p',`${o.total} ★ · ${o.status==='paid'?'Оплата подтверждена сервером':o.status==='review'?'Требует сверки с поддержкой':'Ожидает оплаты'}`));
      if(o.status==='paid')for(const sku of o.items)card.append(button(`Открыть ${products.find(p=>p.id===sku)?.title??sku}`,()=>{void readContent(sku,card);}));
      else card.append(button('Показать заказ',()=>{current=o;status.textContent='Проверьте статус и оплату заказа.';render();}));orders.append(card);}
  }catch{orders.replaceChildren(node('h2','Мои покупки'),node('p','Покупки не удалось загрузить.'),button('Обновить покупки',()=>{void purchases();}));}}
async function readContent(sku:string,parent:HTMLElement){try{const content=await api.request(`/api/content/${encodeURIComponent(sku)}`,v=>string(record(v).text));parent.querySelector('pre')?.remove();const pre=node('pre',content);pre.className='shop-content';parent.append(pre);}catch{status.textContent='Доступ не подтверждён. Обновите покупки или обратитесь в поддержку.';}}
function received(o:Order){current=o;if(o.status==='paid'){pending=null;save();status.textContent='Оплата подтверждена сервером. Материалы доступны в «Мои покупки».';void purchases();}else status.textContent=(o.invoice_state==='unknown'||o.invoice_state==='creating')?'Подготовка оплаты не подтверждена. Новую ссылку не создаём; обратитесь в поддержку.':'Заказ создан. Оплатите Stars или проверьте статус позднее.';render();}
async function submit(){if(blocked||busy||!csrf||!consent.checked||cart.size===0||current)return;
  if(!pending){pending={operation:crypto.randomUUID(),items:[...cart].sort(),terms:termsVersion};if(!save()){pending=null;status.textContent='Не удалось сохранить номер операции. Заказ не отправлен; разрешите локальное хранение.';return;}}
  busy=true;render();status.textContent='Создаём заказ…';
  try{received(await api.request('/api/orders',order,{method:'POST',body:pending}));}catch{status.textContent='Результат неизвестен. Проверьте тот же заказ; номер операции сохранён.';}finally{busy=false;render();}}
async function reconcile(){if(busy||!csrf||(!pending&&!current))return;busy=true;render();
  try{received(await api.request(current?`/api/orders/${current.id}`:`/api/operations/${pending!.operation}`,order));}
  catch(error){if(!current&&pending&&error instanceof ApiError&&error.status===404){status.textContent='Заказ с этим номером пока не найден. Повторяем запрос с тем же номером.';try{received(await api.request('/api/orders',order,{method:'POST',body:pending}));}catch{status.textContent='Результат ещё неизвестен. Сохранён прежний номер заказа.';}}else status.textContent='Статус недоступен. Откройте магазин заново или проверьте позднее; заказ не пересоздаётся.';}
  finally{busy=false;render();}}
async function payInvoice(){if(busy||!current||current.status==='paid')return;busy=true;external.hidden=true;render();
  try{const id=current.id;const url=await api.request(`/api/orders/${id}/invoice`,v=>string(record(v).url),{method:'POST',body:{}});
    if(native.supports('openInvoice')){native.call('openInvoice',url,()=>{status.textContent='Проверяем оплату на сервере…';setTimeout(()=>{void reconcile();},0);});status.textContent='Платёжное окно открыто. После закрытия проверим статус на сервере.';}
    else{external.href=url;external.hidden=false;status.textContent='Откройте счёт в Telegram, затем нажмите «Проверить заказ».';}
  }catch{status.textContent='Результат подготовки оплаты неизвестен. Проверьте заказ; повторную ссылку автоматически не создаём.';}
  finally{busy=false;render();}}
async function boot(){
  try{products=await api.request('/api/catalog',v=>{const items=record(v).items;if(!Array.isArray(items))throw Error();return items.map(item=>{const p=record(item);return {id:string(p.id),title:string(p.title),description:string(p.description),category:string(p.category),stars:integer(p.stars)};});});
    const p=await api.request('/api/policy',record);termsVersion=string(p.version);policyText.textContent=string(p.terms);support.textContent=string(p.support);render();
    if(!host?.initData){status.textContent='Каталог доступен. Для покупки откройте Mini App из Telegram.';return;}
    const session=await api.request('/api/session',record,{method:'POST',body:{initData:host.initData}});csrf=string(session.csrf);scope=string(session.scope);
    try{const raw=localStorage.getItem(key());if(raw){const saved=record(JSON.parse(raw));const op=string(saved.operation),items=strings(saved.items),terms=string(saved.terms);if(!/^[a-f0-9-]{36}$/.test(op)||!items.length||items.some(s=>!products.some(p=>p.id===s)))throw Error();pending={operation:op,items,terms};for(const id of items)cart.add(id);consent.checked=true;}}
    catch{blocked=true;status.textContent='Сохранённый заказ требует проверки. Используйте «Мои покупки»; новая операция заблокирована.';render();return;}
    status.textContent='Выберите материалы. Итоговую цену подтвердит сервер.';render();if(pending)await reconcile();
  }catch{status.textContent='Не удалось загрузить магазин или войти. Откройте Mini App заново; сохранённый заказ не удалён.';render();}}
function hide(){releaseBack?.();releaseBack=undefined;}
function resume(){connectBack();show(mode);if(csrf&&(pending||current))void reconcile();}
window.addEventListener('pagehide',hide);window.addEventListener('pageshow',resume);
connectBack();show('catalog');bridge.start();render();void boot();
export function dispose(){hide();release();bridge.dispose();native.dispose();media.removeEventListener('change',systemTheme);window.removeEventListener('pagehide',hide);window.removeEventListener('pageshow',resume);shell.dispose();}
