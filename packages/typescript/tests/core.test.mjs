import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { ApiClient, ApiError, TelegramBridge, SelectionDraftStore, TelegramNativeAPI, UnsupportedTelegramCapability,
         TELEGRAM_NATIVE_METHODS, TELEGRAM_NATIVE_EVENTS, PatternError, ValidationFailure,
         InvalidType, PermissionDenied, AuthenticationRequired, UnsupportedCapability,
         UnknownOutcome, safeErrorReport } from '../dist/index.js';

test('safe error reports preserve recovery decisions without exception or payload secrets', () => {
  const secret = 'BOT_TOKEN=100:PRIVATE initData=SIGNED_BODY';
  for (const error of [new Error(secret), new ValidationFailure(secret), new PermissionDenied(secret),
    new UnknownOutcome(secret), new InvalidType(secret), {code:'validation-failed',outcome:'rejected',message:secret}]) {
    const value=safeErrorReport(error,'write');
    assert.equal(JSON.stringify(value).includes(secret),false);
    assert.deepEqual(Object.keys(value).sort(), ['category','code','message','outcome','recovery']);
    assert.throws(()=>{value.message=secret;},TypeError);
  }
  assert.equal(safeErrorReport({code:'validation-failed',outcome:'rejected'},'write').outcome,'unknown');
  const error=new PatternError('internal','unknown',secret);
  error.report=()=>{throw Error('Overridden report must not run');};
  assert.equal(safeErrorReport(error).recovery,'reconcile');
});

test('local rejection, unsupported capability, cancellation and timeout give different recovery', () => {
  for (const [error,category,recovery] of [
    [new ValidationFailure(),'validation','fix-input'], [new InvalidType(),'validation','fix-input'],
    [new PermissionDenied(),'permission','check-permissions'], [new AuthenticationRequired(),'permission','authenticate'],
    [new UnsupportedCapability(),'unsupported','use-fallback']]) {
    const value=safeErrorReport(error,'write');
    assert.deepEqual([value.category,value.recovery,value.outcome],[category,recovery,'rejected']);
  }
  assert.equal(new InvalidType() instanceof TypeError,true);
  assert.throws(()=>new TelegramNativeAPI().call('ready'),error=>{
    assert.equal(safeErrorReport(error).recovery,'use-fallback');return true;
  });
  assert.deepEqual([safeErrorReport(new DOMException('private','TimeoutError')).outcome,
    safeErrorReport(new DOMException('private','TimeoutError')).recovery],['read-failed','retry-read']);
  assert.equal(safeErrorReport(new DOMException('private','AbortError'),'write').recovery,'reconcile');
  assert.equal(safeErrorReport(new UnknownOutcome()).outcome,'unknown');
});

test('HTTP denial and invalid response after write keep unknown result and a single transport call', async () => {
  for (const status of [400,401,403,422,500]) {
    let calls=0;
    const api=new ApiClient({baseUrl:'https://example.test',fetch:async()=>{calls++;return new Response('private',{status});}});
    await assert.rejects(api.request('/orders',x=>x,{method:'POST',body:{id:'stable-operation'}}),error=>{
      assert.equal(error instanceof ApiError,true);
      const report=safeErrorReport(error,'write');
      assert.equal(report.outcome,'unknown');assert.equal(report.recovery,'reconcile');
      assert.equal(JSON.stringify(report).includes('private'),false);
      return true;
    });
    assert.equal(calls,1);
  }
  let calls=0;
  const api=new ApiClient({baseUrl:'https://example.test',fetch:async()=>{calls++;return Response.json({saved:true});}});
  await assert.rejects(api.request('/orders',()=>{throw Error('decoder secret');},{method:'POST'}),error=>{
    assert.equal(safeErrorReport(error,'write').recovery,'reconcile');return true;
  });
  assert.equal(calls,1);
});

