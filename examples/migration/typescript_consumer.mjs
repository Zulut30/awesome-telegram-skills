import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {realpathSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {ApiClient,ApiError,SelectionDraftStore,TelegramBridge,TelegramNativeAPI} from '@awesome-telegram/patterns';
const packageDirectory=realpathSync(new URL('./node_modules/@awesome-telegram/patterns/',import.meta.url));
const origin=realpathSync(fileURLToPath(import.meta.resolve('@awesome-telegram/patterns')));
assert.ok(origin.startsWith(packageDirectory+path.sep));
const version=JSON.parse(readFileSync(path.join(packageDirectory,'package.json'),'utf8')).version;

const [mode,directory]=process.argv.slice(2);
const saved=path.join(directory,'browser-storage.json');
const values=mode==='before'?new Map():new Map(JSON.parse(await readFile(saved,'utf8')));
const storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
const observations=[];
const options={namespace:'booking',scope:'bot:100:user:42',ttlMs:5000,now:()=>1000};
const selection=new SelectionDraftStore(()=>storage,options);
if(mode==='before'){
  assert.equal(selection.write({serviceId:'server-service',slotId:'server-slot',botToken:'DROP',paid:true}),true);
  const raw=values.get(selection.key);assert.ok(raw&&!raw.includes('DROP')&&!raw.includes('paid'));
  await writeFile(saved,JSON.stringify([...values]),'utf8');
}else{
  assert.deepEqual(selection.read(),{status:'restored',value:{serviceId:'server-service',slotId:'server-slot'}});
  assert.equal(new SelectionDraftStore(()=>storage,{...options,scope:'bot:100:user:99'}).read().status,'missing');
  const migrated=new SelectionDraftStore(()=>storage,{...options,schemaVersion:2,migrateFrom:{1:value=>value},now:()=>2000,ttlMs:1000});
  assert.equal(migrated.read().status,'restored');
  assert.equal(values.has(selection.key),false);
  assert.equal(JSON.parse(values.get(migrated.key)).expires,3000); // never extends historical lifetime
  assert.equal(new SelectionDraftStore(()=>storage,{...options,schemaVersion:2,now:()=>3000}).read().status,'expired');
  observations.push('schema1-compatible','explicit-v2-migration-preserves-scope-and-bounds-ttl');
}

const calls=[];
const transport=async(input)=>{calls.push(new URL(String(input)).pathname);return new Response('{}',{status:200,headers:{'content-type':'application/json'}});};
const legacy=new ApiClient({baseUrl:'https://api.example.test/api/v1',fetch:transport});
await legacy.request('/orders',value=>value);
assert.equal(calls.pop(),mode==='before'?'/orders':'/api/v1/orders');
// Stable before/after route configuration: base is explicitly a directory, route is relative.
const adapted=new ApiClient({baseUrl:'https://api.example.test/api/v1/',fetch:transport});
await adapted.request('orders',value=>value);assert.equal(calls.pop(),'/api/v1/orders');
let outside=false;
try{await adapted.request('https://api.example.test/outside',value=>value);}catch{outside=true;}
assert.equal(outside,mode==='after');
assert.equal(calls.length,mode==='before'?1:0);calls.length=0;
observations.push('base-prefix-resolution-changed','directory-base-relative-route-portable');
let writes=0;
const lost=new ApiClient({baseUrl:'https://api.example.test/',fetch:async()=>{writes++;throw Error('SYNTHETIC_PRIVATE_DO_NOT_ECHO');}});
try{await lost.request('orders',value=>value,{method:'POST',body:{operation:'original-request'}});assert.fail('lost reply accepted');}
catch(error){assert.ok(error instanceof ApiError);assert.equal(error.outcome,'unknown');assert.equal(error.kind,'network');assert.equal(error.message.includes('SYNTHETIC_PRIVATE'),false);}
assert.equal(writes,1);observations.push('unknown-write-stays-one-attempt');

const missingPlatform={ready(){},onEvent(){},offEvent(){}};
const outsideBridge=new TelegramBridge(missingPlatform,new EventTarget());
assert.equal(outsideBridge.snapshot().insideTelegram,mode==='before');outsideBridge.dispose();
const listeners=new Map();
const app={platform:'tdesktop',version:'10.3',ready(){},onEvent:(name,fn)=>listeners.set(name,fn),offEvent:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name);}};
const bridge=new TelegramBridge(app,new EventTarget());
assert.equal(bridge.snapshot().insideTelegram,true);
let throwing=false,second=0;
bridge.subscribe(()=>{if(throwing)throw Error('owned listener failure');});
bridge.subscribe(()=>{second++;});bridge.start();
const before=second;throwing=true;
assert.throws(()=>listeners.get('themeChanged')());
assert.equal(second-before,mode==='before'?0:1);
bridge.dispose();assert.equal(listeners.size,0);
observations.push('platform-must-be-observed','listener-error-fanout-changed');

let impacts=0;
const feedback={impactOccurred(style){assert.equal(style,'light');impacts++;return feedback;}};
const native=new TelegramNativeAPI({...app,HapticFeedback:feedback});
assert.equal(native.supports('HapticFeedback.impactOccurred'),true);
native.call('HapticFeedback.impactOccurred','light');assert.equal(impacts,1);native.dispose();
observations.push('valid-native-call-preserved','owned-dispose');
const result={passed:true,mode,version,origin,observations,scope:'Installed public ESM with fake transport/SDK and real persistent storage file; no Telegram client or live request.'};
await writeFile(path.join(directory,'typescript-'+mode+'.json'),JSON.stringify(result,null,2)+'\n','utf8');
console.log(JSON.stringify(result));
