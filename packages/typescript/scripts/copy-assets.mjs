// Copies the stylesheet next to the compiled modules: the published package serves everything from dist.
// styles.css.d.ts lets TypeScript resolve `import '@awesome-telegram/patterns/styles.css'` under
// noUncheckedSideEffectImports without a project-wide `declare module '*.css'`.
import {copyFile, writeFile} from 'node:fs/promises';

const root = new URL('../', import.meta.url);
for (const name of ['styles.css', 'tokens.css']) {
  await copyFile(new URL(`src/${name}`, root), new URL(`dist/${name}`, root));
  await writeFile(new URL(`dist/${name}.d.ts`, root), '// Side-effect stylesheet import; it exports nothing.\nexport {};\n');
}