test('each HTTP status maps to a precise code for reads and writes, with an explicit backend contract', async () => {
  const expected={400:['validation-failed','fix-input'],401:['authentication-required','authenticate'],403:['permission-denied','check-permissions'],
    404:['invalid-api-request','fix-input'],405:['invalid-api-request','fix-input'],408:['timeout','retry-read'],409:['operation-conflict','reconcile'],
    413:['invalid-api-request','fix-input'],422:['validation-failed','fix-input'],429:['rate-limited','retry-later'],
    500:['server-error','retry-read'],502:['server-error','retry-read'],503:['server-error','retry-read']};
  const contract=Object.keys(expected).map(Number);
  for (const [text,[code,recovery]] of Object.entries(expected)) {
    const status=Number(text);
    const fetch=async()=>new Response('private body',{status,headers:{'Retry-After':'7'}});
    const plain=new ApiClient({baseUrl:'https://x.test',fetch});
    const declared=new ApiClient({baseUrl:'https://x.test',fetch,rejectedBeforeEffect:contract});
    const check=async(promise,outcome,expectedRecovery)=>assert.rejects(promise,error=>{
      assert.equal(error instanceof ApiError,true);assert.equal(error.status,status);
      const report=error.report();
      assert.deepEqual([report.code,report.outcome,report.recovery],[code,outcome,expectedRecovery],`${status} ${outcome}`);
      assert.equal(JSON.stringify(report).includes('private'),false);
      assert.equal(error.retryAfterMs,status===429||status===503?7000:undefined);
      return true;
    });
    await check(plain.request('/r',x=>x),'read-failed',recovery);
    await check(declared.request('/r',x=>x),'read-failed',recovery);
    await check(plain.request('/w',x=>x,{method:'POST',body:{}}),'unknown','reconcile');
    await check(declared.request('/w',x=>x,{method:'POST',body:{}}),'rejected',recovery);
    await check(declared.request('/w',x=>x,{method:'POST',body:{},rejectedBeforeEffect:[]}),'unknown','reconcile');
    await check(plain.request('/w',x=>x,{method:'POST',body:{},rejectedBeforeEffect:[status]}),'rejected',recovery);
  }
  for (const invalid of [[200],[399],[600],[400.5],['400'],'400']) {
    assert.throws(()=>new ApiClient({baseUrl:'https://x.test',rejectedBeforeEffect:invalid}),ValidationFailure);
  }
});

test('Retry-After accepts seconds and HTTP dates, is bounded and ignores garbage', async () => {
  const at=Date.now()+90_000;
  for (const [header,check] of [['0',v=>v===0],['120',v=>v===120000],[new Date(at).toUTCString(),v=>v>80_000&&v<=90_000],
      ['999999999',v=>v===86_400_000],['soon',v=>v===undefined],['-5',v=>v===undefined],['Thu, 01 Jan 1970 00:00:00 GMT',v=>v===0]]) {
    const api=new ApiClient({baseUrl:'https://x.test',fetch:async()=>new Response('',{status:429,headers:{'Retry-After':header}})});
    await assert.rejects(api.request('/r',x=>x),error=>{assert.equal(check(error.retryAfterMs),true,`${header} -> ${error.retryAfterMs}`);return true;});
  }
});

test('oversized timeout, failing headers and non-JSON bodies are typed rejections before transport', async () => {
  let calls=0;
  const transport=async()=>{calls++;return Response.json({});};
  const api=new ApiClient({baseUrl:'https://x.test',fetch:transport});
  for (const timeoutMs of [3e9,2_147_483_648,Infinity,0,-1,NaN]) {
    await assert.rejects(api.request('/r',x=>x,{timeoutMs}),ValidationFailure,String(timeoutMs));
  }
  await api.request('/r',x=>x,{timeoutMs:2_147_483_647});assert.equal(calls,1);calls=0;
  for (const headers of [()=>{throw Error('PRIVATE header secret');},()=>({'bad header':'x'})]) {
    const failing=new ApiClient({baseUrl:'https://x.test',fetch:transport,headers});
    await assert.rejects(failing.request('/w',x=>x,{method:'POST',body:{}}),error=>{
      assert.equal(error instanceof PatternError,true);
      assert.deepEqual([error.code,error.outcome],['internal','rejected']);
      assert.equal(String(error).includes('PRIVATE'),false);assert.equal(error.cause,undefined);
      return true;
    });
  }
  const cyclic={};cyclic.self=cyclic;
  for (const body of [10n,cyclic,()=>1,Symbol('x'),{toJSON(){throw Error('PRIVATE');}}]) {
    await assert.rejects(api.request('/w',x=>x,{method:'POST',body}),error=>{
      assert.equal(error instanceof ValidationFailure,true);assert.equal(String(error).includes('PRIVATE'),false);return true;
    });
  }
  assert.equal(calls,0);
});

