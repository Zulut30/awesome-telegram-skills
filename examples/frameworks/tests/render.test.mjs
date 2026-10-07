// Each framework renders the bridge snapshot, and its adapter follows a theme change from the client.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToString as renderReact} from 'react-dom/server';
import {createSSRApp, effectScope} from 'vue';
import {renderToString as renderVue} from 'vue/server-renderer';
import {render as renderSvelte} from 'svelte/server';
import {TelegramBridge} from '@awesome-telegram/patterns';
import {useTelegramBridge} from '@awesome-telegram/patterns/vue';
import {telegramBridgeStore} from '@awesome-telegram/patterns/svelte';
import {App as ReactApp} from '../dist/react/App.js';
import {App as VueApp} from '../dist/vue/App.js';
import SvelteApp from '../dist/svelte/App.server.js';
import {demoApp} from '../dist/shared/demo-app.js';

const expected = ['Telegram', 'Scheme: light', 'height: 640', '#ffffff'];

test('React, Vue and Svelte render the same snapshot', async () => {
  for (const [name, html] of [
    ['react', renderReact(createElement(ReactApp, {bridge: new TelegramBridge(demoApp(), undefined)}))],
    ['vue', await renderVue(createSSRApp(VueApp, {bridge: new TelegramBridge(demoApp(), undefined)}))],
    ['svelte', renderSvelte(SvelteApp, {props: {bridge: new TelegramBridge(demoApp(), undefined)}}).body],
  ]) {
    const text = html.replace(/<!--[^]*?-->/g, '');  // React and Svelte mark text boundaries with comments
    for (const fragment of expected) assert.ok(text.includes(fragment), `${name}: ${fragment} in ${html}`);
  }
});

test('Vue and Svelte adapters follow theme changes and release the bridge', () => {
  const app = demoApp(), bridge = new TelegramBridge(app, undefined);
  bridge.start();
  const scope = effectScope();
  const vueSnapshot = scope.run(() => useTelegramBridge(bridge));
  const svelteValues = [];
  const stop = telegramBridgeStore(bridge).subscribe(value => svelteValues.push(value.colorScheme));
  app.colorScheme = 'dark';
  app.fire('themeChanged');
  assert.equal(vueSnapshot.value.colorScheme, 'dark');
  assert.deepEqual(svelteValues, ['light', 'dark']);
  scope.stop();
  stop();
  app.colorScheme = 'light';
  app.fire('themeChanged');
  assert.deepEqual(svelteValues, ['light', 'dark'], 'no updates after unsubscribe');
  bridge.dispose();
});
