"""Use the installed fnOS resource manager inside the Pro application window."""
import json
import re
from pathlib import Path

WEB = Path("/usr/trim/www")
ENTRY = "/cgi/ThirdParty/resmonpro/index.cgi"
ASSETS = {
    "index.js": "index-D1auxRov.js",
    "resource.js": "ResourceMonitor-D36dIPD-.js",
    "cpu-chart.js": "CPUChart-0mxysVWh.js",
    "memory-chart.js": "MemChart-zb089-Xa.js",
    "network-chart.js": "NetChart-CGIW6U7D.js",
    "gpu-chart.js": "GPUChart-nl4G5f1C.js",
    "layout.js": "AppLayoutTabs-N7iHeqJH.js",
    "appview.js": "appview-Dj9klTDM.js",
}
MODULES = {f"/assets/{file}": f"{ENTRY}/native/{route}" for route, file in ASSETS.items()}
RELATIVE_IMPORT = re.compile(r"""(["'`])\./([\w.$-]+\.js)\1""")


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Installed fnOS frontend has a different structure")
    return text.replace(old, new, 1)


def module(name):
    code = (WEB / "assets" / ASSETS[name]).read_text()
    code = RELATIVE_IMPORT.sub(lambda match: f'{match[1]}/assets/{match[2]}{match[1]}', code)
    if name == "index.js":
        code = replace_one(code, 'path:`appview`', f'path:`{ENTRY.lstrip("/")}/native`')
        shell = """function ProShell({children}) {
 const [size,setSize]=P.useState(()=>({width:innerWidth,height:innerHeight,maximized:false}));
 P.useEffect(()=>{const resize=()=>setSize({width:innerWidth,height:innerHeight,maximized:false});addEventListener('resize',resize);return()=>removeEventListener('resize',resize)},[]);
 return F.jsx(PQ,{id:'resmonpro',name:'资源管理 Pro',activated:true,children:F.jsx(U0e,{data:size,children:F.jsx('div',{className:'pro-shell',children})})});
}
export {ProShell};
"""
        code += shell
    elif name == "appview.js":
        start = code.index('k=({app:e,parsed:t,onClose:n})=>')
        end = code.index(',A=({app:e,parsed:t,onClose:n,taskWindows:', start)
        code = code[:start] + 'k=({app:e,parsed:t})=>(0,x.jsx)(ProShell,{children:O(e,t)})' + code[end:]
        code = f'import {{ProShell}} from "{ENTRY}/native/index.js";\n' + code
    elif name == "layout.js":
        code = replace_one(code, 'minWidth:1100', 'minWidth:0')
        code = replace_one(code, 'className:`flex size-full flex-row`,ref:t',
                           'className:`pro-app-tabs flex size-full flex-row`,ref:t')
        code = replace_one(code, 'className:`flex flex-col pt-2`,children:',
                           'className:`pro-app-navigation flex flex-col pt-2`,children:')
        code = replace_one(code, 'className:`w-0 flex-1 overflow-auto`,style:',
                           'className:`pro-app-content w-0 flex-1 overflow-auto`,style:')
    elif name == "resource.js":
        code = code.replace('(0,R.jsx)(ge,{', '(0,R.jsx)(ProTable,{')
        code = replace_one(code, '(0,R.jsx)(dr,{})',
                           '(0,R.jsx)(`div`,{className:`pro-overview-disks`,children:(0,R.jsx)(dr,{})})')
        code = replace_one(code, 'wr=()=>(0,R.jsxs)(Qe,', 'wr=()=>(0,R.jsxs)(ProOverviewGrid,')
        code = replace_one(code, 'className:`gap-4 pb-7`,minWidthCount:3',
                           'className:`pro-overview-grid gap-4 pb-7`,minWidthCount:3')
        code = replace_one(code, 'M(`flex flex-col items-start overflow-hidden rounded-2xl',
                           'M(`pro-overview-card flex flex-col items-start overflow-hidden rounded-2xl')
        code = replace_one(code, 'className:`flex h-full flex-col justify-start gap-5 overflow-hidden`,children:[(0,R.jsx)(Dt,{title:e(`performance.cpu.title`)',
                           'className:`pro-cpu-panel flex h-full flex-col justify-start gap-5 overflow-hidden`,children:[(0,R.jsx)(Dt,{title:e(`performance.cpu.title`)')
        code = replace_one(code, 'className:`flex flex-wrap items-center gap-x-10 gap-y-5 overflow-hidden py-3`,children:[(0,R.jsx)(z,{title:e(`performance.cpu.utilization`)',
                           'className:`pro-cpu-metrics flex flex-wrap items-center gap-x-10 gap-y-5 overflow-hidden py-3`,children:[(0,R.jsx)(z,{title:e(`performance.cpu.utilization`)')
        code = replace_one(code, 'className:`size-full overscroll-x-auto`',
                           'className:`pro-resource-tabs size-full overscroll-x-auto`')
        code = replace_one(code, 'component:ri}];return',
                           'component:ri},{icon:ProTemperatureIcon,key:`hardware-temperature`,title:`硬件温度`,component:ProTemperature}];return')
        code = replace_one(code, 'Or=()=>(0,R.jsx)(ze,{component:Dr})',
                           'Or=()=>(0,R.jsx)(ze,{component:ProPerformance})')
        code = replace_one(code, '(0,R.jsx)(Ht,{data:n,num:c})', '(0,R.jsx)(ProCPUChart,{data:n,num:c})')
        code = replace_one(code, '(0,R.jsx)(ln,{data:t,type:r})', '(0,R.jsx)(ProMemoryChart,{data:t,type:r})')
        code = replace_one(code, 'Vt=()=>(0,L.useContext)(zt)', 'Vt=()=>ProUseCPU((0,L.useContext)(zt))')
        code = replace_one(code, 'Xt=()=>(0,L.useContext)(Jt)', 'Xt=()=>ProUseGPU((0,L.useContext)(Jt))')
        code = replace_one(code, '{...n,time:i}', '{...n,time:n.proTime??i}')
        code = replace_one(code, 'Mn=()=>(0,L.useContext)(An)', 'Mn=()=>ProUseNetwork((0,L.useContext)(An))')
        code = replace_one(code, 'sn=()=>(0,L.useContext)(an)', 'sn=()=>ProUseMemory((0,L.useContext)(an))')
        code = replace_one(code, "export{ii as default};",
            "const {Temperature:ProTemperature,TemperatureIcon:ProTemperatureIcon,useCPUInfo:ProUseCPU,useMemoryInfo:ProUseMemory,useNetworkInfo:ProUseNetwork,useGPUInfo:ProUseGPU,Performance:ProPerformance,CPUChart:ProCPUChart,MemoryChart:ProMemoryChart,Overview:ProOverview,OverviewGrid:ProOverviewGrid,Table:ProTable} = createPerformance(L,{Performance:Dr,CPUChart:Ht,MemoryChart:ln,Overview:Tr,NativeGrid:Qe,NativeTable:ge,useNativeCPU:Vt,useNativeMemory:sn,useNativeGPU:Xt,memoryType:xt.Mem});\nexport{ii as default};")
        code = f'import {{createPerformance}} from "{ENTRY}/native/history.js";\n' + code
    elif name == "cpu-chart.js":
        code = replace_one(code, 'time:c(t),all:s', 'time:e.proTime??c(t),history:!!e.proTime,all:s')
        code = replace_one(code, 'user:o,system:a,ioWait:r', 'user:Number.isFinite(o)?o:`—`,system:Number.isFinite(a)?a:`—`,ioWait:Number.isFinite(r)?r:`—`')
    elif name == "network-chart.js":
        code = replace_one(code, 'let e=c(t[0].payload.index)', 'let e=t[0].payload.proTime??c(t[0].payload.index)')
    elif name == "memory-chart.js":
        code = replace_one(code, 'time:c(n),use:', 'time:e.proTime??c(n),use:')
    return code