test('API preflight rejection is actionable and happens before transport', async () => {
  let calls=0;
  const api=new ApiClient({baseUrl:'https://example.test',fetch:async()=>{calls++;return Response.json({});}});
  await assert.rejects(api.request('https://other.test',x=>x,{method:'POST'}),error=>{
    assert.equal(safeErrorReport(error,'write').recovery,'fix-input');
    assert.equal(safeErrorReport(error,'write').outcome,'rejected');return true;
  });
  assert.equal(calls,0);
});

test('API paths resolve inside the base path and cannot escape it', async () => {
  const calls=[];
  const transport=async(input)=>{calls.push(input.href);return Response.json({});};
  for (const base of ['https://x.test/api/v1','https://x.test/api/v1/','https://x.test/api/v1?ignored=1']) {
    const api=new ApiClient({baseUrl:base,fetch:transport});
    for (const path of ['/orders','orders','orders?id=1','/orders/7','']) await api.request(path,x=>x);
    for (const path of ['../admin','/../admin','%2e%2e/admin','https://x.test/admin','https://x.test/api/v10/x','//other.test/x','https://other.test/api/v1/x']) {
      await assert.rejects(api.request(path,x=>x),ValidationFailure,`${base} ${path}`);
    }
    await api.request('https://x.test/api/v1/same-origin',x=>x);
  }
  assert.deepEqual(calls.slice(0,6),['https://x.test/api/v1/orders','https://x.test/api/v1/orders','https://x.test/api/v1/orders?id=1',
    'https://x.test/api/v1/orders/7','https://x.test/api/v1/','https://x.test/api/v1/same-origin']);
  const root=new ApiClient({baseUrl:'https://x.test',fetch:transport});calls.length=0;
  await root.request('/orders',x=>x);await root.request('orders',x=>x);
  assert.deepEqual(calls,['https://x.test/orders','https://x.test/orders']);
});

test('consumer adapters preserve existing storage and transport ownership and account isolation', async () => {
  const values=new Map(),calls=[];
  const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
  values.set('project-owned','preserve');
  const a=new SelectionDraftStore(()=>storage,{namespace:'fixture',scope:'verified:42',ttlMs:1000,now:()=>100});
  const b=new SelectionDraftStore(()=>storage,{namespace:'fixture',scope:'verified:99',ttlMs:1000,now:()=>100});
  assert.equal(a.write({serviceId:'s1',slotId:null}),true);
  assert.equal(a.read().status,'restored');assert.equal(b.read().status,'missing');
  assert.equal(a.clear(),true);assert.equal(storage.getItem('project-owned'),'preserve');
  const transport=async(input,init)=>{calls.push({input,init});return Response.json({id:'fixture-1'});};
  const api=new ApiClient({baseUrl:'https://fixture.test',fetch:transport,headers:()=>({'X-Project-Token':'fixture'})});
  const result=await api.request('/entries',value=>{assert.equal(typeof value.id,'string');return value.id;});
  assert.equal(result,'fixture-1');assert.equal(calls.length,1);
  assert.equal(calls[0].input.pathname,'/entries');
  assert.equal(calls[0].init.headers.get('X-Project-Token'),'fixture');
  assert.equal(calls[0].init.signal.aborted,false);
});

