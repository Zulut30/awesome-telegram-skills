/** Targeted lifecycle replay on accepted assets, with no Playwright focus capture. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {ownedChrome} from './owned-browser.mjs';

export async function measureLifecycle({chromium, executablePath, origin}) {
  const owned = await ownedChrome(chromium, executablePath, true);
  const result = {observed: false, status: 'not-observed', profile: owned.profile,
    browser: owned.browser.version(), mechanism: 'Owned fresh Chrome/default context, connectOverCDP noDefaults:true; two owned tabs; real Page frozen/active events.',
    limit: 'Desktop Chrome lifecycle exercise only; not mobile OS or Telegram WebView acceptance.',
    external_requests: [], page_errors: []};
  try {
    const context = owned.browser.contexts()[0];
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin !== origin) {result.external_requests.push(route.request().url());return route.abort();}
      return route.continue();
    });
    const page = context.pages()[0] ?? await context.newPage();
    page.on('pageerror', error => result.page_errors.push(error.message));
    await page.setViewportSize({width: 390, height: 844});
    await page.goto(origin + '/fixture');
    await page.evaluate(async () => {
      window.ui = await import('/vendor/index.js');window.resumeEvents = [];
      for (const name of ['freeze', 'resume', 'visibilitychange']) document.addEventListener(name, event => {
        window.resumeEvents.push({name, trusted: event.isTrusted, visibility: document.visibilityState, at_ms: performance.now()});
      });
      window.resumeField = window.ui.createUiField(document, {label: 'Resume draft', value: 'Preserved local draft'});
      document.querySelector('#fixture').append(window.resumeField.root);
    });
    const other = await context.newPage();await other.goto(origin + '/fixture');await other.bringToFront();
    result.before = await page.evaluate(() => ({visibility: document.visibilityState, focused: document.hasFocus()}));
    const session = await context.newCDPSession(page);
    result.browser_protocol = await session.send('Browser.getVersion');
    await session.send('Page.setWebLifecycleState', {state: 'frozen'});
    await new Promise(resolve => setTimeout(resolve, 100));
    await session.send('Page.setWebLifecycleState', {state: 'active'});
    // Hidden pages do not run requestAnimationFrame; use bounded interval polling.
    await page.waitForFunction(() => window.resumeEvents.some(event => event.name === 'resume'), null,
      {timeout: 1500, polling: 25}).catch(() => {});
    await page.bringToFront();
    result.after = await page.evaluate(() => ({events: window.resumeEvents, value: window.resumeField.input.value,
      visibility: document.visibilityState, focused: document.hasFocus()}));
    const events = result.after.events;
    result.observed = result.before.visibility === 'hidden' &&
      events.some(event => event.name === 'freeze' && event.trusted) &&
      events.some(event => event.name === 'resume' && event.trusted) &&
      result.after.value === 'Preserved local draft';
    assert.equal(result.external_requests.length, 0);assert.equal(result.page_errors.length, 0);
    await page.evaluate(() => {window.resumeField.dispose();window.resumeField.root.remove();window.resumeField = null;});
  } finally {result.cleanup = await owned.close();}
  result.observed = result.observed && result.cleanup.owned_process_exited && result.cleanup.owned_profile_removed;
  result.status = result.observed ? 'observed' : 'not-observed';
  return result;
}

async function main() {
  let server, report, output;
  try {
    assert.equal(process.argv.length, 3, 'Supply one configuration file');
    const {validate, newOutput, verifiedAssets} = await import('./run.mjs');
    const configuration = validate(JSON.parse(await readFile(process.argv[2], 'utf8')));
    output = await newOutput(configuration.output);
    const verified = await verifiedAssets(configuration), requests = [];
    server = createServer((request, response) => {
      const route = new URL(request.url, 'http://127.0.0.1').pathname;requests.push(route);
      const asset = verified.assets.get(route);
      if (!asset) {response.writeHead(404).end();return;}
      response.setHeader('Cache-Control', 'no-store');
      response.setHeader('Content-Type', route.endsWith('.js') ? 'text/javascript' : route.endsWith('.css') ? 'text/css' : 'text/html; charset=utf-8');response.end(asset);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const {chromium} = await import('playwright');
    const result = await measureLifecycle({chromium, executablePath: process.env.CHROME_PATH,
      origin: `http://127.0.0.1:${server.address().port}`});
    report = {kind: 'targeted-installed-ui-lifecycle', passed: result.observed,
      provenance: verified.provenance, asset_sha256: verified.witnesses, result, requests,
      source_sha256: Object.fromEntries(await Promise.all(['lifecycle.mjs', 'owned-browser.mjs', 'run.mjs'].map(async name =>
        [name, createHash('sha256').update(await readFile(new URL(name, import.meta.url))).digest('hex')])))};
    await writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
    console.log(JSON.stringify({passed: report.passed, status: result.status, cleanup: result.cleanup}));
    return report.passed ? 0 : 1;
  } catch {
    console.error(JSON.stringify({passed: false, code: 'targeted-lifecycle-refused-or-failed', output_created: Boolean(output)}));return 2;
  } finally {if (server) {server.closeAllConnections();await new Promise(resolve => server.close(resolve));}}
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = await main();
