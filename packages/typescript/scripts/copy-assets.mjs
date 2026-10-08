// Copies the stylesheet next to the compiled modules: the published package serves everything from dist.
// styles.css.d.ts lets TypeScript resolve `import '@awesome-telegram/patterns/styles.css'` under
// noUncheckedSideEffectImports without a project-wide `declare module '*.css'`.
import {copyFile, writeFile} from 'node:fs/promises';

const root = new URL('../', import.meta.url);
await copyFile(new URL('src/styles.css', root), new URL('dist/styles.css', root));
await writeFile(new URL('dist/styles.css.d.ts', root), '// Side-effect stylesheet import; it exports nothing.\nexport {};\n');
