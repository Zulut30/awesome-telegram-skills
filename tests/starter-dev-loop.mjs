/** Development loop of a generated bot-mini-app: Vite dev server with HMR, the starter backend checking signed
 * initData through the Vite proxy, and the same backend serving the production build.
 *
 *   node tests/starter-dev-loop.mjs <project> <python> [label]
 *
 * <project> is a generated starter with installed mini-app/node_modules and a built mini-app/dist; <python> has the
 * starter's dependencies. The official SDK script is replaced by a synthetic window.Telegram.WebApp: this proves the
 * local loop and the server check, not a real Telegram client. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHmac} from 'node:crypto';
import {mkdir,readFile,writeFile,realpath} from 'node:fs/promises';
import {createServer} from 'node:net';
import path from 'node:path';
import {chromium} from 'playwright';

const [projectArgument,python,label='bot-mini-app']=process.argv.slice(2);
if(!projectArgument||!python)throw new Error('Usage: node tests/starter-dev-loop.mjs <project> <python> [label]');
const project=await realpath(projectArgument),mini=path.join(project,'mini-app');
const version=JSON.parse(await readFile('packages/typescript/package.json','utf8')).version;
const output=path.resolve('output',`pattern-library-${version}`,'starter-dev-loop',label);await mkdir(output,{recursive:true});
const token='100:DEV_LOOP_FIXTURE';
let checks=0;const timings={};
function verify(value,message){assert.ok(value,message);checks++;}
async function freePort(){
  const server=createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const {port}=server.address();await new Promise(resolve=>server.close(resolve));return port;
}
function start(name,command,args,options){
  const child=spawn(command,args,{...options,stdio:['ignore','pipe','pipe']});const log=[];
  child.stdout.on('data',chunk=>log.push(String(chunk)));child.stderr.on('data',chunk=>log.push(String(chunk)));
  child.on('exit',code=>log.push(`\n[${name} exited ${code}]\n`));
  return {child,log,name};
}
async function waitFor(url,accept,processes,timeout=60000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    for(const item of processes)if(item.child.exitCode!==null)throw new Error(`${item.name} stopped:\n${item.log.join('')}`);
    try{const response=await fetch(url);if(accept(response.status))return Date.now()-started;}catch{}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw new Error(`Timeout waiting for ${url}`);
}
/** initData signed as Telegram does: HMAC-SHA-256 with the key HMAC-SHA-256("WebAppData", bot token). */
function signedInitData(user){
  const fields={auth_date:String(Math.floor(Date.now()/1000)),query_id:'AAE-dev-loop',user:JSON.stringify(user)};
  const check=Object.keys(fields).sort().map(key=>`${key}=${fields[key]}`).join('\n');
  const secret=createHmac('sha256','WebAppData').update(token).digest();
  return new URLSearchParams({...fields,hash:createHmac('sha256',secret).update(check).digest('hex')}).toString();
}
/** Body served instead of telegram-web-app.js: a synthetic client that counts its live listeners. */
function sdk(initData){
  if(initData===null)return '';
  return `window.devLoopListeners=new Set();window.devLoopHaptics=0;window.Telegram={WebApp:{platform:'tdesktop',version:'9.0',colorScheme:'dark',
    themeParams:{bg_color:'#17212b',text_color:'#f5f5f5'},initData:${JSON.stringify(initData)},ready(){},
    HapticFeedback:{impactOccurred(){window.devLoopHaptics++;}},
    onEvent(name,listener){window.devLoopListeners.add(listener)},offEvent(name,listener){window.devLoopListeners.delete(listener)}}};`;
}

