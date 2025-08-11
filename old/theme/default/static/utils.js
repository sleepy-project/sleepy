// 获取 base url
// const routerIndex = window.location.href.indexOf('?');
// const baseUrl = window.location.href.slice(0, routerIndex > 0 ? routerIndex : window.location.href.length);

// sleep (只能加 await 在 async 函数中使用)
const sleep = (delay) => new Promise((resolve) => setTimeout(resolve, delay));

function sliceText(text, maxLength) {
    /*
    截取指定长度文本
    */
    if (
        text.length <= maxLength || // 文本长度小于指定截取长度
        maxLength == 0 // 截取长度设置为 0 (禁用)
    ) {
        return text;
    }
    return text.slice(0, maxLength - 3) + '...';
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeJs(str) {
    return String(str)
        .replace(/'/g, "\\'")
    // .replace(/\\/g, '\\\\')
    // .replace(/\n/g, '\\n')
    // .replace(/\r/g, '\\r');
}

function getFormattedTime(date) {
    const pad = (num) => (num < 10 ? '0' + num : num);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function checkVercelDeploy() {
    /*
    检查是否为 Vercel 部署 (经测试 Vercel 不支持 SSE)
    测试方法: 请求 /none，检查返回 Headers 中是否包含 x-vercel-id
    - 1: 是 Vercel 部署
    - 0: 不是 Vercel 部署
    - -1: *请求失败*
    */
    console.log(`[Vercel] 测试请求 /none 中...`);
    return await fetch('/none', { timeout: 10000 })
        .then(resp => {
            if (resp.ok) {
                const xVercelId = resp.headers.get('x-vercel-id');
                console.log(`[Vercel] 获取到 x-vercel-id: ${xVercelId}`);
                if (xVercelId) {
                    console.log(`[Vercel] (1) 确定为 Vercel 部署`);
                    return 1;
                } else {
                    console.log(`[Vercel] (0) 非 Vercel 部署`);
                    return 0;
                }
            } else {
                console.warn(`[Vercel] 返回错误: ${resp.status} - ${resp.statusText}`);
                console.log(`[Vercel] (-1) 无法确定是否为 Vercel 部署`);
                return -1;
            }

        })
        .catch(error => {
            console.warn(`[Vercel] 请求错误: ${error}`);
            console.log(`[Vercel] (-1) 无法确定是否为 Vercel 部署`);
            return -1;
        });
}

export {
    sleep,
    sliceText,
    escapeHtml,
    escapeJs,
    getFormattedTime,
    checkVercelDeploy
}