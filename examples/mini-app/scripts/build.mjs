/** Browser bundles after strict tsc. Public /lib ESM remains available for explicit consumer fixtures.
 * esbuild docs checked 2026-11-05: https://esbuild.github.io/api/#tree-shaking and #keep-names
 * Types are checked by the preceding tsc command; esbuild only transforms/bundles JavaScript.
 * TypeScript isolation guidance: https://esbuild.github.io/content-types/#typescript-caveats
 */
import {build,version} from 'esbuild';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const result=await build({
  absWorkingDir:root,
  entryPoints:['src/index.ts','src/native-recipes.ts'],
  outdir:'dist',bundle:true,format:'esm',platform:'browser',target:'es2022',
  minify:true,treeShaking:true,keepNames:true,legalComments:'inline',metafile:true,
  logLevel:'info',
});
await mkdir(path.join(root,'dist'),{recursive:true});
await writeFile(path.join(root,'dist/build-meta.json'),JSON.stringify({esbuild:version,...result.metafile},null,2)+'\n');
