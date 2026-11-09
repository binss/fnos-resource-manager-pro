"""Adapt the installed fnOS frontend client without distributing system code.

The browser uses its existing fnOS login. No NAS password/token is copied into
this application. Fail closed if the installed frontend layout changes.
"""
from pathlib import Path
import json
import re

WEB = Path('/usr/trim/www')
ENTRY = '/cgi/ThirdParty/resmonpro/index.cgi/fan'
RELATIVE = re.compile(r'''(["'`])\./([\w.$-]+\.js)\1''')


def asset(web=WEB):
    page = (web / 'index.html').read_text()
    names = re.findall(r'(?:src|href)=["\'](/assets/index-[\w-]+\.js)["\']', page)
    if len(set(names)) != 1:
        raise ValueError('Unsupported fnOS entry point')
    return names[0]


def import_map(web=WEB):
    return json.dumps({'imports': {asset(web): ENTRY + '/api/fnos-native.js'}}, separators=(',', ':'))


def module(web=WEB):
    code = (web / asset(web).lstrip('/')).read_text()
    # These identifiers were verified against this NAS's installed frontend.
    required = ('Z as $c', 'getFanMode:`appcgi.sysinfo.getFanMode`',
                'setFanMode:`appcgi.sysinfo.setFanMode`', 'var Z=new yHe(aZ',
                'eZ=async()=>{await $X.run()}')
    if not all(value in code for value in required):
        raise ValueError('Unsupported fnOS client version')
    start = code.find('Er.createRoot(document.getElementById(`root`)).render(')
    end = code.find(';export{', start)
    if start < 0 or end < start or code.count('Er.createRoot(document.getElementById(`root`)).render(') != 1:
        raise ValueError('Unsupported fnOS bootstrap')
    # Retain all exports for cyclic system dependencies; suppress only desktop mounting.
    code = code[:start] + 'void 0' + code[end:]
    # The resource app gateway already authenticated this page. Do not run the
    # desktop client's cookie cleanup or login / refresh-token workflow.
    cleanup = '!jq&&!xY()&&(AY(),jY(),DY=void 0);'
    if code.count(cleanup) != 1:
        raise ValueError('Unsupported fnOS authentication bootstrap')
    code = code.replace(cleanup, 'void 0;', 1)
    code = RELATIVE.sub(lambda match: match[1] + '/assets/' + match[2] + match[1], code)
    code += '''
let fanClientPromise;
function fanClient() {
 if (fanClientPromise) return fanClientPromise;
 fanClientPromise=(async()=>{
  const socket=new EG(`${v}?type=resmonpro-fan`,{timeout:8000,isMain:false,genReqId:RK,
    preflight:async()=>{
     await XX(socket,true);
     // Authenticate this socket using only the current same-origin session.
     // Never start login, clear credentials, or redirect the fan frame.
     const reply=await socket.send({req:aK.authToken,...(xY()&&OY()?{token:OY()}:{})},
       {skipPreflight:true,timeout:8000});
     if(reply?.result==='fail'||reply?.errno)throw new Error('当前应用会话无法读取风扇，请从飞牛 App 重新打开资源管理 Pro。');
    }});
  socket.useReq(CX);
  socket.useRes(response=>{if(response.data?.token) socket.token=response.data.token;return response;});
  socket.on(SG.CLOSE,()=>{fanClientPromise=undefined;});
  addEventListener('pagehide',()=>{try{socket.close();}catch{}},{once:true});
  try { await socket.init(); } catch(error) { try { socket.close(); } catch {} throw error; }
  return new yHe(socket,{useIntlLogin:false});
 })().catch(error=>{fanClientPromise=undefined;throw error;});
 return fanClientPromise;
}
function fanResult(result) {
 if (!result || result.result==='fail' || (result.errno && result.errno!==0))
  throw new Error('飞牛未完成风扇请求，请检查登录状态和管理员权限。');
 return result.data ?? {};
}
export async function readNasFan() {
 const client=await fanClient();
 const feature=fanResult(await client.sysinfo.getTrimMachineFeature());
 const supported=!!(feature.cpuFanControl || feature.sysFanControl);
 if (!supported) return {supported:false,mode:null,rpm:[]};
 const mode=fanResult(await client.sysinfo.getFanMode());
 let rpm=[];
 try {
  const data=fanResult(await client.resmo.sysFan());
  rpm=(Array.isArray(data.fanSpeed)?data.fanSpeed:[]).filter(x=>Number.isFinite(x)&&x>=0);
  if (!rpm.length && Number.isFinite(data.speed) && data.speed>=0) rpm=[data.speed];
 } catch { /* A missing tachometer must not hide available mode control. */ }
 if (!rpm.length) {
  try {
   const data=fanResult(await client.resmo.cpu());
   const speed=(data.cpu ?? data).fan?.fanSpeed;
   rpm=(Array.isArray(speed)?speed:[speed]).filter(x=>Number.isFinite(x)&&x>=0);
  } catch { /* Some devices expose no CPU tachometer. */ }
 }
 return {supported:true,mode:[1,2,3].includes(mode.mode)?mode.mode:null,rpm};
}
export async function setNasFanMode(mode) {
 if (!Number.isInteger(mode) || ![1,2,3].includes(mode)) throw new Error('无效的飞牛风扇模式。');
 const current=await readNasFan();
 if (!current.supported) throw new Error('当前设备未开放原生风扇调节。');
 const client=await fanClient();
 fanResult(await client.sysinfo.setFanMode({mode}));
 const result=await readNasFan();
 if(result.mode!==mode) throw new Error('指令已发送，但模式回读未确认，请刷新后检查。');
 return result;
}
'''
    return code
