// gen by ai
import {
    sleep,
    sliceText,
    escapeHtml,
    escapeJs,
    getFormattedTime,
    checkVercelDeploy
} from './utils.js';

function updateDeviceStatus(data) {
    /*
    正常更新状态使用
    data: api / events 返回数据
    */
    const statusElement = document.getElementById('status');
    const lastUpdatedElement = document.getElementById('last-updated');

    // 更新状态
    if (statusElement) {
        // 根据后端返回的状态值显示不同的文本
        let statusText = '未知状态';
        let statusColor = 'error';
        let statusDesc = '';
        
        // 根据状态值设置显示文本和颜色
        switch(data.status) {
            case 0:
                statusText = '在线';
                statusColor = 'awake';
                statusDesc = '用户当前在线';
                break;
            case 1:
                statusText = '离开';
                statusColor = 'away';
                statusDesc = '用户暂时离开';
                break;
            case 2:
                statusText = '离线';
                statusColor = 'sleeping';
                statusDesc = '用户已离线';
                break;
            case 3:
                statusText = '勿扰';
                statusColor = 'busy';
                statusDesc = '请勿打扰';
                break;
            default:
                statusText = '未知';
                statusColor = 'error';
                statusDesc = '未知状态';
        }
        
        statusElement.textContent = statusText;
        document.getElementById('additional-info').textContent = statusDesc;
        
        // 更新状态颜色
        let last_status = statusElement.classList.item(0);
        if (last_status) {
            statusElement.classList.remove(last_status);
        }
        statusElement.classList.add(statusColor);
    }

    // 更新设备状态
    var deviceStatusHTML = '<hr/><b><p id="device-status"><i>Device</i> Status</p></b>';
    const devices = data.devices || [];

    for (let device of devices) {
        let device_status;
        const escapedAppName = escapeHtml(device.status || '...');
        
        // 使用metadata的配置，如果没有则使用默认值
        const sliceLength = window.metadata?.status?.device_slice || 20;
        
        if (device.using) {
            const jsShowName = escapeJs(device.name || device.id);
            const jsAppName = escapeJs(device.status || '...');
            const deviceTime = device.last_updated ? getFormattedTime(new Date(device.last_updated * 1000)) : '未知时间';
            const jsCode = `alert('${jsShowName}: \\n${jsAppName}\\n${deviceTime}')`;
            const escapedJsCode = escapeHtml(jsCode);

            device_status = `
<a
    class="awake"
    title="${escapedAppName}"
    href="javascript:${escapedJsCode}">
${sliceText(escapedAppName, sliceLength).replaceAll('\n', ' <br/>\n')}
</a>`;
        } else {
            device_status = `
<a
    class="sleeping"
    title="${escapedAppName}">
${sliceText(escapedAppName, sliceLength).replaceAll('\n', ' <br/>\n')}
</a>`;
        }
        deviceStatusHTML += `${escapeHtml(device.name || device.id)}: ${device_status} <br/>`;
    }

    // 如果没有设备，清空HTML
    if (deviceStatusHTML === '<hr/><b><p id="device-status"><i>Device</i> Status</p></b>') {
        deviceStatusHTML = '';
    }

    const deviceStatusElement = document.getElementById('device-status');
    if (deviceStatusElement) {
        deviceStatusElement.innerHTML = deviceStatusHTML;
    }

    // 更新最后更新时间
    const timenow = getFormattedTime(new Date());
    const last_updated = getFormattedTime(new Date(data.last_updated * 1000));
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `
最后更新:
<a class="awake" 
href="javascript:alert('浏览器最后更新时间: ${timenow}\\n数据最后更新时间: ${last_updated}')">
${last_updated}
</a>`;
    }
}

// 全局变量 - 重要：保证所有函数可访问
let evtSource = null;
let reconnectInProgress = false;
let countdownInterval = null;
let delayInterval = null;
let connectionCheckTimer = null;
let lastEventTime = Date.now();
let connectionAttempts = 0;
let firstError = true; // 是否为 SSR 第一次出错 (如是则激活 Vercel 部署检测)
const maxReconnectDelay = 30000; // 最大重连延迟时间为 30 秒

