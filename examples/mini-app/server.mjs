import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root=path.dirname(fileURLToPath(import.meta.url));
const library=path.resolve(root,'../../packages/typescript');
const json=(response,status,value)=>{response.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});response.end(JSON.stringify(value));};
/** telegramSdk adds the official telegram-web-app.js for opening the demo in real Telegram; tests and CI stay offline. */
export function createDemoServer({telegramSdk=false}={}){
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
      let content=await readFile(file);
      if(file.endsWith('index.html')) content=content.toString('utf8').replace('<!-- telegram-sdk -->',telegramSdk?'<script src="https://telegram.org/js/telegram-web-app.js?64"></script>':'');
      response.writeHead(200,{'Content-Type':file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.css')?'text/css; charset=utf-8':'text/javascript; charset=utf-8','Cache-Control':'no-store'});response.end(content);
    }catch{json(response,400,{error:'invalid-request'});}
  });
  // Local test observation only; no public diagnostics endpoint.
  return Object.assign(server,{demoStats:()=>({httpWrites,effects:bookings.size})});
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  // Loopback by default. Device checks: DEMO_HOST=0.0.0.0 DEMO_TELEGRAM=1 serves the demo with the official SDK to
  // phones on the LAN, opened from a bot menu button in the Telegram test environment (HTTP is allowed there).
  const host=process.env.DEMO_HOST||'127.0.0.1',port=Number(process.env.DEMO_PORT||4173);
  const server=createDemoServer({telegramSdk:process.env.DEMO_TELEGRAM==='1'}); server.listen(port,host,()=>process.stdout.write(`Demo: http://${host}:${port}\n`));
}
