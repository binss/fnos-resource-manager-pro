const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const source=fs.readFileSync(path.join(__dirname,'../packages/resmonpro/app/ui/gateway.js'),'utf8');
 const {requestJSON}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 const response=(status,data,type='application/json')=>({ok:status>=200&&status<300,status,headers:{get:()=>type},json:async()=>data});
 for(const status of [401,403])await assert.rejects(requestJSON('/api',async()=>response(status,{})),/从飞牛 App 重新打开/);
 await assert.rejects(requestJSON('/api',async()=>response(200,{},'text/html')),/重新打开/);
 await assert.rejects(requestJSON('/api',async()=>response(200,{error:'invalid token'})),/会话已失效/);
 await assert.rejects(requestJSON('/api',async()=>({...response(200,{}),json:async()=>{throw new SyntaxError('bad json')}})),/无法解析/);
 await assert.rejects(requestJSON('/api',async()=>response(200,null)),/无效/);
 const result=await requestJSON('/api',async(url,options)=>{
  assert.equal(url,'/api');assert.equal(options.credentials,'same-origin');assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');
  assert.equal(options.headers,undefined);return response(200,{points:[1]});
 });
 assert.deepEqual(result,{points:[1]});
 await assert.rejects(requestJSON('/api',async()=>{throw new TypeError('redirected')}),/redirected/);
 console.log('PASS: gateway session failures, HTML rejection, redirect rejection and same-origin requests');
})().catch(e=>{console.error(e);process.exitCode=1});
