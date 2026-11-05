/** Loopback-only preview, explicit allowlisted files. */
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../../',import.meta.url));
export function createUiPreviewServer(options={}) {
  const vendor=path.resolve(options.vendorDirectory??path.join(root,'packages/typescript/dist'));
  const example=path.resolve(options.exampleDirectory??path.join(root,'examples/ui-kit/dist'));
  const reference=path.resolve(options.referenceDirectory??path.join(root,'examples/ui-kit/dist/reference'));
  const html=path.resolve(options.htmlPath??path.join(root,'examples/ui-kit/index.html'));
  return createServer(async(req,res)=>{
    const route=new URL(req.url,'http://127.0.0.1').pathname;
    let file,type;
    if(route==='/'){file=html;type='text/html; charset=utf-8';}
    else if(/^\/vendor\/[a-z][a-z0-9-]*\.js$/.test(route)){file=path.join(vendor,path.basename(route));type='text/javascript';}
    else if(/^\/vendor\/(styles|tokens)\.css$/.test(route)){file=path.join(vendor,path.basename(route));type='text/css';}
    else if(/^\/example\/(main|screens)\.js$/.test(route)){file=path.join(example,path.basename(route));type='text/javascript';}
    else if(/^\/reference\/(ui|check)\.js$/.test(route)){file=path.join(reference,path.basename(route));type='text/javascript';}
    else{res.writeHead(404).end();return;}
    try{res.setHeader('Content-Type',type);res.setHeader('Cache-Control','no-store');res.end(await readFile(file));}
    catch{res.writeHead(404).end('Build the local package and UI example first.');}
  });
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const server=createUiPreviewServer();server.listen(0,'127.0.0.1',()=>console.log(`http://127.0.0.1:${server.address().port}`));
}
