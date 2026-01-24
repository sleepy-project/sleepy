// gen by ai
let devices = [];
let currentStatus = 0; // 默认状态为0 (在线)
let privateMode = false;
let accessToken = null;

// 初始化页面
async function initPage() {
    try {
        // 从cookie获取token
        accessToken = getCookie('sleepy_secret_token');
        if (!accessToken) {
            // 如果没有token，重定向到登录页面
            window.location.href = '/panel/login';
            return;
        }

        // 验证token
        try {
            const verifyResponse = await fetch('/panel/verify', {
                headers: {
                    'X-Sleepy-Token': accessToken
                }
            });
            
            if (!verifyResponse.ok) {
                // token无效，重定向到登录
                window.location.href = '/panel/login';
                return;
            }
        } catch (error) {
            console.error('验证token失败:', error);
            window.location.href = '/panel/login';
            return;
        }

        // 获取设备列表
        const devicesResponse = await fetch('/api/devices/', {
            headers: {
                'X-Sleepy-Token': accessToken
            }
        });
        
        if (devicesResponse.ok) {
            const devicesData = await devicesResponse.json();
            devices = devicesData.devices || [];
            console.debug('获取到设备列表:', devices);
        } else if (devicesResponse.status === 401) {
            // 认证失败，重定向到登录
            window.location.href = '/panel/login';
            return;
        }

        // 获取当前状态
        const statusResponse = await fetch('/api/status/', {
            headers: {
                'X-Sleepy-Token': accessToken
            }
        });
        
        if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            currentStatus = statusData.status || 0;
            console.debug('获取到当前状态:', currentStatus);
        }

        // 更新UI
        updateCurrentStatus();
        renderDeviceList();


        // 如果启用了统计功能，获取统计数据
        if (document.getElementById('metrics-container')) {
            await fetchMetrics();
        }
    } catch (error) {
        console.error('初始化失败:', error);
        alert(`加载数据失败，请检查网络连接或重新登录\n${error}`);
    }
}

// 获取cookie值
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

// 更新当前状态显示
function updateCurrentStatus() {
    const statusName = document.getElementById('current-status-name');
    const statusDesc = document.getElementById('current-status-desc');
    
    // 根据状态值显示不同的文本
    let statusText = '未知状态';
    let statusColor = 'red';
    let descText = '';
    
    switch(currentStatus) {
        case 0:
            statusText = '在线';
            statusColor = 'green';
            descText = '用户当前在线';
            break;
        case 1:
            statusText = '离开';
            statusColor = 'orange';
            descText = '用户暂时离开';
            break;
        case 2:
            statusText = '离线';
            statusColor = 'gray';
            descText = '用户已离线';
            break;
        case 3:
            statusText = '勿扰';
            statusColor = 'red';
            descText = '请勿打扰';
            break;
        default:
            statusText = '未知';
            statusColor = 'red';
            descText = '未知状态';
    }
    
    statusName.textContent = statusText;
    statusName.style.color = statusColor;
    if (statusDesc) {
        statusDesc.textContent = descText;
    }

    // 更新状态选择按钮
    updateStatusSelector();
}

// 更新状态选择器
function updateStatusSelector() {
    const buttons = document.querySelectorAll('.status-btn');
    buttons.forEach(btn => {
        const statusValue = parseInt(btn.dataset.status);
        if (statusValue === currentStatus) {
            btn.classList.add('active');
            btn.style.backgroundColor = getStatusColor(statusValue);
        } else {
            btn.classList.remove('active');
            btn.style.backgroundColor = '';
        }
    });
}

// 根据状态值获取颜色
function getStatusColor(status) {
    switch(status) {
        case 0: return 'rgba(0, 200, 0, 0.2)'; // 在线 - 绿色
        case 1: return 'rgba(255, 165, 0, 0.2)'; // 离开 - 橙色
        case 2: return 'rgba(128, 128, 128, 0.2)'; // 离线 - 灰色
        case 3: return 'rgba(255, 0, 0, 0.2)'; // 勿扰 - 红色
        default: return 'rgba(200, 200, 200, 0.2)';
    }
}

