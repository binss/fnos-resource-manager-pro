"use strict";
const $ = selector => document.querySelector(selector);
const series = [
    {column: 1, name: "CPU", color: "var(--blue)", page: "cpu"},
    {column: 2, name: "内存", color: "var(--teal)", page: "memory"}
];
const names = {overview: "性能概览", cpu: "CPU", memory: "内存", history: "资源使用率历史"};
let page = "overview";
let hours = 24;
let lastLive, livePoints = [], timer, request;
const format = value => Number.isFinite(value) ? value.toFixed(1) + "%" : "—";
const time = (ts, days) => new Intl.DateTimeFormat("zh-CN", days
    ? {month: "numeric", day: "numeric"}
    : {hour: "2-digit", minute: "2-digit"}).format(ts * 1000);
const svg = (type, attrs, value) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", type);
    for (const [key, attr] of Object.entries(attrs)) element.setAttribute(key, attr);
    if (value != null) element.textContent = value;
    return element;
};

function chart({start, end, points, bucket}, metrics) {
    const width = Math.max(210, $("#plot").clientWidth);
    const left = 39, right = width - 24, bottom = 188;
    const x = ts => left + (right - left) * (ts - start) / (end - start);
    const y = value => bottom - 173 * value / 100;
    const view = svg("svg", {viewBox: "0 0 " + width + " 213", role: "img",
        "aria-label": metrics.map(item => item.name).join("与") + "使用率曲线"});
    const label = (x, y, anchor, value) => svg("text", {x, y, fill: "var(--muted)",
        "font-size": "11", "text-anchor": anchor}, value);
    for (const value of [0, 25, 50, 75, 100]) {
        view.append(svg("line", {x1: left, x2: right, y1: y(value), y2: y(value), stroke: "var(--border)"}),
            label(left - 5, y(value) + 4, "end", value + "%"));
    }
    for (const fraction of width > 400 ? [0, .25, .5, .75, 1] : [0, .5, 1]) {
        const ts = start + (end - start) * fraction;
        view.append(label(x(ts), 207, "middle", time(ts, end - start > 86400)));
    }
    for (const {column, color} of metrics) {
        let segment = [];
        const flush = () => {
            if (segment.length === 1) {
                const [point] = segment;
                view.append(svg("circle", {cx: x(point[0]), cy: y(point[column]), r: 3, fill: color}));
            } else if (segment.length) {
                view.append(svg("polyline", {points: segment.map(point => x(point[0]) + "," + y(point[column])).join(" "),
                    stroke: color, "stroke-width": 2, fill: "none", "stroke-linejoin": "round"}));
            }
            segment = [];
        };
        for (const point of points) {
            if (!Number.isFinite(point[column]) ||
                (segment.length && point[0] - segment.at(-1)[0] > bucket * 1.7)) flush();
            if (Number.isFinite(point[column])) segment.push(point);
        }
        flush();
    }
    $("#plot").replaceChildren(view);
}

function render(data, current) {
    const metrics = series.filter(item => page === "history" || page === "overview" || item.page === page);
    $("#legend").replaceChildren(...metrics.map(item => {
        const span = document.createElement("span");
        span.style.color = item.color;
        span.textContent = item.name;
        return span;
    }));
    $("#cards").replaceChildren(...metrics.map(item => {
        const card = document.createElement("article");
        card.className = "card";
        const label = document.createElement("span");
        label.textContent = item.name + " 使用率";
        const value = document.createElement("strong");
        value.style.color = item.color;
        value.textContent = format(data.latest?.[item.column]);
        const detail = document.createElement("small");
        detail.textContent = current ? (item.page === "cpu" ? current.cores + " 逻辑核心"
            : current.used_gib.toFixed(1) + " / " + current.memory_gib.toFixed(1) + " GiB") : "最近一次采样";
        card.append(label, value, detail);
        return card;
    }));
    chart(data, metrics);
    $("#status").textContent = data.points.length ? (page === "history"
        ? "每分钟采集 · 保留 30 天" + (data.bucket > 60 ? " · 每 " + data.bucket / 60 + " 分钟取平均" : "") +
          " · 最近采样 " + new Date(data.latest[0] * 1000).toLocaleString("zh-CN")
        : "每 2 秒刷新 · 最近约 2 分钟") : "这个时间范围内暂无采样。";
}

async function update(signal) {
    try {
        const historical = page === "history";
        const response = await fetch(historical ? "api/history?hours=" + hours : "api/live", {signal, cache: "no-store"});
        if (!response.ok) throw new Error("读取失败");
        const data = await response.json();
        if (signal.aborted) return;
        if (historical) {
            render(data);
        } else {
            const elapsed = lastLive ? data.total - lastLive.total : 0;
            const idle = lastLive ? data.idle - lastLive.idle : 0;
            const cpu = elapsed > 0 && idle >= 0 && idle <= elapsed ? 100 * (1 - idle / elapsed) : null;
            lastLive = data;
            const point = [data.ts, cpu, data.memory];
            livePoints = livePoints.filter(row => row[0] >= data.ts - 120 && row[0] < data.ts);
            livePoints.push(point);
            render({start: data.ts - 120, end: data.ts, points: livePoints, latest: point, bucket: 2}, data);
        }
    } catch {
        if (!signal.aborted) $("#status").textContent = "暂时无法读取数据，请重新打开应用或稍后重试。";
    }
}

function refresh() {
    request?.abort();
    clearInterval(timer);
    request = new AbortController();
    const signal = request.signal;
    $("#heading").textContent = names[page];
    $("#mode").textContent = page === "history" ? "历史" : "实时";
    $("#ranges").hidden = page !== "history";
    $("#plot").replaceChildren();
    $("#status").textContent = "正在读取数据…";
    update(signal);
    timer = setInterval(() => update(signal), page === "history" ? 60000 : 2000);
}

for (const button of document.querySelectorAll("[data-page]")) {
    button.onclick = () => {
        page = button.dataset.page;
        $("nav [aria-current]").removeAttribute("aria-current");
        button.setAttribute("aria-current", "page");
        refresh();
    };
}
for (const button of document.querySelectorAll("[data-hours]")) {
    button.onclick = () => {
        hours = Number(button.dataset.hours);
        $("#ranges [aria-pressed=true]").setAttribute("aria-pressed", "false");
        button.setAttribute("aria-pressed", "true");
        refresh();
    };
}
refresh();
