import {createAppShell} from '@awesome-telegram/patterns';
import type {Product} from './api-types.js';
import {createShopApi} from './shop-api.js';
import {telegramFromWindow} from './telegram-adapter.js';
import {shopLaunch,type ShopScreen} from './launch.js';
import {ShopDomainState,type ShopResult} from './domain-state.js';

type ShopMount={dispose():void};
let mounted:ShopMount|null=null;

/** One owned instance: remount first releases the previous app and all its handlers. */
export function mountShop():ShopMount {
  mounted?.dispose();
  const telegram=telegramFromWindow(window);
  const shell=createAppShell(document.getElementById('app')!,'Материалы для Telegram');
  const api=createShopApi(location.origin);
  const domain=new ShopDomainState(()=>localStorage,api.reader);
  let active=true,products:readonly Product[]=[],termsVersion='',authBusy=false,signedOut=false,lastLaunch='',authEpoch=0,booted=false,pendingLaunch:string|null=null;
  let resumeWork:Promise<void>|null=null,closing=false;
  const initial=history.state?.telegramShop,launch=shopLaunch(telegram.initData,location.search);
  let mode=initial?.screen==='orders'?'orders':initial?.screen==='catalog'?'catalog':launch.screen;
  const node=<K extends keyof HTMLElementTagNameMap>(tag:K,text='')=>{const value=document.createElement(tag);value.textContent=text;return value;};
  const button=(text:string,action:()=>void)=>{const value=node('button',text);value.type='button';value.addEventListener('click',action);return value;};
  const nav=node('nav');nav.className='shop-nav';nav.setAttribute('aria-label','Разделы магазина');
  const catalogButton=button('Каталог',()=>navigate('catalog')),purchasesButton=button('Мои покупки',()=>{navigate('orders');void purchases();});
  nav.append(catalogButton,purchasesButton);shell.content.append(nav);
  const intro=node('p','Две практичные памятки для ваших Telegram-проектов. Одноразовая покупка, доступ в этом магазине.');intro.className='shop-intro';shell.content.append(intro);
  const catalog=node('section'),orders=node('section');catalog.setAttribute('aria-label','Каталог материалов');orders.setAttribute('aria-label','Мои покупки');shell.content.append(catalog,orders);
  const title=node('h2','Корзина'),list=node('ul');list.className='shop-list';const total=node('p');total.className='shop-total';
  const consentBox=node('div');consentBox.className='shop-terms';const consent=node('input');consent.type='checkbox';consent.id='terms';
  const consentLabel=node('label','Я прочитал(а) условия покупки ниже и согласен(на) с ними.');consentLabel.htmlFor='terms';consentBox.append(consent,consentLabel);
  const status=node('p','Загружаем каталог…');status.className='shop-status';status.setAttribute('role','status');
  const controls=node('div');controls.className='shop-controls';
  const checkout=button('Создать заказ',()=>{void submit();}),pay=button('Оплатить Stars',()=>{void payInvoice();}),check=button('Проверить заказ',()=>{void reconcile();});
  const retry=button('Повторить сохранённый запрос',()=>{void retrySaved();});
  const again=button('Продолжить выбор',()=>{domain.newSelection();status.textContent='Выберите материалы.';render();navigate('catalog');});
  const refresh=button('Обновить вход',()=>{void refreshSession();}),logout=button('Выйти',()=>{void revokeSession();});
  const external=node('a','Открыть счёт в Telegram');external.target='_blank';external.rel='noopener noreferrer';external.hidden=true;
  controls.append(checkout,pay,check,retry,again,external,refresh,logout);
  const policy=node('details'),policyTitle=node('summary','Условия и поддержка'),policyText=node('p'),support=node('p');policy.append(policyTitle,policyText,support);
  shell.summary.append(title,list,total,consentBox,controls,status,policy);
  const media=matchMedia('(prefers-color-scheme:dark)');
  const release=telegram.subscribe(snapshot=>{const scheme=telegram.present?snapshot.colorScheme:(media.matches?'dark':'light');shell.applyTheme({...snapshot,colorScheme:scheme});shell.setInsets(snapshot.contentInsets??snapshot.systemInsets??{top:0,right:0,bottom:0,left:0});});
  const systemTheme=()=>{if(!telegram.present)shell.applyTheme({...telegram.snapshot(),colorScheme:media.matches?'dark':'light'});};media.addEventListener('change',systemTheme);
  let releaseBack:(()=>void)|undefined,releaseActivated:(()=>void)|undefined;
  const valid=<T>(result:ShopResult<T>)=>active&&result.status!=='stale'&&result.status!=='blocked'&&result.revision===domain.revision;
  function syncClosing(){const next=domain.snapshot().closingNeeded;if(next===closing)return;closing=next;
    telegram.closing(next);}
  function render(){if(!active)return;const state=domain.snapshot(),current=state.order,pending=state.pending?.status==='restored',busy=state.busy||authBusy;
    catalog.replaceChildren();const heading=node('h2','Каталог'),grid=node('div');grid.className='shop-products';catalog.append(heading,grid);
    for(const product of products){const card=node('article');card.className='shop-card';const kind=node('span',product.category);kind.className='shop-category';const price=node('p',`${product.stars} ★`);price.className='shop-price';
      const add=button(state.cart.includes(product.id)?`Убрать ${product.title}`:`Добавить ${product.title}`,()=>{domain.toggleCart(product.id);render();});add.setAttribute('aria-pressed',String(state.cart.includes(product.id)));add.disabled=busy||pending||current!==null;card.append(kind,node('h3',product.title),node('p',product.description),price,add);grid.append(card);}
    list.replaceChildren();for(const id of current?.items??state.cart)list.append(node('li',products.find(p=>p.id===id)?.title??id));if(!list.children.length)list.append(node('li','Пока пусто. Добавьте материал из каталога.'));
    const sum=current?.total??products.filter(p=>state.cart.includes(p.id)).reduce((s,p)=>s+p.stars,0);total.replaceChildren(node('span',current?'Заказ':'Итого'),node('span',`${sum} ★`));
    consent.checked=state.consent;consent.disabled=busy||pending||current!==null;
    checkout.hidden=pending||current!==null;checkout.disabled=state.blocked||busy||!state.cart.length||!state.scope||!state.consent;
    pay.hidden=!current||current.status!=='awaiting'||['unknown','creating'].includes(current.invoice_state);pay.disabled=busy;
    check.hidden=!pending&&!current;check.disabled=busy;retry.hidden=!state.retryAvailable;retry.disabled=busy;again.hidden=current?.status!=='paid';again.disabled=busy;
    refresh.disabled=busy||!telegram.initData;logout.hidden=!state.scope;logout.disabled=busy;syncClosing();
  }
  const consentChanged=()=>{domain.setConsent(consent.checked);render();};consent.addEventListener('change',consentChanged);
  function show(){catalog.hidden=mode!=='catalog';orders.hidden=mode!=='orders';catalogButton.setAttribute('aria-pressed',String(mode==='catalog'));purchasesButton.setAttribute('aria-pressed',String(mode==='orders'));
    telegram.back(mode==='orders');}
  function navigate(next:ShopScreen){if(next===mode){show();return;}
    if(next==='catalog'&&history.state?.telegramShop?.screen==='orders'&&history.state.telegramShop.depth===1){history.back();return;}
    mode=next;history.pushState({...history.state,telegramShop:{screen:mode,depth:mode==='orders'?1:0}},'');show();}
  const popped=()=>{mode=history.state?.telegramShop?.screen==='orders'?'orders':'catalog';show();if(mode==='orders')void purchases();};
  if(!initial)history.replaceState({...history.state,telegramShop:{screen:mode,depth:0}},'');
  function connectBack(){releaseBack??=telegram.onBack(()=>navigate('catalog'));}
  async function purchases(){if(!active)return;if(!domain.snapshot().scope){orders.replaceChildren(node('h2','Мои покупки'),node('p','Откройте магазин из Telegram, чтобы войти.'));return;}
    orders.replaceChildren(node('h2','Мои покупки'),node('p','Проверяем покупки…'));const result=await domain.loadOrders();if(!valid(result))return;
    if(result.status!=='ready'){orders.replaceChildren(node('h2','Мои покупки'),node('p','Покупки не удалось загрузить.'),button('Обновить покупки',()=>{void purchases();}));return;}
    orders.replaceChildren(node('h2','Мои покупки'));if(!result.value.length)orders.append(node('p','Покупок пока нет. Выберите материал в каталоге.'));
    const revision=domain.revision;
    for(const o of result.value){const card=node('article');card.className='shop-card';card.append(node('h3',`Заказ ${o.id.slice(0,8)}`),node('p',`${o.total} ★ · ${o.status==='paid'?'Оплата подтверждена сервером':o.status==='review'?'Требует сверки с поддержкой':'Ожидает оплаты'}`));
      if(o.status==='paid')for(const sku of o.items)card.append(button(`Открыть ${products.find(p=>p.id===sku)?.title??sku}`,()=>{if(revision===domain.revision)void readContent(sku,card);}));
      else card.append(button('Показать заказ',()=>{if(revision===domain.revision&&domain.selectOrder(o.id)){status.textContent='Проверьте статус и оплату заказа.';render();}}));orders.append(card);}
  }
  async function readContent(sku:string,parent:HTMLElement){const result=await domain.readContent(sku);if(!valid(result)||!parent.isConnected)return;
    if(result.status==='ready'){parent.querySelector('pre')?.remove();const pre=node('pre',result.value.text);pre.className='shop-content';parent.append(pre);}else status.textContent='Доступ не подтверждён. Обновите покупки или обратитесь в поддержку.';}
  function received<T>(result:ShopResult<T>){if(!valid(result))return;const order=domain.snapshot().order;if(!order)return;
    if(order.status==='paid'){status.textContent='Оплата подтверждена сервером. Материалы доступны в «Мои покупки».';void purchases();}
    else status.textContent=['unknown','creating'].includes(order.invoice_state)?'Подготовка оплаты не подтверждена. Новую ссылку не создаём; обратитесь в поддержку.':'Заказ создан. Оплатите Stars или проверьте статус позднее.';render();}
  async function submit(){if(authBusy||!active)return;const work=domain.submit(termsVersion,crypto.randomUUID());render();status.textContent='Создаём заказ…';const result=await work;if(!active)return;
    if(result.status==='blocked')status.textContent='Не удалось сохранить номер операции. Заказ не отправлен; проверьте сохранённую операцию и локальное хранение.';
    else if(valid(result)){if(result.status==='ready')received(result);else status.textContent='Результат неизвестен. Проверьте тот же заказ; номер операции сохранён.';}render();}
  async function reconcile(){if(!active||authBusy||!domain.snapshot().scope)return;const work=domain.reconcile();render();const result=await work;if(!active)return;
    if(valid(result)){if(result.status==='ready')received(result);else if(domain.snapshot().retryAvailable)status.textContent='Сервер не нашёл сохранённый запрос. Заказ не создан автоматически; повторите прежний запрос явно, если хотите продолжить.';else status.textContent='Статус недоступен. Откройте магазин заново или проверьте позднее; заказ не пересоздаётся.';}render();}
  async function retrySaved(){if(!active||authBusy)return;const work=domain.retrySavedIntent();render();const result=await work;
    if(result.status!=='blocked'&&!valid(result))return;if(result.status==='ready')received(result);else status.textContent=result.status==='blocked'?'Сохранённый запрос нельзя повторить: проверьте актуальные условия и обратитесь в поддержку.':'Результат неизвестен. Проверьте тот же заказ; номер операции сохранён.';render();}
  async function payInvoice(){if(authBusy||!active)return;external.hidden=true;const work=domain.invoice();render();const result=await work;if(!valid(result))return;
    if(result.status==='ready'){const revision=domain.revision,url=result.value.url;
      if(telegram.invoice(url,()=>{if(active&&revision===domain.revision)queueMicrotask(()=>{if(active&&revision===domain.revision)void reconcile();});})){status.textContent='Платёжное окно открыто. После закрытия проверим статус на сервере.';}
      else{external.href=url;external.hidden=false;status.textContent='Откройте счёт в Telegram, затем нажмите «Проверить заказ».';}
    }else status.textContent='Результат подготовки оплаты неизвестен. Проверьте заказ; повторную ссылку автоматически не создаём.';render();}
  function clearPrivateView(){orders.replaceChildren();external.hidden=true;external.removeAttribute('href');render();}
  async function signIn(raw:string){const epoch=++authEpoch;pendingLaunch=raw;authBusy=true;render();
    try{const session=await api.session(raw);if(!active||epoch!==authEpoch)return;domain.setSession(session);lastLaunch=raw;signedOut=false;clearPrivateView();
      status.textContent=domain.snapshot().blocked?'Сохранённый заказ требует проверки. Используйте «Мои покупки»; новая операция заблокирована.':'Выберите материалы. Итоговую цену подтвердит сервер.';
    }catch{if(active&&epoch===authEpoch)status.textContent='Не удалось загрузить магазин или войти. Откройте Mini App заново; сохранённый заказ не удалён.';}
    finally{if(active&&epoch===authEpoch){pendingLaunch=null;authBusy=false;render();}}
    if(active&&epoch===authEpoch){if(domain.snapshot().pending?.status==='restored')await reconcile();if(mode==='orders')await purchases();}
  }
  async function refreshSession(){if(authBusy||!active||!telegram.initData)return;
    if(telegram.initData!==lastLaunch){domain.clearSession();clearPrivateView();await signIn(telegram.initData);return;}
    if(!domain.snapshot().scope){await signIn(telegram.initData);return;}
    const epoch=++authEpoch;authBusy=true;render();const result=await domain.rotate();if(!active||epoch!==authEpoch)return;authBusy=false;
    if(valid(result)&&result.status==='ready'){status.textContent='Вход обновлён. Номер сохранённого заказа не изменён.';clearPrivateView();if(mode==='orders')await purchases();render();}
    else if(result.status==='failed')await signIn(telegram.initData);else render();
  }
  async function revokeSession(){if(authBusy||!active||!domain.snapshot().scope)return;const epoch=++authEpoch;authBusy=true;signedOut=true;const work=domain.revoke();clearPrivateView();status.textContent='Выходим из магазина…';const result=await work;if(!active||epoch!==authEpoch)return;authBusy=false;clearPrivateView();
    status.textContent=result.status==='ready'?'Вы вышли из магазина. Сохранённый заказ останется для следующего входа.':'Вход закрыт в этом окне. Серверный отзыв не подтверждён; сессия ограничена сроком действия.';render();}
  const hide=()=>{releaseBack?.();releaseBack=undefined;domain.cancelReads();telegram.back(false);};
  function resume(){if(!active||!booted)return;connectBack();show();if(!telegram.initData)return;
    if(telegram.initData!==(pendingLaunch??lastLaunch)){domain.clearSession();clearPrivateView();void signIn(telegram.initData);return;}
    if(authBusy||signedOut||resumeWork)return;resumeWork=(async()=>{if(domain.snapshot().scope){await refreshSession();if(active&&domain.snapshot().scope&&!authBusy){if(domain.snapshot().pending?.status==='restored'||domain.snapshot().order)await reconcile();if(mode==='orders')await purchases();}}})().finally(()=>{resumeWork=null;});}
  const visibility=()=>{if(document.visibilityState==='visible')resume();};
  const beforeUnload=(event:BeforeUnloadEvent)=>{if(domain.snapshot().closingNeeded){event.preventDefault();event.returnValue='';}};
  window.addEventListener('pagehide',hide);window.addEventListener('pageshow',resume);window.addEventListener('popstate',popped);window.addEventListener('beforeunload',beforeUnload);document.addEventListener('visibilitychange',visibility);
  releaseActivated=telegram.onResume(resume);
  const instance:ShopMount={dispose(){if(!active)return;active=false;authEpoch++;hide();releaseActivated?.();release();telegram.dispose();domain.dispose();
    media.removeEventListener('change',systemTheme);consent.removeEventListener('change',consentChanged);window.removeEventListener('pagehide',hide);window.removeEventListener('pageshow',resume);window.removeEventListener('popstate',popped);window.removeEventListener('beforeunload',beforeUnload);document.removeEventListener('visibilitychange',visibility);shell.dispose();if(mounted===instance)mounted=null;}};
  mounted=instance;connectBack();show();telegram.start();render();
  void(async()=>{try{products=(await api.catalog()).items;const p=await api.policy();if(!active)return;domain.configureCatalog(products.map(p=>p.id),p.version);termsVersion=p.version;policyText.textContent=p.terms;support.textContent=p.support;render();
    booted=true;if(telegram.initData)await signIn(telegram.initData);else{status.textContent='Каталог доступен. Для покупки откройте Mini App из Telegram.';if(mode==='orders')await purchases();}
  }catch{if(active)status.textContent='Не удалось загрузить магазин или войти. Откройте Mini App заново; сохранённый заказ не удалён.';}})();
  return instance;
}
export function dispose(){mounted?.dispose();}
mountShop();
