/** Check the documented loopback preview, using the installed starter modules. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';

const base = new URL(process.argv[2]);
assert.equal(base.hostname, '127.0.0.1');
assert.equal(base.protocol, 'http:');
const output = path.resolve(process.argv[3]);
await mkdir(output, {recursive:false});
let browser, checks = 0;
const cases = [];
function verify(value, message) { assert.ok(value, message); checks++; }
try {
  browser = await chromium.launch(process.env.CHROME_PATH
    ? {executablePath:process.env.CHROME_PATH,headless:true}
    : {channel:'chrome',headless:true});
  for (const [name,width,height] of [['phone',320,568],['tablet',768,1024],['desktop',1440,900]]) {
    for (const theme of ['light','dark']) {
      const context = await browser.newContext({viewport:{width,height},colorScheme:theme});
      const page = await context.newPage();
      const errors = [], external = [];
      page.on('pageerror', error => errors.push(error.message));
      // Refuse external traffic, rather than merely detecting it after dispatch.
      await page.route('**/*', async route => {
        if (new URL(route.request().url()).origin !== base.origin) {
          external.push(route.request().url()); await route.abort();
        } else await route.continue();
      });
      await page.goto(base.href);
      await page.getByRole('heading',{name:'Мой Mini App'}).waitFor();
      const appearance = await page.locator('.tp-shell').evaluate(element => ({
        theme:element.dataset.theme,background:getComputedStyle(element).backgroundColor
      }));
      verify(appearance.theme === theme, `${name}/${theme}: selected appearance`);
      verify(appearance.background === (theme === 'dark' ? 'rgb(16, 29, 39)' : 'rgb(241, 245, 250)'), `${name}/${theme}: installed CSS`);
      const action = page.getByRole('button',{name:'Проверить форму'});
      await action.click();
      verify(await page.getByText('Введите имя.',{exact:true}).isVisible(), `${name}/${theme}: invalid input feedback`);
      const field = page.getByLabel('Ваше имя');
      verify(await field.evaluate(element => element === document.activeElement), `${name}/${theme}: invalid input focus`);
      await field.fill('Анна'); await action.click();
      verify((await page.getByRole('status').textContent()).includes('Отправка на сервер не подключена'), `${name}/${theme}: truthful local completion`);
      verify(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}/${theme}: no horizontal overflow`);
      verify(await action.evaluate(element => element.getBoundingClientRect().height >= 44), `${name}/${theme}: touch target`);
      await page.screenshot({path:path.join(output,`${name}-${theme}.png`),fullPage:true});
      await page.emulateMedia({colorScheme:theme === 'light' ? 'dark' : 'light'});
      await page.waitForFunction(previous => document.querySelector('.tp-shell').dataset.theme !== previous, theme);
      verify(await field.inputValue() === 'Анна', `${name}/${theme}: theme change preserves input`);
      verify((await page.getByRole('status').textContent()).includes('Отправка на сервер не подключена'), `${name}/${theme}: theme change preserves feedback`);
      verify(errors.length === 0 && external.length === 0, `${name}/${theme}: no errors or external requests`);
      cases.push({name,width,height,theme,appearance});
      await context.close();
    }
  }
  const report = {passed:true,browser:browser.version(),checks,cases,externalRequests:0,
    scope:'Chrome on installed tarball, six viewport/theme combinations; not physical Telegram device proof'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
} finally { await browser?.close(); }
