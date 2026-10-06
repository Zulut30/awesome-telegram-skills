/** Serve the built Pages project path and exercise real Chrome interactions. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile,stat} from 'node:fs/promises';
import path from 'node:path';

const site=path.resolve(process.argv[2]??'output/docs-preview');
const output=path.resolve(process.argv[3]??'output/playwright/docs-site');
await mkdir(output,{recursive:true});
const manifest=JSON.parse(await readFile(path.join(site,'site-manifest.json'),'utf8'));
const prefix='/awesome-telegram-skills/';
const server=createServer(async(req,res)=>{try{const url=new URL(req.url,'http://127.0.0.1');if(!url.pathname.startsWith(prefix)){res.writeHead(404);res.end();return}let file=path.resolve(site,decodeURIComponent(url.pathname.slice(prefix.length)));if(file!==site&&!file.startsWith(site+path.sep)){res.writeHead(403);res.end();return}if((await stat(file)).isDirectory())file=path.join(file,'index.html');const data=await readFile(file);const type={'.html':'text/html','.css':'text/css','.js':'text/javascript','.json':'application/json','.png':'image/png','.txt':'text/plain'}[path.extname(file)]??'text/plain';res.writeHead(200,{'Content-Type':type+'; charset=utf-8'});res.end(data)}catch{res.writeHead(404);res.end()}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const base=origin+prefix;
let browser,checks=0;const results=[];
function verify(value,label){assert.ok(value,label);checks++}
try{
  browser=await chromium.launch(process.env.DOCS_BROWSER==='chromium'?{headless:true}:process.env.CHROME_PATH?{headless:true,executablePath:process.env.CHROME_PATH}:{channel:'chrome',headless:true});
  for(const [name,width,height]of [['phone',320,720],['phone-large',390,844],['tablet',768,1024],['desktop',1440,900]])for(const theme of ['light','dark']){
    const context=await browser.newContext({viewport:{width,height},colorScheme:theme});const page=await context.newPage();const errors=[],missing=[],outside=[];
    page.on('pageerror',error=>errors.push(error.message));page.on('response',response=>{if(response.status()>=400)missing.push(response.url())});page.on('request',request=>{if(!request.url().startsWith(origin))outside.push(request.url())});
    await page.goto(base);await page.getByRole('heading',{name:'От идеи до работающего Telegram-проекта.'}).waitFor();
    verify(await page.locator('html').getAttribute('data-theme')===theme,`${name}/${theme}: OS theme`);
    verify(await page.locator('html').evaluate(node=>node.scrollWidth<=innerWidth+1),`${name}/${theme}: no horizontal page overflow`);
    await page.getByRole('button',{name:theme==='light'?'Включить темную тему':'Включить светлую тему'}).click();
    verify(await page.locator('html').getAttribute('data-theme')!==theme,`${name}/${theme}: theme switch`);
    if(width<=760){await page.getByRole('button',{name:'Открыть меню'}).click();verify(await page.getByRole('navigation',{name:'Навигация документации'}).isVisible(),`${name}/${theme}: menu visible`);await page.keyboard.press('Escape');verify(await page.getByRole('button',{name:'Открыть меню'}).getAttribute('aria-expanded')==='false',`${name}/${theme}: menu closes`)}
    await page.getByRole('button',{name:'Поиск по документации'}).click();await page.getByRole('searchbox',{name:'Запрос поиска'}).fill('action_menu');
    await page.locator('#search-results a').first().waitFor();
    await page.locator('#search-results a').filter({hasText:'action_menu · telegram_patterns.aiogram'}).first().click();
    verify(page.url().includes('/api/')&&page.url().includes('#telegram-patterns-aiogram-action-menu'),`${name}/${theme}: search reaches exact API`);
    await page.getByRole('searchbox',{name:'Найти API'}).fill('action_menu');
    verify(await page.locator('.api-card:visible').count()===1,`${name}/${theme}: API filters`);
    verify((await page.locator('.api-card:visible pre').textContent()).includes('from telegram_patterns.aiogram import action_menu'),`${name}/${theme}: public import`);
    await page.goto(base+'skills/');await page.getByRole('searchbox',{name:'Найти скилл'}).fill('telegram-mini-app-architecture');
    verify(await page.locator('[data-search-card]:visible').count()===1,`${name}/${theme}: skill filter`);
    await page.getByRole('link',{name:'telegram-mini-app-architecture',exact:true}).click();
    verify((await page.locator('article').textContent()).includes('телефон'),`${name}/${theme}: full skill instructions`);
    verify(await page.locator('.resource-list a').count()>0,`${name}/${theme}: local references discoverable`);
    await page.locator('.resource-list a').first().click();verify(page.url().includes('/references/'),`${name}/${theme}: reference route`);
    verify(await page.locator('html').evaluate(node=>node.scrollWidth<=innerWidth+1),`${name}/${theme}: reference no overflow`);
    await page.goto(base+'for-agents/');verify((await page.locator('article').textContent()).includes('ref.*'),`${name}/${theme}: agent guide distinguishes recipe IDs`);
    verify((await page.locator('article').textContent()).includes('не опубликована'),`${name}/${theme}: local distribution clear`);
    await page.goto(base+'recipes/');await page.getByLabel('Что хотите сделать?').fill('две кнопки');
    await page.getByRole('button',{name:'Две кнопки в ряд',exact:true}).click();
    verify((await page.locator('#code').textContent()).includes('KeyboardLayout([2])'),`${name}/${theme}: gallery example`);
    for(const link of await page.locator('#source-files a').all()){const href=await link.getAttribute('href');const response=await context.request.get(new URL(href,page.url()).href);verify(response.ok(),`${name}/${theme}: gallery source ${href}`)}
    verify(errors.length===0,`${name}/${theme}: no JS errors`);verify(missing.length===0,`${name}/${theme}: no missing resources`);verify(outside.length===0,`${name}/${theme}: no external runtime dependency`);
    await page.goto(base);await page.getByRole('button',{name:theme==='light'?'Включить светлую тему':'Включить темную тему'}).click();await page.screenshot({path:path.join(output,`${name}-${theme}.png`),fullPage:true});
    results.push({name,theme,width,height,errors,missing,passed:true});await context.close();
  }
  const result={passed:true,version:manifest.version,checks,contexts:results.length,results};await writeFile(path.join(output,'report.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve))}
