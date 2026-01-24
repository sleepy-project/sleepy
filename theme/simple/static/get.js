// Simple theme - minimal JavaScript for device status updates

import { sleep, escapeHtml, getFormattedTime } from "../../default/static/utils";

// 获取设备状态
async function getStatus() {
    try {
        const response = await fetch('/api/status/query');
        const data = await response.json();

        if (data.success) {
            updateManualStatus(data.status, data.last_updated);
            updateDeviceStatus(data.device);
        }
    } catch (error) {
        console.error('获取设备状态失败:', error);
    }
}

// 更新手动状态显示
function updateManualStatus(status, last_updated) {
    const statusElement = document.getElementById('status');
    const descElement = document.getElementById('additional-info');
    const lastUpdatedElement = document.getElementById('last-updated');

    if (statusElement) {
        statusElement.innerHTML = status.name;
    }
    if (descElement) {
        descElement.innerHTML = status.desc;
    }
    if (lastUpdatedElement) {
        lastUpdatedElement.innerText = `最后更新: ${getFormattedTime(new Date(last_updated * 1000))}`
    }
}

// 更新设备状态显示
function updateDeviceStatus(devices) {
    const deviceStatusElement = document.getElementById('device-status');
    if (!deviceStatusElement) return;

    if (Object.keys(devices).length === 0) {
        deviceStatusElement.textContent = '[无设备数据]';
        return;
    }

    let deviceList = '';
    for (const [deviceId, device] of Object.entries(devices)) {
        deviceList += `${escapeHtml(device.name)}: ${device.using ? '使用中' : '未使用'} - ${escapeHtml(device.status || '...')} - ${getFormattedTime(new Date(device.last_updated * 1000))}<br/>\n`;
    }

    deviceStatusElement.innerHTML = deviceList.trim();
}

// 页面加载完成后开始获取设备状态
document.addEventListener('DOMContentLoaded', async function () {
    while (true) {
        getStatus();
        await sleep(10000);
    }
});
