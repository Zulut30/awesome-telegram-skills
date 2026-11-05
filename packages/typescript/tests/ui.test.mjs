import test from 'node:test';
import assert from 'node:assert/strict';
import {uiUrl,ValidationFailure} from '../dist/index.js';

test('UI navigation accepts same-origin HTTP preview and public HTTPS, preserving URL semantics',()=>{
  assert.equal(uiUrl('/orders?item=7#review','http://127.0.0.1:8080/app'),'http://127.0.0.1:8080/orders?item=7#review');
  assert.equal(uiUrl('https://example.org/help','http://127.0.0.1:8080'),'https://example.org/help');
  assert.equal(uiUrl('../profile','https://app.example/mini/order'),'https://app.example/profile');
});
test('UI navigation rejects script/data/file, remote cleartext, credentials and control characters',()=>{
  for(const input of ['javascript:alert(1)','data:text/html,private','file:///etc/passwd','http://remote.example/',
    'https://user:secret@example.org/',' https://example.org/','https://example.org/a\nb','',null,'x'.repeat(2049)]){
    assert.throws(()=>uiUrl(input,'https://app.example/'),ValidationFailure);
  }
  assert.throws(()=>uiUrl('/safe','not-an-origin'),ValidationFailure);
});
