import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {realpathSync,readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {ApiClient} from '@awesome-telegram/patterns';
const packageDirectory=realpathSync(new URL('./node_modules/@awesome-telegram/patterns/',import.meta.url));
const origin=realpathSync(fileURLToPath(import.meta.resolve('@awesome-telegram/patterns')));
assert.ok(origin.startsWith(packageDirectory+path.sep));
const version=JSON.parse(readFileSync(path.join(packageDirectory,'package.json'),'utf8')).version;
const [mode,out]=process.argv.slice(2);let calls=0;
const transport=async()=>{calls++;return new Response('{}',{headers:{'content-type':'application/json'}});};
const client=new ApiClient({baseUrl:'https://api.example.test/',fetch:transport});
let timeoutRejected=false;
try{await client.request('orders',v=>v,{timeoutMs:2147483648});}catch{timeoutRejected=true;}
assert.equal(timeoutRejected,mode==='after');assert.equal(calls,mode==='after'?0:1);calls=0;
let bodyRejected=false;
try{await client.request('orders',v=>v,{method:'POST',body:()=> 'not JSON'});}catch{bodyRejected=true;}
assert.equal(bodyRejected,mode==='after');assert.equal(calls,mode==='after'?0:1);calls=0;
const badHeaders=new ApiClient({baseUrl:'https://api.example.test/',fetch:transport,headers:()=>{throw Error('SYNTHETIC_PRIVATE_HEADERS');}});
let headerFailure;
try{await badHeaders.request('orders',v=>v,{method:'POST',body:{id:'original'}});}catch(error){headerFailure=error;}
assert.ok(headerFailure);assert.equal(calls,0);
assert.equal(headerFailure.message.includes('SYNTHETIC_PRIVATE_HEADERS'),mode==='before');
if(mode==='after')assert.equal(headerFailure.outcome,'rejected');
// Portable safe configuration still executes one request, without provider side effects.
await client.request('orders',v=>v,{timeoutMs:1000,method:'POST',body:{id:'original',tags:['one']}});assert.equal(calls,1);
const report={passed:true,mode,version,origin,timeoutAboveInt32Rejected:timeoutRejected,nonJSONFunctionBodyRejected:bodyRejected,headerFailureRedacted:mode==='after',portableValidRequestCalls:calls,scope:'Public installed ApiClient; fake transport only. New validation rejects before transport. No blind retries.'};
await writeFile(out,JSON.stringify(report,null,2)+'\n','utf8');console.log(JSON.stringify(report));
