'use strict';
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="fan-csrf"]').content;
let state = null, busy = false, edited = false, configuring = false, refreshing = false;
let noticeTimer;
function message(text, good = false) {
  clearTimeout(noticeTimer);
  $('notice').textContent = text; $('notice').className = 'notice' + (good ? ' success' : '');
  $('notice').hidden = false;
  if (good) noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 4500);
}
async function request(path, body) {
  const response = await fetch('api/' + path, {method: body ? 'POST' : 'GET', cache: 'no-store', credentials:'same-origin', redirect:'error',
    headers: body ? {'Content-Type': 'application/json', 'X-Fan-CSRF': csrf} : {},
    ...(body ? {body: JSON.stringify(body)} : {}), signal: AbortSignal.timeout(45000)});
  let result;
  try { result = await response.json(); } catch { throw new Error('登录可能已过期，请重新打开此应用。'); }
  if (!response.ok) throw new Error(result.error || '操作未完成，请刷新状态。');
  return result;
}
function controlsDisabled(value) {
  for (const node of document.querySelectorAll('#dashboard button, #dashboard input, #connection-form button')) node.disabled = value;
  if (!value && state && !state.available) {
    for (const node of document.querySelectorAll('#apply,#power-off,#manual-mode,.presets button,#speed')) node.disabled = true;
  }
}
function updateTarget() {
  $('target-speed').value = $('speed').value;
  for (const button of document.querySelectorAll('[data-speed]')) button.classList.toggle('selected', button.dataset.speed === $('speed').value);
}
function render(next) {
  state = next;
  if (next.fan_entity) $('fan-entity').value=next.fan_entity;
  if (next.temperature_entity) $('temperature-entity').value=next.temperature_entity;
  $('setup').hidden = next.configured && !configuring;
  $('dashboard').hidden = !next.configured;
  $('cancel-settings').hidden = !next.configured;
  if (!next.configured) return;
  $('actual-speed').textContent = next.on ? (next.speed ?? '—') : next.available ? '0' : '—';
  $('fan-state').textContent = !next.available ? '设备离线' : next.on ? '运行中' : '已关闭';
  $('fan-state').className = 'tag' + (!next.available ? ' warning' : next.on ? '' : ' off');
  $('fan-icon').classList.toggle('spinning', next.available && next.on);
  $('voltage').textContent = next.available ? `设备回读 · 输出电压约 ${next.voltage == null ? '—' : next.voltage.toFixed(2)} V` : '等待设备重新连接';
  $('temperature').textContent = next.temperature == null ? '—' : next.temperature.toFixed(1);
  const when = next.temperature_updated ? new Date(next.temperature_updated) : null;
  $('temperature-age').textContent = when ? `更新于 ${when.toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'})}` : '温度不可用';
  $('temperature-age').title = when ? when.toLocaleString('zh-CN') : '';
  $('auto-mode').setAttribute('aria-pressed', String(next.mode === 'auto'));
  $('manual-mode').setAttribute('aria-pressed', String(next.mode === 'manual'));
  $('mode-label').textContent = next.mode === 'auto' ? '按温度自动运行' : next.mode === 'manual' ? '自动温控已暂停' : '自动化状态不一致';
  $('mode-description').textContent = next.mode === 'auto' ? '温控已接管。升温及时加速，降温后延时逐档降速。' : next.mode === 'manual' ? '当前由你控制转速。需要自动保护时，请切回自动温控。' : '两条自动化开关状态不同，点击自动温控可恢复。';
  if (!edited) { $('speed').value = next.speed > 0 ? next.speed : 30; updateTarget(); }
  $('sync-time').textContent = '已同步 ' + new Date().toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  if ((next.temperature != null && next.temperature >= 43 || next.temperature == null) && next.mode !== 'auto') {
    message(next.temperature == null ? '温度不可用，当前为手动模式。建议恢复自动温控或设置满速。' : '箱温偏高，当前为手动模式。建议恢复自动温控或设置满速。');
  }
  controlsDisabled(busy);
}
async function refresh() {
  if (busy || refreshing) return;
  refreshing = true;
  try { render(await request('state')); } catch (error) { message(error.message); $('sync-time').textContent = '同步失败 · 请稍后重试'; }
  finally { refreshing = false; }
}
async function act(data) {
  if (busy) return;
  busy = true; controlsDisabled(true);
  try {
    const result = await request('control', data);
    edited = false; render(result);
    const expected = data.action === 'speed' ? result.on && result.speed === data.speed : data.action === 'off' ? !result.on : true;
    if (data.action === 'auto') message('已恢复自动温控；降速仍按 10 分钟延时执行。', true);
    else if (data.action === 'manual') message('已切换手动控制，当前风扇状态保持。', true);
    else message(expected ? '已应用，设备状态已回读。' : '指令已发送，等待设备回读，请留意当前转速。', expected);
  } catch (error) { message(error.message); }
  finally { busy = false; controlsDisabled(false); }
}
$('speed').addEventListener('input', () => { edited = true; updateTarget(); });
for (const button of document.querySelectorAll('[data-speed]')) button.addEventListener('click', () => { edited = true; $('speed').value = button.dataset.speed; updateTarget(); });
$('apply').addEventListener('click', () => act({action:'speed', speed:Number($('speed').value)}));
$('power-off').addEventListener('click', () => act({action:'off'}));
$('auto-mode').addEventListener('click', () => act({action:'auto'}));
$('manual-mode').addEventListener('click', () => act({action:'manual'}));
$('settings').addEventListener('click', () => { configuring = !configuring; if (state) render(state); });
$('cancel-settings').addEventListener('click', () => { configuring = false; $('token').value = ''; render(state); });
$('connection-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  busy = true; controlsDisabled(true);
  try {
    const result = await request('connect', {token:$('token').value,fan_entity:$('fan-entity').value.trim(),temperature_entity:$('temperature-entity').value.trim()});
    $('token').value = ''; configuring = false; render(result); message('已连接弱电箱风扇。', true);
  } catch (error) { message(error.message); }
  finally { busy = false; controlsDisabled(false); }
});
refresh(); setInterval(refresh, 5000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });

