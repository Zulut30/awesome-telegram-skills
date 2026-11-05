/** Launch parameters are bounded navigation hints, never identity, price, order proof or permissions. */
export type ShopScreen='catalog'|'orders';
export interface ShopLaunch {readonly screen:ShopScreen;readonly valid:boolean;readonly source:'initData'|'query'|'none'}
export function shopLaunch(initData:string,search:string):ShopLaunch {
  if(initData.length>16384||search.length>4096)return {screen:'catalog',valid:false,source:'none'};
  const signed=new URLSearchParams(initData).getAll('start_param'),query=new URLSearchParams(search).getAll('tgWebAppStartParam');
  if(signed.length>1||query.length>1)return {screen:'catalog',valid:false,source:'none'};
  if(!signed.length&&!query.length)return {screen:'catalog',valid:true,source:'none'};
  const value=signed[0]??query[0]??'';
  if((signed.length&&query.length&&signed[0]!==query[0])||!['catalog','orders'].includes(value))return {screen:'catalog',valid:false,source:'none'};
  return {screen:value as ShopScreen,valid:true,source:signed.length?'initData':'query'};
}
