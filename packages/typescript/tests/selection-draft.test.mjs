import test from 'node:test';
import assert from 'node:assert/strict';
import {SelectionDraftStore,PendingOperationStore,ValidationFailure} from '../dist/index.js';

class MemoryStorage {
  data=new Map();failRead=false;failWrite=false;failRemove=false;
  getItem(key){if(this.failRead)throw Error('private read');return this.data.get(key)??null;}
  setItem(key,value){if(this.failWrite)throw Error('private quota');this.data.set(key,value);}
  removeItem(key){if(this.failRemove)throw Error('private removal');this.data.delete(key);}
}
const first='123e4567-e89b-42d3-a456-426614174000',second='123e4567-e89b-42d3-a456-426614174001';
const settings={namespace:'booking',scope:'100:42',ttlMs:100,now:()=>0};
function legacy(storage,options=settings,value={service:'cut',slot:'10'},expires=50,scope=options.scope){
  const key=new SelectionDraftStore(()=>storage,options).key;
  storage.setItem(key,JSON.stringify({schema:1,scope,expires,value}));return key;
}
const migration=value=>({serviceId:value.service,slotId:value.slot,token:'PRIVATE_TOKEN'});

test('default draft v1 API and key remain compatible and allowlist persisted fields',()=>{
  const storage=new MemoryStorage(),store=new SelectionDraftStore(()=>storage,settings);
  assert.equal(store.key,'tg-selection:booking:100%3A42:v1');
  assert.equal(store.write({serviceId:'cut',slotId:null,token:'PRIVATE_TOKEN',operation:first}),true);
  assert.deepEqual(store.read(),{status:'restored',value:{serviceId:'cut',slotId:null}});
  assert.equal(storage.getItem(store.key).includes('PRIVATE_TOKEN'),false);
  assert.equal(storage.getItem(store.key).includes(first),false);
});

test('explicit draft migration keeps scope original expiry and strips decoder extra fields',()=>{
  const storage=new MemoryStorage();const oldKey=legacy(storage);const decoders={1:migration};
  const options={...settings,schemaVersion:2,migrateFrom:decoders,now:()=>20};
  const store=new SelectionDraftStore(()=>storage,options);
  options.scope='100:77';decoders[1]=()=>{throw Error('mutated config');};
  assert.deepEqual(store.read(),{status:'restored',value:{serviceId:'cut',slotId:'10'}});
  assert.equal(storage.getItem(oldKey),null);
  const saved=JSON.parse(storage.getItem(store.key));
  assert.deepEqual(saved,{schema:2,scope:'100:42',expires:50,value:{serviceId:'cut',slotId:'10'}});
  assert.equal(JSON.stringify(saved).includes('PRIVATE_TOKEN'),false);
});

test('migration can shorten but never extend draft lifetime',()=>{
  const storage=new MemoryStorage();legacy(storage,settings,undefined,9000);
  const store=new SelectionDraftStore(()=>storage,{...settings,schemaVersion:2,migrateFrom:{1:migration},now:()=>20});
  assert.equal(store.read().status,'restored');assert.equal(JSON.parse(storage.getItem(store.key)).expires,120);
});

test('explicit draft clear removes known legacy copies so they cannot reappear after reload',()=>{
  const storage=new MemoryStorage(),oldKey=legacy(storage);
  const store=new SelectionDraftStore(()=>storage,{...settings,schemaVersion:2,migrateFrom:{1:migration}});
  storage.failRemove=true;assert.equal(store.read().status,'restored');assert.notEqual(storage.getItem(oldKey),null);
  assert.equal(store.clear(),false);
  storage.failRemove=false;assert.equal(store.clear(),true);assert.equal(store.read().status,'missing');
  assert.equal(storage.getItem(oldKey),null);
});

test('failed migration write preserves legacy until a durable current copy succeeds',()=>{
  const storage=new MemoryStorage(),oldKey=legacy(storage),raw=storage.getItem(oldKey);
  const store=new SelectionDraftStore(()=>storage,{...settings,schemaVersion:2,migrateFrom:{1:migration}});
  storage.failWrite=true;assert.deepEqual(store.read(),{status:'unavailable'});
  assert.equal(storage.getItem(oldKey),raw);assert.equal(storage.getItem(store.key),null);
  storage.failWrite=false;assert.equal(store.read().status,'restored');assert.equal(storage.getItem(oldKey),null);
});

test('migration decoder failure and wrong account are preserved and never restored',()=>{
  for(const label of ['decoder','account','invalid_value']){
    const storage=new MemoryStorage(),oldKey=legacy(storage,settings,undefined,50,label==='account'?'100:77':'100:42'),raw=storage.getItem(oldKey);
    const decoder=label==='decoder'?()=>{throw Error('PRIVATE_TOKEN');}:label==='invalid_value'?()=>({serviceId:7,slotId:null}):migration;
    const store=new SelectionDraftStore(()=>storage,{...settings,schemaVersion:2,migrateFrom:{1:decoder}});
    assert.deepEqual(store.read(),{status:'corrupt'});assert.equal(storage.getItem(oldKey),raw);assert.equal(storage.getItem(store.key),null);
  }
});

test('expired legacy draft is never migrated and unknown legacy versions are not discovered',()=>{
  const storage=new MemoryStorage(),oldKey=legacy(storage);
  const current=new SelectionDraftStore(()=>storage,{...settings,schemaVersion:2,migrateFrom:{1:migration},now:()=>50});
  assert.deepEqual(current.read(),{status:'expired'});assert.equal(storage.getItem(oldKey),null);
  legacy(storage);const withoutDecoder=new SelectionDraftStore(()=>storage,{...settings,schemaVersion:3});
  assert.deepEqual(withoutDecoder.read(),{status:'missing'});assert.notEqual(storage.getItem(oldKey),null);
});

