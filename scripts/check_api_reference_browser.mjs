/** Real Chrome runtime for the documented ESM/DOM examples from a copied consumer. */
import {chromium} from 'playwright';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
const [directory, output] = process.argv.slice(2);
const root = fs.realpathSync(directory); fs.mkdirSync(output, {recursive: false});
const mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css'};
const server = http.createServer((request, response) => {
  try {
    const target = fs.realpathSync(path.join(root, decodeURIComponent(new URL(request.url, 'http://localhost').pathname)));
    if (!target.startsWith(root + path.sep) || !mime[path.extname(target)]) throw Error('Unavailable');
    response.writeHead(200, {'content-type': mime[path.extname(target)] + '; charset=utf-8'}); response.end(fs.readFileSync(target));
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/index.html`;
// CHROME_PATH overrides; otherwise Playwright finds installed Google Chrome on any OS.
const launch = process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH, headless: true} : {channel: 'chrome', headless: true};
let browser;
const results = []; let checks = 0;
try {
  browser = await chromium.launch(launch);
  for (const [name, width, height] of [['phone', 320, 568], ['tablet', 768, 1024], ['desktop', 1440, 900]]) {
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({viewport: {width, height}, colorScheme: theme});
      const failures = [], external = [];
      page.on('pageerror', error => failures.push(error.message));
      page.on('request', request => { if (!request.url().startsWith(new URL(url).origin)) external.push(request.url()); });
      await page.goto(url); await page.waitForFunction(() => window.referenceReport?.passed === true, undefined, {timeout: 20000});
      const proof = await page.evaluate(() => ({report: window.referenceReport,
        css: [...document.styleSheets].some(s => s.href?.endsWith('/dist/styles.css') && s.cssRules.length > 0),
        scripts: [...document.querySelectorAll('script[type="module"]')].length,
        clean: document.querySelectorAll('.tp-shell').length === 0}));
      for (const accepted of [proof.report.cases.length === 6, proof.css, proof.scripts === 1, proof.clean, failures.length === 0, external.length === 0]) {
        if (!accepted) throw Error('Installed reference example browser check failed'); checks++;
      }
      await page.screenshot({path: path.join(output, `${name}-${theme}.png`)});
      results.push({name, width, height, theme, cases: proof.report.cases}); await page.close();
    }
  }
  const report = {passed: true, checks, browser: browser.version(), results,
    scope: 'Installed tarball; six documented ESM/DOM recipes in six viewport/theme cases, synthetic SDK/HTTP, no physical Telegram or backend auth proof'};
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n'); console.log(JSON.stringify(report));
} finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
