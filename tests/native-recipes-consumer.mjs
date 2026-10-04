/** Run against compiled recipe imports from the installed tarball consumer. */
import assert from 'node:assert/strict';
import {requestNativeLocation,showNativeConfirmation} from './compiled/native-recipes.js';

const appBase={platform:'android',version:'10.3'};
const seen=[];requestNativeLocation(undefined,result=>seen.push(result));assert.deepEqual(seen.pop(),{status:'unavailable'});
for(const value of [null,{latitude:55.7,longitude:37.6},{latitude:999,longitude:37.6}]){
  let calls=0;
  const app={...appBase,LocationManager:{init(cb){cb();cb();},getLocation(cb){calls++;cb(value);cb(value);}}};
  const result=[];requestNativeLocation(app,item=>result.push(item));assert.equal(calls,1);assert.equal(result.length,1);
  assert.equal(result[0].status,value===null?'denied':value.latitude===999?'error':'accepted');
}
let lateInit,lateLocation;
const app={...appBase,LocationManager:{init(cb){lateInit=cb;},getLocation(cb){lateLocation=cb;}}};
let count=0;const cancelBefore=requestNativeLocation(app,()=>count++);cancelBefore();lateInit();assert.equal(lateLocation,undefined);
const cancelAfter=requestNativeLocation(app,()=>count++);lateInit();cancelAfter();lateLocation({latitude:1,longitude:2});assert.equal(count,0);
const broken={...appBase,LocationManager:{init(cb){cb();},getLocation(){throw Error('fixture');}}};
const brokenResult=[];requestNativeLocation(broken,result=>brokenResult.push(result));assert.deepEqual(brokenResult,[{status:'error'}]);
for(const [nativeValue,expected] of [['confirm','confirmed'],['cancel','cancelled'],[undefined,'cancelled']]){
  const result=[];showNativeConfirmation({...appBase,showPopup(params,cb){cb(nativeValue);cb('confirm');}},value=>result.push(value));
  assert.equal(result.length,1);assert.equal(result[0].status,expected);
}
const unavailable=[];showNativeConfirmation(undefined,result=>unavailable.push(result));assert.deepEqual(unavailable,[{status:'unavailable'}]);
const popupError=[];showNativeConfirmation({...appBase,showPopup(){throw Error('fixture');}},result=>popupError.push(result));assert.deepEqual(popupError,[{status:'error'}]);
let latePopup;const disposePopup=showNativeConfirmation({...appBase,showPopup(params,cb){latePopup=cb;}},()=>count++);
disposePopup();latePopup('confirm');assert.equal(count,0);
console.log(JSON.stringify({passed:true,network:false,checks:['location_unavailable_denied_invalid_success','init_once','settle_once',
  'late_init_location_suppressed','native_error','popup_confirm_cancel_unavailable_error','late_popup_suppressed']}));
