// Hitokoto 一言插件注入脚本
// Part from https://developer.hitokoto.cn/sentence/demo.html#演示

async function fetchHitokoto() {
    try {
        const response = await fetch('https://v1.hitokoto.cn');
        if (!response.ok) throw new Error(`Network response was not ok: ${response.status}`);

        const data = await response.json();

        // 一言内容元素（假设页面中有 <a id="hitokoto_text">...</a>）
        const hitokotoLink = document.querySelector('#hitokoto-text');
        if (!hitokotoLink) {
            console.warn('[Hitokoto] 未找到 #hitokoto_text 元素');
            return;
        }

        // 设置一言内容
        hitokotoLink.innerText = data.hitokoto;
        
        // 处理作者/出处（小字显示）
        const authorEl = document.querySelector('#hitokoto-author');
        if (authorEl) {
            let authorText = '';
            if (data.from_who) {
                authorText = data.from_who;
            } else if (data.from) {
                authorText = data.from;
            } else {
                authorText = '佚名';
            }
            authorEl.innerText = `—— ${authorText}`;
            authorEl.href = `https://hitokoto.cn/?uuid=${data.uuid}`;
        }

    } catch (e) {
        console.error(`[Hitokoto] 获取失败: ${e}`);

        // 失败时显示默认文案
        const hitokotoLink = document.querySelector('#hitokoto-text');
        const authorEl = document.querySelector('#hitokoto-author');

        if (hitokotoLink) {
            hitokotoLink.innerText = '用代码表达言语的魅力，用代码书写山河的壮丽。';
        }
        if (authorEl) {
            authorEl.href = 'https://hitokoto.cn';
            authorEl.innerText = '—— Hitokoto';
        }
    }
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', () => {
    fetchHitokoto();
});