/** Real installed frontend + loopback backend. Only private fixture stdin creates receipts. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {mkdir,writeFile} from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import {chromium} from 'playwright';

const [python,frontend,folder,caller]=process.argv.slice(2);
const output=path.resolve(folder);await mkdir(output,{recursive:false});
const reserve=net.createServer();await new Promise(resolve=>reserve.listen(0,'127.0.0.1',resolve));const port=reserve.address().port;await new Promise(resolve=>reserve.close(resolve));
const base=`http://127.0.0.1:${port}`;
const processes=[];let browser,checks=0;const cases=[];
function verify(condition,message){assert.ok(condition,message);checks++;}
// Bearer session tokens seen in /api/session responses, per page: the app keeps its token only in memory.
const tokens=new WeakMap();const owner=target=>typeof target.page==='function'?target.page():target;const bearer=target=>({Authorization:'Bearer '+tokens.get(owner(target))});
// The observer records only fully read session replies; deliberate lost replies or context cleanup may interrupt a body.
// Application auth/recovery and old-token refusal are asserted independently below.
function trackSession(page){const sequence=new WeakMap();let latest=0;page.on('request',request=>{if(['/api/session','/api/session/rotate'].includes(new URL(request.url()).pathname)&&request.method()==='POST')sequence.set(request,++latest);});page.on('response',async response=>{if(['/api/session','/api/session/rotate'].includes(new URL(response.url()).pathname)&&response.ok()){let session;try{session=await response.json();}catch{return;}if(sequence.get(response.request())===latest)tokens.set(page,session.token);}});page.on('dialog',dialog=>dialog.accept());}
function start(name){
  const child=spawn(python,['-I','-B','-m','telegram_shop_example.offline','--database',path.join(output,`${name}.sqlite`),'--frontend',frontend,'--port',String(port)],{cwd:caller,env:{...process.env,PYTHONPATH:caller,BOT_TOKEN:'100:PRIVATE_CANARY'},stdio:['pipe','pipe','pipe'],windowsHide:true});
  const queue=[],waiters=[];let chunk='',stderr='',exitCode=null,closed=false;
  const exit=new Promise(resolve=>child.on('close',code=>{exitCode=code;closed=true;for(const w of waiters.splice(0))w.reject(Error('Owned backend exited before expected record'));resolve(code);}));
  child.stderr.setEncoding('utf8');child.stderr.on('data',text=>stderr+=text);
  child.stdout.setEncoding('utf8');child.stdout.on('data',text=>{chunk+=text;while(chunk.includes('\n')){const i=chunk.indexOf('\n'),line=chunk.slice(0,i);chunk=chunk.slice(i+1);if(!line.trim())continue;const record=JSON.parse(line);const index=waiters.findIndex(w=>w.predicate(record));if(index>=0)waiters.splice(index,1)[0].resolve(record);else queue.push(record);}});
  const take=predicate=>new Promise((resolve,reject)=>{const i=queue.findIndex(predicate);if(i>=0){resolve(queue.splice(i,1)[0]);return;}if(closed){reject(Error('Owned backend is terminal'));return;}const waiter={predicate,resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}};const timer=setTimeout(()=>{const i=waiters.indexOf(waiter);if(i>=0)waiters.splice(i,1);reject(Error('Owned backend record timeout'));},45000);waiters.push(waiter);});
  const command=async data=>{const pending=take(r=>r.action===data.action);child.stdin.write(JSON.stringify(data)+'\n');return pending;};
  const server={child,take,command,exit,get closed(){return closed;},get stderr(){return stderr;},get exitCode(){return exitCode;},async stop(){if(closed)return;const record=take(r=>r.phase==='closed');child.stdin.write('{"action":"stop"}\n');const proof=await record;verify(proof.passed&&proof.session_closed&&proof.lock_released&&proof.external_network_attempts===0&&!proof.telegram_requests,'owned backend cleanup');verify(await exit===0,'owned backend successful exit');}};
  processes.push(server);return server;
}
async function host(context,launch,theme){await context.addInitScript(({launch,theme})=>{
  const tracked=new Map(),add=EventTarget.prototype.addEventListener,remove=EventTarget.prototype.removeEventListener;
  const relevant=(target,event)=>(target===window||target===document)&&['pagehide','pageshow','popstate','beforeunload','visibilitychange'].includes(event);
  EventTarget.prototype.addEventListener=function(event,listener,options){if(relevant(this,event)){const key=(this===window?'window:':'document:')+event;if(!tracked.has(key))tracked.set(key,new Set());tracked.get(key).add(listener);}return add.call(this,event,listener,options);};
  EventTarget.prototype.removeEventListener=function(event,listener,options){if(relevant(this,event))tracked.get((this===window?'window:':'document:')+event)?.delete(listener);return remove.call(this,event,listener,options);};
  window.__shopWindowListeners=()=>[...tracked.values()].reduce((count,listeners)=>count+listeners.size,0);
  const listeners=new Map();const app={initData:launch,platform:'tdesktop',version:'10.3',colorScheme:theme,themeParams:{},ready(){this.readyCount=(this.readyCount??0)+1;},isVersionAtLeast(){return true;},onEvent(event,fn){if(!listeners.has(event))listeners.set(event,new Set());listeners.get(event).add(fn);},offEvent(event,fn){listeners.get(event)?.delete(fn);},emit(event){for(const fn of listeners.get(event)??[])fn();},listenerCount(){return [...listeners.values()].reduce((total,set)=>total+set.size,0);},closing:false,enableClosingConfirmation(){this.closing=true;},disableClosingConfirmation(){this.closing=false;},BackButton:{visible:false,show(){this.visible=true;},hide(){this.visible=false;}},invoiceCalls:[],openInvoice(url,callback){this.invoiceCalls.push(url);this.invoiceCallback=callback;}};
  window.Telegram={WebApp:app};window.__shopHost=app;
},{launch,theme});}
async function pageFor(ready,{width,height,theme},drop=false){
  const context=await browser.newContext({viewport:{width,height},colorScheme:theme,reducedMotion:'reduce'});await host(context,ready.launch['42'],theme);const page=await context.newPage();trackSession(page);const errors=[],external=[];let lost=false;
  page.on('pageerror',error=>errors.push(error.message));await page.route('**/*',async route=>{const request=route.request();if(new URL(request.url()).origin!==base){external.push(request.url());await route.abort();}else if(drop&&!lost&&request.method()==='POST'&&new URL(request.url()).pathname==='/api/orders'){lost=true;await route.fetch();await route.abort();}else await route.continue();});
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Выберите материалы'));
  return {context,page,errors,external,get lost(){return lost;}};
}
const pending=page=>page.evaluate(()=>{const key=Object.keys(localStorage).find(k=>k.startsWith('telegram-shop:pending:'));return key?JSON.parse(localStorage.getItem(key)):null;});
const orderData=page=>page.evaluate(async headers=>{const result=await fetch('/api/orders',{headers});return (await result.json()).orders[0];},bearer(page));
const tokenKept=page=>page.evaluate(token=>Object.values(localStorage).join('').includes(token)||Object.values(sessionStorage).join('').includes(token)||document.cookie!=='',tokens.get(owner(page)));
async function choose(page,both=true){await page.getByRole('button',{name:'Добавить Бот без путаницы',exact:true}).focus();await owner(page).keyboard.press('Enter');if(both)await page.getByRole('button',{name:'Добавить Mini App на любом экране',exact:true}).click();await page.getByLabel('Я прочитал(а) условия покупки ниже и согласен(на) с ними.').check();}
async function created(page){await page.getByRole('button',{name:'Создать заказ',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Заказ создан'));return orderData(page);}
function ratio(a,b){const luminance=color=>{const values=color.match(/\d+(?:\.\d+)?/g).slice(0,3).map(Number).map(n=>{const v=n/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return .2126*values[0]+.7152*values[1]+.0722*values[2];};const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
try{
  browser=await chromium.launch(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH,headless:true}:{channel:'chrome',headless:true});
  for(const [name,width,height] of [['phone',320,568],['tablet',768,1024],['desktop',1440,900]])for(const theme of ['light','dark']){
    const id=`${name}-${theme}`,server=start(id),ready=await server.take(r=>r.phase==='ready');const fixture=await pageFor(ready,{width,height,theme},id==='phone-light');const {context,page}=fixture;
    await page.screenshot({path:path.join(output,`${id}-catalog.png`),fullPage:true});
    verify(await page.locator('.tp-shell').getAttribute('data-theme')===theme,`${id}: theme`);
    const colors=await page.locator('.tp-panel').first().evaluate(e=>({text:getComputedStyle(e).color,background:getComputedStyle(e).backgroundColor}));verify(ratio(colors.text,colors.background)>=4.5,`${id}: text contrast`);
    await choose(page);verify((await page.locator('.shop-total').textContent()).includes('65'),`${id}: cart total`);
    await page.evaluate(()=>{const h=window.__shopHost;h.colorScheme=h.colorScheme==='light'?'dark':'light';h.emit('themeChanged');});
    await page.setViewportSize({width,height:320});verify((await page.locator('.shop-total').textContent()).includes('65')&&await page.getByLabel('Я прочитал(а) условия покупки ниже и согласен(на) с ними.').isChecked(),`${id}: theme/resize preserves cart and consent`);
    await page.evaluate(()=>{const h=window.__shopHost;h.colorScheme=h.colorScheme==='light'?'dark':'light';h.emit('themeChanged');});await page.setViewportSize({width,height});
    let row;
    if(id==='phone-light'){
      await page.getByRole('button',{name:'Создать заказ',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Результат неизвестен'));const previous=await pending(page);verify(fixture.lost&&previous!==null,'response deliberately lost after real server effect');await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Заказ создан'));row=await orderData(page);verify((await pending(page)).operation===previous.operation&&row.operation===previous.operation,'reload reconciles the same operation');
    }else row=await created(page);
    verify(row.total===65&&row.currency==='XTR'&&row.status==='awaiting',`${id}: server-owned order`);
    verify((await context.request.get(base+'/api/content/bot-kit',{headers:bearer(page)})).status()===403,`${id}: access denied before receipt`);
    verify((await context.request.get(base+'/api/content/bot-kit')).status()===401,`${id}: no ambient credential`);
    await page.getByRole('button',{name:'Оплатить Stars',exact:true}).click();await page.waitForFunction(()=>window.__shopHost.invoiceCalls.length===1);
    const lookup=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/orders/${row.id}`);await page.evaluate(()=>window.__shopHost.invoiceCallback('paid'));await lookup;
    verify((await orderData(page)).status==='awaiting',`${id}: invoice callback is not payment proof`);
    verify((await server.command({action:'precheckout',id:row.id,actor:77})).checkout[0]===false,`${id}: foreign checkout denied`);
    verify((await server.command({action:'precheckout',id:row.id,amount:1})).checkout[0]===false,`${id}: underpayment denied`);
    verify((await server.command({action:'precheckout',id:row.id})).checkout[0]===true,`${id}: owner checkout approved`);
    await server.command({action:'receipt',id:row.id,actor:77});verify((await orderData(page)).status==='awaiting',`${id}: foreign receipt refused`);
    await server.command({action:'receipt',id:row.id});await server.command({action:'receipt',id:row.id});
    await page.getByRole('button',{name:'Проверить заказ',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Оплата подтверждена сервером'));
    await page.getByRole('button',{name:'Мои покупки',exact:true}).click();await page.getByRole('button',{name:'Открыть Бот без путаницы',exact:true}).click();await page.locator('.shop-content').waitFor();
    verify((await page.locator('.shop-content').textContent()).includes('владельца'),`${id}: authorized content available`);
    verify(await page.evaluate(()=>window.__shopHost.BackButton.visible),`${id}: native back tracks screen`);await page.evaluate(()=>window.__shopHost.emit('backButtonClicked'));verify(await page.getByRole('heading',{name:'Каталог',exact:true}).isVisible(),`${id}: back to catalog`);
    verify(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id}: no horizontal overflow`);
    verify(await page.getByRole('button',{name:'Мои покупки',exact:true}).evaluate(e=>e.getBoundingClientRect().height>=44),`${id}: touch action`);
    const stats=await server.command({action:'stats'});verify(stats.orders===1&&stats.receipts===1&&stats.access===2&&stats.invoice_requests===1,`${id}: one order/invoice/receipt effect`);verify(stats.external_network_attempts===0&&!stats.telegram_requests,`${id}: no provider network`);
    verify((await pending(page))===null,`${id}: paid clears pending identity`);
    verify(!(await tokenKept(page))&&(await context.cookies()).length===0,`${id}: session token only in memory, no cookies`);verify(fixture.errors.length===0&&fixture.external.length===0,`${id}: no browser exceptions/external traffic`);
    await page.screenshot({path:path.join(output,`${id}-paid.png`),fullPage:true});cases.push({name,width,height,theme,stats,contrast:ratio(colors.text,colors.background)});await context.close();await server.stop();
  }
  // Telegram Web: the Mini App is an iframe of another site (web.telegram.org). Here the top page is
  // http://localhost and the shop http://127.0.0.1 — different sites, so SameSite cookies are not available.
  {
    const server=start('telegram-web'),ready=await server.take(r=>r.phase==='ready');
    const top=createServer((request,response)=>{response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});response.end(`<!doctype html><title>Telegram Web stand-in</title><iframe src="${base}/" title="Mini App" width="420" height="860" style="border:0"></iframe>`);});
    await new Promise(resolve=>top.listen(0,'127.0.0.1',resolve));const topBase=`http://localhost:${top.address().port}`;
    const context=await browser.newContext({viewport:{width:1280,height:900},colorScheme:'light',reducedMotion:'reduce'});await host(context,ready.launch['42'],'light');
    const page=await context.newPage();trackSession(page);const errors=[],external=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',async route=>{const origin=new URL(route.request().url()).origin;if(origin!==base&&origin!==topBase){external.push(route.request().url());await route.abort();}else await route.continue();});
    try{
      await page.goto(topBase+'/');const frame=page.frames().find(item=>item.url().startsWith(base));verify(frame!==undefined,'telegram-web: shop runs in a cross-site iframe');
      await frame.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('Выберите материалы'));
      verify(await frame.evaluate(()=>{document.cookie='samesite-probe=1; SameSite=Strict; path=/';return !document.cookie.includes('samesite-probe');}),'telegram-web: the browser refuses SameSite=Strict cookies in this iframe (why the session is a header)');
      await choose(frame,false);const row=await created(frame);
      verify(row.total===25&&row.status==='awaiting','telegram-web: authenticated order inside the iframe');
      await frame.getByRole('button',{name:'Оплатить Stars',exact:true}).click();await frame.waitForFunction(()=>window.__shopHost.invoiceCalls.length===1);
      verify((await server.command({action:'precheckout',id:row.id})).checkout[0]===true,'telegram-web: owner checkout approved');
      await server.command({action:'receipt',id:row.id});
      await frame.getByRole('button',{name:'Проверить заказ',exact:true}).click();await frame.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Оплата подтверждена сервером'));
      await frame.getByRole('button',{name:'Мои покупки',exact:true}).click();await frame.getByRole('button',{name:'Открыть Бот без путаницы',exact:true}).click();await frame.locator('.shop-content').waitFor();
      verify((await frame.locator('.shop-content').textContent()).includes('владельца'),'telegram-web: purchased content opens in the iframe');
      verify(!(await tokenKept(frame))&&(await context.cookies()).length===0,'telegram-web: no cookies, token only in memory');
      await page.reload();const again=page.frames().find(item=>item.url().startsWith(base));
      await again.getByRole('button',{name:'Мои покупки',exact:true}).click();await again.getByRole('button',{name:'Открыть Бот без путаницы',exact:true}).waitFor();
      verify(true,'telegram-web: reload signs in again from initData');
      verify(errors.length===0&&external.length===0,'telegram-web: no exceptions or external traffic');
      await page.screenshot({path:path.join(output,'telegram-web-iframe.png')});cases.push({name:'telegram-web-iframe',width:1280,height:900,theme:'light'});
    }finally{await context.close();await new Promise(resolve=>top.close(resolve));}
    await server.stop();
  }
  // Actual wired UI lifecycle/account transitions against the same real Python backend.
  {
    const server=start('lifecycle'),ready=await server.take(r=>r.phase==='ready');
    const fixture=await pageFor(ready,{width:414,height:896,theme:'light'});const {page,context}=fixture;
    const apiRequests=[];page.on('request',request=>{const url=new URL(request.url());if(url.origin===base&&url.pathname.startsWith('/api/'))apiRequests.push(request.method()+' '+url.pathname);});
    verify(!(await page.evaluate(()=>window.__shopHost.closing)),'lifecycle: pristine app does not request close confirmation');
    const listeners=await page.evaluate(()=>window.__shopHost.listenerCount());verify(listeners>0,'lifecycle: owned SDK listeners registered');
    const browserListeners=await page.evaluate(()=>window.__shopWindowListeners());verify(browserListeners>0,'lifecycle: browser lifecycle listeners observed');
    await choose(page,false);verify(await page.evaluate(()=>window.__shopHost.closing),'lifecycle: actual dirty cart requests native close confirmation');
    verify(await page.evaluate(()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}),'lifecycle: browser closing handler protects dirty work');
    const row=await created(page),original=(await pending(page)).operation;
    let invoiceLost=false;
    await page.route(base+'/api/orders/'+row.id+'/invoice',async route=>{invoiceLost=true;await route.fetch();await route.abort();});
    await page.getByRole('button',{name:'Оплатить Stars',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Результат подготовки оплаты неизвестен'));
    verify(invoiceLost&&await page.getByRole('button',{name:'Оплатить Stars',exact:true}).isHidden(),'lifecycle: lost invoice reply blocks another payment dispatch before reconciliation');
    verify((await server.command({action:'stats'})).invoice_requests===1,'lifecycle: lost invoice reply followed one actual remote preparation');
    await page.unroute(base+'/api/orders/'+row.id+'/invoice');
    await page.getByRole('button',{name:'Проверить заказ',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Заказ создан'));
    await page.getByRole('button',{name:'Оплатить Stars',exact:true}).click();await page.waitForFunction(()=>window.__shopHost.invoiceCalls.length===1);
    verify((await server.command({action:'stats'})).invoice_requests===1,'lifecycle: reconciled ready invoice reuses its link without a new remote preparation');
    await page.evaluate(()=>{window.__oldShopInvoice=window.__shopHost.invoiceCallback;});
    const beforeLostRotation=tokens.get(page);let rotationLost=false;
    await page.route(base+'/api/session/rotate',async route=>{rotationLost=true;await route.fetch();await route.abort();});
    const renewedLogin=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/session'&&response.request().method()==='POST');
    await page.getByRole('button',{name:'Обновить вход',exact:true}).click();await renewedLogin;await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Заказ создан'));
    await page.unroute(base+'/api/session/rotate');
    verify(rotationLost&&(await context.request.get(base+'/api/orders',{headers:{Authorization:'Bearer '+beforeLostRotation}})).status()===401,'lifecycle: lost rotation reply reauthenticates after actual server token replacement');
    verify((await pending(page)).operation===original&&(await orderData(page)).id===row.id,'lifecycle: lost rotation keeps original order ID and payload');
    await page.getByRole('button',{name:'Мои покупки',exact:true}).click();await page.locator('section[aria-label="Мои покупки"] article').waitFor();
    verify(await page.evaluate(()=>history.state.telegramShop.screen==='orders'),'lifecycle: purchases owns a browser-history entry');
    await page.goBack();await page.getByRole('heading',{name:'Каталог',exact:true}).waitFor();
    await page.goForward();await page.locator('section[aria-label="Мои покупки"] article').waitFor();
    verify(await page.evaluate(()=>window.__shopHost.BackButton.visible),'lifecycle: forward navigation restores native BackButton');
    await page.evaluate(()=>window.__shopHost.emit('backButtonClicked'));await page.getByRole('heading',{name:'Каталог',exact:true}).waitFor();
    verify(!(await page.evaluate(()=>window.__shopHost.BackButton.visible)),'lifecycle: native Back uses same history transition');

    // Real server answers first; keep that old browser read pending while rotate invalidates its bearer.
    let heldResolve,releaseHeld;const held=new Promise(resolve=>{heldResolve=resolve;}),released=new Promise(resolve=>{releaseHeld=resolve;});let hold=true;
    await page.route(base+'/api/orders',async route=>{if(hold&&route.request().method()==='GET'){hold=false;const response=await route.fetch();heldResolve();await released;try{await route.fulfill({response});}catch{/* browser request was genuinely aborted by account generation */}}else await route.continue();});
    await page.getByRole('button',{name:'Мои покупки',exact:true}).click();await held;const oldToken=tokens.get(page);
    await page.getByRole('button',{name:'Обновить вход',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Вход обновлён'));
    const rotatedToken=tokens.get(page);verify(rotatedToken!==oldToken,'lifecycle: rotation updates actual UI memory bearer');
    verify((await context.request.get(base+'/api/orders',{headers:{Authorization:'Bearer '+oldToken}})).status()===401,'lifecycle: old bearer read rejected by real backend');
    releaseHeld();await page.locator('section[aria-label="Мои покупки"] article').waitFor();
    verify((await pending(page)).operation===original,'lifecycle: rotation preserves linked original intent');
    await page.unroute(base+'/api/orders');
    // Draft expiry never destroys the independent unknown operation or recreates the order.
    await page.evaluate(()=>{for(const key of Object.keys(localStorage))if(key.startsWith('telegram-shop:cart:')){const draft=JSON.parse(localStorage.getItem(key));draft.expires=0;localStorage.setItem(key,JSON.stringify(draft));}});
    await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Заказ создан'));
    verify((await pending(page)).operation===original&&(await orderData(page)).id===row.id,'lifecycle: expired draft reload reconciles original server order');
    await page.getByRole('button',{name:'Оплатить Stars',exact:true}).click();await page.waitForFunction(()=>window.__shopHost.invoiceCalls.length===1);
    await page.evaluate(()=>{window.__oldShopInvoice=window.__shopHost.invoiceCallback;});

    let pendingAuth,releaseAuth;const authHeld=new Promise(resolve=>{pendingAuth=resolve;}),authRelease=new Promise(resolve=>{releaseAuth=resolve;});
    await page.route(base+'/api/session/rotate',async route=>{const response=await route.fetch();pendingAuth();await authRelease;try{await route.fulfill({response});}catch{/* superseded login may abort the old transport */}});
    await page.getByRole('button',{name:'Обновить вход',exact:true}).click();await authHeld;
    await page.evaluate(launch=>{window.__shopHost.initData=launch;window.__shopHost.emit('activated');},ready.launch['77']);
    await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Выберите материалы'));
    await page.getByText('Покупок пока нет. Выберите материал в каталоге.',{exact:true}).waitFor();
    const delayedReply=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/session/rotate');releaseAuth();await delayedReply;await page.unroute(base+'/api/session/rotate');await page.waitForTimeout(30);
    const newActorRead=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/orders'&&response.request().method()==='GET');
    await page.getByRole('button',{name:'Мои покупки',exact:true}).click();await newActorRead;await page.getByText('Покупок пока нет. Выберите материал в каталоге.',{exact:true}).waitFor();
    verify((await context.request.get(base+'/api/orders',{headers:bearer(page)})).status()===200,'lifecycle: delayed previous-account rotation cannot replace new login or subsequent actual UI read');
    verify((await page.locator('.shop-total').textContent()).includes('0'),'lifecycle: account switch clears old cart/order immediately');
    verify((await context.request.get(base+'/api/orders/'+row.id,{headers:bearer(page)})).status()===403,'lifecycle: new actor cannot fetch old order');
    verify(await page.evaluate(operation=>JSON.parse(localStorage.getItem('telegram-shop:pending:100:42:v1')).operation===operation&&!localStorage.getItem('telegram-shop:pending:100:77:v1'),original),'lifecycle: pending payload remains in original verified account scope');
    let revokeHeld,revokeRelease;const heldRevoke=new Promise(resolve=>{revokeHeld=resolve;}),releaseRevoke=new Promise(resolve=>{revokeRelease=resolve;});
    await page.route(base+'/api/session/revoke',async route=>{const response=await route.fetch();revokeHeld();await releaseRevoke;await route.fulfill({response});});
    const actor77=tokens.get(page);await page.getByRole('button',{name:'Выйти',exact:true}).click();await heldRevoke;
    verify(await page.getByRole('button',{name:'Выйти',exact:true}).isHidden()&&await page.locator('section[aria-label="Мои покупки"] article').count()===0,'lifecycle: local logout clears identity and private view before delayed server acknowledgement');
    revokeRelease();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Вы вышли'));await page.unroute(base+'/api/session/revoke');
    verify((await context.request.get(base+'/api/orders',{headers:{Authorization:'Bearer '+actor77}})).status()===401,'lifecycle: logout revokes current bearer durably');
    verify(await page.locator('section[aria-label="Мои покупки"] article').count()===0,'lifecycle: logout removes private cards');
    await page.getByRole('button',{name:'Обновить вход',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Выберите материалы'));
    await page.getByRole('button',{name:'Каталог',exact:true}).click();await page.getByRole('heading',{name:'Каталог',exact:true}).waitFor();await choose(page,false);
    const rotations=apiRequests.filter(item=>item==='POST /api/session/rotate').length;
    const resumed=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/session/rotate');
    await page.evaluate(()=>{window.dispatchEvent(new PageTransitionEvent('pagehide'));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));window.__shopHost.emit('activated');document.dispatchEvent(new Event('visibilitychange'));});
    await resumed;await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Вход обновлён'));
    verify(apiRequests.filter(item=>item==='POST /api/session/rotate').length===rotations+1,'lifecycle: simultaneous resume sources perform one rotation');
    verify(await page.evaluate(()=>window.__shopHost.listenerCount())===listeners,'lifecycle: suspend/resume does not duplicate SDK listeners');
    verify(await page.evaluate(()=>window.__shopWindowListeners())===browserListeners,'lifecycle: suspend/resume keeps one owned browser listener set');
    verify((await page.locator('.shop-total').textContent()).includes('25')&&await page.getByLabel('Я прочитал(а) условия покупки ниже и согласен(на) с ними.').isChecked(),'lifecycle: renewal preserves cart and consent');
    await page.evaluate(async()=>{const app=await import('/assets/app/main.js');app.dispose();app.dispose();});
    verify(await page.evaluate(()=>window.__shopHost.listenerCount()===0&&!window.__shopHost.closing&&!window.__shopHost.BackButton.visible),'lifecycle: repeated dispose releases SDK handlers and owned native state');
    verify(await page.evaluate(()=>window.__shopWindowListeners())===0,'lifecycle: dispose removes every owned window/document listener');
    verify(await page.locator('.tp-shell').count()===0,'lifecycle: dispose removes owned view');
    verify(!(await page.evaluate(()=>{const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;})),'lifecycle: dispose removes browser closing listener');
    await page.evaluate(async()=>{const app=await import('/assets/app/main.js');app.mountShop();app.mountShop();});await page.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('Выберите материалы'));
    verify(await page.locator('.tp-shell').count()===1&&await page.evaluate(()=>window.__shopHost.listenerCount())===listeners,'lifecycle: remount keeps one view and one set of handlers');
    verify(await page.evaluate(()=>window.__shopWindowListeners())===browserListeners,'lifecycle: repeated remount does not duplicate browser listeners');
    verify((await page.locator('.shop-total').textContent()).includes('25')&&await page.getByLabel('Я прочитал(а) условия покупки ниже и согласен(на) с ними.').isChecked(),'lifecycle: same-account remount restores allowlisted draft');
    await page.route(base+'/api/policy',async route=>{const response=await route.fetch();const policy=await response.json();await route.fulfill({response,json:{...policy,version:'demo-v2'}});});
    await page.evaluate(async()=>{(await import('/assets/app/main.js')).mountShop();});await page.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('Выберите материалы'));
    verify((await page.locator('.shop-total').textContent()).includes('25')&&!(await page.getByLabel('Я прочитал(а) условия покупки ниже и согласен(на) с ними.').isChecked())&&await page.getByRole('button',{name:'Создать заказ',exact:true}).isDisabled(),'lifecycle: a new policy version preserves product draft but requires fresh consent');
    await page.unroute(base+'/api/policy');
    verify(await page.evaluate(()=>typeof window.__oldShopInvoice==='function'),'lifecycle: delayed callback belongs to a real earlier invoice request');
    const calls=apiRequests.length;await page.evaluate(()=>window.__oldShopInvoice('paid'));await page.waitForTimeout(50);
    verify(apiRequests.length===calls,'lifecycle: callback of disposed mount does not start requests');
    await page.evaluate(async()=>{window.__shopHost.version='7.0';(await import('/assets/app/main.js')).mountShop();});await page.waitForFunction(()=>document.querySelector('[role=status]')?.textContent.includes('Выберите материалы'));
    verify(await page.evaluate(()=>window.__shopHost.listenerCount())===listeners-1,'lifecycle: unsupported activated event does not prevent older-client mount');
    const oldClientResume=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/session/rotate');await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));await oldClientResume;
    await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Вход обновлён'));
    verify(await page.evaluate(()=>window.__shopWindowListeners())===browserListeners,'lifecycle: older client resumes through one browser lifecycle listener set');
    const stats=await server.command({action:'stats'});verify(stats.orders===1&&stats.invoice_requests===1,'lifecycle: navigation/renewal/remount never recreate the order or invoice');
    verify(!(await tokenKept(page))&&fixture.errors.length===0&&fixture.external.length===0,'lifecycle: no auth persistence, exceptions or external traffic');
    await context.close();await server.stop();
  }
  // No response before dispatch: read-only recovery cannot create a first order implicitly.
  {
    const server=start('explicit-retry'),ready=await server.take(r=>r.phase==='ready');
    const fixture=await pageFor(ready,{width:390,height:844,theme:'light'});const {page,context}=fixture;
    let posts=0;page.on('request',request=>{if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/orders')posts++;});
    await choose(page,false);await page.route(base+'/api/orders',async route=>{if(route.request().method()==='POST')await route.abort();else await route.continue();});
    await page.getByRole('button',{name:'Создать заказ',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Результат неизвестен'));
    const original=(await pending(page)).operation;verify((await server.command({action:'stats'})).orders===0,'retry: original request was dropped before reaching server');
    await page.unroute(base+'/api/orders');await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Сервер не нашёл сохранённый запрос'));
    verify((await server.command({action:'stats'})).orders===0&&posts===1,'retry: reload and GET 404 never send an automatic order POST');
    verify((await pending(page)).operation===original&&await page.getByRole('button',{name:'Повторить сохранённый запрос',exact:true}).isVisible(),'retry: original ID is preserved for an explicit decision');
    await server.command({action:'role',role:'viewer'});
    await page.getByRole('button',{name:'Повторить сохранённый запрос',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Результат неизвестен'));
    verify((await server.command({action:'stats'})).orders===0&&posts===2,'retry: current read-only server role denies an explicit write before its effect');
    await server.command({action:'role',role:'customer'});
    await page.getByRole('button',{name:'Проверить заказ',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Сервер не нашёл сохранённый запрос'));
    await page.getByRole('button',{name:'Повторить сохранённый запрос',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Заказ создан'));
    const row=await orderData(page);verify(row.operation===original&&posts===3&&(await server.command({action:'stats'})).orders===1,'retry: authorized explicit repeat uses exactly the original UUID and one server order');
    verify(fixture.errors.length===0&&fixture.external.length===0,'retry: no exceptions or external traffic');await context.close();await server.stop();
  }
  // These are protocol fixtures for launch profiles; they do not claim real Telegram client launches.
  {
    const server=start('launch-matrix'),ready=await server.take(r=>r.phase==='ready');
    for(const [name,raw] of Object.entries(ready.launch_profiles)){
      const context=await browser.newContext({viewport:{width:390,height:844}});await host(context,raw,'light');const page=await context.newPage();trackSession(page);const errors=[],external=[];
      page.on('pageerror',error=>errors.push(error.message));await page.route('**/*',async route=>{if(new URL(route.request().url()).origin!==base){external.push(route.request().url());await route.abort();}else await route.continue();});
      const screen=name==='main'?'orders':'catalog';await page.goto(base+'/?tgWebAppStartParam='+screen+'&user_id=77&role=admin');
      if(raw){await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Выберите материалы'));verify(tokens.has(page),'launch: '+name+' uses server-issued bearer');}
      else{await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Для покупки откройте Mini App'));verify(!tokens.has(page),'launch: '+name+' without initData never creates a session');}
      verify(await page.getByRole('heading',{name:screen==='orders'?'Мои покупки':'Каталог',exact:true}).isVisible(),'launch: '+name+' selects only the allowlisted screen');
      verify((await context.request.get(base+'/api/orders',{headers:raw?bearer(page):{}})).status()===(raw?200:401),'launch: '+name+' query identity/role cannot authorize a private route');
      if(!raw){await choose(page,false);verify(await page.getByRole('button',{name:'Создать заказ',exact:true}).isDisabled(),'launch: '+name+' remains useful as public catalog without pretending to buy');}
      verify((await server.command({action:'stats'})).orders===0,'launch: '+name+' navigation never creates an order');
      verify(errors.length===0&&external.length===0,'launch: '+name+' has no exceptions or external traffic');await context.close();
    }
    await server.stop();
  }
  // Two actual abrupt exits, then a fresh server on the same SQLite database.
  let server=start('crash');let ready=await server.take(r=>r.phase==='ready');const fixture=await pageFor(ready,{width:375,height:812,theme:'dark'});const {page,context}=fixture;await choose(page,false);const row=await created(page);
  await server.command({action:'crash-invoice'});const marker=server.take(r=>r.phase==='crash-invoice');await page.getByRole('button',{name:'Оплатить Stars',exact:true}).click();verify((await marker).invoice_called&&await server.exit===75,'actual exit after invoice call');
  server=start('crash');ready=await server.take(r=>r.phase==='ready');verify(ready.recovered===1,'restart reconciles creating invoice to unknown');await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Подготовка оплаты не подтверждена'));verify(await page.getByRole('button',{name:'Оплатить Stars',exact:true}).isHidden(),'unknown invoice cannot be reissued from UI');
  let stats=await server.command({action:'stats'});verify(stats.orders===1&&stats.invoice_requests===0&&stats.access===0,'no new invoice or access after crash');
  await server.command({action:'crash-receipt'});const committed=server.take(r=>r.phase==='crash-receipt');server.child.stdin.write(JSON.stringify({action:'receipt',id:row.id,charge:'fault-charge'})+'\n');verify((await committed).committed&&await server.exit===76,'actual exit after atomic receipt/access commit');
  server=start('crash');await server.take(r=>r.phase==='ready');await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Оплата подтверждена сервером'));await server.command({action:'receipt',id:row.id,charge:'fault-charge'});stats=await server.command({action:'stats'});verify(stats.receipts===1&&stats.access===1&&stats.orders===1&&stats.invoice_requests===0,'restart and duplicate receipt preserve one grant');
  verify(fixture.errors.length===0&&fixture.external.length===0,'fault UI has no exceptions or external traffic');await context.close();await server.stop();
  const report={passed:true,browser:browser.version(),checks,cases,telegram_web_iframe:true,lifecycle_account_integration:true,read_only_recovery:true,explicit_original_retry:true,launch_profiles:['menu','main','inline','reply','inline_mode'],crash_exit_codes:[75,76],lost_response_reconciled:true,invoice_callback_not_proof:true,receipt_and_access_atomic:true,external_requests:0,telegram_requests:false,scope:'Six actual Chrome viewport/theme cases, a cross-site iframe, wired shop account/lifecycle/history/session flows, and real HTTP/SQLite/backend processes. Native host and payment updates synthetic; no live Telegram/Stars settlement or physical device acceptance.'};await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser?.close();for(const server of processes)if(!server.closed){server.child.kill('SIGKILL');await server.exit;}}
