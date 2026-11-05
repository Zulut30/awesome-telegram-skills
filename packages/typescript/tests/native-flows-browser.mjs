/** Fake SDK + real local Chrome. No native device, Telegram, Serverless or payment acceptance. */
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {createNativePreviewServer} from '../../../examples/native-flows/server.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),output=path.join(root,'output/production-run-2026-11-05/native-flows');
await mkdir(output,{recursive:true});await readFile(path.join(root,'packages/typescript/dist/native-flows.js'));
const server=createNativePreviewServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser,report;const checks=[];
try{
  browser=await chromium.launch({headless:true,...process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{channel:'chrome'}});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],external=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(new URL(request.url()).hostname!=='127.0.0.1')external.push(request.url());});
  await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>window.nativePreview?.active.scope.capabilities().length===15);
  await page.getByRole('button',{name:'Fake MainButton',exact:true}).click();await page.waitForFunction(()=>window.nativePreview.nativePresses===1);checks.push('DOM mirror invokes owned fake native MainButton and loading lifecycle');
  await page.getByLabel('Ответ fake SDK',{exact:true}).selectOption('denied');await page.getByRole('button',{name:'Поделиться контактом',exact:true}).click();
  await page.getByLabel('Контакт вручную',{exact:false}).waitFor();assert.equal(await page.getByLabel('Контакт вручную',{exact:false}).isVisible(),true);await page.getByLabel('Контакт вручную',{exact:false}).fill('+70000000000');checks.push('denied contact consent reveals usable manual input rather than granting identity');
  await page.getByRole('button',{name:'Сменить account scope fixture',exact:true}).click();assert.equal(await page.getByLabel('Контакт вручную',{exact:false}).inputValue(),'');checks.push('account switch clears private DOM draft and invalidates old native/account callbacks');
  await page.getByLabel('Ответ fake SDK',{exact:true}).selectOption('completed');await page.getByRole('button',{name:'Открыть invoice fixture',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('серверная сверка'));assert.equal((await page.locator('#result').innerText()).includes('paid'),false);checks.push('fake invoice paid callback is shown only as server-reconciliation requirement');
  await page.getByRole('button',{name:'Подготовить геолокацию',exact:true}).click();await page.getByRole('button',{name:'Запросить геолокацию',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#result').textContent.startsWith('Location: completed'));
  await page.getByRole('button',{name:'Подготовить биометрию',exact:true}).click();await page.getByRole('button',{name:'Разрешить локальную биометрию',exact:true}).click();await page.getByRole('button',{name:'Локальная биометрия',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#result').textContent.startsWith('Local unlock: completed'));
  assert.equal((await page.locator('body').innerText()).includes('PRIVATE_BIOMETRIC_TOKEN'),false);checks.push('manager init precedes contextual permission/unlock; local token never enters DOM output');
  await page.getByRole('button',{name:'Сохранить device draft',exact:true}).click();await page.getByRole('button',{name:'Прочитать device draft',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#result').textContent.startsWith('Device read: completed'));checks.push('device draft composes scoped write/read without bearer-session behavior');
  await page.getByRole('button',{name:'Запросить download',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('не доказывает запись'));checks.push('download acceptance does not claim filesystem persistence');
  await page.getByLabel('Ответ fake SDK',{exact:true}).selectOption('error');await page.getByRole('button',{name:'Fake Serverless read',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#result').textContent.startsWith('Serverless: failed'));
  assert.equal((await page.locator('body').innerText()).includes('PRIVATE_ENDPOINT'),false);checks.push('Serverless endpoint message/parameters and initData are not rendered');
  await page.getByLabel('Версия fixture',{exact:true}).selectOption('6.4');await page.getByLabel('Ответ fake SDK',{exact:true}).selectOption('completed');
  await page.getByRole('button',{name:'Поделиться контактом',exact:true}).click();await page.getByLabel('Контакт вручную',{exact:false}).waitFor();checks.push('old client method gate provides manual contact fallback');
  for(const platform of ['android','ios','tdesktop','web','unknown'])for(const launch of ['direct','keyboard','attachment','unknown']){
    await page.getByLabel('Платформа fixture',{exact:true}).selectOption(platform);await page.getByLabel('Контекст запуска fixture',{exact:true}).selectOption(launch);
    const matrix=await page.evaluate(()=>window.nativePreview.active.scope.capabilities());assert.ok(matrix.every(row=>row.platform===platform&&row.launch===launch));
    if(platform==='unknown'||launch==='unknown')assert.ok(matrix.every(row=>!row.available));
  }
  checks.push('five fake platforms xfour launch contexts exercise method gates and explicit tested-policy fallback');
  await page.getByLabel('Версия fixture',{exact:true}).selectOption('9.6');await page.getByLabel('Платформа fixture',{exact:true}).selectOption('android');await page.getByLabel('Контекст запуска fixture',{exact:true}).selectOption('direct');
  const file=page.locator('input[type=file]');await file.setInputFiles({name:'preview.png',mimeType:'image/png',buffer:Buffer.from([1,2,3])});
  await page.waitForFunction(()=>document.querySelector('#result').textContent.includes('Выбрано файлов: 1'));assert.equal(await file.getAttribute('capture'),'environment');
  await file.setInputFiles({name:'too-large.png',mimeType:'image/png',buffer:Buffer.alloc(1024*1024+1)});await page.waitForFunction(()=>!document.querySelector('#result').textContent.includes('Выбрано файлов: 1'));
  checks.push('real HTML file input accepts a synthetic File and rejects oversize; capture remains a hint, no OS camera/dialog');
  const reference=await page.evaluate(async()=>{const {referenceFlows}=await import('/reference/flows.js');await referenceFlows(document);return true;});assert.equal(reference,true);checks.push('all21 public reference symbols execute with DOM/listener/timer teardown');
  assert.equal((await page.locator('body').innerText()).includes('PRIVATE_INIT_DATA'),false);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  await page.screenshot({path:path.join(output,'native-flows-fake-browser.png'),fullPage:true});
  report={passed:true,browser:browser.version(),checks,platformLaunchCases:20,externalRequests:external,limits:['All SDK callbacks are synthetic local fixtures','No Telegram/Serverless/payment or signed-session validation','File upload uses synthetic File, not OS picker/camera','Device/native permissions/storage/biometric hardware and screen readers NOT RUN']};
}catch(error){report={passed:false,error:String(error),checks};throw error;}
finally{if(report)await writeFile(path.join(output,'browser-report.json'),JSON.stringify(report,null,2)+'\n');await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
console.log(JSON.stringify(report));