// 设置状态
async function setStatus(statusValue) {
    try {
        const response = await fetch('/api/status/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Sleepy-Token': accessToken
            },
            body: JSON.stringify({
                status: statusValue
            })
        });

        if (response.ok) {
            currentStatus = statusValue;
            updateCurrentStatus();
            showToast('状态更新成功');
        } else if (response.status === 401) {
            window.location.href = '/panel/login';
        } else {
            const errorData = await response.json();
            alert('设置状态失败: ' + (errorData.detail || errorData.message || '未知错误'));
        }
    } catch (error) {
        console.error('设置状态失败:', error);
        alert('设置状态失败，请检查网络连接');
    }
}

// 渲染设备列表
function renderDeviceList() {
    const tbody = document.getElementById('device-list-body');
    if (!tbody) return;
    
    tbody.innerHTML = '';

    if (devices.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="6" style="text-align: center;">暂无设备数据</td>';
        tbody.appendChild(tr);
        return;
    }

    for (const device of devices) {
        const tr = document.createElement('tr');

        // 设备ID
        const tdDeviceId = document.createElement('td');
        tdDeviceId.textContent = device.id;

        // 设备名称
        const tdName = document.createElement('td');
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = device.name || device.id;
        nameInput.className = 'form-control';
        nameInput.dataset.deviceId = device.id;
        nameInput.addEventListener('change', function() {
            updateDeviceField(device.id, 'name', this.value);
        });
        tdName.appendChild(nameInput);

        // 使用状态
        const tdUsing = document.createElement('td');
        const usingSelect = document.createElement('select');
        usingSelect.className = 'form-control';
        usingSelect.dataset.deviceId = device.id;
        
        const optionFalse = document.createElement('option');
        optionFalse.value = 'false';
        optionFalse.textContent = '未使用';
        optionFalse.selected = !device.using;
        
        const optionTrue = document.createElement('option');
        optionTrue.value = 'true';
        optionTrue.textContent = '使用中';
        optionTrue.selected = device.using;
        
        usingSelect.appendChild(optionFalse);
        usingSelect.appendChild(optionTrue);
        usingSelect.addEventListener('change', function() {
            updateDeviceField(device.id, 'using', this.value === 'true');
        });
        tdUsing.appendChild(usingSelect);

        // 状态文本
        const tdStatus = document.createElement('td');
        const statusInput = document.createElement('input');
        statusInput.type = 'text';
        statusInput.value = device.status || '';
        statusInput.className = 'form-control';
        statusInput.dataset.deviceId = device.id;
        statusInput.addEventListener('change', function() {
            updateDeviceField(device.id, 'status', this.value);
        });
        tdStatus.appendChild(statusInput);

        // 最后更新时间
        const tdLastUpdated = document.createElement('td');
        if (device.last_updated) {
            const date = new Date(device.last_updated * 1000);
            tdLastUpdated.textContent = date.toLocaleString();
        } else {
            tdLastUpdated.textContent = '未知';
        }

        // 操作按钮
        const tdAction = document.createElement('td');
        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn btn-danger btn-sm';
        deleteButton.textContent = '删除';
        deleteButton.addEventListener('click', function () {
            removeDevice(device.id);
        });
        tdAction.appendChild(deleteButton);

        tr.appendChild(tdDeviceId);
        tr.appendChild(tdName);
        tr.appendChild(tdUsing);
        tr.appendChild(tdStatus);
        tr.appendChild(tdLastUpdated);
        tr.appendChild(tdAction);

        tbody.appendChild(tr);
    }
}

// 更新设备字段
async function updateDeviceField(deviceId, field, value) {
    try {
        const updateData = {};
        updateData[field] = value;
        
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-Sleepy-Token': accessToken
            },
            body: JSON.stringify(updateData)
        });

        if (response.ok) {
            showToast('设备更新成功');
            
            // 更新本地数据
            const device = devices.find(d => d.id === deviceId);
            if (device) {
                device[field] = value;
                device.last_updated = Date.now() / 1000;
            }
        } else if (response.status === 401) {
            window.location.href = '/panel/login';
        } else {
            const errorData = await response.json();
            alert('更新设备失败: ' + (errorData.detail || errorData.message || '未知错误'));
        }
    } catch (error) {
        console.error('更新设备失败:', error);
        alert('更新设备失败，请检查网络连接');
    }
}