// 重连函数
function reconnectWithDelay(delay) {
    if (reconnectInProgress) {
        console.log('[SSE] 已经在重连过程中，忽略此次请求');
        return;
    }

    reconnectInProgress = true;
    console.log(`[SSE] 安排在 ${delay / 1000} 秒后重连`);

    // 清除可能存在的倒计时
    if (countdownInterval) {
        clearInterval(countdownInterval);
    }

    // 更新UI状态
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = '[!错误!]';
        document.getElementById('additional-info').textContent = '与服务器的连接已断开，正在尝试重新连接...';
        let last_status = statusElement.classList.item(0);
        if (last_status) {
            statusElement.classList.remove(last_status);
        }
        statusElement.classList.add('error');
    }

    // 添加倒计时更新
    let remainingSeconds = Math.floor(delay / 1000);
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `连接服务器失败，${remainingSeconds} 秒后重新连接... <a href="javascript:reconnectNow();" target="_self" style="color: rgb(0, 255, 0);">立即重连</a>`;
    }

    countdownInterval = setInterval(() => {
        remainingSeconds--;
        if (remainingSeconds > 0 && lastUpdatedElement) {
            lastUpdatedElement.innerHTML = `连接服务器失败，${remainingSeconds} 秒后重新连接... <a href="javascript:reconnectNow();" target="_self" style="color: rgb(0, 255, 0);">立即重连</a>`;
        } else if (remainingSeconds <= 0) {
            clearInterval(countdownInterval);
        }
    }, 1000);

    delayInterval = setTimeout(() => {
        if (reconnectInProgress) {
            console.log('[SSE] 开始重连...');
            clearInterval(countdownInterval); // 清除倒计时
            setupEventSource();
            reconnectInProgress = false;
        }
    }, delay);
}

// 立即重连函数
window.reconnectNow = function () {
    console.log('[SSE] 用户选择立即重连');
    clearInterval(delayInterval); // 清除当前倒计时
    clearInterval(countdownInterval);
    connectionAttempts = 0; // 重置重连计数
    setupEventSource(); // 立即尝试重新连接
    reconnectInProgress = false;
}

// 建立SSE连接
function setupEventSource() {
    // 重置重连状态
    reconnectInProgress = false;

    // 清除可能存在的倒计时
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }

    // 清除旧的定时器
    if (connectionCheckTimer) {
        clearTimeout(connectionCheckTimer);
        connectionCheckTimer = null;
    }

    // 更新UI状态
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `正在连接服务器... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
    }

    // 关闭旧连接
    if (evtSource) {
        evtSource.close();
    }

    // 创建新连接
    evtSource = new EventSource('/api/events');

    // 监听连接打开事件
    evtSource.onopen = function () {
        console.log('[SSE] 连接已建立');
        connectionAttempts = 0; // 重置重连计数
        lastEventTime = Date.now(); // 初始化最后事件时间
    };

    // 监听更新事件
    evtSource.addEventListener('update', function (event) {
        lastEventTime = Date.now(); // 更新最后收到消息的时间

        try {
            const data = JSON.parse(event.data);
            console.log(`[SSE] [#${event.lastEventId}] 收到数据更新:`, data);
            
            // 处理更新数据 - 根据事件类型处理
            if (event.type === 'connected' || event.type === 'refresh' || event.type === 'status_changed') {
                // 这些事件直接包含状态数据
                if (data && data.status !== undefined) {
                    updateDeviceStatus({
                        status: data.status,
                        devices: data.devices || [],
                        last_updated: data.last_updated || data.time || Date.now() / 1000
                    });
                }
            } else if (event.type === 'device_added' || event.type === 'device_updated' || event.type === 'device_deleted') {
                // 设备相关事件，需要重新获取完整状态
                fetchCurrentStatus();
            }
        } catch (e) {
            console.error('[SSE] 解析事件数据失败:', e);
        }
    });

    // 监听心跳事件
    evtSource.addEventListener('heartbeat', function (event) {
        console.log(`[SSE] [#${event.lastEventId}] 收到心跳包`);
        lastEventTime = Date.now(); // 更新最后收到消息的时间
    });

    // 错误处理 (定时重连 / 回退)
    evtSource.onerror = async function (e) {
        console.error(`[SSE] 连接错误:`, e);
        if (evtSource) {
            evtSource.close();
        }

        // 如是第一次错误, 检查是否为 Vercel 部署
        if (firstError) {
            const isVercel = await checkVercelDeploy();
            if (isVercel === 1) {
                // 如是，清除所有定时器, 并回退到原始轮询函数
                if (countdownInterval) {
                    clearInterval(countdownInterval);
                    countdownInterval = null;
                }
                if (connectionCheckTimer) {
                    clearTimeout(connectionCheckTimer);
                    connectionCheckTimer = null;
                }
                update();
                return;
            } else if (isVercel === 0) {
                // 如不是 (非错误), 以后错误跳过检查
                firstError = false;
            }
            // 如请求错误, 下次继续检查
        }

        // 计算重连延迟时间 (指数退避)
        const reconnectDelay = Math.min(1000 * Math.pow(2, connectionAttempts), maxReconnectDelay);
        connectionAttempts++;

        // 使用统一重连函数
        reconnectWithDelay(reconnectDelay);
    };

    // 设置长时间未收到消息的检测
    function checkConnectionStatus() {
        const currentTime = Date.now();
        const elapsedTime = currentTime - lastEventTime;

        // 只有在连接正常但长时间未收到消息时才触发重连
        if (elapsedTime > 120 * 1000 && !reconnectInProgress) {
            console.warn('[SSE] 长时间未收到服务器消息，正在重新连接...');
            if (evtSource) {
                evtSource.close();
            }

            // 使用与onerror相同的重连逻辑
            const reconnectDelay = Math.min(1000 * Math.pow(2, connectionAttempts), maxReconnectDelay);
            connectionAttempts++;
            reconnectWithDelay(reconnectDelay);
        }

        // 仅当没有正在进行的重连时才设置下一次检查
        if (!reconnectInProgress) {
            connectionCheckTimer = setTimeout(checkConnectionStatus, 10000);
        }
    }

    // 启动连接状态检查
    connectionCheckTimer = setTimeout(checkConnectionStatus, 10000);

    // 在页面卸载时关闭连接
    window.addEventListener('beforeunload', function () {
        if (evtSource) {
            evtSource.close();
        }
    });
}

