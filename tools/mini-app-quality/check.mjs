/** Lighthouse, bundle and axe gates for the Mini App demo (examples/mini-app); exits 1 when a budget is crossed.
 *
 *   npm ci && npm run build                     # repository root: builds the demo and the library
 *   npm ci --prefix tools/mini-app-quality
 *   node tools/mini-app-quality/check.mjs [output-dir]
 *
 * Lighthouse runs its default mobile profile (simulated throttling) several times and takes the median score.
 * Budgets live in budgets.json. CHROME_PATH selects the browser; otherwise an installed Chrome is used.
 */
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import * as chromeLauncher from 'chrome-launcher';
import lighthouse from 'lighthouse';
import {chromium} from 'playwright';
import {createDemoServer} from '../../examples/mini-app/server.mjs';
import {evaluate, median} from './gates.mjs';

const here = path.dirname(fileURLToPath(import.meta.url)), root = path.resolve(here, '../..');
const budgets = JSON.parse(await readFile(path.join(here, 'budgets.json'), 'utf8'));
const output = path.resolve(process.argv[2] ?? path.join(root, 'output/mini-app-quality'));
await mkdir(output, {recursive: true});
await readFile(path.join(root, 'examples/mini-app/dist/index.js')).catch(() => {
  throw new Error('Build the demo first: npm run build at the repository root');
});
const axeSource = await readFile(path.join(here, 'node_modules/axe-core/axe.min.js'), 'utf8');
const chromePath = process.env.CHROME_PATH;
// Root containers need --no-sandbox; regular CI users keep the sandbox.
const sandbox = process.getuid?.() === 0 ? ['--no-sandbox'] : [];

const server = createDemoServer();
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}/`;
const categories = Object.keys(budgets.lighthouse.min_scores);
const runs = [];
let chrome, browser;
try {
  chrome = await chromeLauncher.launch({chromePath, chromeFlags: ['--headless=new', ...sandbox]});
  for (let run = 0; run < budgets.lighthouse.runs; run++) {
    const result = await lighthouse(base, {port: chrome.port, output: 'json', logLevel: 'error', onlyCategories: categories});
    runs.push(result.lhr);
  }
  await chrome.kill();chrome = undefined;

  browser = await chromium.launch(chromePath ? {executablePath: chromePath, headless: true, args: sandbox}
    : {channel: 'chrome', headless: true, args: sandbox});
  // Bundle: every script and stylesheet the first load fetches, uncompressed (the demo server sends no gzip).
  const bundle = {script_bytes: 0, stylesheet_bytes: 0, requests: 0, files: []};
  {
    const page = await browser.newPage(), pending = [];
    page.on('response', response => pending.push((async () => {
      bundle.requests++;
      const type = response.request().resourceType();
      if (type !== 'script' && type !== 'stylesheet') return;
      const bytes = (await response.body()).length;
      bundle[type === 'script' ? 'script_bytes' : 'stylesheet_bytes'] += bytes;
      bundle.files.push({url: new URL(response.url()).pathname, type, bytes});
    })()));
    await page.goto(base, {waitUntil: 'networkidle'});
    await page.getByRole('heading', {name: 'Запись на консультацию'}).waitFor();
    await Promise.all(pending);await page.close();
    bundle.files.sort((a, b) => b.bytes - a.bytes);
  }

  // axe: phone and desktop, light and dark, before and after a validation error.
  const axe = [];
  async function audit(page, name) {
    if (!await page.evaluate(() => 'axe' in window)) await page.addScriptTag({content: axeSource});
    const result = await page.evaluate(tags => window.axe.run(document, {runOnly: {type: 'tag', values: tags}}), budgets.axe.tags);
    axe.push({name, passes: result.passes.length, violations: result.violations.map(item => ({id: item.id, impact: item.impact, nodes: item.nodes.length, help: item.help}))});
  }
  for (const [device, width, height] of [['phone', 320, 640], ['desktop', 1440, 900]]) for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({viewport: {width, height}, colorScheme: theme});
    const page = await context.newPage();
    await page.goto(base);await page.getByRole('heading', {name: 'Запись на консультацию'}).waitFor();
    if (theme === 'dark') await page.getByRole('button', {name: 'Сменить тему'}).click();
    await audit(page, `${device}-${theme}`);
    await page.getByRole('button', {name: '10:00', exact: true}).click();
    await page.getByLabel('Ваше имя', {exact: true}).fill('Проверка доступности');
    await page.getByLabel('Телефон', {exact: true}).fill('bad-number');
    await page.getByRole('button', {name: 'Подтвердить запись'}).click();
    await audit(page, `${device}-${theme}-invalid`);
    await context.close();
  }

  const scores = Object.fromEntries(categories.map(category => [category, median(runs.map(lhr => lhr.categories[category].score))]));
  const measured = {lighthouse: scores, bundle, axe};
  const failures = evaluate(measured, budgets);
  const representative = runs.find(lhr => lhr.categories.performance.score === scores.performance) ?? runs[0];
  const metrics = Object.fromEntries(['first-contentful-paint', 'largest-contentful-paint', 'total-blocking-time', 'cumulative-layout-shift', 'speed-index']
    .map(id => [id, representative.audits[id]?.numericValue ?? null]));
  await writeFile(path.join(output, 'lighthouse.json'), JSON.stringify(representative));
  const report = {passed: failures.length === 0, failures, budgets, lighthouse: {median: scores, runs: runs.map(lhr => Object.fromEntries(categories.map(category => [category, lhr.categories[category].score]))),
    version: representative.lighthouseVersion, form_factor: representative.configSettings.formFactor, throttling: representative.configSettings.throttlingMethod, metrics},
    bundle, axe: {version: JSON.parse(await readFile(path.join(here, 'node_modules/axe-core/package.json'), 'utf8')).version, states: axe},
    browser: browser.version(), scope: 'Local demo server without compression; Lighthouse mobile profile with simulated throttling; not a real device or Telegram WebView'};
  await writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: report.passed, failures, lighthouse: scores, bundle: {script_bytes: bundle.script_bytes, stylesheet_bytes: bundle.stylesheet_bytes, requests: bundle.requests}, axe_states: axe.length}));
  if (failures.length) process.exitCode = 1;
} finally {
  await chrome?.kill();
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
