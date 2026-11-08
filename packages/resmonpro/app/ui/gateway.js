// Use only the existing same-origin application gateway session.
export async function requestJSON(url, fetchImpl=fetch) {
    const response = await fetchImpl(url, {
        credentials:'same-origin', cache:'no-store', redirect:'error'
    });
    if (!response.ok) {
        throw new Error(response.status===401 || response.status===403
            ? '应用会话已失效，请关闭此页并从飞牛 App 重新打开。'
            : '暂时无法读取数据，请稍后重试。');
    }
    if (!response.headers.get('content-type')?.includes('json')) {
        throw new Error('应用入口未返回有效数据，请从飞牛 App 重新打开。');
    }
    let data;
    try { data = await response.json(); }
    catch { throw new Error('应用入口返回的数据无法解析，请重新打开应用。'); }
    if (!data || typeof data !== 'object') throw new Error('应用入口返回的数据无效，请重新打开应用。');
    if (data.error) {
        throw new Error(/token|auth|login/i.test(data.error)
            ? '应用会话已失效，请关闭此页并从飞牛 App 重新打开。'
            : '暂时无法读取数据。');
    }
    return data;
}