class FakeApp {
  colorScheme = 'light'; themeParams = { bg_color: '#ffffff', text_color: '#000000' };
  viewportStableHeight = 600; readyCalls = 0; callbacks = new Map();
  ready() { this.readyCalls++; }
  onEvent(name, fn) { if (!this.callbacks.has(name)) this.callbacks.set(name, new Set()); this.callbacks.get(name).add(fn); }
  offEvent(name, fn) { this.callbacks.get(name)?.delete(fn); }
  emit(name) { for (const fn of this.callbacks.get(name) ?? []) fn(); }
  count() { return [...this.callbacks.values()].reduce((n, set) => n + set.size, 0); }
}
test('bridge repeated start, theme, actual EventTarget lifecycle and disposal', () => {
  const app = new FakeApp(), host = new EventTarget(), bridge = new TelegramBridge(app, host);
  const seen = []; bridge.subscribe(s => seen.push(s)); bridge.start(); bridge.start();
  assert.equal(app.readyCalls, 1); assert.equal(app.count(), 4);
  app.colorScheme = 'dark'; app.emit('themeChanged'); assert.equal(seen.at(-1).colorScheme, 'dark');
  host.dispatchEvent(new Event('pagehide')); assert.equal(app.count(), 0);
  app.viewportStableHeight = 420; host.dispatchEvent(new Event('pageshow'));
  assert.equal(app.count(), 4); assert.equal(seen.at(-1).stableHeight, 420); assert.equal(app.readyCalls, 1);
  bridge.dispose(); host.dispatchEvent(new Event('pageshow')); assert.equal(app.count(), 0);
  assert.throws(() => bridge.start());
});
test('outside-Telegram snapshot, absent/invalid insets and safe theme values', () => {
  assert.equal(new TelegramBridge(undefined, undefined).snapshot().insideTelegram, false);
  const app = new FakeApp(); app.safeAreaInset = {top: NaN,right:0,bottom:0,left:0}; app.viewportStableHeight = -1;
  app.themeParams = {bg_color: 'url(https://invalid.example)',text_color:'#ffffff'};
  const snapshot = new TelegramBridge(app, undefined).snapshot();
  assert.equal(snapshot.systemInsets, undefined); assert.equal(snapshot.stableHeight, undefined);
  assert.equal(snapshot.theme.bg_color, undefined); assert.equal(snapshot.theme.text_color,'#ffffff');
  assert.throws(() => { snapshot.theme.text_color = '#000000'; }, TypeError);
  app.platform='unknown';assert.equal(new TelegramBridge(app).snapshot().insideTelegram,false);
  app.platform='android';assert.equal(new TelegramBridge(app).snapshot().insideTelegram,true);
});

test('failed initial subscriber is removed instead of poisoning future events', () => {
  const app=new FakeApp(),bridge=new TelegramBridge(app,new EventTarget());
  assert.throws(()=>bridge.subscribe(()=>{throw new Error('consumer failure');}));
  let updates=0;bridge.subscribe(()=>{updates++;});bridge.start();app.emit('themeChanged');
  assert.equal(updates,3);bridge.dispose();
});

test('partially failed SDK registration is cleaned and start can be retried', () => {
  const app=new FakeApp(),original=app.onEvent;let fail=true;
  app.onEvent=function(event,listener){original.call(this,event,listener);if(fail&&event==='safeAreaChanged')throw new Error('SDK registration failure');};
  const bridge=new TelegramBridge(app,new EventTarget());assert.throws(()=>bridge.start());
  assert.equal(app.count(),0);fail=false;bridge.start();assert.equal(app.count(),4);assert.equal(app.readyCalls,1);
  bridge.dispose();assert.equal(app.count(),0);
});

test('all documented native paths bind the SDK receiver and preserve arguments/results', () => {
  const app = {platform:'android',version:'10.3'}, calls=[];
  for (const path of Object.keys(TELEGRAM_NATIVE_METHODS)) {
    const parts=path.split('.');let owner=app;
    for (const part of parts.slice(0,-1)) owner=owner[part]??= {};
    owner[parts.at(-1)]=function(...args){assert.equal(this,owner);if(path==='isVersionAtLeast'&&typeof args[0]==='string')return true;calls.push({path,args});return 'native-result';};
  }
  const api=new TelegramNativeAPI(app);
  for (const path of Object.keys(TELEGRAM_NATIVE_METHODS)) {
    assert.equal(api.supports(path),true,path);
    const callback=()=>{};assert.equal(api.call(path,{fixture:true},callback),'native-result');
    assert.equal(calls.at(-1).args[1],callback);
  }
  assert.equal(calls.length,99);assert.equal(Object.isFrozen(TELEGRAM_NATIVE_METHODS),true);
  assert.equal(Object.isFrozen(TELEGRAM_NATIVE_METHODS['ready']),true);
});

test('native availability separates missing methods, client version and outside-Telegram context', () => {
  for (const app of [undefined,{}, {platform:'unknown',version:'10.3',ready(){}},
    {platform:'android',version:'5.9',ready(){}},{platform:'android',version:'invalid',ready(){}}]) {
    const api=new TelegramNativeAPI(app);assert.equal(api.supports('ready'),false);
    assert.throws(()=>api.call('ready'),UnsupportedTelegramCapability);
  }
  const app={platform:'ios',version:'7.0',ready(){return undefined;},LocationManager:{getLocation(){throw Error('should not call');}}};
  const api=new TelegramNativeAPI(app);assert.equal(api.supports('ready'),true);assert.equal(api.call('ready'),undefined);
  assert.equal(api.supports('LocationManager.getLocation'),false);
  assert.equal(api.supports('__proto__.constructor'),false);
  assert.throws(()=>api.call('__proto__.constructor'),UnsupportedTelegramCapability);
  app.version='10.3';app.isVersionAtLeast=()=>false;assert.equal(api.supports('ready'),false);
});

