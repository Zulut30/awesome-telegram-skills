/** Real-browser integration of the public package through the compiled demo. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {createDemoServer} from '../examples/mini-app/server.mjs';

const version=JSON.parse(await readFile(new URL('../packages/typescript/package.json',import.meta.url),'utf8')).version;
const output=path.resolve(process.env.PATTERNS_BROWSER_OUTPUT ?? (version==='0.1.0'?'output/pattern-library/browser':`output/pattern-library-${version}/browser`)); await mkdir(output,{recursive:true});
const server=createDemoServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`;
const config=process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {channel:'chrome'};
const results=[];let checks=0;let browser;
function verify(value,message){assert.ok(value,message);checks++;}
try{
  browser=await chromium.launch({...config,headless:true});
  const devices=[['small-phone',320,568],['phone',390,844],['landscape-phone',844,390],['tablet',768,1024],['wide-tablet',1024,768],['desktop',1440,900],['large-desktop',1920,1080]];
  for(const [label,width,height] of devices){
    for(const theme of ['light','dark']){
      const context=await browser.newContext({viewport:{width,height}});const page=await context.newPage();
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto(base);await page.getByRole('heading',{name:'Запись на консультацию'}).waitFor();
      if(theme==='dark') await page.getByRole('button',{name:'Сменить тему'}).click();
      await page.getByRole('button',{name:'10:00',exact:true}).click();
      await page.getByLabel('Ваше имя', {exact:true}).fill('Тестовый участник');
      await page.getByLabel('Телефон',{exact:true}).fill('bad-number');
      await page.getByRole('button',{name:'Подтвердить запись'}).click();
      await page.getByText('Проверьте номер телефона.',{exact:true}).waitFor();
      const geometry=await page.evaluate(()=>{
        const shell=document.querySelector('.tp-shell'),input=document.querySelector('[name=phone]');
        const columns=getComputedStyle(document.querySelector('.tp-columns')).gridTemplateColumns.split(' ').length;
        const buttons=[...document.querySelectorAll('button')].filter(button=>!button.hidden).map(button=>button.getBoundingClientRect().height);
        const boxes=[input,...document.querySelectorAll('.tp-field:last-of-type p')].filter(el=>!el.hidden).map(el=>el.getBoundingClientRect());
        return {overflow:document.documentElement.scrollWidth>innerWidth,columns,buttons,focused:document.activeElement===input,theme:shell.dataset.theme,
          labeled:input.labels.length===1,described:input.getAttribute('aria-describedby').includes('-error'),
          noOverlap:boxes.slice(1).every((box,index)=>box.top>=boxes[index].bottom),color:getComputedStyle(input).color,background:getComputedStyle(input).backgroundColor};
      });
      verify(!geometry.overflow,`${label}/${theme}: horizontal overflow`);
      verify(geometry.columns===(width>=800?2:1),`${label}/${theme}: responsive columns`);
      verify(geometry.buttons.every(value=>value>=48),`${label}/${theme}: action targets`);
      verify(geometry.focused&&geometry.labeled&&geometry.described,`${label}/${theme}: invalid field focus/label/error`);
      verify(geometry.noOverlap,`${label}/${theme}: hint/error overlap`);
      verify(geometry.theme===theme,`${label}/${theme}: requested theme`);
      await page.getByLabel('Телефон',{exact:true}).fill('+7 900 123-45-67');
      await page.getByRole('button',{name:'Сменить тему'}).click();
      verify(await page.getByLabel('Ваше имя',{exact:true}).inputValue()==='Тестовый участник',`${label}/${theme}: theme lost input`);
      await page.setViewportSize({width:Math.max(320,width-30),height:Math.max(280,height-200)});
      verify(await page.getByLabel('Телефон',{exact:true}).inputValue()==='+7 900 123-45-67',`${label}/${theme}: resize lost input`);
      await page.setViewportSize({width,height});await page.getByRole('button',{name:'Сменить тему'}).click();
      await page.screenshot({path:path.join(output,`${label}-${theme}.png`),fullPage:true});
      verify(errors.length===0,`${label}/${theme}: page errors ${errors}`);
      results.push({label,width,height,theme,geometry});await context.close();
    }
  }
  const componentContext=await browser.newContext();const componentPage=await componentContext.newPage();await componentPage.goto(base);
  const components=await componentPage.evaluate(async()=>{
    const {createAppShell,createTextField,TelegramBridge}=await import('/lib/index.js');
    const legacy=document.createElement('input');legacy.id='tp-field-3';document.body.prepend(legacy);
    const host=document.createElement('div');document.body.append(host);const shell=createAppShell(host,'Component contract');
    const field=createTextField(document,'Имя в новом компоненте');shell.content.append(field.root);field.root.querySelector('label').click();
    const labelFocusCorrect=document.activeElement===field.input;
    // Detached documents have no window/crypto: exercise the fallback while
    // pre-existing input, hint and error IDs occupy consecutive candidates.
    const detached=document.implementation.createHTMLDocument('Fallback contract');
    for(const id of ['tp-field-1','tp-field-2-hint','tp-field-3-error']){
      const occupied=detached.createElement('div');occupied.id=id;detached.body.append(occupied);
    }
    const fallback=createTextField(detached,'Поле без окна');detached.body.append(fallback.root);
    const fallbackIds=[...fallback.root.querySelectorAll('[id]')].map(element=>element.id);
    const fallbackIdsUnique=fallback.input.id==='tp-field-4'&&fallbackIds.every(id=>detached.querySelectorAll(`[id="${id}"]`).length===1);
    const app={colorScheme:'dark',platform:'unknown',themeParams:{bg_color:'#151f30',text_color:'#eaf0ff',section_bg_color:'#243246',hint_color:'#c1cbe0',section_separator_color:'#78869d',destructive_text_color:'#ff9b9b'},ready(){},onEvent(){},offEvent(){}};
    const snapshot=new TelegramBridge(app).snapshot();shell.applyTheme(snapshot);field.setError('Проверьте поле');
    const style=getComputedStyle(shell.content),hint=getComputedStyle(field.root.querySelector('.tp-hint')),error=getComputedStyle(field.root.querySelector('.tp-error'));
    return {labelFocusCorrect,fallbackIdsUnique,surface:style.backgroundColor,hint:hint.color,error:error.color,border:style.borderTopColor,nativeScheme:getComputedStyle(shell.element).colorScheme,insideTelegram:snapshot.insideTelegram};
  });
  await writeFile(path.join(output,'component-contract.json'),JSON.stringify(components,null,2));
  verify(components.labelFocusCorrect,'existing DOM ID redirects the new label to a foreign input');
  verify(components.fallbackIdsUnique,'fallback IDs collide with existing input/hint/error elements');
  verify(components.surface==='rgb(36, 50, 70)'&&components.hint==='rgb(193, 203, 224)'&&components.error==='rgb(255, 155, 155)'&&components.border==='rgb(120, 134, 157)','Telegram semantic theme colors ignored');
  verify(components.nativeScheme==='dark','native controls remain in the wrong color scheme');
  verify(components.insideTelegram===false,'standalone SDK classified as a Telegram host');await componentContext.close();
  // Real lost HTTP response after a server effect, then query the SAME operation.
  const context=await browser.newContext({viewport:{width:390,height:844}});const page=await context.newPage();let writes=0;
  page.on('request',request=>{if(request.method()==='POST'&&request.url().includes('/api/bookings'))writes++;});
  await page.goto(base);await page.getByRole('button',{name:'14:30',exact:true}).click();
  await page.getByLabel('Ваше имя',{exact:true}).fill('Local fixture');await page.getByLabel('Телефон',{exact:true}).fill('+7 900 123-45-67');
  await page.locator('[data-test=drop]').check();await page.getByRole('button',{name:'Подтвердить запись'}).click();
  await page.evaluate(()=>document.querySelector('form').requestSubmit());
  await page.getByText('Ответ не получен. Проверьте результат, прежде чем повторять запись.',{exact:true}).waitFor();
  verify(writes===1,'double submit or unknown response repeated mutation');
  verify(server.demoStats().httpWrites>=1,'no real POST reached the demo server');
  verify(server.demoStats().effects===1,'transport retry created a second business effect');
  verify(await page.getByRole('button',{name:'Подтвердить запись'}).isDisabled(),'pending operation permits a new intent');
  await page.getByRole('button',{name:'Проверить результат'}).click();await page.getByText(/Запись №\d+ подтверждена на 14:30\./).waitFor();
  verify(writes===1,'recovery repeated POST');await context.close();
  verify(server.demoStats().effects===1,'recovery created a second effect');

  // Actual browser storage failures: app remains interactive and tells the user.
  const blocked=await browser.newContext({viewport:{width:320,height:568}});
  await blocked.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked fixture');}}));
  const blockedPage=await blocked.newPage();await blockedPage.goto(base);
  await blockedPage.getByText('Сохранение выбора недоступно в этом браузере.',{exact:true}).waitFor();
  await blockedPage.getByRole('button',{name:'10:00',exact:true}).click();
  verify(await blockedPage.getByRole('button',{name:'10:00',exact:true}).getAttribute('aria-pressed')==='true','blocked storage breaks selection');
  verify(await blockedPage.getByText('Выбор не удалось сохранить. Не закрывайте страницу до завершения.',{exact:true}).isVisible(),'failed save not observable');
  await blocked.close();

  const draftContext=await browser.newContext();const draftPage=await draftContext.newPage();await draftPage.goto(base);
  await draftPage.getByRole('button',{name:'14:30',exact:true}).click();await draftPage.getByLabel('Ваше имя',{exact:true}).fill('Never persisted');
  await draftPage.reload();verify(await draftPage.getByRole('button',{name:'14:30',exact:true}).getAttribute('aria-pressed')==='true','selection not restored after reload');
  verify(await draftPage.getByLabel('Ваше имя',{exact:true}).inputValue()==='','contact/name persisted with draft');await draftContext.close();

  const report={version,browser:browser.version(),checks,viewportThemeCases:results.length,transport:server.demoStats(),components,results,limits:'Local browser viewports, synthetic storage/HTTP; no physical Telegram client or soft-keyboard proof.'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(`PASS ${checks} browser checks, ${results.length} viewport/theme cases, Chrome ${report.browser}`);
}finally{
  await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
}
