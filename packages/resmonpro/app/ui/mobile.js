// Mobile presentation shares the native data adapters and Pro history providers.
export function useCompactLayout(React) {
    const read = () => document.documentElement.dataset.proLayout === "mobile";
    const [compact, setCompact] = React.useState(read);
    React.useEffect(() => {
        const update = () => setCompact(read());
        window.addEventListener("pro-layout-change", update);
        return () => window.removeEventListener("pro-layout-change", update);
    }, []);
    return compact;
}

export function createMobileViews(React, {NativeGrid, NativeTable, useNativeCPU, useNativeMemory, useNativeGPU}) {
    const h = React.createElement;
    function OverviewGrid(props) {
        const compact = useCompactLayout(React);
        const cpu = useNativeCPU().latestCpuData;
        const memory = useNativeMemory().latestMen.mem;
        const gpu = useNativeGPU().latestGpuData?.gpu?.[0];
        if (!compact) return h(NativeGrid, props);
        const [system, , , network, , disk, fan, npu] = React.Children.toArray(props.children);
        const number = value => Number.isFinite(value) ? Math.round(value) : null;
        function ring(label, value, display, target) {
            return h("button", {type:"button", className:"pro-mobile-ring", key:label,
                "aria-label":label + " " + display,
                onClick:() => document.getElementById("semiTab" + target)?.click()},
                h("span", {className:"pro-mobile-ring-track", style:{"--progress":(Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0) + "%"}},
                    h("span", {className:"pro-mobile-ring-value"}, display)),
                h("span", {className:"pro-mobile-ring-label"}, label));
        }
        const usedGiB = memory.used / 1073741824;
        return h("div", {className:"pro-mobile-overview"},
            h("div", {className:"pro-mobile-uptime"}, system),
            h("section", {className:"pro-mobile-summary", "aria-label":"系统资源总览"},
                h("div", {className:"pro-mobile-rings"},
                    ring("CPU", cpu.busy.all, number(cpu.busy.all) === null ? "—" : number(cpu.busy.all) + "%", "cpu"),
                    ring("内存", memory.total > 0 ? memory.used / memory.total * 100 : NaN,
                        Number.isFinite(usedGiB) && memory.total > 0 ? usedGiB.toFixed(2) + " GB" : "—", "mem"),
                    ...(gpu ? [ring("GPU", gpu.busy, number(gpu.busy) === null ? "—" : number(gpu.busy) + "%", "GPU")] : [])),
                h("div", {className:"pro-mobile-summary-details"}, network, disk,
                    h("div", {className:"pro-mobile-temperature"}, h("strong", null, "温度"),
                        h("div", null, "CPU ", number(cpu.temp?.[0]) === null ? "—" : number(cpu.temp[0]) + "°C"),
                        ...(gpu ? [h("div", {key:"gpu"}, "GPU ", number(gpu.temp) === null ? "—" : number(gpu.temp) + "°C")] : [])),
                    fan, npu)));
    }

    function Table(props) {
        const compact = useCompactLayout(React);
        const [sort, setSort] = React.useState({key:"memory", descending:true});
        const [query, setQuery] = React.useState("");
        const [limit, setLimit] = React.useState(80);
        if (!compact || !String(props.className || "").includes("serve-process-table")) return h(NativeTable, props);
        const columns = props.columns || [];
        const byKey = new Map(columns.map(column=>[column.dataIndex, column]));
        const sorter = byKey.get(sort.key)?.sorter;
        const matched = [...(props.dataSource || [])].filter(row=>String(row.name || "").toLowerCase().includes(query.toLowerCase())).sort((a,b)=>typeof sorter === "function" ? sorter(a,b)*(sort.descending?-1:1) : 0);
        const rows = matched.slice(0,limit);
        function cell(key, row, index) {
            const column = byKey.get(key);
            if (!column) return null;
            return column.render ? column.render(row[key], row, index, {}) : String(row[key] ?? "—");
        }
        function rowDetails(row, index, nested=false) {
            return h("details", {className:"pro-mobile-process-row"+(nested?" nested":""), key:row.key ?? row.pid ?? index},
                h("summary", null,
                    h("span", {className:"pro-mobile-process-name", title:row.name}, cell("name",row,index)),
                    h("span", null, cell("cpu",row,index)), h("span", null, cell("memory",row,index))),
                h("dl", null, columns.filter(column=>column.dataIndex && !["name","cpu","memory","auto-width"].includes(column.dataIndex))
                    .map(column=>{
                        const key = column.dataIndex;
                        const heading = typeof column.title === "function" ? column.title() : column.title;
                        const label = heading?.props?.title || (typeof heading === "string" ? heading : key);
                        return h("div",{key},h("dt",null,label),h("dd",null,cell(key,row,index)));
                    })),
                row.children?.length ? h("div",{className:"pro-mobile-process-children"},row.children.map((child,i)=>rowDetails(child,i,true))) : null);
        }
        return h("section", {className:"pro-mobile-process", "aria-label":"进程资源列表"},
            h("input", {type:"search", className:"pro-mobile-process-search", "aria-label":"搜索服务或进程", placeholder:"搜索名称", value:query,
                onChange:event=>{setQuery(event.target.value);setLimit(80);}}),
            h("div", {className:"pro-mobile-process-header"}, [["name","名称"],["cpu","CPU"],["memory","内存"]].map(([key,label])=>
                h("button", {key,type:"button",onClick:()=>setSort({key,descending:sort.key===key?!sort.descending:true}),
                    "aria-label":label+"排序"}, label, sort.key===key?(sort.descending?" ↓":" ↑"):""))),
            props.loading && !rows.length ? h("p",{role:"status"},"正在读取进程…") : rows.length ? rows.map((row,index)=>rowDetails(row,index)) : h("p",{role:"status"},query?"没有匹配的进程":"暂无进程数据"),
            matched.length > rows.length ? h("button",{type:"button",className:"pro-mobile-load-more",onClick:()=>setLimit(value=>value+80)},"显示更多（"+rows.length+" / "+matched.length+"）") : null);
    }
    return {OverviewGrid, Table};
}
