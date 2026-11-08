import {createMobileViews, useCompactLayout} from "./mobile.js";
const endpoint = "/cgi/ThirdParty/resmonpro/index.cgi/api/history";
const ranges = [[0, "实时"], [1, "1 小时"], [24, "24 小时"], [168, "7 天"], [720, "30 天"]];

export function createPerformance(React, {Performance, CPUChart, MemoryChart, Overview, NativeGrid, NativeTable, useNativeCPU, useNativeMemory, useNativeGPU, memoryType}) {
    const h = React.createElement;
    const Context = React.createContext({hours: 0, data: null, live: null});

    const {OverviewGrid, Table} = createMobileViews(React, {NativeGrid, NativeTable, useNativeCPU, useNativeMemory, useNativeGPU});
    function PerformanceWithRange(props) {
        const compact = useCompactLayout(React);
        const [hours, setHours] = React.useState(0);
        const [result, setResult] = React.useState(null);
        const [live, setLive] = React.useState(null);
        React.useEffect(() => {
            const abort = new AbortController();
            let history = null;
            let loadedAt = 0;
            let busy = false;
            async function refresh() {
                if (busy) return;
                busy = true;
                try {
                    if (!hours || !history || Date.now() - loadedAt >= 60000) {
                        const response = await fetch(hours ? endpoint + "?hours=" + hours : endpoint.replace("/history", "/recent"), {
                            signal: abort.signal, cache: "no-store", credentials: "same-origin"
                        });
                        if (!response.ok) throw new Error("History unavailable");
                        history = await response.json();
                        if (!Array.isArray(history.points)) throw new Error("Invalid history");
                        loadedAt = Date.now();
                    }
                    let data = history;
                    if (!hours) {
                        const response = await fetch(endpoint.replace('/history', '/live'), {
                            signal: abort.signal, cache: "no-store", credentials: "same-origin"
                        });
                        if (!response.ok) throw new Error("Live data unavailable");
                        const sample = await response.json();
                        const cpu = history.latest?.[1];
                        if (!abort.signal.aborted) setLive({...sample, cpu});
                    }
                    if (!abort.signal.aborted) setResult({hours, data});
                } catch {
                    if (!abort.signal.aborted) setResult({hours, error: true});
                } finally {
                    busy = false;
                }
            }
            refresh();
            const timer = setInterval(refresh, hours ? 60000 : 3000);
            return () => { abort.abort(); clearInterval(timer); };
        }, [hours]);
        const current = result?.hours === hours ? result : null;
        const status = hours ? (current?.error ? "暂时无法读取历史记录" : !current ? "正在读取历史…"
            : "每分钟采集" + (current.data.bucket > 60 ? " · " + current.data.bucket / 60 + " 分钟平均" : "")) : "实时 · 最近 3 分钟 · 每 3 秒刷新";
        return h(Context.Provider, {value: {hours, data: current?.data, error: current?.error, live}},
            h("div", {className: "pro-performance"},
                h("div", {className: "pro-range-bar", style: {display: "flex", alignItems: "center", justifyContent: "space-between",
                    gap: 8, flexWrap: "wrap", minWidth: 0, padding: "8px 16px", boxSizing: "border-box"}},
                    h("span", {style: {fontSize: 12, color: "var(--semi-color-text-2)"}, role: "status"}, status),
                    h("label", {className:"pro-layout-picker"}, h("span", {className:"pro-sr-only"}, "界面布局"),
                        h("select", {"aria-label":"界面布局", defaultValue:window.resmonproLayout?.mode || "auto",
                            onChange:event=>window.resmonproLayout?.setMode(event.target.value)},
                            [["auto","自动布局"],["mobile","手机布局"],["desktop","桌面布局"]].map(([value,label])=>h("option",{value,key:value},label)))),
                    compact ? h("select", {className:"pro-range-select", "aria-label":"运行状态时间范围", value:hours,
                        onChange:event=>setHours(Number(event.target.value))}, ranges.map(([value,label])=>h("option",{key:value,value},label))) :
                    h("div", {role: "group", "aria-label": "运行状态时间范围", style: {display: "flex", gap: 4, flexWrap: "wrap"}},
                        ranges.map(([value, label]) => h("button", {key: value, type: "button",
                            "aria-pressed": hours === value, onClick: () => setHours(value),
                            style: {height: 28, minHeight: 0, padding: "3px 9px", fontSize: 12, lineHeight: "18px", whiteSpace: "nowrap", borderRadius: 6, cursor: "pointer",
                                border: "1px solid var(--semi-color-border)",
                                background: hours === value ? "var(--semi-color-primary)" : "transparent",
                                color: hours === value ? "white" : "var(--semi-color-text-0)"}}, label)))),
                h("div", {className: "pro-performance-body"}, h(Performance, props))));
    }

    function historyPoints(data) {
        const byBucket = new Map(data.points.map(point => [Math.floor(point[0] / data.bucket), point]));
        const rows = [];
        for (let ts = Math.floor(data.start / data.bucket) * data.bucket; ts <= data.end; ts += data.bucket) {
            const point = byBucket.get(Math.floor(ts / data.bucket)) || [ts, null, null];
            rows.push({point, proTime: new Date(point[0] * 1000).toLocaleString("zh-CN")});
        }
        return rows;
    }

    function HistoricalChart({kind, props}) {
        const {hours, data, error} = React.useContext(Context);
        const Original = kind === "cpu" ? CPUChart : MemoryChart;
        if (!data?.points.length || (kind === "memory" && props.type !== memoryType)) {
            return h("div", {style: {height: 300, display: "grid", placeItems: "center", color: "var(--semi-color-text-2)"}},
                error ? "历史数据读取失败" : !data ? "正在读取历史…" : "该范围暂无此项历史记录");
        }
        const rows = historyPoints(data).map(({point, proTime}) => kind === "cpu"
            ? {proTime, busy: {all: point[1] ?? NaN, user: point[4] ?? NaN, system: point[5] ?? NaN, iowait: point[6] ?? NaN}, temp: Number.isFinite(point[3]) ? [Math.round(point[3])] : []}
            : {proTime, mem: {used: point[2] ?? NaN, total: 100}, swap: {used: NaN, total: NaN}});
        return h(Original, {...props, data: rows, ...(kind === "cpu" ? {num: rows.some(row => row.temp.length) ? 1 : 0} : {})});
    }

    function useNetworkInfo(original) {
        const {data} = React.useContext(Context);
        if (!data) return original;
        const networks = data.networks || [];
        const maps = networks.map(net => new Map(net.points.map(point => [Math.floor(point[0] / data.bucket), point])));
        const rows = historyPoints(data).map(({point, proTime}) => {
            const ifs = networks.map((net, index) => {
                const stored = maps[index].get(Math.floor(point[0] / data.bucket));
                const native = original.latestNetData?.ifs?.find(item => item.name === net.name);
                return {...native, name: net.name, index: native?.index ?? index + 1, ifType: native?.ifType ?? 0,
                    proTime, receive: stored?.[1] ?? NaN, transmit: stored?.[2] ?? NaN};
            });
            return {ifs, all: {name: original.latestNetData?.all?.name || "总计", index: 0, proTime,
                receive: ifs.length ? ifs.reduce((sum, item) => sum + item.receive, 0) : NaN,
                transmit: ifs.length ? ifs.reduce((sum, item) => sum + item.transmit, 0) : NaN}};
        });
        return {...original, netData: rows, latestNetData: rows.at(-1) || original.latestNetData};
    }

    function useGPUInfo(original) {
        const {data} = React.useContext(Context);
        if (!data) return original;
        const recorded = data.gpus || [];
        const maps = recorded.map(gpu => new Map(gpu.points.map(point => [Math.floor(point[0] / data.bucket), point])));
        const templates = recorded.map((gpu, index) => original.latestGpuData?.gpu?.find(item => item.index === Number(gpu.card.replace("card", ""))) || original.latestGpuData?.gpu?.[index] || {index, vendorId:4098, device:gpu.card});
        const rows = historyPoints(data).map(({point, proTime}) => {
            const gpu = recorded.map((record, index) => {
                const stored = maps[index].get(Math.floor(point[0] / data.bucket));
                const total = stored?.[3] ?? NaN, used = stored?.[4] ?? NaN;
                return {...templates[index], proTime, busy:stored?.[1] ?? NaN, temp:Number.isFinite(stored?.[2]) ? Math.round(stored[2]) : NaN,
                    ram:{total,used,free:total-used}, engine:{compute:stored?.[5] ?? NaN,encoder:stored?.[6] ?? NaN}};
            });
            return {num:gpu.length,gpu};
        });
        return {...original,gpuData:rows,latestGpuData:rows.at(-1) || {num:0,gpu:[]},num:recorded.length};
    }

    function useCPUInfo(original) {
        const {live, data} = React.useContext(Context);
        const temperature = live?.cpu_temperature ?? data?.latest?.[3];
        const old = original.latestCpuData;
        const cpu = data?.latest?.[1];
        const details = data?.latest;
        return {...original, latestCpuData: {...old,
            ...(live ? {name: live.cpu_name, thread: live.cores, core: live.physical_cores,
                loadavg: {avg1min: live.loadavg[0], avg5min: live.loadavg[1], avg15min: live.loadavg[2]}} : {}),
            temp: Number.isFinite(temperature) ? [Math.round(temperature)] : old.temp.map(value => Number.isFinite(value) ? Math.round(value) : value),
            busy: {...old.busy, ...(Number.isFinite(cpu) ? {all: cpu, user: details[4] ?? NaN, system: details[5] ?? NaN, iowait: details[6] ?? NaN} : {})}}};
    }
    function useMemoryInfo(original) {
        const {live} = React.useContext(Context);
        if (!live || original.latestMen.mem.total > 0) return original;
        const total = live.memory_gib * 1073741824;
        const used = live.used_gib * 1073741824;
        return {...original, latestMen: {...original.latestMen, mem: {...original.latestMen.mem,
            total, used, available: total - used, free: total - used, physical: total}}};
    }
    function Temperature() {
        return h("iframe", {title:"硬件温度面板", src:"/cgi/ThirdParty/resmonpro/index.cgi/temperature/",
            className:"pro-temperature-frame", style:{width:"100%",height:"100%",display:"block",border:0},
            referrerPolicy:"same-origin"});
    }
    function TemperatureIcon(props) {
        return h("svg", {...props,width:20,height:20,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.7,"aria-hidden":true},
            h("path",{d:"M9 14.5V5a3 3 0 0 1 6 0v9.5a5 5 0 1 1-6 0Z"}),
            h("path",{d:"M12 8v9"}),h("circle",{cx:12,cy:18,r:1.5,fill:"currentColor",stroke:"none"}));
    }
    return {
        useCPUInfo, useMemoryInfo, useNetworkInfo, useGPUInfo, Temperature, TemperatureIcon,
        Performance: PerformanceWithRange,
        CPUChart: props => h(HistoricalChart, {kind: "cpu", props}),
        MemoryChart: props => h(HistoricalChart, {kind: "memory", props}),
        Overview, OverviewGrid, Table
    };
}
