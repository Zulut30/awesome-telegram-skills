/** Actual Chrome + same-origin fetch/localStorage; no Telegram/device/live acceptance. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const output=path.resolve(process.env.PATTERNS_STATE_OUTPUT??path.join(root,'output/production-run-2026-11-05/mini-app-state/browser'));
const domain=path.resolve(process.env.SHOP_DOMAIN_JS??path.join(root,'output/production-run-2026-11-05/mini-app-state/domain/domain-state.js'));
await mkdir(output,{recursive:true});await readFile(domain); // Explicit prerequisite, never silently skip shop composition.
const requests=[];
const server=createServer(async(req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  try{
    if(url.pathname==='/'){
      res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>State boundary fixture</title><script type="importmap">{"imports":{"@awesome-telegram/patterns":"/vendor/index.js"}}</script>');return;
    }
    if(/^\/vendor\/[a-z][a-z0-9-]*\.js$/.test(url.pathname)){
      res.setHeader('Content-Type','text/javascript');res.end(await readFile(path.join(root,'packages/typescript/dist',path.basename(url.pathname))));return;
    }
    if(url.pathname==='/domain/domain-state.js'){
      res.setHeader('Content-Type','text/javascript');res.end(await readFile(domain));return;
    }
    if(url.pathname==='/data'){
      requests.push('data');const value={label:url.searchParams.get('label')};
      setTimeout(()=>{if(!res.destroyed){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));}},Number(url.searchParams.get('delay'))||0);return;
    }
    if(url.pathname.startsWith('/operation/')){
      const actor=req.headers.authorization==='Bearer fixture-42'?42:req.headers.authorization==='Bearer fixture-77'?77:null;
      if(actor===null){res.writeHead(401).end();return;}
      requests.push(`operation-${actor}`);
      setTimeout(()=>{if(!res.destroyed){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({id:`order-${actor}`,operation:url.pathname.split('/').at(-1),items:['bot-kit'],total:25,currency:'XTR',status:'awaiting',invoice_state:'unknown'}));}},actor===42?80:1);return;
    }
    res.writeHead(404).end();
  }catch{res.writeHead(500).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;let report;
try{
  browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{channel:'chrome'})});
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const first=await page.evaluate(async()=>{
    const {ScopedAsyncState,SelectionDraftStore,PendingOperationStore}=await import('@awesome-telegram/patterns');
    const {ShopDomainState}=await import('/domain/domain-state.js');
    const checks=[];const verify=(condition,label)=>{if(!condition)throw Error(label);checks.push(label);};
    const state=new ScopedAsyncState();state.setScope('100:42');let oldSignal;
    const old=state.read('catalog',async({signal})=>{oldSignal=signal;return (await fetch('/data?label=old&delay=80')).json();});
    const current=await state.read('catalog',async({signal})=>(await fetch('/data?label=new&delay=1',{signal})).json());
    verify(current.status==='ready'&&current.value.label==='new','actual fetch accepted latest response');
    verify(oldSignal.aborted&&(await old).status==='stale','ignore-abort loader settled stale');
    await new Promise(resolve=>setTimeout(resolve,120));verify(state.snapshot('catalog').value.label==='new','late HTTP response did not overwrite cache');
    let abortSignal;const pending=state.read('private',async({signal})=>{abortSignal=signal;return (await fetch('/data?label=private&delay=200',{signal})).json();});
    state.setScope('100:77');verify(abortSignal.aborted&&(await pending).status==='stale','account change aborts actual fetch');
    verify(state.snapshot('catalog').status==='idle'&&state.snapshot('private').status==='idle','account cache cleared synchronously');
    const dto={items:[{id:'first'}]};const frozen=await state.read('immutable',async()=>dto);dto.items[0].id='mutated';
    verify(frozen.value.items[0].id==='first'&&Object.isFrozen(frozen.value.items[0]),'browser snapshot detached and frozen');

    let now=0;const config={namespace:'browser-state',scope:'100:42',ttlMs:10,now:()=>now};
    const v1=new SelectionDraftStore(()=>localStorage,config);v1.write({serviceId:'cut',slotId:'ten',token:'PRIVATE_TOKEN'});
    const pointer=new PendingOperationStore(()=>localStorage,{namespace:'browser-state',scope:'100:42',now:()=>now});
    const id='123e4567-e89b-42d3-a456-426614174000';pointer.reserve(id);pointer.markUnknown(id);
    now=5;const v2=new SelectionDraftStore(()=>localStorage,{...config,schemaVersion:2,migrateFrom:{1:value=>({serviceId:value.serviceId,slotId:value.slotId})}});
    verify(v2.read().status==='restored'&&JSON.parse(localStorage.getItem(v2.key)).expires===10,'real localStorage migration preserves original expiry');
    now=10;verify(v2.read().status==='expired','draft expired exactly at TTL');v2.clear();
    verify(pointer.read().value.operation===id&&pointer.read().value.state==='unknown','draft expiry and clear preserve unknown operation');
    const blocked=new PendingOperationStore(()=>localStorage,{namespace:'blocked',scope:'100:42'});localStorage.setItem(blocked.key,'{');
    verify(blocked.reserve(id).status==='blocked'&&localStorage.getItem(blocked.key)==='{','corrupt storage blocks dispatch without deleting pointer');
    verify(!Object.values(localStorage).join('').includes('PRIVATE_TOKEN'),'no auth extras persisted');

    const shop=new ShopDomainState(()=>localStorage,{operation:async(session,operation,signal)=>{
      // Intentionally ignore abort here: domain generation must protect a changed account independently.
      return (await fetch('/operation/'+operation,{headers:{Authorization:'Bearer '+session.token}})).json();
    }});
    shop.setSession({scope:'100:42',token:'fixture-42'});shop.setCart(['bot-kit']);shop.reserveOrder(id);shop.markUnknown(id);
    const oldOrder=shop.reconcile();
    shop.setSession({scope:'100:77',token:'fixture-77'});
    verify(shop.snapshot().cart.length===0&&shop.snapshot().order===null&&shop.snapshot().pending.status==='missing','shop account switch clears visible order cart and pending view');
    const second='123e4567-e89b-42d3-a456-426614174001';shop.reserveOrder(second);
    const newOrder=await shop.reconcile();verify(newOrder.status==='ready'&&shop.snapshot().order.id==='order-77','shop uses new captured session for HTTP read');
    verify((await oldOrder).status==='stale','old shop account read rejected');
    await new Promise(resolve=>setTimeout(resolve,120));verify(shop.snapshot().order.id==='order-77','late old shop result stays isolated');
    verify(!JSON.stringify(shop.snapshot()).includes('fixture-'),'shop snapshots exclude session tokens');
    verify(shop.completeOrder(id)===false&&shop.completeOrder(second)===true,'only reconciled exact operation may complete pointer');
    shop.dispose();shop.dispose();state.dispose();
    verify(shop.snapshot().scope===null&&shop.snapshot().order===null,'dispose clears headless shop state');

    let settle;const gate=new Promise(resolve=>{settle=resolve;});
    const raceShop=new ShopDomainState(()=>localStorage,{operation:()=>gate});
    raceShop.setSession({scope:'100:42',token:'fixture-42'});
    const race=raceShop.reconcile();
    settle({id:'old-ready',operation:id,items:['bot-kit'],total:25,currency:'XTR',status:'awaiting',invoice_state:'unknown'});
    // Resolve the read, then switch identity before the domain's own await continuation.
    queueMicrotask(()=>queueMicrotask(()=>queueMicrotask(()=>queueMicrotask(()=>raceShop.setSession({scope:'100:77',token:'fixture-77'})))));
    verify((await race).status==='stale'&&raceShop.snapshot().order===null,'account generation also guards already-resolved read continuation');
    raceShop.dispose();
    return {checks,id};
  });
  await page.reload();
  const reload=await page.evaluate(async()=>{
    const {PendingOperationStore}=await import('@awesome-telegram/patterns');
    const pointer=new PendingOperationStore(()=>localStorage,{namespace:'browser-state',scope:'100:42'});
    const saved=pointer.reserve('123e4567-e89b-42d3-a456-426614174009');
    const other=new PendingOperationStore(()=>localStorage,{namespace:'browser-state',scope:'100:77'}).read();
    return {status:saved.status,id:saved.value?.operation,state:saved.value?.state,other:other.status,authStored:Object.values(localStorage).join('').includes('fixture-')};
  });
  assert.equal(reload.status,'existing');assert.equal(reload.id,first.id);assert.equal(reload.state,'unknown');assert.equal(reload.other,'missing');assert.equal(reload.authStored,false);
  assert.deepEqual(errors,[]);assert.ok(requests.includes('operation-42')&&requests.includes('operation-77'));
  report={passed:true,browser:await browser.version(),checks:[...first.checks,'actual reload retains same unknown operation and isolates accounts'],requests:requests.length,limits:['HTTP/launch fixtures, no real Telegram auth','desktop Chrome localStorage/fetch, no real Telegram clients or physical devices','headless domain example, current shop main UI unchanged','not installed tarball consumer acceptance']};
}catch(error){report={passed:false,error:String(error)};throw error;}
finally{
  if(report)await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
}
console.log(JSON.stringify(report));