// 删除设备
async function removeDevice(deviceId) {
    if (!confirm(`确定要删除设备 "${deviceId}" 吗？`)) {
        return;
    }

    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE',
            headers: {
                'X-Sleepy-Token': accessToken
            }
        });

        if (response.ok) {
            // 从本地数据中移除
            devices = devices.filter(device => device.id !== deviceId);
            renderDeviceList();
            showToast('设备删除成功');
        } else if (response.status === 401) {
            window.location.href = '/panel/login';
        } else {
            const errorData = await response.json();
            alert('删除设备失败: ' + (errorData.detail || errorData.message || '未知错误'));
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
        const response = await fetch('/api/devices/', {
            method: 'DELETE',
            headers: {
                'X-Sleepy-Token': accessToken
            }
        });

        if (response.ok) {
            devices = [];
            renderDeviceList();
            showToast('所有设备已清除');
        } else if (response.status === 401) {
            window.location.href = '/panel/login';
        } else {
            const errorData = await response.json();
            alert('清除设备失败: ' + (errorData.detail || errorData.message || '未知错误'));
        }
    } catch (error) {
        console.error('清除设备失败:', error);
        alert('清除设备失败，请检查网络连接');
    }
}

// 创建新设备
async function createNewDevice() {
    const deviceName = prompt('请输入设备名称:');
    if (!deviceName) return;

    try {
        const response = await fetch('/api/devices/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Sleepy-Token': accessToken
            },
            body: JSON.stringify({
                name: deviceName,
                status: '',
                using: false,
                fields: {}
            })
        });

        if (response.ok) {
            const data = await response.json();
            
            // 添加新设备到列表
            devices.push(data.device);
            renderDeviceList();
            
            // 显示token信息
            alert(`设备创建成功！\n设备ID: ${data.id}\n访问Token: ${data.token}\n刷新Token: ${data.refresh_token}\n\n请妥善保存这些信息！`);
            showToast('设备创建成功');
        } else if (response.status === 401) {
            window.location.href = '/panel/login';
        } else {
            const errorData = await response.json();
            alert('创建设备失败: ' + (errorData.detail || errorData.message || '未知错误'));
        }
    } catch (error) {
        console.error('创建设备失败:', error);
        alert('创建设备失败，请检查网络连接');
    }
}

// 获取统计数据（如果需要的话）
async function fetchMetrics() {
    try {
        // 这里可以添加统计数据的获取逻辑
        // 根据你的后端API实现
        console.log('获取统计数据...');
    } catch (error) {
        console.error('获取统计数据失败:', error);
        const container = document.getElementById('metrics-container');
        if (container) {
            container.innerHTML = '<p>获取统计数据失败，请刷新页面重试</p>';
        }
    }
}

// 显示Toast消息
function showToast(message) {
    // 创建或获取toast容器
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        `;
        document.body.appendChild(toastContainer);
    }

    // 创建toast元素
    const toast = document.createElement('div');
    toast.style.cssText = `
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 10px 20px;
        margin-bottom: 10px;
        border-radius: 4px;
        animation: fadeIn 0.3s, fadeOut 0.3s 2.7s;
    `;
    toast.textContent = message;

    toastContainer.appendChild(toast);

    // 3秒后移除
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 3000);
}

// 退出登录
function logout() {
    // 清除cookie
    document.cookie = "sleepy_secret_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    document.cookie = "sleepy_secret_refresh_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    
    // 重定向到登录页面
    window.location.href = '/panel/login';
}

// 初始化事件监听器
document.addEventListener('DOMContentLoaded', function () {
    // 状态按钮点击事件
    document.querySelectorAll('.status-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const statusValue = parseInt(this.dataset.status);
            setStatus(statusValue);
        });
    });

    // 清除所有设备按钮
    const clearDevicesBtn = document.getElementById('clear-devices-btn');
    if (clearDevicesBtn) {
        clearDevicesBtn.addEventListener('click', clearAllDevices);
    }

    // 创建设备按钮
    const createDeviceBtn = document.getElementById('create-device-btn');
    if (createDeviceBtn) {
        createDeviceBtn.addEventListener('click', createNewDevice);
    }

    // 刷新数据按钮
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', initPage);
    }

    // 退出登录按钮
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }

    // 切换隐私模式按
});

// 初始化页面
window.onload = initPage;