// 获取当前状态
async function fetchCurrentStatus() {
    try {
        const response = await fetch('/api/query', { timeout: 10000 });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log('[Update] 获取到状态数据:', data);
        
        // 更新设备状态
        updateDeviceStatus({
            status: data.status,
            devices: data.devices || [],
            last_updated: data.last_updated || data.time || Date.now() / 1000
        });
        
        return data;
    } catch (error) {
        console.error('[Update] 获取状态失败:', error);
        
        // 更新错误状态
        const statusElement = document.getElementById('status');
        if (statusElement) {
            statusElement.textContent = '[!错误!]';
            document.getElementById('additional-info').textContent = '获取状态失败: ' + error.message;
            let last_status = statusElement.classList.item(0);
            if (last_status) {
                statusElement.classList.remove(last_status);
            }
            statusElement.classList.add('error');
        }
        
        throw error;
    }
}

// 原始轮询函数 (仅作为后备方案)
async function update() {
    let refresh_time = 5000; // 默认5秒
    
    // 如果有metadata配置，使用配置的刷新间隔
    if (window.metadata && window.metadata.status && window.metadata.status.refresh_interval) {
        refresh_time = window.metadata.status.refresh_interval;
    }
    
    while (true) {
        if (document.visibilityState == 'visible') {
            console.log('[Update] 页面可见，更新中...');
            
            // 显示更新状态
            const lastUpdatedElement = document.getElementById('last-updated');
            if (lastUpdatedElement) {
                lastUpdatedElement.innerHTML = `正在更新状态, 请稍候... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
            }
            
            // 获取数据
            try {
                await fetchCurrentStatus();
            } catch (error) {
                // 错误已在fetchCurrentStatus中处理
            }
        } else {
            console.log('[Update] 页面不可见，跳过更新');
        }

        await sleep(refresh_time);
    }
}

// 初始化SSE连接或回退到轮询
document.addEventListener('DOMContentLoaded', function () {
    try {
        // 首先获取初始状态和配置
        fetch('/api/query', { timeout: 10000 })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then((data) => {
                // 保存元数据（从响应中提取配置）
                window.metadata = {
                    status: {
                        // 这里可以添加从后端返回的配置
                        refresh_interval: 5000, // 默认值
                        device_slice: 20 // 默认值
                    }
                };
                
                // 更新初始状态
                updateDeviceStatus({
                    status: data.status,
                    devices: data.devices || [],
                    last_updated: data.last_updated || data.time || Date.now() / 1000
                });
                
                lastEventTime = Date.now();
                connectionAttempts = 0;

                // 检查浏览器是否支持SSE
                if (typeof (EventSource) !== "undefined") {
                    console.log('[SSE] 浏览器支持SSE，开始建立连接...');
                    // 初始建立连接
                    setupEventSource();
                } else {
                    // 浏览器不支持SSE，回退到轮询方案
                    console.log('[SSE] 浏览器不支持SSE，回退到轮询方案');
                    update();
                }
            })
            .catch(error => {
                console.error('获取初始状态失败:', error);
                alert(`获取初始状态错误: ${error}, 请刷新页面`);
            });
    } catch (e) {
        console.error('初始化错误:', e);
        alert(`初始化错误: ${e}, 请刷新页面`);
    }
});