test('draft clock and storage failures never return restored data or destroy an existing draft',()=>{
  const storage=new MemoryStorage(),good=new SelectionDraftStore(()=>storage,settings);good.write({serviceId:'cut',slotId:null});
  const raw=storage.getItem(good.key),badClock=new SelectionDraftStore(()=>storage,{...settings,now:()=>NaN});
  assert.equal(badClock.write({serviceId:'cut',slotId:null}),false);assert.deepEqual(badClock.read(),{status:'unavailable'});
  assert.equal(storage.getItem(good.key),raw);
  storage.failRead=true;assert.deepEqual(good.read(),{status:'unavailable'});storage.failRead=false;
  storage.failRemove=true;assert.equal(good.clear(),false);assert.equal(storage.getItem(good.key),raw);
});

test('invalid schema versions and ambiguous migration maps are rejected',()=>{
  const storage=new MemoryStorage();
  for(const schemaVersion of [0,-1,1.5,NaN,true])assert.throws(()=>new SelectionDraftStore(()=>storage,{...settings,schemaVersion}),ValidationFailure);
  for(const migrateFrom of [{2:migration},{3:migration},{'01':migration},{1:7},7,null,[]])assert.throws(()=>new SelectionDraftStore(()=>storage,{...settings,schemaVersion:2,migrateFrom}),ValidationFailure);
});

test('pending pointer survives expired cleared drafts and reload without creating a new operation',()=>{
  const storage=new MemoryStorage();let now=0;
  const draft=new SelectionDraftStore(()=>storage,{...settings,now:()=>now});draft.write({serviceId:'cut',slotId:'10'});
  const pointer=new PendingOperationStore(()=>storage,{namespace:'booking',scope:'100:42',now:()=>now});
  assert.equal(pointer.reserve(first).status,'reserved');assert.equal(pointer.markUnknown(first),true);
  now=100;assert.deepEqual(draft.read(),{status:'expired'});draft.clear();now=10**12;
  const reloaded=new PendingOperationStore(()=>storage,{namespace:'booking',scope:'100:42',now:()=>now});
  assert.deepEqual(reloaded.reserve(second),{status:'existing',value:{operation:first,createdAt:0,state:'unknown'}});
  assert.equal(new PendingOperationStore(()=>storage,{namespace:'booking',scope:'100:77'}).read().status,'missing');
});

test('pending markUnknown and completion require the exact operation ID and durable storage success',()=>{
  const storage=new MemoryStorage(),store=new PendingOperationStore(()=>storage,{namespace:'booking',scope:'100:42',now:()=>0});
  store.reserve(first);assert.equal(store.markUnknown(second),false);assert.equal(store.complete(second),false);
  storage.failWrite=true;assert.equal(store.markUnknown(first),false);assert.equal(store.read().value.state,'pending');
  storage.failWrite=false;assert.equal(store.markUnknown(first),true);assert.equal(store.markUnknown(first),true);
  storage.failRemove=true;assert.equal(store.complete(first),false);assert.equal(store.read().value.operation,first);
  storage.failRemove=false;assert.equal(store.complete(first),true);assert.equal(store.read().status,'missing');
  assert.equal(store.reserve(second).status,'reserved');
});

test('corrupt unsupported and unavailable pending records block dispatch without deleting the pointer',()=>{
  for(const label of ['corrupt','unsupported','scope']){
    const storage=new MemoryStorage(),store=new PendingOperationStore(()=>storage,{namespace:'booking',scope:'100:42'});
    const raw=label==='corrupt'?'{':JSON.stringify({schema:label==='unsupported'?99:1,scope:label==='scope'?'100:77':'100:42',operation:first,createdAt:0,state:'unknown'});
    storage.setItem(store.key,raw);
    const result=store.reserve(second);assert.equal(result.status,'blocked');assert.equal(store.complete(first),false);assert.equal(store.markUnknown(first),false);
    assert.equal(storage.getItem(store.key),raw);
  }
  const storage=new MemoryStorage(),store=new PendingOperationStore(()=>storage,{namespace:'booking',scope:'100:42'});
  storage.failRead=true;assert.deepEqual(store.reserve(first),{status:'blocked',reason:'unavailable'});
  storage.failRead=false;storage.failWrite=true;assert.deepEqual(store.reserve(first),{status:'blocked',reason:'unavailable'});
  storage.failWrite=false;assert.equal(store.read().status,'missing');
});

test('pending pointers allow only UUID and minimal scoped metadata and ignore options mutation',()=>{
  const storage=new MemoryStorage(),options={namespace:'booking',scope:'100:42',now:()=>0};
  const store=new PendingOperationStore(()=>storage,options);options.scope='100:77';options.namespace='other';
  for(const value of ['',null,{operation:first,token:'PRIVATE_TOKEN'},'../operation'])assert.throws(()=>store.reserve(value),ValidationFailure);
  const result=store.reserve(first);assert.deepEqual(Object.keys(result.value).sort(),['createdAt','operation','state']);
  assert.throws(()=>{result.value.operation=second;},TypeError);
  assert.equal(JSON.parse(storage.getItem(store.key)).scope,'100:42');
  assert.equal(store.key.startsWith('tg-pending:booking:'),true);
});