test('native callback denial/cancel/errors remain actual results with no automatic retry', () => {
  let count=0;const app={platform:'android',version:'10.3',LocationManager:{getLocation(callback){count++;callback(null);return this;}},
    showPopup(params, callback){callback(undefined);},requestWriteAccess(callback){callback(false);}};
  const api=new TelegramNativeAPI(app),results=[];
  assert.equal(api.call('LocationManager.getLocation',value=>results.push(value)),app.LocationManager);
  api.call('showPopup',{},value=>results.push(value));api.call('requestWriteAccess',value=>results.push(value));
  assert.deepEqual(results,[null,undefined,false]);assert.equal(count,1);
  app.LocationManager.getLocation=()=>{count++;throw Error('native failure');};
  assert.throws(()=>api.call('LocationManager.getLocation',()=>{}),/native failure/);assert.equal(count,2);
});

test('all native events keep distinct listener ownership and clean disposal', () => {
  const app=new FakeApp();app.platform='android';app.version='10.3';const api=new TelegramNativeAPI(app);
  const listener=()=>{};const cleanups=TELEGRAM_NATIVE_EVENTS.map(event=>api.listen(event,listener));
  assert.equal(app.count(),44);
  let seen=0;const callback=()=>seen++;const first=api.listen('themeChanged',callback),second=api.listen('themeChanged',callback);
  first();first();app.emit('themeChanged');assert.equal(seen,1);second();
  cleanups[0]();api.dispose();api.dispose();assert.equal(app.count(),0);
  assert.equal(api.supports('ready'),false);assert.throws(()=>api.listen('themeChanged',callback),UnsupportedTelegramCapability);
});

test('native partial registration and failed cleanup are retryable; late callbacks are suppressed', () => {
  const app=new FakeApp();app.platform='android';app.version='10.3';const api=new TelegramNativeAPI(app);
  const originalOn=app.onEvent,originalOff=app.offEvent;
  app.onEvent=function(name,fn){originalOn.call(this,name,fn);throw Error('register failed');};
  assert.throws(()=>api.listen('themeChanged',()=>{}),/register failed/);assert.equal(app.count(),0);
  app.onEvent=originalOn;let seen=0,failOff=false;
  app.offEvent=function(name,fn){if(failOff)throw Error('cleanup failed');originalOff.call(this,name,fn);};
  const unsubscribe=api.listen('themeChanged',()=>seen++);
  failOff=true;assert.throws(()=>unsubscribe(),/cleanup failed/);
  app.emit('themeChanged');assert.equal(seen,0);
  assert.throws(()=>api.dispose(),/cleanup failed/);failOff=false;api.dispose();assert.equal(app.count(),0);
});

test('native future/unknown events and old client events are rejected', () => {
  const app=new FakeApp();app.platform='android';app.version='6.1';const api=new TelegramNativeAPI(app);
  assert.throws(()=>api.listen('userTyping',()=>{}),TypeError);
  assert.throws(()=>api.listen('locationRequested',()=>{}),UnsupportedTelegramCapability);
  const stop=api.listen('themeChanged',()=>{});stop();assert.equal(app.count(),0);
});

class MemoryStorage {
  values = new Map(); getItem(key) { return this.values.get(key) ?? null; }
  setItem(key,value) { this.values.set(key,value); } removeItem(key) { this.values.delete(key); }
}
test('selection draft is scoped, expires, and never copies arbitrary fields', () => {
  const storage = new MemoryStorage(); let now = 100;
  const one = new SelectionDraftStore(() => storage,{namespace:'booking',scope:'server:a',ttlMs:200,now:()=>now});
  assert.equal(one.write({serviceId:'cut',slotId:'slot',name:'test',initData:'secret',operationId:'unknown-op'}),true);
  const saved = storage.getItem(one.key); assert.equal(saved.includes('secret'),false); assert.equal(saved.includes('unknown-op'),false);
  assert.deepEqual(one.read(),{status:'restored',value:{serviceId:'cut',slotId:'slot'}});
  const two = new SelectionDraftStore(() => storage,{namespace:'booking',scope:'server:b',ttlMs:200});
  assert.deepEqual(two.read(),{status:'missing'});
  now = 300; assert.deepEqual(one.read(),{status:'expired'}); assert.equal(storage.getItem(one.key),null);
});
test('corrupt/schema/scope/quota/blocked storage are observable without crashing UI', () => {
  const storage = new MemoryStorage(); const draft = new SelectionDraftStore(()=>storage,{namespace:'b',scope:'a',ttlMs:100,now:()=>0});
  for (const raw of ['invalid',JSON.stringify({schema:2,scope:'a',expires:100}),JSON.stringify({schema:1,scope:'foreign',expires:100})]) {
    storage.setItem(draft.key,raw); assert.deepEqual(draft.read(),{status:'corrupt'});
  }
  const blocked = new SelectionDraftStore(()=>{throw new Error('disabled');},{namespace:'b',scope:'a',ttlMs:100});
  assert.deepEqual(blocked.read(),{status:'unavailable'}); assert.equal(blocked.write({serviceId:null,slotId:null}),false); assert.equal(blocked.clear(),false);
  storage.setItem = () => {throw new Error('quota');}; assert.equal(draft.write({serviceId:'cut',slotId:null}),false);
});

