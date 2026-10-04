import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root=path.dirname(fileURLToPath(import.meta.url));
const library=path.resolve(root,'../../packages/typescript');
const json=(response,status,value)=>{response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});response.end(JSON.stringify(value));};
export function createDemoServer(){
  const bookings=new Map();let nextId=1;let httpWrites=0;
  const server=createServer(async(request,response)=>{
    try{
      const url=new URL(request.url,'http://localhost');
      if(request.method==='POST' && url.pathname==='/api/bookings'){
        httpWrites++;
        let raw=''; for await(const chunk of request){raw+=chunk;if(raw.length>4096){json(response,413,{error:'too-large'});return;}}
        const value=JSON.parse(raw);
        if(!value || typeof value.operation!=='string' || value.operation.length>128 || value.serviceId!=='consultation' || !['10:00','14:30'].includes(value.slotId)){json(response,400,{error:'invalid'});return;}
        const payload=JSON.stringify([value.serviceId,value.slotId]); const prior=bookings.get(value.operation);
        if(prior && prior.payload!==payload){json(response,409,{error:'conflict'});return;}
        const saved=prior ?? {payload,result:{id:nextId++,slot:value.slotId}}; bookings.set(value.operation,saved);
        if(url.searchParams.get('drop')==='1'){response.destroy();return;}
        json(response,200,saved.result);return;
      }
      if(request.method==='GET' && url.pathname.startsWith('/api/bookings/')){
        const saved=bookings.get(decodeURIComponent(url.pathname.slice('/api/bookings/'.length)));
        json(response,saved?200:404,saved?.result??{error:'missing'});return;
      }
      if(request.method!=='GET'){json(response,405,{error:'method'});return;}
      let file;
      if(url.pathname==='/') file=path.join(root,'index.html');
      else if(url.pathname==='/app/index.js') file=path.join(root,'dist/index.js');
      else if(url.pathname==='/lib/styles.css') file=path.join(library,'src/styles.css');
      else if(/^\/lib\/[a-z-]+\.js$/.test(url.pathname)) file=path.join(library,'dist',path.basename(url.pathname));
      else {json(response,404,{error:'missing'});return;}
      const content=await readFile(file);
      response.writeHead(200,{'Content-Type':file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.css')?'text/css; charset=utf-8':'text/javascript; charset=utf-8','Cache-Control':'no-store'});response.end(content);
    }catch{json(response,400,{error:'invalid-request'});}
  });
  // Local test observation only; no public diagnostics endpoint.
  return Object.assign(server,{demoStats:()=>({httpWrites,effects:bookings.size})});
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const server=createDemoServer(); server.listen(4173,'127.0.0.1',()=>process.stdout.write('Demo: http://127.0.0.1:4173\n'));
}
