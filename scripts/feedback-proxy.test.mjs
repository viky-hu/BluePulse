import assert from 'node:assert/strict';
import { test } from 'node:test';
const proxy=await import('../src/app/api/bluepulse/site/feedback/_proxy.ts').catch(()=>null);
test('disabled feedback never contacts a receiver',async()=>{
 assert.ok(proxy,'feedback proxy exists');let calls=0;
 const response=await proxy.proxyFeedback(new Request('http://local/api',{method:'POST',body:'x'}),{enabled:false,apiBase:'http://upstream'},async()=>{calls++;throw Error();});
 assert.equal(response.status,503);assert.equal(calls,0);assert.match(response.headers.get('cache-control'),/no-store/);
});
test('multipart forwarding preserves bytes, strips cookies and retains Retry-After',async()=>{
 assert.ok(proxy);const form=new FormData();form.set('content','文章来源有误');form.set('email','reader@example.com');form.set('pageUrl','/all');form.set('screenshot',new File([new Uint8Array([1,2,3])],'a.png',{type:'image/png'}));
 const request=new Request('http://local/api',{method:'POST',body:form,headers:{cookie:'secret=yes','user-agent':'TestBrowser'}});
 let calls=0;
 const response=await proxy.proxyFeedback(request,{enabled:true,apiBase:'http://upstream'},async(url,init)=>{
  calls++;assert.equal(String(url),'http://upstream/api/v1/site/feedback');assert.equal(new Headers(init.headers).has('cookie'),false);
  const decoded=await new Request('http://upstream',{method:'POST',body:init.body,headers:init.headers}).formData();assert.equal(decoded.get('content'),'文章来源有误');assert.equal(decoded.get('screenshot').size,3);
  return Response.json({error:{code:'rate_limited',message:'稍后重试'}},{status:429,headers:{'Retry-After':'60'}});
 });
 assert.equal(calls,1);assert.equal(response.status,429);assert.equal(response.headers.get('retry-after'),'60');
});
test('oversized and cross-origin uploads are rejected before forwarding',async()=>{
 assert.ok(proxy);const run=req=>proxy.proxyFeedback(req,{enabled:true,apiBase:'http://upstream'},async()=>{throw Error('must not forward');});
 assert.equal((await run(new Request('http://local/api',{method:'POST',body:'x',headers:{'content-type':'multipart/form-data; boundary=abc','content-length':'12582913'}}))).status,413);
 assert.equal((await run(new Request('http://local/api',{method:'POST',body:'x',headers:{'content-type':'multipart/form-data; boundary=abc',origin:'http://evil'}}))).status,403);
});
test('public origin behind a reverse proxy is accepted while a hostile origin is rejected',async()=>{
 assert.ok(proxy);let calls=0;
 const config={enabled:true,apiBase:'http://upstream',publicOrigin:'https://pulse.example'};
 const make=origin=>new Request('http://127.0.0.1:3000/api/bluepulse/site/feedback',{method:'POST',body:'--x--',headers:{host:'pulse.example',origin,'content-type':'multipart/form-data; boundary=x'}});
 const receiver=async()=>{calls++;return Response.json({id:123},{status:201});};
 assert.equal((await proxy.proxyFeedback(make('https://pulse.example'),config,receiver)).status,201);
 assert.equal((await proxy.proxyFeedback(make('https://hostile.example'),config,receiver)).status,403);
 assert.equal(calls,1);
});