test('caller config mutation cannot move draft into another account or change its TTL', () => {
  const storage=new MemoryStorage();let now=100;
  const config={namespace:'booking',scope:'account:a',ttlMs:1000,now:()=>now};
  const original=new SelectionDraftStore(()=>storage,config);original.write({serviceId:'consult',slotId:'one'});
  config.scope='account:b';config.ttlMs=1;original.write({serviceId:'consult',slotId:'two'});now=500;
  const accountA=new SelectionDraftStore(()=>storage,{namespace:'booking',scope:'account:a',ttlMs:1000,now:()=>now});
  const accountB=new SelectionDraftStore(()=>storage,config);
  assert.deepEqual(accountA.read(),{status:'restored',value:{serviceId:'consult',slotId:'two'}});
  assert.deepEqual(accountB.read(),{status:'missing'});
});

async function serverFixture(run) {
  let writes = 0;
  const server = http.createServer((req,res) => {
    if (req.url === '/slow') { setTimeout(()=>{if(!res.destroyed){res.writeHead(200,{'Content-Type':'application/json'});res.end('{"id":1}');}},100); return; }
    if (req.url === '/write-lost') { writes++; req.socket.destroy(); return; }
    if (req.url === '/unauthorized') {res.writeHead(401);res.end();return;}
    if (req.url === '/invalid') {res.writeHead(200);res.end('not-json');return;}
    if (req.url === '/wrong-shape') {res.writeHead(200);res.end('{"id":"one"}');return;}
    if (req.url === '/empty' || req.url === '/reset') {res.writeHead(req.url==='/empty'?204:205,{'Content-Length':'0'});res.end();return;}
    if (req.url === '/truncated') {res.writeHead(200,{'Content-Type':'application/json','Content-Length':'100'});res.write('{"id":');setTimeout(()=>res.destroy(),10);return;}
    res.writeHead(200,{'Content-Type':'application/json'});res.end(req.method==='HEAD'?'':JSON.stringify({id:1,csrf:req.headers['x-csrf-token']??null}));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}/`;
  try { await run(base,()=>writes); } finally {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
}
function order(value) {if(!value || typeof value!=='object' || !Number.isSafeInteger(value.id))throw new Error('schema');return value;}
test('real HTTP JSON decode and consumer-supplied CSRF header', async () => serverFixture(async base => {
  const client = new ApiClient({baseUrl:base,headers:()=>({'X-CSRF-Token':'synthetic'})});
  assert.deepEqual(await client.request('/ok',order),{id:1,csrf:'synthetic'});
  assert.equal(await client.request('/ok',v=>v,{method:'HEAD'}),null);
}));

test('successful 204/205 response passes null to runtime decoder', async () => serverFixture(async base => {
  const client=new ApiClient({baseUrl:base});
  for(const path of ['/empty','/reset']) assert.equal(await client.request(path,value=>{assert.equal(value,null);return 'done';},{method:'DELETE'}),'done');
}));

test('broken response body is a network failure, not malformed JSON', async () => serverFixture(async base => {
  const client=new ApiClient({baseUrl:base});
  await assert.rejects(client.request('/truncated',order,{method:'POST'}),error=>error.kind==='network'&&error.outcome==='unknown');
}));
test('401 and invalid JSON/schema are classified; HTTP body secrets not exposed', async () => serverFixture(async base => {
  const client = new ApiClient({baseUrl:base});
  await assert.rejects(client.request('/unauthorized',order),e=>e instanceof ApiError&&e.kind==='http'&&e.status===401);
  for (const path of ['/invalid','/wrong-shape']) await assert.rejects(client.request(path,order),e=>e.kind==='invalid-response');
}));
test('lost write response has unknown outcome and no automatic second write', async () => serverFixture(async (base,writes) => {
  const client = new ApiClient({baseUrl:base});
  await assert.rejects(client.request('/write-lost',order,{method:'POST',body:{operationId:'one'}}),e=>e.kind==='network'&&e.outcome==='unknown');
  assert.equal(writes(),1);
}));
test('timeout and caller cancellation release a real HTTP request', async () => serverFixture(async base => {
  const client = new ApiClient({baseUrl:base});
  await assert.rejects(client.request('/slow',order,{timeoutMs:20}),e=>e.kind==='timeout');
  const controller = new AbortController(); controller.abort();
  await assert.rejects(client.request('/slow',order,{signal:controller.signal}),e=>e.kind==='aborted');
}));
test('cross-origin destination cannot receive configured headers', async () => {
  let calls = 0; const client = new ApiClient({baseUrl:'https://example.test/api/',headers:()=>({Authorization:'test-only'}),fetch:async()=>{calls++;}});
  for (const path of ['https://outside.test/x','//outside.test/x']) await assert.rejects(client.request(path,order));
  assert.equal(calls,0);
});

test('actual HTTP redirect cannot forward CSRF headers to another origin', async () => {
  let received=0;
  const destination=http.createServer((req,res)=>{received++;res.end('{}');});
  await new Promise(resolve=>destination.listen(0,'127.0.0.1',resolve));
  const redirect=http.createServer((req,res)=>{res.writeHead(302,{Location:`http://127.0.0.1:${destination.address().port}/other`});res.end();});
  await new Promise(resolve=>redirect.listen(0,'127.0.0.1',resolve));
  try{
    const api=new ApiClient({baseUrl:`http://127.0.0.1:${redirect.address().port}`,headers:()=>({'X-CSRF-Token':'synthetic'})});
    await assert.rejects(api.request('/redirect',order),e=>e.kind==='network');
    assert.equal(received,0);
  }finally{
    destination.closeAllConnections();redirect.closeAllConnections();
    await Promise.all([new Promise(resolve=>destination.close(resolve)),new Promise(resolve=>redirect.close(resolve))]);
  }
});

