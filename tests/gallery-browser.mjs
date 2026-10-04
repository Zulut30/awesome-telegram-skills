/** Real Chrome gallery checks; serves only three known static files on loopback. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=path.resolve('.');
const version=JSON.parse(await readFile(path.join(root,'packages/typescript/package.json'),'utf8')).version;
const output=path.join(root,'output',`pattern-library-${version}`,'gallery-browser');await mkdir(output,{recursive:true});
const resources=new Map();
for(const [file,type] of [['index.html','text/html'],['gallery.js','text/javascript'],['gallery.css','text/css']])resources.set('/'+file,[await readFile(path.join(root,'gallery',file)),type]);
const server=createServer((req,res)=>{
  const resource=resources.get(req.url==='/'?'/index.html':req.url);
  if(!resource){res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':resource[1]+'; charset=utf-8'});res.end(resource[0]);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${server.address().port}`;
let browser,checks=0;const results=[];
function verify(value,message){assert.ok(value,message);checks++;}
try{
  browser=await chromium.launch(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH,headless:true}:{channel:'chrome',headless:true});
  for(const [name,width,height] of [['phone',320,568],['phone-large',390,844],['landscape',844,390],['tablet',768,1024],['wide-tablet',1024,768],['desktop',1440,900],['large-desktop',1920,1080]]){
    for(const theme of ['light','dark']){
      const context=await browser.newContext({viewport:{width,height},colorScheme:theme});const page=await context.newPage();const errors=[],outside=[];
      page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(!request.url().startsWith(base))outside.push(request.url());});
      await page.goto(base);await page.getByRole('heading',{name:'Найти рецепт. Собрать бота.'}).waitFor();
      verify(await page.locator('#recipes .recipe-card').count()===298,`${name}/${theme}: catalog count`);
      await page.getByLabel('Зрелость',{exact:true}).selectOption('experimental');
      verify(await page.locator('#recipes .recipe-card').count()===14,`${name}/${theme}: experimental count`);
      await page.getByLabel('Проверка',{exact:true}).selectOption('mock');
      verify(await page.locator('#recipes .recipe-card').count()===3,`${name}/${theme}: independent evidence filter`);
      await page.getByLabel('Зрелость',{exact:true}).selectOption('reference');
      verify(await page.locator('#recipes .recipe-card').count()===0,`${name}/${theme}: mock does not imply reference or stable`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();
      await page.getByLabel('Зрелость',{exact:true}).selectOption('stable');
      verify(await page.locator('#recipes .recipe-card').count()===0,`${name}/${theme}: no fabricated stable claim`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();
      verify(await page.locator('#recipes .recipe-card').count()===298,`${name}/${theme}: reset clears maturity`);
      await page.getByLabel('Что хотите сделать?').fill('две кнопки');
      await page.getByRole('button',{name:'Две кнопки в ряд',exact:true}).click();
      verify((await page.locator('#preview .keyboard-row').evaluateAll(rows=>rows.map(row=>row.children.length))).join(',')==='2,2',`${name}/${theme}: two rows`);
      await page.getByLabel('Что хотите сделать?').fill('три кнопки');
      await page.getByRole('button',{name:'Три кнопки в ряд',exact:true}).click();
      verify((await page.locator('#preview .keyboard-row').evaluateAll(rows=>rows.map(row=>row.children.length))).join(',')==='3,3',`${name}/${theme}: three rows`);
      const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
        columns:getComputedStyle(document.querySelector('.workspace')).gridTemplateColumns.split(' ').length,
        targetHeights:[...document.querySelectorAll('#preview button')].map(button=>button.getBoundingClientRect().height)}));
      verify(!geometry.overflow,`${name}/${theme}: horizontal overflow`);
      verify(geometry.columns===(width<=720?1:2),`${name}/${theme}: responsive columns`);
      verify(geometry.targetHeights.every(value=>value>=44),`${name}/${theme}: keyboard targets`);
      await page.getByLabel('Что хотите сделать?').fill('цветные');
      verify(await page.locator('#preview button.primary').count()===1&&await page.locator('#preview button.success').count()===1&&await page.locator('#preview button.danger').count()===1,`${name}/${theme}: styles`);
      await page.locator('#preview button.success').click();verify((await page.locator('#preview-status').textContent()).includes('Запрос не отправлен'),`${name}/${theme}: preview no Telegram claim`);
      await page.getByLabel('Что хотите сделать?').fill('NO_MATCH_FIXTURE');verify(await page.locator('#detail').isHidden(),`${name}/${theme}: no stale details`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Проверка',{exact:true}).selectOption('live');
      verify(await page.locator('#recipes .recipe-card').count()===0,`${name}/${theme}: no fabricated live verification`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Раздел',{exact:true}).selectOption('keyboards');
      verify(await page.locator('#recipes .recipe-card').count()===11,`${name}/${theme}: category filter`);
      verify(errors.length===0&&outside.length===0,`${name}/${theme}: page errors/external requests`);
      await page.getByLabel('Что хотите сделать?').fill('цветные');
      await page.screenshot({path:path.join(output,`${name}-${theme}.png`),fullPage:true});results.push({name,width,height,theme,geometry});await context.close();
    }
  }
  const context=await browser.newContext();const page=await context.newPage();await page.goto(base);
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('blocked fixture');}}}));
  await page.getByRole('button',{name:'Копировать',exact:true}).click();verify((await page.locator('#copy-status').textContent()).includes('Код выделен'), 'clipboard failure offers selection');
  verify((await page.evaluate(()=>window.getSelection()?.toString())).includes('inline_keyboard'),'clipboard fallback selected actual code');
  await page.evaluate(()=>{catalog.recipes[0].title='<img src=x onerror="window.PWNED=true">';render();});
  verify(await page.locator('#recipes img').count()===0&&await page.evaluate(()=>window.PWNED===undefined),'untrusted title rendered as text');
  verify(await page.locator('pre').getAttribute('tabindex')==='0','keyboard accessible code block');await context.close();
  const local=await browser.newContext();const offlinePage=await local.newPage();const localErrors=[],localHTTP=[];
  offlinePage.on('pageerror',error=>localErrors.push(error.message));offlinePage.on('request',request=>{if(/^https?:/.test(request.url()))localHTTP.push(request.url());});
  await offlinePage.goto(pathToFileURL(path.join(root,'gallery/index.html')).href);
  await offlinePage.getByLabel('Что хотите сделать?').fill('две кнопки');
  verify(await offlinePage.getByRole('button',{name:'Две кнопки в ряд',exact:true}).isVisible(),'standalone file gallery search');
  verify((await offlinePage.locator('#preview .keyboard-row').evaluateAll(rows=>rows.map(row=>row.children.length))).join(',')==='2,2','standalone file preview');
  verify(localErrors.length===0&&localHTTP.length===0,'standalone file has no page errors or HTTP');await local.close();
  const report={passed:true,version,browser:browser.version(),checks,viewportThemeCases:results.length,telegram_network:false,results,
    limits:'Local web preview; no physical Telegram client or native keyboard appearance proof'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({passed:true,version,checks,viewportThemeCases:results.length,telegram_network:false}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
