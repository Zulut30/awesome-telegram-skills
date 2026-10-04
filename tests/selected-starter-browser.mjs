/** Real Chrome checks of all selected modules installed from the supplied tarball. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile,realpath} from 'node:fs/promises';
import path from 'node:path';
const root=await realpath(process.argv[2]);
const version=JSON.parse(await readFile('packages/typescript/package.json','utf8')).version;
const output=path.resolve('output',`pattern-library-${version}`,'selected-starter-browser');
await mkdir(output,{recursive:true});
const server=createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://localhost');
    const file=await realpath(path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname)));
    if(!file.startsWith(root+path.sep))throw new Error('Outside preview');
    const type={'.html':'text/html','.css':'text/css','.js':'text/javascript'}[path.extname(file)];
    if(!type)throw new Error('Not a preview asset');
    res.writeHead(200,{'Content-Type':type+'; charset=utf-8'});res.end(await readFile(file));
  }catch {res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`;
let browser,checks=0;
const cases=[];
function verify(value,message){assert.ok(value,message);checks++;}
try {
  browser=await chromium.launch(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH,headless:true}:{channel:'chrome',headless:true});
  for(const [name,width,height] of [['phone',320,568],['tablet',768,1024],['desktop',1440,900]])for(const theme of ['light','dark']){
    const context=await browser.newContext({viewport:{width,height},colorScheme:theme});
    const page=await context.newPage(),errors=[],external=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',async route=>{
      if(!route.request().url().startsWith(base+'/')){external.push(route.request().url());await route.abort();}
      else await route.continue();
    });
    await page.goto(base);await page.getByRole('heading',{name:'Мой Mini App'}).waitFor();
    verify(await page.locator('.tp-shell').getAttribute('data-theme')===theme,`${name}/${theme}: appearance`);
    verify(await page.locator('[data-component]').count()===3,`${name}/${theme}: all frontend components mounted`);
    await page.getByRole('button',{name:'Отклик Telegram',exact:true}).click();
    verify(await page.getByText('Отклик недоступен; интерфейс работает.',{exact:true}).isVisible(),`${name}/${theme}: native fallback`);
    await page.getByRole('button',{name:'Проверить fixture API',exact:true}).click();
    await page.getByText('Fixture прочитан. Backend auth не подключен.',{exact:true}).waitFor();
    verify(await page.getByText('Fixture прочитан. Backend auth не подключен.',{exact:true}).isVisible(),`${name}/${theme}: fixture decode`);
    await page.getByLabel('Ваше имя').fill('Анна');
    await page.getByRole('button',{name:'Сохранить публичный выбор',exact:true}).click();
    verify(await page.getByText('Сохранен публичный выбор.',{exact:true}).isVisible(),`${name}/${theme}: write draft`);
    const stored=await page.evaluate(()=>Object.values(localStorage).join(''));
    verify(stored.includes('demo-service')&&!stored.includes('Анна'),`${name}/${theme}: only public ID persisted`);
    await page.reload();
    verify(await page.getByText('Восстановлен публичный выбор demo-service.',{exact:true}).isVisible(),`${name}/${theme}: restore draft`);
    await page.evaluate(()=>{const key=Object.keys(localStorage).find(key=>key.startsWith('tg-selection:'));const saved=JSON.parse(localStorage.getItem(key));saved.value.serviceId='unknown';localStorage.setItem(key,JSON.stringify(saved));});
    await page.reload();
    verify(await page.getByText('Черновик не соответствует публичному списку.',{exact:true}).isVisible(),`${name}/${theme}: reject stale ID`);
    await page.getByRole('button',{name:'Сохранить публичный выбор',exact:true}).click();
    await page.getByRole('button',{name:'Очистить выбор',exact:true}).click();
    verify(await page.getByText('Черновик: missing.',{exact:true}).isVisible(),`${name}/${theme}: clear own draft`);
    verify(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}/${theme}: no overflow`);
    verify(await page.locator('[data-component] button').evaluateAll(elements=>elements.every(element=>element.getBoundingClientRect().height>=44)),`${name}/${theme}: touch targets`);
    verify(errors.length===0&&external.length===0,`${name}/${theme}: no page errors or external traffic`);
    await page.screenshot({path:path.join(output,`${name}-${theme}.png`),fullPage:true});
    cases.push({name,width,height,theme});await context.close();
  }
  const native=await browser.newContext(),nativePage=await native.newPage();
  await nativePage.addInitScript(()=>{
    window.hapticCalls=0;window.listeners=new Map();
    const haptic={impactOccurred(style){if(this!==haptic||style!=='light')throw Error('Wrong receiver or style');window.hapticCalls++;}};
    window.Telegram={WebApp:{platform:'android',version:'6.1',colorScheme:'light',themeParams:{},ready(){},
      onEvent(name,listener){window.listeners.set(name,listener)},offEvent(name){window.listeners.delete(name)},HapticFeedback:haptic}};
  });
  await nativePage.goto(base);await nativePage.getByRole('button',{name:'Отклик Telegram',exact:true}).click();
  verify(await nativePage.evaluate(()=>window.hapticCalls===1),'fake native receiver and style');
  await nativePage.evaluate(async()=>{window.detachedButton=document.querySelector('[data-component="mini-app-native-api"] button');const module=await import('./dist/main.js');module.disposeApp();window.detachedButton.click();});
  verify(await nativePage.evaluate(()=>window.hapticCalls===1&&window.listeners.size===0)&&await nativePage.locator('.tp-shell').count()===0,'dispose all module UI, events and detached handlers');
  await native.close();
  const blocked=await browser.newContext(),blockedPage=await blocked.newPage();
  await blockedPage.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Unavailable','SecurityError')}}));
  await blockedPage.goto(base);await blockedPage.getByRole('button',{name:'Сохранить публичный выбор',exact:true}).click();
  verify(await blockedPage.getByText('Storage недоступен; продолжайте без сохранения.',{exact:true}).isVisible(),'storage denial fallback');
  await blockedPage.getByLabel('Ваше имя').fill('Анна');await blockedPage.getByRole('button',{name:'Проверить форму',exact:true}).click();
  verify(await blockedPage.getByText('Поле заполнено. Отправка на сервер не подключена.',{exact:true}).isVisible(),'storage denial preserves base form');
  await blocked.close();
  const report={passed:true,version,browser:browser.version(),checks,cases,externalRequests:0,
    scope:'Installed tarball, selected modules; native SDK is synthetic, fixture transport offline; not real Telegram/backend auth'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
