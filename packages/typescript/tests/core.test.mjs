import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { ApiClient, ApiError, TelegramBridge, SelectionDraftStore, TelegramNativeAPI, UnsupportedTelegramCapability,
         TELEGRAM_NATIVE_METHODS, TELEGRAM_NATIVE_EVENTS } from '../dist/index.js';

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
