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
        statusElement.textContent = data.status.name;
        document.getElementById('additional-info').innerHTML = data.status.desc;
        let last_status = statusElement.classList.item(0);
        statusElement.classList.remove(last_status);
        statusElement.classList.add(data.status.color);
    }

    // 更新设备状态
    var deviceStatus = '<hr/><b><p id="device-status"><i>Device</i> Status</p></b>';
    const devices = Object.values(data.device);

    for (let device of devices) {
        let device_status;
        const escapedAppName = escapeHtml(device.status || '...');
        if (device.using) {
            const jsShowName = escapeJs(device.show_name);
            const jsAppName = escapeJs(device.status || '...');
            const jsCode = `alert('${jsShowName}: \\n${jsAppName}\\n${getFormattedTime(new Date(device.last_updated * 1000))}')`;
            const escapedJsCode = escapeHtml(jsCode);

            device_status = `
<a
    class="awake"
    title="${escapedAppName}"
    href="javascript:${escapedJsCode}">
${sliceText(escapedAppName, metadata.status.device_slice).replaceAll('\n', ' <br/>\n')}
</a>`;
        } else {
            device_status = `
<a
    class="sleeping"
    title="${escapedAppName}">
${sliceText(escapedAppName, metadata.status.device_slice).replaceAll('\n', ' <br/>\n')}
</a>`
        }
        deviceStatus += `${escapeHtml(device.show_name)}: ${device_status} <br/>`;
    }

    if (deviceStatus == '<hr/><b><p id="device-status"><i>Device</i> Status</p></b>') {
        deviceStatus = '';
    }

    const deviceStatusElement = document.getElementById('device-status');
    if (deviceStatusElement) {
        deviceStatusElement.innerHTML = deviceStatus;
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
        statusElement.classList.remove(last_status);
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
    const statusElement = document.getElementById('status');
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `正在连接服务器... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
    }

    // 关闭旧连接
    if (evtSource) {
        evtSource.close();
    }

    // 创建新连接
    evtSource = new EventSource('/api/status/events');

    // 监听连接打开事件
    evtSource.onopen = function () {
        console.log('[SSE] 连接已建立');
        connectionAttempts = 0; // 重置重连计数
        lastEventTime = Date.now(); // 初始化最后事件时间
    };

    // 监听更新事件
    evtSource.addEventListener('update', function (event) {
        lastEventTime = Date.now(); // 更新最后收到消息的时间

        const data = JSON.parse(event.data);
        console.log(`[SSE] [#${event.lastEventId}] 收到数据更新:`, data);

        if (!metadata) {
            getMetadata();
        }

        // 处理更新数据
        if (data.success) {
            updateDeviceStatus(data);
        } else {
            if (statusElement) {
                statusElement.textContent = '[!错误!]';
                document.getElementById('additional-info').textContent = data.details || '未知错误';
                let last_status = statusElement.classList.item(0);
                statusElement.classList.remove(last_status);
                statusElement.classList.add('error');
            }
        }
    });

    // 监听心跳事件
    evtSource.addEventListener('heartbeat', function (event) {
        console.log(`[SSE] [#${event.lastEventId}] 收到心跳包`);
        lastEventTime = Date.now(); // 更新最后收到消息的时间
    });

    // 错误处理 (定时重连 / 回退)
    evtSource.onerror = async function (e) {
        console.error(`[SSE] 连接错误: ${e}`);
        evtSource.close();

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
            evtSource.close();

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

// 初始化SSE连接或回退到轮询
document.addEventListener('DOMContentLoaded', function () {
    try {
        // 获取元数据
        fetch('/api/meta', { timeout: 10000 })
            .then((response) => response.json())
            .then((data) => {
                window.metadata = data;
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
    } catch (e) {
        alert(`请求元数据错误: ${e}, 请刷新页面`);
    }
    
});

// 原始轮询函数 (仅作为后备方案)
async function update() {
    let refresh_time = metadata.status.refresh_interval || 5000;
    while (true) {
        if (document.visibilityState == 'visible') {
            console.log('[Update] 页面可见，更新中...');
            let success_flag = true;
            let errorinfo = '';
            const statusElement = document.getElementById('status');
            // --- show updating
            document.getElementById('last-updated').innerHTML = `正在更新状态, 请稍候... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
            // fetch data
            fetch('/api/status/query', { timeout: 10000 })
                .then(response => response.json())
                .then(async (data) => {
                    console.log(`[Update] 返回: ${data}`);
                    if (data.success) {
                        updateDeviceStatus(data);
                    } else {
                        errorinfo = data.details || '未知错误';
                        success_flag = false;
                    }
                })
                .catch(error => {
                    errorinfo = error;
                    success_flag = false;
                });
            // 出错时显示
            if (!success_flag) {
                statusElement.textContent = '[!错误!]';
                document.getElementById('additional-info').textContent = errorinfo;
                last_status = statusElement.classList.item(0);
                statusElement.classList.remove(last_status);
                statusElement.classList.add('error');
            }
        } else {
            console.log('[Update] 页面不可见，跳过更新');
        }

        await sleep(refresh_time);
    }
}