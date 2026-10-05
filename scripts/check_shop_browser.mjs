/** Real installed frontend + loopback backend. Only private fixture stdin creates receipts. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
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
  const listeners=new Map();const app={initData:launch,platform:'tdesktop',version:'10.3',colorScheme:theme,themeParams:{},ready(){this.readyCount=(this.readyCount??0)+1;},isVersionAtLeast(){return true;},onEvent(event,fn){if(!listeners.has(event))listeners.set(event,new Set());listeners.get(event).add(fn);},offEvent(event,fn){listeners.get(event)?.delete(fn);},emit(event){for(const fn of listeners.get(event)??[])fn();},BackButton:{visible:false,show(){this.visible=true;},hide(){this.visible=false;}},invoiceCalls:[],openInvoice(url,callback){this.invoiceCalls.push(url);this.invoiceCallback=callback;}};
  window.Telegram={WebApp:app};window.__shopHost=app;
},{launch,theme});}
async function pageFor(ready,{width,height,theme},drop=false){
  const context=await browser.newContext({viewport:{width,height},colorScheme:theme,reducedMotion:'reduce'});await host(context,ready.launch['42'],theme);const page=await context.newPage();const errors=[],external=[];let lost=false;
  page.on('pageerror',error=>errors.push(error.message));await page.route('**/*',async route=>{const request=route.request();if(new URL(request.url()).origin!==base){external.push(request.url());await route.abort();}else if(drop&&!lost&&request.method()==='POST'&&new URL(request.url()).pathname==='/api/orders'){lost=true;await route.fetch();await route.abort();}else await route.continue();});
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Выберите материалы'));
  return {context,page,errors,external,get lost(){return lost;}};
}
const pending=page=>page.evaluate(()=>{const key=Object.keys(localStorage).find(k=>k.startsWith('telegram-shop:pending:'));return key?JSON.parse(localStorage.getItem(key)):null;});
const orderData=page=>page.evaluate(async()=>{const result=await fetch('/api/orders');return (await result.json()).orders[0];});
async function choose(page,both=true){await page.getByRole('button',{name:'Добавить Бот без путаницы',exact:true}).focus();await page.keyboard.press('Enter');if(both)await page.getByRole('button',{name:'Добавить Mini App на любом экране',exact:true}).click();await page.getByLabel('Я прочитал(а) условия покупки ниже и согласен(на) с ними.').check();}
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
    verify((await context.request.get(base+'/api/content/bot-kit')).status()===403,`${id}: access denied before receipt`);
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
    verify((await pending(page))===null,`${id}: paid clears pending identity`);verify(fixture.errors.length===0&&fixture.external.length===0,`${id}: no browser exceptions/external traffic`);
    await page.screenshot({path:path.join(output,`${id}-paid.png`),fullPage:true});cases.push({name,width,height,theme,stats,contrast:ratio(colors.text,colors.background)});await context.close();await server.stop();
  }
  // Two actual abrupt exits, then a fresh server on the same SQLite database.
  let server=start('crash');let ready=await server.take(r=>r.phase==='ready');const fixture=await pageFor(ready,{width:375,height:812,theme:'dark'});const {page,context}=fixture;await choose(page,false);const row=await created(page);
  await server.command({action:'crash-invoice'});const marker=server.take(r=>r.phase==='crash-invoice');await page.getByRole('button',{name:'Оплатить Stars',exact:true}).click();verify((await marker).invoice_called&&await server.exit===75,'actual exit after invoice call');
  server=start('crash');ready=await server.take(r=>r.phase==='ready');verify(ready.recovered===1,'restart reconciles creating invoice to unknown');await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Подготовка оплаты не подтверждена'));verify(await page.getByRole('button',{name:'Оплатить Stars',exact:true}).isHidden(),'unknown invoice cannot be reissued from UI');
  let stats=await server.command({action:'stats'});verify(stats.orders===1&&stats.invoice_requests===0&&stats.access===0,'no new invoice or access after crash');
  await server.command({action:'crash-receipt'});const committed=server.take(r=>r.phase==='crash-receipt');server.child.stdin.write(JSON.stringify({action:'receipt',id:row.id,charge:'fault-charge'})+'\n');verify((await committed).committed&&await server.exit===76,'actual exit after atomic receipt/access commit');
  server=start('crash');await server.take(r=>r.phase==='ready');await page.reload();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('Оплата подтверждена сервером'));await server.command({action:'receipt',id:row.id,charge:'fault-charge'});stats=await server.command({action:'stats'});verify(stats.receipts===1&&stats.access===1&&stats.orders===1&&stats.invoice_requests===0,'restart and duplicate receipt preserve one grant');
  verify(fixture.errors.length===0&&fixture.external.length===0,'fault UI has no exceptions or external traffic');await context.close();await server.stop();
  const report={passed:true,browser:browser.version(),checks,cases,crash_exit_codes:[75,76],lost_response_reconciled:true,invoice_callback_not_proof:true,receipt_and_access_atomic:true,external_requests:0,telegram_requests:false,scope:'Six actual Chrome viewport/theme cases and real HTTP/SQLite/backend processes. Native host and payment updates synthetic; no live Telegram/Stars settlement or physical device acceptance.'};await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser?.close();for(const server of processes)if(!server.closed){server.child.kill('SIGKILL');await server.exit;}}
