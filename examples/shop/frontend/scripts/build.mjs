import {copyFile,cp,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
await mkdir(path.join(root,'dist/assets/vendor'),{recursive:true});
await copyFile(path.join(root,'index.html'),path.join(root,'dist/index.html'));
await copyFile(path.join(root,'src/styles.css'),path.join(root,'dist/assets/shop.css'));
await cp(path.join(root,'node_modules/@awesome-telegram/patterns/dist'),path.join(root,'dist/assets/vendor'),{recursive:true});
await copyFile(path.join(root,'node_modules/@awesome-telegram/patterns/src/styles.css'),path.join(root,'dist/assets/vendor/styles.css'));
