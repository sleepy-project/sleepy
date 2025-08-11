// 全局变量
let statusList = [];
let currentStatus = { 'color': 'sleeping', 'desc': '', 'id': -1, 'name': '未知' };
let deviceData = {};
let privateMode = false;

// 初始化页面
async function initPage() {
    try {
        // 获取状态列表
        const statusResponse = await fetch('/api/status/list');
        statusListResp = await statusResponse.json();
        statusList = statusListResp.status_list;
        console.debug(`got statusList: ${statusList}`);
        renderStatusSelector();

        // 获取当前状态和设备信息
        const queryResponse = await fetch('/api/status/query');
        const queryData = await queryResponse.json();
        currentStatus = queryData.status;
        deviceData = queryData.device;
        privateMode = queryData.private_mode || false;

        // 更新UI
        updateCurrentStatus();
        renderDeviceList();
        document.getElementById('private-mode-toggle').checked = privateMode;

        // 如果启用了统计功能，获取统计数据
        if (document.getElementById('metrics-container')) {
            await fetchMetrics();
        }
    } catch (error) {
        console.error('初始化失败:', error);
        alert(`加载数据失败，请检查网络连接或重新登录\n${error}`);
    }
}

// 渲染状态选择器
function renderStatusSelector() {
    const container = document.getElementById('status-selector');
    container.innerHTML = '';

    let status;
    for (let index = 0; index < statusList.length; index++) {
        status = statusList[index];
        const statusItem = document.createElement('div');
        statusItem.className = `status-item ${currentStatus.id === index ? 'active' : ''}`;
        statusItem.style.backgroundColor = getStatusColor(status.color);
        statusItem.textContent = status.name;
        statusItem.dataset.index = index;
        statusItem.addEventListener('click', function () {
            setStatus(parseInt(this.dataset.index));
        });
        container.appendChild(statusItem);
    };
}

// 获取状态颜色
function getStatusColor(colorName) {
    const colors = {
        'awake': 'rgba(0, 200, 0, 0.2)',
        'sleeping': 'rgba(128, 128, 128, 0.2)',
        'error': 'rgba(255, 0, 0, 0.2)'
    };
    return colors[colorName] || 'rgba(200, 200, 200, 0.2)';
}

// 更新当前状态显示
function updateCurrentStatus() {
    const statusName = document.getElementById('current-status-name');
    if (statusList[currentStatus.id]) {
        statusName.textContent = statusList[currentStatus.id].name;
        statusName.style.color = statusList[currentStatus.id].color === 'awake' ? 'green' :
            statusList[currentStatus.id].color === 'error' ? 'red' : 'gray';
    } else {
        statusName.textContent = '未知状态';
        statusName.style.color = 'red';
    }

    // 更新状态选择器中的活动状态
    document.querySelectorAll('.status-item').forEach((item, index) => {
        item.classList.toggle('active', index === currentStatus.id);
    });
}

