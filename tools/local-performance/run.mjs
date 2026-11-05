/** Measure exact installed UI assets, a synthetic dataset and a loopback HTTP fixture. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {lstat, mkdir, readFile, readdir, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';
import {summary} from './metrics.mjs';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const helperSha256 = hash(await readFile(fileURLToPath(import.meta.url)));
const readJson = async name => JSON.parse(await readFile(name, 'utf8'));
const required = ['distributionReport', 'acceptance', 'tarball', 'output'];
export function validate(configuration) {
  assert.ok(configuration && typeof configuration === 'object' && !Array.isArray(configuration));
  assert.ok(Object.keys(configuration).every(key => [...required, 'samples', 'largeItems', 'cycles', 'delayMs'].includes(key)));
  for (const key of required) assert.ok(typeof configuration[key] === 'string' && configuration[key]);
  const settings = {...configuration, samples: configuration.samples ?? 7,
    largeItems: configuration.largeItems ?? 500, cycles: configuration.cycles ?? 100,
    delayMs: configuration.delayMs ?? 150};
  for (const [key, low, high] of [['samples', 3, 30], ['largeItems', 100, 1000],
    ['cycles', 20, 500], ['delayMs', 50, 2000]]) {
    assert.ok(Number.isSafeInteger(settings[key]) && settings[key] >= low && settings[key] <= high);
  }
  return settings;
}
export async function newOutput(name) {
  const output = path.resolve(name);
  for (let part = output; ; part = path.dirname(part)) {
    const information = await lstat(part).catch(error => error.code === 'ENOENT' ? null : Promise.reject(error));
    assert.ok(!information?.isSymbolicLink(), 'Linked output refused');
    if (part === output) assert.equal(information, null, 'Existing output refused');
    if (path.dirname(part) === part) break;
  }
  await mkdir(path.dirname(output), {recursive: true});
  await mkdir(output);
  return output;
}
function tarFiles(compressed) {
  const bytes = gunzipSync(compressed), files = new Map();
  for (let offset = 0; offset + 512 <= bytes.length; ) {
    const header = bytes.subarray(offset, offset + 512);
    if (header.every(value => value === 0)) break;
    const name = header.subarray(0, 100).toString().replace(/\0.*$/, '');
    const size = parseInt(header.subarray(124, 136).toString().replace(/\0.*$/, '').trim(), 8);
    assert.ok(Number.isSafeInteger(size) && size >= 0 && offset + 512 + size <= bytes.length);
    const type = header[156];
    if (type === 0 || type === 48) files.set(name, bytes.subarray(offset + 512, offset + 512 + size));
    offset += 512 + Math.ceil(size / 512) * 512;
  }
  return files;
}
export async function verifiedAssets(configuration) {
  const acceptance = await readJson(configuration.acceptance);
  const bytes = await readFile(configuration.distributionReport);
  assert.equal(hash(bytes), acceptance.report_sha256, 'Distribution report changed');
  const report = JSON.parse(bytes);
  assert.equal(report.passed, true);
  const ui = report.ui_browser;
  assert.equal(ui.library_version, '0.28.0');
  const tgz = await readFile(configuration.tarball);
  assert.equal(hash(tgz), ui.artifact.sha256);
  assert.equal(ui.artifact.sha256, acceptance.artifacts.find(item => item.name.endsWith('.tgz')).sha256);
  const packed = tarFiles(tgz), served = ui.browser.served, assets = new Map(), witnesses = [];
  const installedPackage = await readJson(path.join(served.vendor, '..', 'package.json'));
  assert.equal(installedPackage.version, '0.28.0');
  for (const file of await readdir(served.vendor)) {
    if (!/^[a-z][a-z0-9-]*\.(js|css)$/.test(file)) continue;
    const content = await readFile(path.join(served.vendor, file));
    assert.equal(hash(content), hash(packed.get(`package/dist/${file}`)), 'Installed asset differs from accepted tarball');
    assets.set(`/vendor/${file}`, content);
    witnesses.push({route: `/vendor/${file}`, sha256: hash(content), bound_to_accepted_tarball: true});
  }
  for (const file of ['screens.js', 'main.js']) {
    const content = await readFile(path.join(served.example, file));
    assets.set(`/example/${file}`, content);
    witnesses.push({route: `/example/${file}`, sha256: hash(content),
      scope: 'Retained installed-consumer compiled fixture, separate from library tarball'});
  }
  assets.set('/', await readFile(served.html));
  const fixture = '<!doctype html><html><head><meta charset="UTF-8"><link rel="stylesheet" href="/vendor/styles.css"><link rel="stylesheet" href="/vendor/tokens.css"><script type="importmap">{"imports":{"@awesome-telegram/patterns":"/vendor/index.js"}}</script></head><body><main id="fixture"></main></body></html>';
  assets.set('/fixture', Buffer.from(fixture));
  return {assets, witnesses, provenance: {version: ui.library_version,
    tarball_sha256: hash(tgz), distribution_report_sha256: hash(bytes),
    source_commit: acceptance.source_commit, installed_package: installedPackage.name,
    installed_example_source_sha256: ui.source_sha256}};
}

async function execute(configuration, output) {
  const verified = await verifiedAssets(configuration);
  const dataset = Array.from({length: configuration.largeItems}, (_, index) => ({id: `item-${index}`,
    title: `Local measured item ${index}`, description: 'Synthetic catalog data for a repeatable laboratory profile.', priceLabel: `${index} units`}));
  const report = {passed: false, kind: 'local-installed-ui-performance', created_utc: new Date().toISOString(),
    provenance: verified.provenance, asset_sha256: verified.witnesses,
    profile: {os: os.platform(), release: os.release(), architecture: os.arch(), node: process.version,
      viewport: {width: 390, height: 844}, browser: null, headless: true,
      cpu_throttling: 'none; desktop host', cache: 'fresh contexts; HTTP no-store',
      network: 'Loopback HTTP fixture; explicit server delay only', delay_ms: configuration.delayMs,
      dataset_items: dataset.length, dataset_sha256: hash(JSON.stringify(dataset)),
      repetitions: configuration.samples, remount_cycles: configuration.cycles},
    load: [], large_list: [], interactions: [], network: [], memory: [], checks: [],
    page_errors: [], refused_external_requests: [], requests: [], limits: [
      'No target-device, weak physical device, Telegram WebView, live backend or field performance claim.',
      'Readiness, render and pointer-to-two-frame timing are laboratory observations, not LCP or INP.',
      'HeapProfiler.collectGarbage + Performance metrics measure this renderer JS heap, not process RSS/native/GPU memory.',
      'Finite soak with positive retention control cannot prove absence of all leaks.',
      'CDP frozen/active is a Chrome page lifecycle exercise, not mobile OS background/resume.',
      'Only local fixture writes use an in-memory server ledger; no payment or external message is sent.'
    ]};
  const effects = new Map(), payloads = new Map(), writeAttempts = new Map(), timers = new Set(), serverEvents = [];
  const server = createServer((request, response) => {
    const route = new URL(request.url, 'http://127.0.0.1').pathname;
    serverEvents.push({route, method: request.method, at_ms: performance.now()});
    response.setHeader('Cache-Control', 'no-store');
    const json = (value, code = 200) => {if (!response.destroyed) {response.writeHead(code, {'Content-Type': 'application/json'});response.end(JSON.stringify(value));}};
    if (route === '/api/delayed') {
      const timer = setTimeout(() => {timers.delete(timer);json({ready: true});}, configuration.delayMs);
      timers.add(timer);return;
    }
    if (route === '/api/drop-write' && request.method === 'POST') {
      let body = '';request.on('data', chunk => {body += chunk;if (body.length > 1024) request.destroy();});
      request.on('end', () => {
        const value = JSON.parse(body), payload = JSON.stringify(value);
        writeAttempts.set(value.operation, (writeAttempts.get(value.operation) ?? 0) + 1);
        if (payloads.has(value.operation) && payloads.get(value.operation) !== payload) {json({conflict: true}, 409);return;}
        // This fixture owns server idempotency. One fetch can be replayed by browser/proxy transport.
        if (!effects.has(value.operation)) {payloads.set(value.operation, payload);effects.set(value.operation, 1);}
        request.socket.destroy();
      });return;
    }
    if (route === '/api/operation') {json({operation: '11111111-1111-4111-8111-111111111111', effects: effects.get('11111111-1111-4111-8111-111111111111') ?? 0});return;}
    const asset = verified.assets.get(route);
    if (!asset) {response.writeHead(404).end();return;}
    response.setHeader('Content-Type', route.endsWith('.js') ? 'text/javascript' : route.endsWith('.css') ? 'text/css' : 'text/html; charset=utf-8');response.end(asset);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const context = async () => {
    const value = await browser.newContext({viewport: report.profile.viewport, reducedMotion: 'reduce'});
    await value.route('**/*', route => {
      const request = route.request();
      if (new URL(request.url()).origin !== origin) {report.refused_external_requests.push(request.url());return route.abort();}
      return route.continue();
    });
    value.on('page', page => page.on('pageerror', error => report.page_errors.push(error.message)));
    return value;
  };
  try {
    const {chromium} = await import('playwright');
    browser = await chromium.launch({headless: true, ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {channel: 'chrome'})});
    report.profile.browser = browser.version();
    for (let repetition = 0; repetition < configuration.samples; repetition++) {
      const holder = await context(), page = await holder.newPage();
      await page.addInitScript(() => {const timer = setInterval(() => {
        if (window.uiPreview?.views.every(view => view.state === 'ready')) {window.localReadyObservation = performance.now();clearInterval(timer);}
      }, 1);});
      await page.goto(origin);
      await page.waitForFunction(() => window.localReadyObservation !== undefined);
      report.load.push(await page.evaluate(() => ({ready_observation_ms: window.localReadyObservation,
        navigation_response_ms: performance.getEntriesByType('navigation')[0].responseEnd,
        resources: performance.getEntriesByType('resource').map(item => ({name: new URL(item.name).pathname, transfer_bytes: item.transferSize, duration_ms: item.duration}))})));
      await holder.close();
    }
    const holder = await context(), page = await holder.newPage();
    await page.goto(origin + '/fixture');
    await page.evaluate(async () => {window.ui = await import('/vendor/index.js');window.screens = await import('/example/screens.js');});
    for (let repetition = 0; repetition < configuration.samples; repetition++) {
      const measured = await page.evaluate(async items => {
        const start = performance.now();window.selectedItem = null;window.interaction = null;
        window.view = window.screens.createCatalogScreen(document.querySelector('#fixture'), {scope: 'local-measured-scope', async load() {return {items};}}, id => {
          window.selectedItem = id;requestAnimationFrame(() => requestAnimationFrame(() => {window.interaction = performance.now() - window.pointerStarted;}));
        });
        while (window.view.state === 'loading') await new Promise(resolve => setTimeout(resolve, 0));
        if (window.view.state !== 'ready') throw Error('Large catalog did not become ready');
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const buttons = window.view.element.querySelectorAll('button');
        buttons[buttons.length - 1].addEventListener('pointerdown', () => {window.pointerStarted = performance.now();}, {once: true, capture: true});
        return {render_two_frames_ms: performance.now() - start, rendered_items: buttons.length,
          dom_nodes: window.view.element.querySelectorAll('*').length};
      }, dataset);
      assert.equal(measured.rendered_items, dataset.length);report.large_list.push(measured);
      const actionStart = performance.now();
      await page.getByRole('button', {name: 'Подробнее', exact: true}).last().click();
      await page.waitForFunction(() => window.interaction !== null);
      const interaction = await page.evaluate(() => ({pointer_to_two_frames_ms: window.interaction, selected: window.selectedItem}));
      assert.equal(interaction.selected, dataset.at(-1).id);
      report.interactions.push({...interaction, automation_wall_ms: performance.now() - actionStart});
      await page.evaluate(() => {window.view.dispose();window.view = null;});
    }
    report.checks.push('large list renders every declared item and real pointer selects the last item');
    const cdp = await holder.newCDPSession(page);
    await cdp.send('Performance.enable');
    const memory = async label => {
      await cdp.send('HeapProfiler.collectGarbage');
      const metrics = Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(item => [item.name, item.value]));
      const measured = {label, ...Object.fromEntries(['JSHeapUsedSize', 'JSHeapTotalSize', 'Documents', 'Nodes', 'JSEventListeners'].map(key => [key, metrics[key]]))};
      assert.ok(Object.values(measured).slice(1).every(Number.isFinite));report.memory.push(measured);return measured;
    };
    const cycle = async count => page.evaluate(async repetitions => {
      for (let index = 0; index < repetitions; index++) {
        const view = window.screens.createSettingsScreen(document.querySelector('#fixture'), {scope: 'local-reentry', async load() {return {name: 'Local name', email: 'local@example.org'};}, async save() {}});
        while (view.state === 'loading') await new Promise(resolve => setTimeout(resolve, 0));
        if (view.state !== 'ready') throw Error('Remount not ready');
        view.dispose();if (view.state !== 'disposed' || view.element.isConnected) throw Error('Remount cleanup failed');
      }
      return document.querySelector('#fixture').childElementCount;
    }, count);
    await cycle(10);const baselineMemory = await memory('after-10-warmup-cycles');
    for (let count = 0; count < configuration.cycles; count += 10) {
      assert.equal(await cycle(Math.min(10, configuration.cycles - count)), 0);
      await memory(`after-${Math.min(count + 10, configuration.cycles)}-measured-cycles`);
    }
    const cleanMemory = report.memory.at(-1);
    assert.equal(cleanMemory.JSEventListeners, baselineMemory.JSEventListeners, 'Listener accumulation after disposal');
    report.checks.push('finite repeated mount/dispose leaves no connected screen and post-GC listener count returns to baseline');
    await page.evaluate(async () => {
      window.retainedPositiveControl = [];
      for (let index = 0; index < 20; index++) {
        const view = window.screens.createSettingsScreen(document.querySelector('#fixture'), {scope: 'positive-retention', async load() {return {name: 'Retained', email: 'local@example.org'};}, async save() {}});
        while (view.state === 'loading') await new Promise(resolve => setTimeout(resolve, 0));window.retainedPositiveControl.push(view);
      }
    });
    const retainedMemory = await memory('intentional-retention-positive-control');
    assert.ok(retainedMemory.Nodes > cleanMemory.Nodes && retainedMemory.JSEventListeners > cleanMemory.JSEventListeners);
    await page.evaluate(() => {window.retainedPositiveControl.forEach(view => view.dispose());window.retainedPositiveControl = null;});
    await memory('positive-control-released');
    report.checks.push('memory instrumentation detects intentionally retained live views; positive control is released');
    const network = await page.evaluate(async delayMs => {
      const ui = window.ui, client = new ui.ApiClient({baseUrl: location.origin + '/api/'});
      const decode = value => {if (value?.ready !== true) throw Error('Invalid fixture');return value;};
      const rows = [];
      const start = performance.now();await client.request('delayed', decode, {timeoutMs: delayMs * 4});
      rows.push({case: 'delayed-read', elapsed_ms: performance.now() - start, outcome: 'ready'});
      const timeoutStart = performance.now();
      try {await client.request('delayed', decode, {timeoutMs: 30});throw Error('Timeout not enforced');}
      catch (error) {if (error.kind !== 'timeout' || error.outcome !== 'read-failed') throw error;rows.push({case: 'bounded-read-timeout', elapsed_ms: performance.now() - timeoutStart, outcome: error.outcome});}
      const operation = '11111111-1111-4111-8111-111111111111';
      const pointer = new ui.PendingOperationStore(() => localStorage, {namespace: 'local-performance', scope: 'synthetic-user'});
      if (pointer.reserve(operation).status !== 'reserved') throw Error('Operation not reserved');
      try {await client.request('drop-write', value => value, {method: 'POST', body: {operation}, timeoutMs: delayMs * 4});throw Error('Lost response expected');}
      catch (error) {if (error.outcome !== 'unknown' || !pointer.markUnknown(operation)) throw error;}
      const restored = new ui.PendingOperationStore(() => localStorage, {namespace: 'local-performance', scope: 'synthetic-user'});
      const read = restored.read();if (read.status !== 'restored' || read.value.operation !== operation || read.value.state !== 'unknown') throw Error('Unknown identity lost');
      if (restored.reserve('22222222-2222-4222-8222-222222222222').value.operation !== operation) throw Error('Unknown replaced');
      const verified = await client.request('operation', value => value);
      if (verified.operation !== operation || verified.effects !== 1 || !restored.complete(operation)) throw Error('Reconciliation failed');
      rows.push({case: 'lost-write-reopen-reconcile', operation, effects: verified.effects,
        application_write_calls: 1, application_retries_after_unknown: 0});
      // A never-resolving loader ignoring cancellation must still let the view finish disposal.
      const never = window.screens.createCatalogScreen(document.querySelector('#fixture'), {scope: 'pending-dispose', load() {return new Promise(() => {});}}, () => {});
      const pending = never.reload();const disposeStart = performance.now();never.dispose();
      await Promise.race([pending, new Promise((_, reject) => setTimeout(() => reject(Error('Pending disposal stayed unresolved')), 250))]);
      if (never.state !== 'disposed' || never.element.isConnected) throw Error('Pending disposal failed');
      rows.push({case: 'never-resolving-read-disposed', elapsed_ms: performance.now() - disposeStart, state: never.state});
      // Real HTTP timeout enters error state with retry; it must not remain a spinner.
      window.failureView = window.screens.createCatalogScreen(document.querySelector('#fixture'), {scope: 'timeout-view', async load(context) {await client.request('delayed', decode, {timeoutMs: 30, signal: context.signal});return {items: []};}}, () => {});
      return rows;
    }, configuration.delayMs);
    report.network.push(...network);
    await page.waitForFunction(() => window.failureView.state === 'error');
    assert.equal(await page.getByRole('button', {name: 'Повторить загрузку', exact: true}).count(), 1);
    await page.evaluate(() => {window.failureView.dispose();window.failureView = null;});
    report.checks.push('HTTP delay/timeout finishes; failed read offers retry; lost committed write retains same operation and reconciles exactly one effect');
    const {measureLifecycle} = await import('./lifecycle.mjs');
    report.lifecycle = await measureLifecycle({chromium, executablePath: process.env.CHROME_PATH, origin});
    const lifecycleObserved = report.lifecycle.observed;
    if (lifecycleObserved) report.checks.push('actual Chrome page freeze/resume events preserve local field; native app lifecycle remains untested');
    await holder.close();
    report.calibration = {rule: 'Observed maximum + 3 * median absolute deviation, computed per metric from this run.',
      scope: 'Provisional same-profile laboratory regression sentinel, not a production budget; no independent holdout validation yet.',
      ready_observation_ms: summary(report.load.map(row => row.ready_observation_ms)),
      large_render_two_frames_ms: summary(report.large_list.map(row => row.render_two_frames_ms)),
      pointer_to_two_frames_ms: summary(report.interactions.map(row => row.pointer_to_two_frames_ms))};
    assert.equal(report.page_errors.length, 0);
    assert.equal(report.refused_external_requests.length, 0);
    assert.equal(effects.get('11111111-1111-4111-8111-111111111111'), 1);
    report.measurements_completed = true;
    report.passed = lifecycleObserved;
    report.incomplete = lifecycleObserved ? [] : ['Actual background/resume events were not observed; lifecycle acceptance remains open.'];
  } catch (error) {
    report.failure = {name: error.name, message: error.message};
  } finally {
    if (browser) await browser.close();
    for (const timer of timers) clearTimeout(timer);
    server.closeAllConnections();await new Promise(resolve => server.close(resolve));
    report.server_timers_after_cleanup = 0;
    report.requests = serverEvents.map(({route, method}) => ({route, method}));
    report.server_effects = [...effects.entries()].map(([operation, count]) => ({operation, count,
      transport_attempts: writeAttempts.get(operation)}));
    report.helper_sha256 = helperSha256;
    report.metrics_helper_sha256 = hash(await readFile(new URL('./metrics.mjs', import.meta.url)));
    await writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
  }
  return report;
}

export async function main(argv = process.argv) {
  let output;
  try {
    assert.equal(argv.length, 3, 'Supply one configuration file');
    const configuration = validate(await readJson(argv[2]));
    output = await newOutput(configuration.output);
    const report = await execute(configuration, output);
    console.log(JSON.stringify({passed: report.passed, checks: report.checks.length, memory_checkpoints: report.memory.length}));
    return report.passed ? 0 : 1;
  } catch {
    // Do not echo arbitrary argv/config or caller filesystem contents.
    console.error(JSON.stringify({passed: false, code: 'local-performance-refused-or-failed', output_created: Boolean(output)}));
    return 2;
  }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = await main();
