/** Candidate screenshots only: exact installed assets, deterministic local UI fixture, no baseline approval. */
import {chromium} from 'playwright';
import {createHash} from 'node:crypto';
import {lstat, mkdir, readFile, readdir, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createUiPreviewServer} from '../../examples/ui-kit/server.mjs';

const argv = process.argv.slice(2);
const options = {};
for (let i = 0; i < argv.length; i += 2) {
  if (!['--consumer', '--output'].includes(argv[i]) || !argv[i + 1] || options[argv[i]]) {
    throw Error('Use --consumer <owned-installed-ui> --output <absent-directory>');
  }
  options[argv[i]] = path.resolve(argv[i + 1]);
}
if (!options['--consumer'] || !options['--output']) throw Error('consumer-and-output-required');
const consumer = options['--consumer'], output = options['--output'];
const sha = value => createHash('sha256').update(value).digest('hex');
async function noLinks(file) {
  let cursor = path.resolve(file);
  for (;;) {
    try {if ((await lstat(cursor)).isSymbolicLink()) throw Error('linked-path-refused');}
    catch (error) {if (error.code !== 'ENOENT') throw error;}
    const parent = path.dirname(cursor);
    if (parent === cursor) return;
    cursor = parent;
  }
}
await noLinks(consumer);
await noLinks(output);
await mkdir(output); // Existing output is never replaced; parent must already exist.
const sourceFiles = {};
async function inventory(directory, depth = 0) {
  if (depth > 3) throw Error('consumer-depth-limit');
  for (const entry of await readdir(path.join(consumer, directory), {withFileTypes: true})) {
    const relative = `${directory}/${entry.name}`;
    const file = path.join(consumer, relative);
    await noLinks(file);
    if (entry.isDirectory()) await inventory(relative, depth + 1);
    else {
      if (!entry.isFile() || Object.keys(sourceFiles).length >= 1000) throw Error('owned-consumer-files-required');
      sourceFiles[relative] = sha(await readFile(file));
    }
  }
}
for (const directory of ['vendor', 'example', 'reference']) await inventory(directory);
await noLinks(path.join(consumer, 'index.html'));
sourceFiles['index.html'] = sha(await readFile(path.join(consumer, 'index.html')));
const server = createUiPreviewServer({vendorDirectory: path.join(consumer, 'vendor'),
  exampleDirectory: path.join(consumer, 'example'), referenceDirectory: path.join(consumer, 'reference'),
  htmlPath: path.join(consumer, 'index.html')});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
const report = {schema_version: 1, kind: 'visual-capture', review_status: 'awaiting-human-review',
  product_acceptance: false, human_review_verified: false,
  source: {kind: 'caller-supplied installed UI assets; hashes, not an installation attestation', files: sourceFiles},
  environment: {os: `${os.platform()} ${os.release()} ${os.arch()}`, browser: '', playwright: '',
    device_scale_factor: 1, locale: 'ru-RU', timezone: 'UTC', reduced_motion: 'reduce',
    animation_policy: 'screenshot animations disabled; two consecutive identical images',
    data: 'explicit ui-kit educational fixture; no identity, payment or live request',
    clock: 'no date or changing time rendered in this fixture'}, cases: [], errors: [], external_requests: []};
const names = [['catalog', 'Каталог'], ['product', 'Товар'], ['cart', 'Корзина'],
  ['profile', 'Профиль'], ['settings', 'Настройки'], ['booking', 'Запись']];
try {
  browser = await chromium.launch({headless: true,
    ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {channel: 'chrome'})});
  report.environment.browser = browser.version();
  report.environment.playwright = JSON.parse(await readFile(new URL('../../node_modules/playwright/package.json', import.meta.url), 'utf8')).version;
  for (const [width, height] of [[320, 568], [768, 1024], [1280, 800]]) for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({viewport: {width, height}, deviceScaleFactor: 1,
      locale: 'ru-RU', timezoneId: 'UTC', reducedMotion: 'reduce', colorScheme: theme});
    const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    await page.route('**/*', route => {
      if (route.request().url().startsWith(origin + '/')) return route.continue();
      report.external_requests.push(route.request().url());
      return route.abort();
    });
    await page.goto(origin);
    await page.waitForFunction(() => window.uiPreview?.views.every(v => v.state === 'ready'));
    await page.evaluate(() => document.fonts.ready);
    if (theme === 'dark') await page.getByRole('button', {name: 'Переключить тему превью', exact: true}).click();
    const font = await page.evaluate(() => getComputedStyle(window.uiPreview.shell.element).fontFamily);
    if (report.environment.font_family && report.environment.font_family !== font) throw Error('font-environment-changed');
    report.environment.font_family = font;
    for (const state of ['ready', 'loading', 'empty', 'error']) {
      // The fixture exposes controlled Promise outcomes; no production hook or timeout guesses.
      await page.evaluate(state => {void window.uiPreview.setMode(state);}, state);
      await page.waitForFunction(state => window.uiPreview.views.every(v => v.state === state), state);
      for (const [screen, label] of names) {
        await page.getByRole('tab', {name: label, exact: true}).click();
        await page.mouse.move(0, 0);
        await page.evaluate(() => document.fonts.ready);
        const target = page.getByRole('tabpanel').locator('.tp-ui-screen');
        let previous = await target.screenshot({animations: 'disabled'}), image, stable = false;
        for (let attempt = 0; attempt < 5; attempt++) {
          image = await target.screenshot({animations: 'disabled'});
          if (image.equals(previous)) {stable = true; break;}
          previous = image;
        }
        if (!stable) throw Error('capture-never-stabilized');
        const id = `${screen}-${state}-${theme}-${width}x${height}`;
        const name = `${id}.png`;
        await writeFile(path.join(output, name), image, {flag: 'wx'});
        report.cases.push({id, screen, state, theme, locale: 'ru-RU', viewport: {width, height},
          width: image.readUInt32BE(16), height: image.readUInt32BE(20), image: name, sha256: sha(image),
          stable_pair_sha256: [sha(previous), sha(image)], capture_area: 'visible composition element; shell/tabs not included'});
      }
    }
    await context.close();
  }
  if (report.errors.length || report.external_requests.length) throw Error('capture-errors-or-external-network');
  await writeFile(path.join(output, 'capture.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({captured: report.cases.length, product_acceptance: false,
    human_review_verified: false, output, capture_sha256: sha(await readFile(path.join(output, 'capture.json')))}));
} finally {
  if (browser) await browser.close();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