const apiPort=await freePort(),vitePort=await freePort();
const environment={...process.env,BOT_TOKEN:token,MINI_APP_API_PORT:String(apiPort),PYTHONUTF8:'1'};
delete environment.TELEGRAM_TEST_ENVIRONMENT;delete environment.MINI_APP_URL;
const backend=start('backend',python,['mini_app_server.py'],{cwd:project,env:environment});
const vite=start('vite',process.execPath,[path.join(mini,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port',String(vitePort),'--strictPort'],{cwd:mini,env:environment});
const processes=[backend,vite];
const main=path.join(mini,'src/main.ts'),original=await readFile(main,'utf8');
let browser;
try{
  timings.backend_ready_ms=await waitFor(`http://127.0.0.1:${apiPort}/api/me`,status=>status===401,processes);
  timings.vite_ready_ms=await waitFor(`http://127.0.0.1:${vitePort}/`,status=>status===200,processes);
  browser=await chromium.launch(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH,headless:true}:{channel:'chrome',headless:true});
  async function open(base,initData){
    const page=await browser.newPage(),errors=[],external=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',async route=>{
      const url=route.request().url();
      if(url.startsWith('https://telegram.org/js/telegram-web-app.js'))await route.fulfill({contentType:'text/javascript',body:sdk(initData)});
      else if(url.startsWith(base+'/'))await route.continue();
      else{external.push(url);await route.abort();}
    });
    await page.goto(base+'/');await page.getByRole('heading',{name:'Мой Mini App'}).waitFor();
    return {page,errors,external};
  }
  const dev=`http://127.0.0.1:${vitePort}`;
  const user={id:42,first_name:'Анна'};
  const started=Date.now();const {page,errors,external}=await open(dev,signedInitData(user));
  await page.getByText('Backend проверил initData: Анна (id 42).',{exact:true}).waitFor();
  timings.first_verified_open_ms=Date.now()-started;
  verify(true,'signed initData verified by the backend through the Vite proxy');
  verify(await page.locator('.tp-shell').getAttribute('data-theme')==='dark','Telegram theme applied in dev');
  const changed=signedInitData(user).replace(/hash=([0-9a-f])/,(_,digit)=>'hash='+(digit==='0'?'1':'0'));
  const rejected=await open(dev,changed);
  await rejected.page.getByText('Backend отклонил initData: откройте Mini App заново из Telegram.',{exact:true}).waitFor();
  verify(true,'changed initData rejected by the backend');
  const outside=await open(dev,null);
  verify(await outside.page.getByText('Откройте Mini App из Telegram: без initData backend не подтверждает пользователя.',{exact:true}).isVisible(),'outside Telegram no identity is claimed');
  verify(await outside.page.locator('.tp-shell').getAttribute('data-theme')!==null,'outside Telegram the UI still works');
  // Disposal before any edit: a hot update would replace the module instance this import returns.
  const disposable=await open(dev,signedInitData(user));
  // A selected native module must not call the client from a button detached by disposal.
  const nativeButton=disposable.page.locator('[data-component="mini-app-native-api"] button');
  const withNative=await nativeButton.count()===1;
  if(withNative){await nativeButton.click();verify(await disposable.page.evaluate(()=>window.devLoopHaptics)===1,'native module calls the client before disposal');}
  await disposable.page.evaluate(async()=>{window.devLoopDetached=document.querySelector('[data-component="mini-app-native-api"] button');
    const module=await import('/src/main.ts');module.disposeApp();window.devLoopDetached?.click();});
  if(withNative)verify(await disposable.page.evaluate(()=>window.devLoopHaptics)===1,'detached native button no longer calls the client');
  verify(await disposable.page.locator('.tp-shell').count()===0&&await disposable.page.locator('[data-component]').count()===0,'disposeApp removes the shell and every mounted component');
  verify(await disposable.page.evaluate(()=>window.devLoopListeners.size)===0,'disposeApp releases client listeners');
  // Hot update: the edited module replaces the UI without reloading the page or leaking client listeners.
  const listeners=await page.evaluate(()=>window.devLoopListeners.size);
  await page.getByLabel('Ваше имя').fill('Анна');
  await page.evaluate(()=>{window.devLoopMarker='same document';});
  const edited=original.replace("createAppShell(host, 'Мой Mini App')","createAppShell(host, 'Мой Mini App · HMR')");
  verify(edited!==original,'title literal present for the hot update');
  const hmrStarted=Date.now();await writeFile(main,edited,'utf8');
  await page.getByRole('heading',{name:'Мой Mini App · HMR'}).waitFor({timeout:15000});
  timings.hot_update_ms=Date.now()-hmrStarted;
  verify(await page.evaluate(()=>window.devLoopMarker==='same document'),'hot update without a full page reload');
  verify(await page.locator('.tp-shell').count()===1,'old UI removed by import.meta.hot.dispose');
  verify(await page.evaluate(()=>window.devLoopListeners.size)===listeners,'client listeners released and re-added once');
  await page.getByText('Backend проверил initData: Анна (id 42).',{exact:true}).waitFor();
  verify(true,'identity re-verified by the new module');
  await writeFile(main,original,'utf8');await page.getByRole('heading',{name:'Мой Mini App',exact:true}).waitFor({timeout:15000});
  verify(await page.locator('.tp-shell').count()===1,'restored source hot-updates back');
  // Production: the backend serves mini-app/dist and /api from one origin, without Vite.
  const production=await open(`http://127.0.0.1:${apiPort}`,signedInitData(user));
  await production.page.getByText('Backend проверил initData: Анна (id 42).',{exact:true}).waitFor();
  verify(await production.page.evaluate(()=>[...document.scripts].some(script=>script.src.includes('/assets/'))),'built assets served by the backend');
  for(const item of [{page,errors,external},rejected,outside,disposable,production])verify(item.errors.length===0&&item.external.length===0,'no page errors or other external requests');
  const report={passed:true,label,version,browser:browser.version(),checks,timings,vite:'8.3.3',
    scope:'Generated project, installed tarball, real Vite dev server and starter backend; synthetic Telegram client'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}catch(error){
  for(const item of processes)console.error(`--- ${item.name} ---\n${item.log.join('')}`);
  throw error;
}finally{
  await writeFile(main,original,'utf8');
  await browser?.close();
  for(const item of processes)item.child.kill();
}
