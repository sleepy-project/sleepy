let autoRefreshInterval = null;
const REFRESH_INTERVAL = 114514;  // Placeholder 勿动

function refreshOnlineCount() {
    let statusEl = document.getElementById('update-status');
    if (statusEl) {
        statusEl.textContent = '加载中...';
        statusEl.style.color = '#666';
    }

    fetch('/plugin/online_count/')
        .then(r => {
            if (!r.ok) throw new Error(`Response error, code: ${r.status}`);
            return r.json();
        })
        .then(data => {
            // 更新当前人数
            document.getElementById('count-global').textContent = data.current;

            // 更新今日最高
            document.getElementById('peak-today-global').textContent = data.peak_today;

            // 更新历史最高
            document.getElementById('peak-all-global').textContent = data.peak_all_time;

            // 更新状态提示
            if (statusEl) {
                const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                statusEl.textContent = `更新于 ${now} (${REFRESH_INTERVAL / 1000}s)`;
                statusEl.style.color = '#28a745';
            }
        })
        .catch(err => {
            console.error('刷新在线人数失败:', err);
            if (statusEl) {
                statusEl.textContent = `刷新失败 (${REFRESH_INTERVAL / 1000}s)`;
                statusEl.style.color = '#dc3545';
            }
        });
}

// 启动自动刷新
function startAutoRefresh() {
    console.log('[inject] Auto Refresh started');
    if (autoRefreshInterval) return;  // 防止重复启动

    let statusEl = document.getElementById('update-status');
    if (statusEl) statusEl.style.color = '#28a745';

    // 首次立即刷新一次
    refreshOnlineCount();

    // 之后每 10 秒刷新一次（不显示“加载中...”，只更新时间）
    autoRefreshInterval = setInterval(() => {
        refreshOnlineCount();
    }, REFRESH_INTERVAL);
}

// 停止自动刷新
function stopAutoRefresh() {
    console.log('[inject] Auto Refresh stopped');
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }

    let statusEl = document.getElementById('update-status');
    if (statusEl) statusEl.style.color = '#666';
}

// 页面加载完成时启动自动刷新
document.addEventListener('DOMContentLoaded', () => {
    startAutoRefresh();
});

// 可选：页面隐藏时暂停，显示时恢复（节省资源）
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        startAutoRefresh();
    }
});