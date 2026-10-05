/** Real Chrome gallery checks; serves only three known static files on loopback. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const version=JSON.parse(await readFile(path.join(root,'packages/typescript/package.json'),'utf8')).version;
const galleryDirectory=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'gallery');
const exported=galleryDirectory!==path.join(root,'gallery');
const output=process.argv[3]?path.resolve(process.argv[3]):path.join(root,'output',`pattern-library-${version}`,'gallery-browser');await mkdir(output,{recursive:true});
const resources=new Map();
for(const [file,type] of [['index.html','text/html'],['gallery.js','text/javascript'],['gallery.css','text/css']])resources.set('/'+file,[await readFile(path.join(galleryDirectory,file)),type]);
const catalogData=JSON.parse(await readFile(exported?path.join(galleryDirectory,'recipes.json'):path.join(root,'catalog/recipe-gallery.json'),'utf8'));
for(const name of new Set(catalogData.recipes.flatMap(recipe=>[...recipe.source_files,...recipe.check_files]))){
  const supplied=exported?path.join(galleryDirectory,'files',name):path.join(root,name);
  resources.set('/'+(exported?'files/':'')+name,[await readFile(supplied),'text/plain']);
}
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
      verify(await page.locator('#recipes .recipe-card').count()===303,`${name}/${theme}: catalog count`);
      if(width===320)await page.screenshot({path:path.join(output,`phone-initial-${theme}.png`),fullPage:true});
      if(!await page.locator('#advanced-filters').evaluate(details=>details.open))await page.locator('#advanced-filters summary').click();
      await page.getByLabel('Зрелость',{exact:true}).selectOption('experimental');
      verify(await page.locator('#recipes .recipe-card').count()===19,`${name}/${theme}: experimental count`);
      await page.getByLabel('Проверка',{exact:true}).selectOption('mock');
      verify(await page.locator('#recipes .recipe-card').count()===8,`${name}/${theme}: independent evidence filter`);
      await page.getByLabel('Зрелость',{exact:true}).selectOption('reference');
      verify(await page.locator('#recipes .recipe-card').count()===0,`${name}/${theme}: mock does not imply reference or stable`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();
      await page.getByLabel('Зрелость',{exact:true}).selectOption('stable');
      verify(await page.locator('#recipes .recipe-card').count()===0,`${name}/${theme}: no fabricated stable claim`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();
      verify(await page.locator('#recipes .recipe-card').count()===303,`${name}/${theme}: reset clears maturity`);
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
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Что хотите сделать?').fill('назад');
      verify(await page.getByRole('button',{name:'Две кнопки в ряд',exact:true}).isVisible(),`${name}/${theme}: back layout searchable`);
      await page.getByLabel('SDK',{exact:true}).selectOption('telegram-webapp');
      verify(await page.locator('#recipes .recipe-card').count()>0&&await page.locator('#code').textContent().then(code=>code.includes('BackButton')),`${name}/${theme}: native back SDK filter`);
      verify(!(await page.locator('#execution-command').textContent()).includes('--offline')&&(await page.locator('#execution-requirements').textContent()).includes('Справочный фрагмент'),`${name}/${theme}: native requirements do not invent an executor`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Что хотите сделать?').fill('потерянный ответ');
      await page.getByLabel('Задача',{exact:true}).selectOption('recovery');await page.getByLabel('Контекст',{exact:true}).selectOption('backend');
      verify(await page.locator('#recipes .recipe-card').count()===1,`${name}/${theme}: recovery intersection`);
      verify((await page.locator('#code').textContent()).includes('must_not_apply')&&(await page.locator('#detail-scope').textContent()).includes('Нет HTTP'),`${name}/${theme}: real local recovery with clear limits`);
      await page.locator('#execution-details').evaluate(details=>details.open=true);
      verify((await page.locator('#execution-command').textContent())==='telegram-patterns run-recipe demo-recovery --offline',`${name}/${theme}: closed offline command`);
      verify((await page.locator('#execution-requirements').textContent()).includes('Секреты и Telegram-права не требуются')&&(await page.locator('#execution-requirements').textContent()).includes('Авторизация до записи'),`${name}/${theme}: offline and live obligations are distinct`);
      verify(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}/${theme}: expanded requirements fit viewport`);
      if(['phone','tablet','desktop'].includes(name))await page.screenshot({path:path.join(output,`${name}-${theme}-requirements.png`),fullPage:true});
      await page.locator('#execution-details').evaluate(details=>details.open=false);
      for(const id of ['source-files','check-files']){
        const href=await page.locator('#'+id+' a').first().getAttribute('href');const response=await context.request.get(new URL(href,base+'/').href);
        verify(response.status()===200&&(await response.text()).includes('SQLiteOnce'),`${name}/${theme}: ${id} resolves to source code`);
      }
      await page.getByLabel('Контекст',{exact:true}).selectOption('private');
      verify(await page.locator('#detail').isHidden()&&await page.locator('#recipes .recipe-card').count()===0,`${name}/${theme}: context mismatch has no stale details`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Что хотите сделать?').fill('история');
      await page.getByLabel('Задача',{exact:true}).selectOption('navigation');await page.getByLabel('Контекст',{exact:true}).selectOption('private');
      verify(await page.locator('#recipes .recipe-card').count()===1&&await page.getByRole('button',{name:'Экраны и история в одном сообщении',exact:true}).isVisible(),`${name}/${theme}: owned navigation discoverable`);
      await page.getByRole('button',{name:'Экраны и история в одном сообщении',exact:true}).click();
      await page.locator('#execution-details').evaluate(details=>details.open=true);
      verify((await page.locator('#code').textContent()).includes('MessageNavigation')&&(await page.locator('#execution-command').textContent())==='telegram-patterns run-recipe demo-navigation --offline',`${name}/${theme}: navigation public composition and closed fixture`);
      for(const id of ['source-files','check-files']){
        const href=await page.locator('#'+id+' a').first().getAttribute('href');const response=await context.request.get(new URL(href,base+'/').href);
        verify(response.status()===200&&(await response.text()).includes('build_menu'),`${name}/${theme}: navigation ${id} resolves`);
      }
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Что хотите сделать?').fill('multiselect');
      await page.getByLabel('Задача',{exact:true}).selectOption('input');await page.getByLabel('Контекст',{exact:true}).selectOption('private');
      verify(await page.locator('#recipes .recipe-card').count()===1&&await page.getByRole('button',{name:'Переключатели, выбор, количество и подтверждение',exact:true}).isVisible(),`${name}/${theme}: composite selection discoverable`);
      await page.getByRole('button',{name:'Переключатели, выбор, количество и подтверждение',exact:true}).click();
      await page.locator('#execution-details').evaluate(details=>details.open=true);
      verify((await page.locator('#code').textContent()).includes('SelectionMenu')&&(await page.locator('#execution-command').textContent())==='telegram-patterns run-recipe demo-selection --offline',`${name}/${theme}: selection public composition and closed fixture`);
      for(const id of ['source-files','check-files']){
        const href=await page.locator('#'+id+' a').first().getAttribute('href');const response=await context.request.get(new URL(href,base+'/').href);
        verify(response.status()===200&&(await response.text()).includes('build_selection_router'),`${name}/${theme}: selection ${id} resolves`);
      }
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Что хотите сделать?').fill('календарь');
      await page.getByLabel('Задача',{exact:true}).selectOption('input');await page.getByLabel('Контекст',{exact:true}).selectOption('private');
      verify(await page.locator('#recipes .recipe-card').count()===1&&await page.getByRole('button',{name:'Календарь и запись на свободное время',exact:true}).isVisible(),`${name}/${theme}: calendar discoverable`);
      await page.getByRole('button',{name:'Календарь и запись на свободное время',exact:true}).click();
      await page.locator('#execution-details').evaluate(details=>details.open=true);
      verify((await page.locator('#code').textContent()).includes('SQLiteSlotStore')&&(await page.locator('#execution-command').textContent())==='telegram-patterns run-recipe demo-calendar --offline',`${name}/${theme}: calendar public composition and closed fixture`);
      for(const id of ['source-files','check-files']){
        const href=await page.locator('#'+id+' a').first().getAttribute('href');const response=await context.request.get(new URL(href,base+'/').href);
        verify(response.status()===200&&(await response.text()).includes('build_calendar_router'),`${name}/${theme}: calendar ${id} resolves`);
      }
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Что хотите сделать?').fill('поля');
      await page.getByLabel('Задача',{exact:true}).selectOption('input');await page.getByLabel('Контекст',{exact:true}).selectOption('private');
      verify(await page.locator('#recipes .recipe-card').count()===1&&await page.getByRole('button',{name:'Семь типов полей диалога',exact:true}).isVisible(),`${name}/${theme}: typed dialog discoverable`);
      await page.getByRole('button',{name:'Семь типов полей диалога',exact:true}).click();
      await page.locator('#execution-details').evaluate(details=>details.open=true);
      verify((await page.locator('#code').textContent()).includes('dialog_form_router')&&(await page.locator('#execution-command').textContent())==='telegram-patterns run-recipe demo-dialog-fields --offline',`${name}/${theme}: dialog public composition and closed fixture`);
      for(const id of ['source-files','check-files']){
        const href=await page.locator('#'+id+' a').first().getAttribute('href');const response=await context.request.get(new URL(href,base+'/').href);
        verify(response.status()===200&&(await response.text()).includes('attach_dialog'),`${name}/${theme}: dialog ${id} resolves`);
      }
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('SDK',{exact:true}).selectOption('aiogram');
      await page.getByLabel('Версия SDK / снимок',{exact:true}).selectOption('3.31.0');await page.getByLabel('Версия API',{exact:true}).selectOption('bot:10.3');
      verify(await page.locator('#recipes .recipe-card').count()===203,`${name}/${theme}: SDK/version/API exact intersection`);
      await page.getByLabel('SDK',{exact:true}).selectOption('python-core');
      verify(await page.getByLabel('Версия SDK / снимок',{exact:true}).inputValue()==='',`${name}/${theme}: changing SDK clears incompatible version`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Контекст',{exact:true}).selectOption('supergroup');
      await page.getByLabel('Задача',{exact:true}).selectOption('moderation');
      verify(await page.locator('[data-id="api.createForumTopic"]').isVisible(),`${name}/${theme}: reviewed supergroup context`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();await page.getByLabel('Контекст',{exact:true}).selectOption('group');
      verify(await page.locator('[data-id="api.getUpdates"]').count()===0,`${name}/${theme}: unspecified context is not all chats`);
      await page.getByRole('button',{name:'Сбросить',exact:true}).click();
      verify(await page.locator('#recipes .recipe-card').count()===303&&await page.getByLabel('Что хотите сделать?').evaluate(input=>input===document.activeElement),`${name}/${theme}: full filter reset and focus`);
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
  verify(await page.getByLabel('Код рецепта',{exact:true}).getAttribute('tabindex')==='0','keyboard accessible code block');
  await page.evaluate(()=>{catalog.recipes[0].source_files=['../secret.env','javascript:alert(1)','https://invalid.test'];render();});
  verify(await page.locator('#source-files a').count()===0,'malformed source paths never become links');await context.close();
  const local=await browser.newContext();const offlinePage=await local.newPage();const localErrors=[],localHTTP=[];
  offlinePage.on('pageerror',error=>localErrors.push(error.message));offlinePage.on('request',request=>{if(/^https?:/.test(request.url()))localHTTP.push(request.url());});
  await offlinePage.goto(pathToFileURL(path.join(galleryDirectory,'index.html')).href);
  await offlinePage.getByLabel('Что хотите сделать?').fill('две кнопки');
  verify(await offlinePage.getByRole('button',{name:'Две кнопки в ряд',exact:true}).isVisible(),'standalone file gallery search');
  verify((await offlinePage.locator('#preview .keyboard-row').evaluateAll(rows=>rows.map(row=>row.children.length))).join(',')==='2,2','standalone file preview');
  verify(localErrors.length===0&&localHTTP.length===0,'standalone file has no page errors or HTTP');await local.close();
  const report={passed:true,version,browser:browser.version(),checks,viewportThemeCases:results.length,telegram_network:false,results,exported,
    limits:'Local web preview; no physical Telegram client or native keyboard appearance proof'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({passed:true,version,checks,viewportThemeCases:results.length,telegram_network:false}));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
