/** Explicit loopback-only static fixture server; no reverse proxy or Telegram endpoint. */
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../../',import.meta.url));
export function createNativePreviewServer(){return createServer(async(req,res)=>{
  const route=new URL(req.url,'http://127.0.0.1').pathname;let file,type;
  if(route==='/'){file='examples/native-flows/index.html';type='text/html; charset=utf-8';}
  else if(/^\/vendor\/[a-z][a-z0-9-]*\.js$/.test(route)){file='packages/typescript/dist/'+path.basename(route);type='text/javascript';}
  else if(/^\/vendor\/(styles|tokens)\.css$/.test(route)){file='packages/typescript/dist/'+path.basename(route);type='text/css';}
  else if(/^\/example\/(main|fake-sdk)\.mjs$/.test(route)){file='examples/native-flows/'+path.basename(route);type='text/javascript';}
  else if(/^\/reference\/(flows|check)\.js$/.test(route)){file='output/production-run-2026-11-05/native-flows/reference/'+path.basename(route);type='text/javascript';}
  else{res.writeHead(404).end();return;}
  try{res.setHeader('Content-Type',type);res.setHeader('Cache-Control','no-store');res.end(await readFile(path.join(root,file)));}catch{res.writeHead(404).end('Build the local package first.');}
});}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){const server=createNativePreviewServer();server.listen(0,'127.0.0.1',()=>console.log(`http://127.0.0.1:${server.address().port}`));}