def page():
    html = (WEB / "index.html").read_text()
    for stock, adapted in MODULES.items():
        html = html.replace(f'src="{stock}"', f'src="{adapted}"')
    setup = f'''<script type="importmap">{json.dumps({"imports": MODULES})}</script>
<script>
  const proUrl = new URL(location.href);
  proUrl.searchParams.set("anchor", "trim.resource-manager");
  history.replaceState(null, "", proUrl);
  // The iframe viewport is authoritative; allow a per-device manual override.
  let layoutMode = "auto";
  try {{ layoutMode = proUrl.searchParams.get("view") || localStorage.getItem("resmonpro.layout") || "auto"; }} catch {{}}
  if (!["auto","mobile","desktop"].includes(layoutMode)) layoutMode = "auto";
  function applyProLayout() {{
    const compact = layoutMode === "mobile" || (layoutMode === "auto" && (innerWidth <= 640 ||
      (matchMedia("(pointer:coarse)").matches && innerWidth <= 1024)));
    document.documentElement.dataset.proLayout = compact ? "mobile" : "desktop";
    let theme = proUrl.searchParams.get("theme");
    try {{if (!theme && parent !== window) theme = parent.document.body.getAttribute("theme-mode") === "dark" ? "dark" : "light";}} catch {{}}
    if (theme !== "dark" && theme !== "light") theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.dataset.proMobileTheme = compact ? theme : "";
    const sheet = document.getElementById("pro-mobile-styles");
    if (sheet) sheet.media = compact ? "all" : "not all";
    window.dispatchEvent(new Event("pro-layout-change"));
  }}
  window.resmonproLayout = {{get mode() {{return layoutMode;}},setMode(value) {{
    if (!["auto","mobile","desktop"].includes(value)) return;
    layoutMode = value;
    try {{localStorage.setItem("resmonpro.layout",value);}} catch {{}}
    const url = new URL(location.href); url.searchParams.delete("view"); history.replaceState(null,"",url);
    applyProLayout(); window.dispatchEvent(new Event("resize"));
  }}}};
  addEventListener("resize",applyProLayout); addEventListener("DOMContentLoaded",applyProLayout);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change",applyProLayout);
  try {{if (parent !== window) new MutationObserver(applyProLayout).observe(parent.document.body,{{attributes:true,attributeFilter:["theme-mode"]}});}} catch {{}}
  applyProLayout();
  // fnOS remembers iframe window geometry per user; migrate this app once only.
  try {{
    if (document.documentElement.dataset.proLayout === "mobile") throw new Error("Compact viewport");
    const desktop = window.parent;
    const width = Math.min(1280, Math.max(640, desktop.innerWidth - 100));
    const height = Math.min(800, Math.max(480, desktop.innerHeight - 70));
    for (const key of Object.keys(localStorage).filter(key => /^UserSettings/.test(key))) {{
      const flag = 'resmonpro.window.v2:' + key;
      if (localStorage.getItem(flag)) continue;
      const settings = JSON.parse(localStorage.getItem(key) || '{{}}');
      const id = 'resmonpro.Application';
      if (!settings[id]) continue;
      settings[id] = {{...settings[id], width, height, pageX:Math.max(66,(desktop.innerWidth-width)/2), pageY:Math.max(0,(desktop.innerHeight-height)/2)}};
      localStorage.setItem(key, JSON.stringify(settings));
      localStorage.setItem(flag, '1');
    }}
  }} catch {{ /* Native desktop or another origin can own its window geometry. */ }}

</script>'''
    html = replace_one(html, "<head>", "<head>" + setup)
    html = replace_one(html, "<title>飞牛 fnOS</title>", "<title>资源管理 Pro</title>")
    style = """<style>
html, body { background: var(--semi-color-app, var(--semi-color-bg-0, #fff)); }
html, body, #root { height: 100%; margin: 0; overflow: hidden; }
.pro-shell { height:100dvh; width:100%; font-size:14px; line-height:1.5; overflow:hidden; background:var(--semi-color-app); }
.pro-shell *, .pro-shell *::before, .pro-shell *::after { box-sizing:border-box; }
.pro-shell [role=tabpanel] { min-width:0; min-height:0; max-width:100%; }
.pro-shell .grid-cols-2 { grid-template-columns:repeat(2,minmax(0,1fr)); }
@media(max-width:850px) { .pro-shell .grid-cols-2 { grid-template-columns:minmax(0,1fr); } }
.pro-shell [role=tablist][aria-orientation=vertical] { width:170px!important; }
.pro-layout-picker select { height:28px; border:1px solid var(--semi-color-border); border-radius:6px; background:var(--semi-color-bg-0); color:var(--semi-color-text-1); font-size:12px; padding:0 5px; }
.pro-sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
.pro-range-bar > [role=status] { flex:1 1 180px; min-width:0; }
.pro-range-bar > [role=group] { flex:0 1 auto; max-width:100%; }
.pro-performance { width:100%; height:100%; min-height:0; display:flex; flex-direction:column; overflow:hidden; }
.pro-performance > div:first-child { flex-shrink:0; }
.pro-performance-body { width:100%; flex:1; min-height:0; overflow:auto; }
.pro-overview { min-height:0; overflow:auto; }
.pro-shell .h-\\[300px\\] { height:clamp(170px,32vh,240px)!important; }
.pro-shell .text-\\[20px\\] { font-size:18px; line-height:1.5; }
.pro-shell .text-xs { line-height:1.5; }
.pro-shell .recharts-surface { overflow:visible; }
.pro-shell .inline-flex.h-6.w-full { height:auto; min-height:24px; flex-wrap:wrap; row-gap:8px; }
.pro-shell .gap-3.text-base.leading-tight { flex-wrap:wrap; row-gap:6px; }
.pro-shell .gap-3.text-base.leading-tight > div { flex-shrink:0; }
@media(max-width:760px) { .pro-shell [role=tablist][aria-orientation=vertical] { width:125px!important; } }

</style>"""
    html = replace_one(html, "</head>", style + f'<link id="pro-mobile-styles" rel="stylesheet" media="not all" href="{ENTRY}/native/mobile.css">' + "</head>")
    recovery = f'''<aside id="pro-recovery" hidden style="position:fixed;bottom:12px;right:12px;z-index:99999;padding:10px;background:var(--semi-color-bg-0,#fff);border:1px solid var(--semi-color-border,#ddd);border-radius:6px">
原版界面仍在加载。 <a href="{ENTRY}/basic">打开基础视图</a>
</aside>
<script>
  const recovery = document.getElementById("pro-recovery");
  const ready = () => document.querySelector("#root [role='tablist']");
  setTimeout(() => {{
    if (ready()) return;
    recovery.hidden = false;
    const watcher = new MutationObserver(() => {{
      if (ready()) {{ recovery.hidden = true; watcher.disconnect(); }}
    }});
    watcher.observe(document.getElementById("root"), {{childList:true, subtree:true}});
  }}, 15000);
</script>'''
    return replace_one(html, "</body>", recovery + "</body>")