// 设置状态
async function setStatus(statusIndex) {
    try {
        const response = await fetch(`/api/status/set?status=${statusIndex}`);
        const data = await response.json();

        if (data.success) {
            currentStatus.id = statusIndex;
            updateCurrentStatus();
        } else {
            alert('设置状态失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        console.error('设置状态失败:', error);
        alert('设置状态失败，请检查网络连接');
    }
}

// 渲染设备列表
function renderDeviceList() {
    const tbody = document.getElementById('device-list-body');
    tbody.innerHTML = '';

    if (Object.keys(deviceData).length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="5" style="text-align: center;">暂无设备数据</td>';
        tbody.appendChild(tr);
        return;
    }

    for (const [deviceId, device] of Object.entries(deviceData)) {
        const tr = document.createElement('tr');

        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn btn-danger';
        deleteButton.textContent = '删除';
        deleteButton.dataset.deviceId = deviceId;
        deleteButton.addEventListener('click', function () {
            removeDevice(this.dataset.deviceId);
        });

        const tdDevice = document.createElement('td');
        tdDevice.textContent = deviceId;

        const tdName = document.createElement('td');
        tdName.textContent = device.show_name;

        const tdUsing = document.createElement('td');
        tdUsing.textContent = device.using ? '使用中' : '未使用';

        const tdApp = document.createElement('td');
        tdApp.textContent = device.status;

        const tdAction = document.createElement('td');
        tdAction.appendChild(deleteButton);

        tr.appendChild(tdDevice);
        tr.appendChild(tdName);
        tr.appendChild(tdUsing);
        tr.appendChild(tdApp);
        tr.appendChild(tdAction);

        tbody.appendChild(tr);
    }
}

// 删除设备
async function removeDevice(deviceId) {
    if (!confirm(`确定要删除设备 "${deviceId}" 吗？`)) {
        return;
    }

    try {
        const response = await fetch(`/api/device/remove?id=${deviceId}`);
        const data = await response.json();

        if (data.success) {
            delete deviceData[deviceId];
            renderDeviceList();
        } else {
            alert('删除设备失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        console.error('删除设备失败:', error);
        alert('删除设备失败，请检查网络连接');
    }
}

// 清除所有设备
async function clearAllDevices() {
    if (!confirm('确定要清除所有设备吗？此操作不可撤销！')) {
        return;
    }

    try {
        const response = await fetch(`/api/device/clear`);
        const data = await response.json();

        if (data.success) {
            deviceData = {};
            renderDeviceList();
        } else {
            alert('清除设备失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        console.error('清除设备失败:', error);
        alert('清除设备失败，请检查网络连接');
    }
}

// 切换隐私模式
async function togglePrivateMode(isPrivate) {
    try {
        const response = await fetch(`/api/device/private?private=${isPrivate}`);
        const data = await response.json();

        if (data.success) {
            privateMode = isPrivate;
        } else {
            alert('切换隐私模式失败: ' + (data.message || '未知错误'));
            document.getElementById('private-mode-toggle').checked = privateMode;
        }
    } catch (error) {
        console.error('切换隐私模式失败:', error);
        alert('切换隐私模式失败，请检查网络连接');
        document.getElementById('private-mode-toggle').checked = privateMode;
    }
}

// 获取统计数据
async function fetchMetrics() {
    try {
        const response = await fetch('/api/metrics');
        const data = await response.json();

        const container = document.getElementById('metrics-container');
        container.innerHTML = '';

        // 今日访问
        if (data.daily) {
            if (data.daily['/']) {
                addMetricCard(container, '今日首页访问量', data.daily['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.daily)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '今日 API 调用次数', apiCalls);
        }

        // 本周访问
        if (data.weekly) {
            if (data.weekly['/']) {
                addMetricCard(container, '本周首页访问量', data.weekly['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.weekly)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '本周 API 调用次数', apiCalls);
        }

        // 本月访问
        if (data.monthly) {
            if (data.monthly['/']) {
                addMetricCard(container, '本月首页访问量', data.monthly['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.monthly)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '本月 API 调用次数', apiCalls);
        }

        // 本年访问
        if (data.yearly) {
            if (data.yearly['/']) {
                addMetricCard(container, '本年首页访问量', data.yearly['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.yearly)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '本年 API 调用次数', apiCalls);
        }

        // 总访问
        if (data.total) {
            if (data.total['/']) {
                addMetricCard(container, '首页总访问量', data.total['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.total)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, 'API 总调用次数', apiCalls);
        }

    } catch (error) {
        console.error('获取统计数据失败:', error);
        const container = document.getElementById('metrics-container');
        container.innerHTML = '<p>获取统计数据失败，请刷新页面重试</p>';
    }
}

// 添加统计卡片
function addMetricCard(container, label, value) {
    const card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML = `
        <div class="metric-value">${value}</div>
        <div class="metric-label">${label}</div>
    `;
    container.appendChild(card);
}

// 退出登录
function logout() {
    // 清除本地存储的密钥
    localStorage.removeItem('sleepy_secret');
    // 重定向到退出登录路由，该路由会清除 cookie
    window.location.href = '/panel/logout';
}

// 初始化事件监听器
document.addEventListener('DOMContentLoaded', function () {
    // 添加事件监听器
    const clearDevicesBtn = document.getElementById('clear-devices-btn');
    if (clearDevicesBtn) {
        clearDevicesBtn.addEventListener('click', clearAllDevices);
    }

    // 刷新数据按钮
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', initPage)
    }

    // 退出登录按钮
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }

    // 切换隐私模式按钮
    const privateModeToggle = document.getElementById('private-mode-toggle');
    if (privateModeToggle) {
        privateModeToggle.addEventListener('change', function () {
            togglePrivateMode(this.checked);
        });
    }

    // 设备删除按钮
    document.addEventListener('click', function (event) {
        const target = event.target;
        if (target.matches('button[onclick^="removeDevice"]')) {
            event.preventDefault();
            const deviceId = target.getAttribute('onclick').match(/'([^']+)'/)[1];
            removeDevice(deviceId);
            target.removeAttribute('onclick');
        }
    });
});

// 初始化页面
window.onload = initPage;
