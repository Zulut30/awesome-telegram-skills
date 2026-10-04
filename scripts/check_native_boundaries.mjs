/** Copy to installed tarball consumer before running: only presence is gated. */
import assert from 'node:assert/strict';
import {TelegramNativeAPI} from '@awesome-telegram/patterns';

let calls=0;
for(const launch of ['keyboard','inline']) {
  const app={platform:'android',version:'10.3',sendData(){calls++;}};
  const api=new TelegramNativeAPI(app);
  // SDK method presence cannot authenticate or discover the launch context.
  assert.equal(api.supports('sendData'),true);
  if(launch==='keyboard') api.call('sendData','fixture');
  api.dispose();
}
assert.equal(calls,1,'Host launch gate must not send data for inline launch');
const outside=new TelegramNativeAPI({platform:'unknown',version:'10.3',sendData(){calls++;}});
assert.equal(outside.supports('sendData'),false);
console.log(JSON.stringify({passed:true,network:false,native_presence_checks:3,
  keyboard_calls:1,inline_calls:0,limits:'Synthetic SDK/host launch guard, not real client acceptance'}));
