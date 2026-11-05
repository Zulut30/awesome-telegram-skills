/** Verify that the rendered site and its explicit preview/production manifest agree in a real browser. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const site=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
const manifest=JSON.parse(await readFile(path.join(site,'site-manifest.json'),'utf8'));
assert.ok(['preview','production'].includes(manifest.mode));
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'};
const server=createServer(async(request,response)=>{
  try{
    const route=decodeURIComponent(new URL(request.url,'http://127.0.0.1').pathname);
    const file=path.resolve(site,'.'+(route.endsWith('/')?route+'index.html':route));
    if(!file.startsWith(site+path.sep)){response.writeHead(403).end();return;}
    const content=await readFile(file);
    response.writeHead(200,{'Content-Type':types[path.extname(file)]??'text/plain'});response.end(content);
  }catch{response.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
  browser=await chromium.launch({headless:true,...(process.env.DOCS_BROWSER==='chromium'?{}:process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{channel:'chrome'})});
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const banner=page.locator('[data-build-mode="preview"]');
  if(manifest.mode==='preview'){
    assert.equal(await banner.count(),1);assert.equal(await banner.isVisible(),true);
    assert.match(await banner.textContent(),/режим разработки/);
    assert.equal(await page.locator('meta[name=robots]').getAttribute('content'),'noindex,nofollow');
    assert.equal(await page.getByText(`Принятая версия ${manifest.version}, experimental.`,{exact:true}).count(),0);
  }else{
    assert.equal(manifest.accepted_version,true);assert.equal(await banner.count(),0);
    assert.equal(await page.locator('meta[name=robots]').count(),0);
  }
  assert.deepEqual(errors,[]);
  await mkdir(output,{recursive:true});
  await page.screenshot({path:path.join(output,'build-mode.png'),fullPage:false});
  const report={passed:true,mode:manifest.mode,version:manifest.version,browser:browser.version(),preview_notice_visible:manifest.mode==='preview'};
  await writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}finally{await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
