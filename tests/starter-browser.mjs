/** Real browser acceptance of the generated, installed Mini App built by Vite (mini-app/dist).
 * The official SDK script is stubbed; HMR and disposal run in tests/starter-dev-loop.mjs. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile,realpath} from 'node:fs/promises';
import path from 'node:path';
const root=await realpath(path.join(process.argv[2],'dist'));
const SDK='https://telegram.org/js/telegram-web-app.js';
const version=JSON.parse(await readFile('packages/typescript/package.json','utf8')).version;
const output=path.resolve('output',`pattern-library-${version}`,'starter-browser');await mkdir(output,{recursive:true});
const server=createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://localhost');
    const candidate=await realpath(path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname)));
    if(!candidate.startsWith(root+path.sep)){res.writeHead(404);res.end();return;}
    const extension=path.extname(candidate);const type={'.html':'text/html','.css':'text/css','.js':'text/javascript'}[extension];
    if(!type){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':type+'; charset=utf-8'});res.end(await readFile(candidate));
  }catch{res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
let browser,checks=0;const cases=[];
function verify(value,message){assert.ok(value,message);checks++;}
/** Empty body for the official SDK: pages below inject their own window.Telegram (or none) without network. */
async function stubSdk(context){await context.route(SDK+'*',route=>route.fulfill({contentType:'text/javascript',body:''}));}
try{
  browser=await chromium.launch(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH,headless:true}:{channel:'chrome',headless:true});
  for(const [name,width,height] of [['phone',320,568],['tablet',768,1024],['desktop',1440,900]])for(const theme of ['dark','light']){
    const context=await browser.newContext({viewport:{width,height},colorScheme:theme});await stubSdk(context);const page=await context.newPage();const errors=[],outside=[];let sdk=0;
    page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(request.url().startsWith(SDK))sdk++;else if(!request.url().startsWith(base))outside.push(request.url());});
    await page.goto(base);await page.getByRole('heading',{name:'Мой Mini App'}).waitFor();
    const appearance=await page.locator('.tp-shell').evaluate(element=>({theme:element.dataset.theme,scheme:getComputedStyle(element).colorScheme,bg:getComputedStyle(element).backgroundColor}));
    verify(appearance.theme===theme&&appearance.scheme===theme,`${name}/${theme}: actual system appearance`);
    verify(appearance.bg===(theme==='dark'?'rgb(16, 29, 39)':'rgb(241, 245, 250)'),`${name}/${theme}: actual background`);
    await page.getByRole('button',{name:'Проверить форму'}).click();
    verify(await page.getByText('Введите имя.',{exact:true}).isVisible(),`${name}/${theme}: invalid input`);
    const field=page.getByLabel('Ваше имя');verify(await field.evaluate(element=>document.activeElement===element),`${name}/${theme}: focus on invalid field`);
    await field.fill('Анна');await page.getByRole('button',{name:'Проверить форму'}).click();
    verify((await page.getByRole('status').textContent()).includes('Отправка на сервер не подключена'),`${name}/${theme}: truthful local result`);
    verify(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}/${theme}: no horizontal overflow`);
    verify(await page.getByRole('button',{name:'Проверить форму'}).evaluate(element=>element.getBoundingClientRect().height>=44),`${name}/${theme}: touch target`);
    verify(errors.length===0&&outside.length===0&&sdk===1,`${name}/${theme}: official SDK only, no page errors or other external requests`);
    await page.screenshot({path:path.join(output,`${name}-${theme}.png`),fullPage:true});
    const opposite=theme==='dark'?'light':'dark';await page.emulateMedia({colorScheme:opposite});
    await page.waitForFunction(expected=>document.querySelector('.tp-shell').dataset.theme===expected,opposite);
    verify(await field.inputValue()==='Анна',`${name}/${theme}: theme change keeps input`);
    verify((await page.getByRole('status').textContent()).includes('Отправка на сервер не подключена'),`${name}/${theme}: theme change keeps result`);
    cases.push({name,width,height,theme,appearance});await context.close();
  }
  const native=await browser.newContext({colorScheme:'dark'});await stubSdk(native);const nativePage=await native.newPage();
  await nativePage.addInitScript(()=>{
    window.nativeListeners=new Map();
    window.Telegram={WebApp:{platform:'tdesktop',colorScheme:'light',themeParams:{bg_color:'#222233'},
      ready(){},onEvent(name,listener){window.nativeListeners.set(name,listener)},offEvent(name){window.nativeListeners.delete(name)}}};
  });
  await nativePage.goto(base);await nativePage.getByRole('heading',{name:'Мой Mini App'}).waitFor();
  verify(await nativePage.locator('.tp-shell').getAttribute('data-theme')==='light','native Telegram scheme overrides system dark');
  verify(await nativePage.locator('.tp-shell').evaluate(element=>getComputedStyle(element).backgroundColor)==='rgb(34, 34, 51)','native theme color applied');
  await nativePage.evaluate(()=>{window.Telegram.WebApp.colorScheme='dark';window.nativeListeners.get('themeChanged')();});
  verify(await nativePage.locator('.tp-shell').getAttribute('data-theme')==='dark','native theme event updates UI');
  verify(await nativePage.locator('[data-identity]').textContent()==='Откройте Mini App из Telegram: без initData backend не подтверждает пользователя.','no identity claimed without initData');await native.close();
  const outside=await browser.newContext({colorScheme:'dark'});await stubSdk(outside);const outsidePage=await outside.newPage();
  await outsidePage.addInitScript(()=>{window.Telegram={WebApp:{platform:'unknown',colorScheme:'light',themeParams:{bg_color:'#ffffff'},ready(){},onEvent(){},offEvent(){}}};});
  await outsidePage.goto(base);await outsidePage.getByRole('heading',{name:'Мой Mini App'}).waitFor();
  verify(await outsidePage.locator('.tp-shell').getAttribute('data-theme')==='dark','unknown Telegram platform follows system appearance');
  verify(await outsidePage.locator('.tp-shell').evaluate(element=>getComputedStyle(element).backgroundColor)==='rgb(16, 29, 39)','unknown platform does not override system colors');await outside.close();
  const report={passed:true,version,browser:browser.version(),checks,cases,network:false,limits:'Vite production build with a stubbed SDK; backend initData and HMR are in starter-dev-loop; no real Telegram device proof'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