// NAS fan modes use the authenticated fnOS client in the current browser session.
let nasClient, nasState = null, nasBusy = false, nasRefreshing = false;
const nasLabels = {1:'静音模式',2:'均衡模式',3:'全速模式'};
async function nativeClient() {
  if (!nasClient) nasClient = await import('./api/fnos-native.js');
  return nasClient;
}
async function nasTimeout(promise) {
  let timer;
  try { return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('飞牛请求超时，结果可能尚未回读，请刷新确认。')),30000);})]); }
  finally { clearTimeout(timer); }
}
function renderNas(result) {
  nasState = result;
  $('nas-mode-label').textContent = result.supported ? nasLabels[result.mode] || '模式未识别' : '设备未开放';
  $('nas-mode-label').className = 'tag' + (result.supported ? '' : ' neutral');
  $('nas-rpm').textContent = result.rpm.length ? result.rpm.map((rpm,index)=>`风扇 ${index+1} · ${rpm} RPM`).join('　') : '未提供实际转速';
  for (const button of document.querySelectorAll('[data-nas-mode]')) {
    button.disabled = nasBusy || !result.supported;
    button.setAttribute('aria-pressed', String(Number(button.dataset.nasMode) === result.mode));
  }
  $('nas-status').textContent = result.supported ? '使用飞牛原生风扇模式。此处切换不会改变弱电箱温控。' : '当前设备未开放原生风扇模式控制。弱电箱控制仍可独立使用。';
}
async function refreshNas() {
  if (nasBusy || nasRefreshing) return;
  nasRefreshing = true;
  $('nas-refresh').disabled = true;
  try { const client = await nativeClient(); renderNas(await nasTimeout(client.readNasFan())); }
  catch (error) {
    $('nas-mode-label').textContent = '暂未连接'; $('nas-mode-label').className = 'tag warning';
    $('nas-rpm').textContent = '无法读取 NAS 风扇状态';
    $('nas-status').textContent = error.message || '当前应用会话无法读取风扇，请从飞牛 App 重新打开资源管理 Pro。';
    for (const button of document.querySelectorAll('[data-nas-mode]')) button.disabled = true;
  } finally { nasRefreshing = false; $('nas-refresh').disabled = false; }
}
for (const button of document.querySelectorAll('[data-nas-mode]')) button.addEventListener('click', async () => {
  if (nasBusy || nasRefreshing || !nasState?.supported) return;
  nasBusy = true;
  const mode = Number(button.dataset.nasMode);
  for (const item of document.querySelectorAll('[data-nas-mode]')) item.disabled = true;
  $('nas-refresh').disabled = true; $('nas-status').textContent = '正在应用模式并读取设备确认…';
  try {
    const client = await nativeClient(); const result = await nasTimeout(client.setNasFanMode(mode));
    renderNas(result); $('nas-status').textContent = `已切换为${nasLabels[mode]}，模式回读已确认。`;
  } catch (error) { $('nas-status').textContent = error.message || '操作未完成，请刷新检查当前模式。'; }
  finally {
    nasBusy = false; $('nas-refresh').disabled = false;
    for (const item of document.querySelectorAll('[data-nas-mode]')) item.disabled = !nasState?.supported;
  }
});
$('nas-refresh').addEventListener('click', refreshNas);
refreshNas();
setInterval(()=>{if(nasState?.supported && !document.hidden)refreshNas();},15000);

function syncTheme(){try{const root=parent.document.documentElement;const dark=root.dataset.theme==='dark'||root.dataset.proMobileTheme==='dark'||parent.document.body.getAttribute('theme-mode')==='dark'||parent.document.querySelector('.pro-shell [theme-mode="dark"]');document.documentElement.dataset.theme=dark?'dark':root.dataset.theme==='light'?'light':matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}catch{}}
syncTheme();setInterval(syncTheme,2000);
