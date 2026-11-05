/** Real local Chrome + axe. Synthetic viewport/theme/touch fixtures, not approved baselines or device acceptance. */
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {createUiPreviewServer} from '../../../examples/ui-kit/server.mjs';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const supplied=process.argv[2]?JSON.parse(await readFile(path.resolve(process.argv[2]),'utf8')):{};
const configuration={
  vendorDirectory:path.join(root,'packages/typescript/dist'),
  exampleDirectory:path.join(root,'examples/ui-kit/dist'),
  referenceDirectory:path.join(root,'examples/ui-kit/dist/reference'),
  htmlPath:path.join(root,'examples/ui-kit/index.html'),
  axeDirectory:path.join(root,'tools/mini-app-quality/node_modules/axe-core'),
  mode:'source',...supplied,
};
if(!['source','installed'].includes(configuration.mode))throw Error('Declare source or installed UI fixture');
const output=path.resolve(configuration.output??process.env.PATTERNS_UI_OUTPUT??path.join(root,'output/ui-kit-check'));
await mkdir(output,{recursive:true});
for(const file of [path.join(configuration.vendorDirectory,'index.js'),path.join(configuration.vendorDirectory,'styles.css'),path.join(configuration.vendorDirectory,'tokens.css'),path.join(configuration.exampleDirectory,'main.js'),path.join(configuration.referenceDirectory,'ui.js')])await readFile(file);
const axeSource=await readFile(path.join(configuration.axeDirectory,'axe.min.js'),'utf8');
const server=createUiPreviewServer(configuration);await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
let browser,report;const checks=[],audits=[],geometry=[],supplementalContrast=[];
function solidContrast(foreground,background){
  const luminance=color=>{const values=color.match(/[\d.]+/g)?.map(Number);assert.ok(values?.length===3||(values?.length===4&&values[3]===1),'opaque RGB contrast fixture');const linear=values.slice(0,3).map(value=>{const s=value/255;return s<=0.04045?s/12.92:((s+0.055)/1.055)**2.4;});return linear[0]*0.2126+linear[1]*0.7152+linear[2]*0.0722;};
  const first=luminance(foreground),second=luminance(background);return (Math.max(first,second)+0.05)/(Math.min(first,second)+0.05);
}
try{
  browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{channel:'chrome'})});
  const context=await browser.newContext({hasTouch:true,viewport:{width:390,height:844}});
  const page=await context.newPage();const errors=[],external=[];page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(new URL(request.url()).origin!==origin)external.push(request.url());});
  await page.goto(origin+'/');
  await page.waitForFunction(()=>window.uiPreview?.views.every(view=>view.state==='ready'));
  const controlChecks=await page.evaluate(async()=>{
    const ui=await import('/vendor/index.js');const {createAppShell}=await import('/vendor/index.js');
    const passed=[];const verify=(condition,label)=>{if(!condition)throw Error(label);passed.push(label);};
    const fixture=document.createElement('section');fixture.id='control-fixture';window.uiPreview.shell.content.append(fixture);
    const card=ui.createUiCard(document,'<img src=x onerror=alert(1)>','<script>PRIVATE_CANARY</script>');fixture.append(card);
    verify(card.querySelector('img,script')===null&&card.textContent.includes('<script>'),'literal text never becomes HTML');
    const link=ui.createUiLink(document,'Помощь','https://example.org/help');fixture.append(link);
    verify(link.rel==='noopener noreferrer'&&link.target==='_blank','external HTTPS link uses safe navigation semantics');
    let calls=0,release;const button=ui.createUiButton(document,{label:'Подтвердить без изменения подписи',onPress:()=>{calls++;return new Promise(resolve=>{release=resolve;});}});
    fixture.append(button.element);button.element.focus();button.element.click();button.element.click();await Promise.resolve();
    verify(calls===1&&button.pending&&!button.element.disabled,'pending mutex prevents second invocation without disabling focus');
    verify(document.activeElement===button.element&&button.element.textContent==='Подтвердить без изменения подписи','pending keeps focus and accessible label');
    release();await new Promise(resolve=>setTimeout(resolve,0));verify(!button.pending,'pending follows actual promise completion');
    button.setDisabled(true);button.element.click();verify(calls===1,'explicit disabled prevents activation');button.setDisabled(false);
    button.element.click();await Promise.resolve();button.dispose();release();await new Promise(resolve=>setTimeout(resolve,0));button.element.click();
    verify(calls===2&&!button.element.isConnected,'dispose removes listener; already sent action is not claimed cancelled');
    let queuedCalls=0;const queued=ui.createUiButton(document,{label:'Не начать после dispose',onPress:()=>{queuedCalls++;}});
    fixture.append(queued.element);queued.element.click();queued.dispose();await new Promise(resolve=>setTimeout(resolve,0));
    verify(queuedCalls===0,'dispose before action microtask prevents starting a new action');
    let rejectRemote,remoteState='idle',remoteCalls=0;
    const remote=ui.createUiButton(document,{label:'Сверяем неизвестный результат',onPress:async()=>{
      remoteCalls++;remoteState='sending';try{await new Promise((_resolve,reject)=>{rejectRemote=reject;});}
      catch(error){remoteState='unknown';throw error;}
    }});fixture.append(remote.element);remote.element.click();await Promise.resolve();remote.dispose();
    verify(remote.pending&&remoteState==='sending','dispose during pending does not pretend the remote operation was cancelled');
    rejectRemote(new ui.UnknownOutcome());await new Promise(resolve=>setTimeout(resolve,0));remote.element.click();
    verify(remoteCalls===1&&remoteState==='unknown'&&ui.safeErrorReport(new ui.UnknownOutcome(),'write').recovery==='reconcile','host unknown outcome survives disposed view and requires reconciliation');
    const first=ui.createUiField(document,{label:'Имя',value:'Александра',required:true,inputMode:'text'});
    const second=ui.createUiField(document,{label:'Почта',type:'email',inputMode:'email',value:'bad',validate:v=>v.includes('@')?null:'Укажите почту.'});
    fixture.append(first.root,second.root);first.input.focus();first.input.setSelectionRange(2,4);first.setError('Сервер отказал.');
    verify(first.input.value==='Александра'&&first.input.selectionStart===2&&first.input.selectionEnd===4,'server error preserves literal input and selection');
    verify(first.input.labels.length===1&&first.input.getAttribute('aria-describedby').includes('-error'),'label and inline error are associated');
    first.input.value='';verify(!ui.validateUiFields([first,second])&&document.activeElement===first.input,'submit validation focuses first error');
    first.input.value='Александра';verify(!ui.validateUiFields([first,second])&&document.activeElement===second.input,'all fields validate and next error receives focus');
    second.input.value='a@example.org';verify(ui.validateUiFields([first,second]),'corrected form passes without replacing controls');
    const opener=ui.createUiButton(document,{label:'Открыть проверочный диалог'});fixture.append(opener.element);
    const dialog=ui.createUiDialog(document,'Проверочный диалог');const modalField=ui.createUiField(document,{label:'Поле в диалоге'});dialog.content.append(modalField.root);fixture.append(dialog.element);
    window.uiContract={fixture,dialog,opener,modalField};opener.element.focus();dialog.open(opener.element);
    verify(dialog.element.open&&dialog.element.contains(document.activeElement),'native modal opens with focus inside');
    const unsupported=ui.createUiDialog(document,'Недоступный диалог');fixture.append(unsupported.element);
    Object.defineProperty(unsupported.element,'showModal',{value:undefined});let refusal=false;try{unsupported.open();}catch(error){refusal=error.code==='unsupported-capability';}
    verify(refusal&&!unsupported.element.open,'unsupported modal fails explicitly');unsupported.dispose();
    first.dispose();second.dispose();return passed;
  });checks.push(...controlChecks);
  await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');
  assert.equal(await page.evaluate(()=>window.uiContract.dialog.element.contains(document.activeElement)),true);checks.push('actual Chrome Tab/Shift+Tab stays in native modal');
  await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(()=>!window.uiContract.dialog.element.open&&document.activeElement===window.uiContract.opener.element),true);checks.push('Escape closes native modal and restores initiating focus');
  await page.evaluate(()=>window.uiContract.dialog.open(window.uiContract.opener.element));
  const close=page.getByRole('dialog',{name:'Проверочный диалог'}).getByRole('button',{name:'Закрыть'});
  const closeBounds=await close.boundingBox();await page.touchscreen.tap(closeBounds.x+closeBounds.width/2,closeBounds.y+closeBounds.height/2);
  assert.equal(await page.evaluate(()=>!window.uiContract.dialog.element.open&&document.activeElement===window.uiContract.opener.element),true);checks.push('synthetic touch activates visible modal close and restores focus');
  await page.evaluate(()=>{window.uiContract.dialog.open(window.uiContract.opener.element);window.uiContract.dialog.dispose();if(document.activeElement!==window.uiContract.opener.element)throw Error('dispose focus');window.uiContract.fixture.remove();});
  checks.push('dispose closes modal and restores focus without global listeners');
  await page.evaluate(async()=>{const {referenceUi}=await import('/reference/ui.js');await referenceUi(document);});
  checks.push('public 26-symbol UI reference executes and tears down DOM, modal and bridge listeners');

  await page.getByRole('tab',{name:'Каталог',exact:true}).focus();await page.keyboard.press('End');
  assert.equal(await page.evaluate(()=>window.uiPreview.tabs.selected),'Запись');await page.keyboard.press('Home');await page.keyboard.press('ArrowRight');
  assert.equal(await page.evaluate(()=>window.uiPreview.tabs.selected),'Товар');checks.push('real keyboard tabs support Home/End/arrows and selected panels');

  const themeChecks=await page.evaluate(async()=>{
    const {createAppShell}=await import('/vendor/index.js');const {connectUiShell,createUiField}=await import('/vendor/index.js');
    const host=document.createElement('div');document.body.append(host);const shell=createAppShell(host,'Theme fixture');
    const field=createUiField(document,{label:'Сохранённое значение',value:'Не терять ввод'});shell.content.append(field.root);field.input.focus();
    let listener;const snapshot={insideTelegram:true,colorScheme:'light',theme:{bg_color:'#ffffff',text_color:'#172f45'},stableHeight:600,systemInsets:{top:10,right:10,bottom:10,left:10},contentInsets:{top:20,right:20,bottom:20,left:20}};
    const stop=connectUiShell(shell,{subscribe(callback){listener=callback;callback(snapshot);return()=>{listener=undefined;};}},{resolveInsets:()=>({top:15,right:7,bottom:20,left:7})});
    const computed=getComputedStyle(shell.element);if(computed.paddingTop!=='35px')throw Error('Insets summed or applied twice');
    if(computed.backgroundColor!=='rgb(255, 255, 255)')throw Error('Native theme ignored');
    listener({...snapshot,colorScheme:'dark',theme:{bg_color:'#101d27',text_color:'#edf4ff'}});
    if(getComputedStyle(shell.element).backgroundColor!=='rgb(16, 29, 39)')throw Error('Native dark did not override system light');
    if(field.input.value!=='Не терять ввод'||document.activeElement!==field.input)throw Error('Theme reset form/focus');
    if(getComputedStyle(field.root).paddingTop!=='0px')throw Error('Nested safe area padding');
    stop();stop();if(listener!==undefined)throw Error('Subscription leaked');field.dispose();shell.dispose();host.remove();return ['resolved inset applied once, independent raw safe/content values never summed','native theme update preserves input and focus','theme subscription cleanup idempotent'];
  });checks.push(...themeChecks);

  const sizes=[[320,568],[390,844],[844,390],[768,1024],[1024,768],[1280,800],[480,720],[390,420]];
  for(const theme of ['light','dark']){
    await page.emulateMedia({colorScheme:theme});
    await page.waitForFunction(theme=>document.querySelector('.tp-shell').dataset.theme===theme,theme);
    for(const [width,height] of sizes){
      await page.setViewportSize({width,height});
      for(const name of ['Каталог','Товар','Корзина','Профиль','Настройки','Запись']){
        await page.getByRole('tab',{name,exact:true}).click();
        const measure=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,selected:window.uiPreview.tabs.selected}));
        assert.ok(measure.scroll<=measure.width+1,`${name} ${theme} ${width} overflow ${measure.scroll}`);geometry.push({theme,width,height,screen:name,...measure});
      }
      await page.screenshot({path:path.join(output,`${theme}-${width}x${height}-synthetic.png`),fullPage:true});
    }
  }
  checks.push('six compositions reflow across eight desktop Chrome viewport sizes/orientations in light/dark');
  for(const [width,height] of [[320,568],[844,390],[768,1024]]){
    await page.setViewportSize({width,height});await page.getByRole('tab',{name:'Запись',exact:true}).click();
    await page.getByRole('button',{name:'Понедельник — с 10:30 до 11:15 по вашему часовому поясу',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'Обзор выбранного действия',exact:true});
    assert.equal(await dialog.evaluate(element=>{const rect=element.getBoundingClientRect();return rect.top>=-1&&rect.bottom<=innerHeight+1&&rect.left>=-1&&rect.right<=innerWidth+1;}),true);
    await page.screenshot({path:path.join(output,`sheet-${width}x${height}-synthetic.png`),fullPage:true});
    await dialog.getByRole('button',{name:'Закрыть',exact:true}).tap();
  }
  checks.push('bottom sheet bounds and synthetic touch close work at narrow, landscape and tablet sizes');
  await page.setViewportSize({width:320,height:568});
  await page.evaluate(()=>{document.documentElement.style.fontSize='200%';window.uiPreview.tabs.select('Настройки');});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(output,'text-200-percent-320-synthetic.png'),fullPage:true});
  await page.evaluate(()=>{document.documentElement.style.fontSize='';});checks.push('200% root text enlargement reflows at 320 CSS px');
  const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setPageScaleFactor',{pageScaleFactor:2});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await cdp.send('Emulation.setPageScaleFactor',{pageScaleFactor:1});
  checks.push('Chrome page-scale approximation remains horizontally reachable, not native browser/device zoom acceptance');
  await page.setViewportSize({width:390,height:420});await page.getByRole('tab',{name:'Настройки',exact:true}).click();
  const focusedEmail=page.getByLabel('Электронная почта',{exact:true});await focusedEmail.fill('resume@example.org');await focusedEmail.focus();
  await page.setViewportSize({width:390,height:300});await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await focusedEmail.evaluate(input=>{const rect=input.getBoundingClientRect();return rect.top>=-1&&rect.bottom<=(visualViewport?.height??innerHeight)+1;}),true);
  await page.keyboard.press('Tab');
  assert.equal(await page.getByRole('button',{name:'Сохранить настройки',exact:true}).evaluate(button=>{const rect=button.getBoundingClientRect();return document.activeElement===button&&rect.top>=-1&&rect.bottom<=(visualViewport?.height??innerHeight)+1;}),true);
  await page.evaluate(()=>{dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  assert.equal(await focusedEmail.inputValue(),'resume@example.org');assert.equal(await page.evaluate(()=>window.uiPreview.shell.element.isConnected),true);
  checks.push('first focused field and following action remain reachable after reduced-height resize; synthetic persisted resume keeps input');
  await page.setViewportSize({width:390,height:844});
  const targetSizes=await page.evaluate(()=>{const shell=window.uiPreview.shell.element;shell.dataset.density='compact';return Array.from(shell.querySelectorAll('button,input,a')).filter(el=>el.getClientRects().length&&!el.closest('[hidden]')).map(el=>{const r=el.getBoundingClientRect();return {width:r.width,height:r.height};});});
  assert.ok(targetSizes.every(size=>size.width>=44&&size.height>=44));await page.evaluate(()=>{delete window.uiPreview.shell.element.dataset.density;});
  checks.push('visible compact controls meet the toolkit 44 CSS px target criterion');

  await page.addScriptTag({content:axeSource});
  async function audit(name){
    const result=await page.evaluate(async()=>window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
    const violations=result.violations.map(item=>({id:item.id,impact:item.impact,nodes:item.nodes.map(node=>({target:node.target,summary:node.failureSummary}))}));
    const incomplete=result.incomplete.map(item=>({id:item.id,nodes:item.nodes.map(node=>({target:node.target,summary:node.failureSummary}))}));
    audits.push({name,passes:result.passes.length,incomplete,violations});assert.deepEqual(violations,[],`axe ${name}`);
  }
  for(const theme of ['light','dark']){
    await page.emulateMedia({colorScheme:theme});await page.setViewportSize({width:390,height:844});
    for(const name of ['Каталог','Товар','Корзина','Профиль','Настройки','Запись']){await page.getByRole('tab',{name,exact:true}).click();await audit(`${theme}-${name}-ready`);}
    await page.getByRole('button',{name:'Понедельник — с 10:30 до 11:15 по вашему часовому поясу',exact:true}).click();
    await page.getByRole('dialog',{name:'Обзор выбранного действия',exact:true}).waitFor();await audit(`${theme}-bottom-sheet`);
    const colors=await page.getByRole('dialog',{name:'Обзор выбранного действия',exact:true}).evaluate(dialog=>({foreground:getComputedStyle(dialog).color,background:getComputedStyle(dialog).backgroundColor}));
    const ratio=solidContrast(colors.foreground,colors.background);assert.ok(ratio>=4.5);supplementalContrast.push({name:`${theme}-solid-dialog-text`,...colors,ratio,minimum:4.5,scope:'Known solid dialog parent surface; supplemental check for axe overlap incomplete, not blanket contrast acceptance'});
    await page.getByRole('dialog',{name:'Обзор выбранного действия',exact:true}).getByRole('button',{name:'Закрыть',exact:true}).click();
    await page.getByRole('tab',{name:'Настройки',exact:true}).click();
    await page.getByLabel('Как к вам обращаться (обязательно)',{exact:true}).fill('');
    await page.getByRole('button',{name:'Сохранить настройки',exact:true}).click();
    assert.equal(await page.getByLabel('Как к вам обращаться (обязательно)',{exact:true}).evaluate(input=>document.activeElement===input),true);
    await audit(`${theme}-settings-invalid`);
    await page.getByLabel('Как к вам обращаться (обязательно)',{exact:true}).fill('Александра');
    await page.getByLabel('Электронная почта',{exact:true}).fill('kept@example.org');
    await page.getByRole('button',{name:'Сохранить настройки',exact:true}).click();
    await page.getByRole('heading',{name:'Действие не подтверждено'}).waitFor();
    assert.equal(await page.getByLabel('Электронная почта',{exact:true}).inputValue(),'kept@example.org');
    assert.equal((await page.locator('body').innerText()).includes('PRIVATE_SAVE_CANARY'),false);await audit(`${theme}-server-rejection-keeps-values`);
    for(const mode of ['empty','error','loading']){
      await page.evaluate(mode=>window.uiPreview.setMode(mode),mode==='loading'?'empty':mode); // finish a cancellable prior read
      if(mode==='loading'){await page.evaluate(()=>{void window.uiPreview.setMode('loading');});await page.waitForFunction(()=>window.uiPreview.views.every(view=>view.state==='loading'));}
      else await page.waitForFunction(mode=>window.uiPreview.views.every(view=>view.state===mode),mode);
      await page.getByRole('tab',{name:'Каталог',exact:true}).click();await audit(`${theme}-${mode}`);
      await page.evaluate(()=>window.uiPreview.setMode('ready'));await page.waitForFunction(()=>window.uiPreview.views.every(view=>view.state==='ready'));
    }
  }
  checks.push('six injected-service compositions cover loading/empty/error/ready; error text is sanitized; settings rejection preserves draft');
  await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>{void window.uiPreview.setMode('loading');});
  await page.waitForFunction(()=>window.uiPreview.views.every(view=>view.state==='loading'));
  assert.equal(await page.locator('.tp-ui-skeleton>span[aria-hidden]').first().evaluate(element=>getComputedStyle(element).animationName),'none');
  checks.push('reduced motion disables skeleton animation');
  await page.evaluate(()=>window.uiPreview.setMode('ready'));
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);checks.push('no unhandled browser errors or external requests');
  report={passed:true,mode:configuration.mode,served:{vendor:configuration.vendorDirectory,example:configuration.exampleDirectory,reference:configuration.referenceDirectory,html:configuration.htmlPath},externalRequests:external,browser:browser.version(),axe:JSON.parse(await readFile(path.join(configuration.axeDirectory,'package.json'),'utf8')).version,checks,audits,geometry,supplementalContrast,
    limits:['Synthetic local preview domain services; no real auth, payment or Telegram launch','Headless Chrome resize/page-scale/touch and keyboard DOM automation; no physical devices or native keyboards','Screenshots are synthetic review artifacts, not approved visual baselines','axe applicable tagged rules plus incomplete findings retained; no overall WCAG conformance or screen-reader claim']};
}catch(error){report={passed:false,error:String(error),checks,audits,geometry,supplementalContrast};throw error;}
finally{if(report)await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
console.log(JSON.stringify({passed:report.passed,checks:checks.length,axe_states:audits.length,geometry:geometry.length,output}));
