// ==UserScript==
// @name         页面标题上报脚本
// @namespace    sleepy
// @version      2025.3.9
// @description  获取页面标题并上报到指定 API (包括浏览器名称) / 请在安装脚本后手动编辑下面的配置
// @author       nuym
// @author       wyf9
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @connect      sleepy.wyf9.top
// @homepage     https://github.com/sleepy-project/sleepy
// @source       https://github.com/sleepy-project/sleepy/raw/refs/heads/main/client/browser-script.user.js
// ==/UserScript==

(function () {
    'use strict';

    // ===== 参数配置 =====
    const API_URL = 'https://sleepy.wyf9.top/api/device/set'; // 完整 API 地址（以 /api/device/set 结尾）
    const SECRET = '绝对猜不出来的密码';                // 你的 secret
    const ID = '114514';                               // 设备 id
    const SHOW_NAME = '';                              // 设备名称，若为空则使用浏览器名称
    const NO_TITLE = 'url';                            // 页面标题为空时返回的值：'url' 使用完整 URL, 'host' 使用域名, 其他值则直接使用该值
    const BLACKLIST = ['admin', '后台'];               // 黑名单关键词数组（标题或 URL 包含即停止上报，不区分大小写）
    // 请确保 @connect 指令中的域名与 API_URL 域名一致

    // ===== 日志处理函数 =====
    function log(msg) {
        console.log(msg.replace(SECRET, '[REPLACED]'));
    }
    function error(msg) {
        console.error(msg.replace(SECRET, '[REPLACED]'));
    }

    // ===== 黑名单检查函数 =====
    function checkBlacklist(currentTitle, currentUrl) {
        return BLACKLIST.some(keyword => {
            const lowerKeyword = keyword.toLowerCase();
            return currentTitle.toLowerCase().includes(lowerKeyword) ||
                   currentUrl.toLowerCase().includes(lowerKeyword);
        });
    }

    // ===== 获取浏览器名称 =====
    function getBrowserName() {
        const userAgent = navigator.userAgent;
        if (userAgent.includes("Edg")) {
            return "Edge";
        } else if (userAgent.includes("Chrome") && !userAgent.includes("Edg")) {
            return "Chrome";
        } else if (userAgent.includes("Firefox")) {
            return "Firefox";
        } else if (userAgent.includes("Safari") && !userAgent.includes("Chrome")) {
            return "Safari";
        } else if (userAgent.includes("Opera") || userAgent.includes("OPR")) {
            return "Opera";
        } else {
            return "Unknown Browser";
        }
    }

    // ===== 获取备用标题 =====
    function getFallbackTitle() {
        switch (NO_TITLE) {
            case 'url':  return window.location.href;
            case 'host': return window.location.hostname;
            default:     return NO_TITLE;
        }
    }

    // ===== 发送上报请求 =====
    function sendRequest(using) {
        const pageTitle = document.title;
        const pageUrl = window.location.href;

        // 黑名单检查
        if (BLACKLIST && BLACKLIST.length > 0 && checkBlacklist(pageTitle, pageUrl)) {
            log(`黑名单拦截：标题包含敏感词（${pageTitle}）或 URL 包含敏感词（${pageUrl}）`);
            return;
        }

        // 统一获取页面标题：若标题为空则采用备用标题
        const appName = pageTitle.trim() ? pageTitle : getFallbackTitle();
        log(`App name: ${appName}`);

        // 显示名称：使用配置或浏览器名称
        const showName = SHOW_NAME || getBrowserName();

        // 构造请求数据
        const postData = {
            secret: SECRET,
            id: ID,
            show_name: showName,
            using: using,
            status: appName
        };

        // 发送 POST 请求，上报数据（JSON 格式）
        GM_xmlhttpRequest({
            method: 'POST',
            url: API_URL,
            headers: {
                'Content-Type': 'application/json'
            },
            data: JSON.stringify(postData),
            onload: (response) => {
                log(`API Response: ${response.responseText}`);
                if (response.status !== 200) {
                    error(`API 请求失败: ${response.status} ${response.statusText}`);
                }
            },
            onerror: (errInfo) => {
                error(`API 请求出错: ${errInfo}`);
            }
        });
    }

    // ===== 事件监听 =====
    window.addEventListener('DOMContentLoaded', () => sendRequest(true));
    window.addEventListener('focus', () => sendRequest(true));
    window.addEventListener('blur', () => sendRequest(false));
    window.addEventListener('beforeunload', () => sendRequest(false));
})();
