/** Headless consumer: the same domain and transport used by main.ts run without a DOM or Telegram. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {ShopDomainState} from '../dist/assets/app/domain-state.js';
import {createShopApi} from '../dist/assets/app/shop-api.js';
import {shopLaunch} from '../dist/assets/app/launch.js';
import {ApiError} from '@awesome-telegram/patterns';
const operation='12345678-1234-4123-8123-123456789abc';
const dto={id:'22345678-1234-4123-8123-123456789abc',operation,items:['bot-kit'],total:25,currency:'XTR',status:'awaiting',invoice_state:'none'};
const memory=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};};

test('reload and missing original operation never dispatch; an explicit retry uses the identical saved intent',async()=>{
  assert.equal(typeof document,'undefined');assert.equal(typeof window,'undefined');
  const storage=memory();let writes=0;const bodies=[];
  const reader={operation:async()=>{throw new ApiError('http',404,'read-failed');},create:async(session,body)=>{writes++;bodies.push(body);if(writes===1)throw new ApiError('network',undefined,'unknown');return dto;}};
  const original=new ShopDomainState(()=>storage,reader);original.configureCatalog(['bot-kit'],'v1');original.setSession({token:'first',scope:'100:42'});original.setCart(['bot-kit']);original.setConsent(true);
  assert.equal((await original.submit('v1',operation)).status,'failed');original.dispose();
  const restored=new ShopDomainState(()=>storage,reader);restored.configureCatalog(['bot-kit'],'v1');restored.setSession({token:'renewed',scope:'100:42'});
  assert.equal(restored.snapshot().pending.value.operation,operation);assert.equal((await restored.reconcile()).status,'failed');
  assert.equal(writes,1);assert.equal(restored.snapshot().retryAvailable,true);assert.equal(restored.snapshot().order,null);
  assert.equal((await restored.retrySavedIntent()).status,'ready');assert.equal(writes,2);assert.deepEqual(bodies[1],bodies[0]);
  assert.equal(restored.snapshot().order.operation,operation);assert.equal(restored.snapshot().retryAvailable,false);restored.dispose();
});

test('changed terms and account scope prevent a stale saved-intent retry without discarding its identity',async()=>{
  const storage=memory();let writes=0;
  const reader={operation:async()=>{throw new ApiError('http',404,'read-failed');},create:async()=>{writes++;throw new ApiError('network',undefined,'unknown');}};
  const first=new ShopDomainState(()=>storage,reader);first.configureCatalog(['bot-kit'],'v1');first.setSession({token:'first',scope:'100:42'});first.setCart(['bot-kit']);first.setConsent(true);await first.submit('v1',operation);first.dispose();
  const restored=new ShopDomainState(()=>storage,reader);restored.configureCatalog(['bot-kit'],'v2');restored.setSession({token:'new',scope:'100:42'});await restored.reconcile();
  assert.equal((await restored.retrySavedIntent()).status,'blocked');assert.equal(writes,1);assert.equal(restored.snapshot().pending.value.operation,operation);
  restored.clearSession();assert.equal(restored.snapshot().retryAvailable,false);
  restored.setSession({token:'other',scope:'100:77'});assert.equal(restored.snapshot().pending.status,'missing');assert.equal((await restored.retrySavedIntent()).status,'blocked');assert.equal(writes,1);restored.dispose();
});

test('transport captures immutable server credential and checks response contract without Telegram or DOM',async()=>{
  const requests=[];const transport=async(input,init)=>{requests.push({url:String(input),method:init.method,headers:new Headers(init.headers),body:init.body});return new Response(JSON.stringify(dto),{status:200,headers:{'Content-Type':'application/json'}});};
  const api=createShopApi('https://shop.invalid',transport);const session=Object.freeze({token:'server-issued',scope:'100:42'});
  const row=await api.reader.create(session,{operation,items:['bot-kit'],terms:'v1'});
  assert.equal(row.operation,operation);assert.equal(requests[0].headers.get('Authorization'),'Bearer server-issued');
  assert.deepEqual(JSON.parse(requests[0].body),{operation,items:['bot-kit'],terms:'v1'});assert.equal(requests[0].method,'POST');
  assert.equal(JSON.parse(requests[0].body).user_id,undefined);assert.equal(JSON.parse(requests[0].body).role,undefined);
});

test('launch hints distinguish signed-field routing and raw query fallback while accepting only known screens',()=>{
  assert.deepEqual(shopLaunch('start_param=orders','?tgWebAppStartParam=orders'),{screen:'orders',valid:true,source:'initData'});
  assert.deepEqual(shopLaunch('','?tgWebAppStartParam=orders'),{screen:'orders',valid:true,source:'query'});
  for(const [raw,search] of [['start_param=orders','?tgWebAppStartParam=catalog'],['start_param=orders&start_param=catalog',''],['','?tgWebAppStartParam=admin'],['start_param=user_77',''],['','?tgWebAppStartParam=orders&tgWebAppStartParam=orders'],['','?tgWebAppStartParam='+('x'.repeat(5000))]])assert.deepEqual(shopLaunch(raw,search),{screen:'catalog',valid:false,source:'none'});
});

test('a server-confirmed refund completes only its original pending pointer and permits a fresh selection',async()=>{
  const storage=memory();let sent=0;
  const domain=new ShopDomainState(()=>storage,{operation:async()=>({...dto,status:'refunded'}),order:async()=>({...dto,status:'refunded'}),create:async()=>{sent++;return dto;}});
  domain.configureCatalog(['bot-kit'],'v1');domain.setSession({token:'server-issued',scope:'100:42'});domain.setCart(['bot-kit']);domain.setConsent(true);
  await domain.submit('v1',operation);assert.equal(domain.snapshot().pending.status,'restored');
  await domain.reconcile();assert.equal(domain.snapshot().order.status,'refunded');assert.equal(domain.snapshot().pending.status,'missing');assert.equal(sent,1);
  domain.newSelection();domain.setCart(['bot-kit']);domain.setConsent(true);assert.equal(domain.snapshot().order,null);assert.equal(sent,1,'selecting again never dispatches a new order automatically');domain.dispose();
});