test('a failing bridge listener does not stop the others; failures surface after everyone is notified', () => {
  const app=new FakeApp();app.platform='ios';
  const bridge=new TelegramBridge(app,new EventTarget()),seen=[];
  bridge.subscribe(()=>{});bridge.start();
  let fail=false;
  bridge.subscribe(()=>{if(fail)throw new Error('first listener');});
  bridge.subscribe(snapshot=>seen.push(snapshot.colorScheme));
  fail=true;app.colorScheme='dark';
  assert.throws(()=>app.emit('themeChanged'),/first listener/);
  assert.deepEqual(seen,['light','dark'],'the later listener still received the update');
  bridge.subscribe(snapshot=>{if(fail&&snapshot.colorScheme==='light')throw new TypeError('third listener');});
  app.colorScheme='light';
  assert.throws(()=>app.emit('themeChanged'),error=>error instanceof AggregateError&&error.errors.length===2);
  assert.deepEqual(seen,['light','dark','light']);
  fail=false;app.colorScheme='dark';app.emit('themeChanged');assert.equal(seen.at(-1),'dark');
  bridge.dispose();
});

test('bridge and native API agree on running inside Telegram', () => {
  for (const platform of [undefined,'','unknown',42,null,'ios','android','tdesktop','weba']) {
    const app={platform,version:'10.3',ready(){},onEvent(){},offEvent(){},isVersionAtLeast:()=>true};
    const inside=new TelegramBridge(app,undefined).snapshot().insideTelegram;
    assert.equal(new TelegramNativeAPI(app).supports('ready'),inside,`platform ${String(platform)}`);
    assert.equal(inside,typeof platform==='string'&&platform!==''&&platform!=='unknown');
  }
  for (const app of [undefined,null,'telegram',7]) {
    assert.equal(new TelegramBridge(app,undefined).snapshot().insideTelegram,false);
    assert.equal(new TelegramNativeAPI(app).supports('ready'),false);
  }
});
