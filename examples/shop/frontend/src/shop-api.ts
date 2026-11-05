/** Contract-aware transport composition. UI and Telegram callbacks do not enter the domain. */
import {ApiClient,type FetchTransport} from '@awesome-telegram/patterns';
import {callApi} from './api-types.js';
import type {ShopOrderReader,ShopSession} from './domain-state.js';

export function createShopApi(baseUrl:string,fetch?:FetchTransport) {
  const transport=fetch?{fetch}:{};
  const publicApi=new ApiClient({baseUrl,...transport});
  const client=(session:Readonly<ShopSession>)=>new ApiClient({baseUrl,...transport,headers:()=>({Authorization:'Bearer '+session.token})});
  const rejectedBeforeEffect=[401,403,409,422];
  const reader:ShopOrderReader={
    operation:(s,operation,signal)=>callApi(client(s),'getOperation',{params:{operation},signal}),
    order:(s,id,signal)=>callApi(client(s),'getOrder',{params:{id},signal}),
    orders:async(s,signal)=>(await callApi(client(s),'listOrders',{signal})).orders,
    content:(s,sku,signal)=>callApi(client(s),'getContent',{params:{sku},signal}),
    create:(s,body)=>callApi(client(s),'createOrder',{body,rejectedBeforeEffect}),
    invoice:(s,id)=>callApi(client(s),'createInvoice',{params:{id},body:{},rejectedBeforeEffect}),
    rotate:s=>callApi(client(s),'rotateSession',{body:{},rejectedBeforeEffect}),
    revoke:s=>callApi(client(s),'revokeSession',{body:{},rejectedBeforeEffect}),
  };
  return {reader,catalog:()=>callApi(publicApi,'getCatalog'),policy:()=>callApi(publicApi,'getPolicy'),session:(initData:string)=>callApi(publicApi,'createSession',{body:{initData}})};
}
