// Compiles the Svelte component twice: for the browser (client) and for the server-side render test.
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {compile} from 'svelte/compiler';

const root = new URL('../', import.meta.url);
const source = await readFile(new URL('svelte/App.svelte', root), 'utf8');
await mkdir(new URL('dist/svelte/', root), {recursive: true});
for (const generate of ['client', 'server']) {
  const {js, warnings} = compile(source, {generate, filename: 'App.svelte'});
  if (warnings.length) throw new Error(warnings.map(warning => warning.message).join('\n'));
  await writeFile(new URL(`dist/svelte/App.${generate}.js`, root), js.code);
}
console.log('svelte: client and server builds');
