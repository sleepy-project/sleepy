/*

这个版本的预期是在autox.js设定为“更多-定时任务-特定事件-每分钟一次时”启动
（最初是考虑用循环执行来替代代码中的循环，也是为了避免脚本关闭的问题）该脚本初次启动时会创建文件保存上次提交的信息，如果重复则不上报，更节约系统资源（大概）

autoxjs_device.js
使用 Autox.js 编写的安卓自动更新状态脚本 - 集成音乐状态读取
需要配合 autoxjs_music_status_handle.js 一起使用
by wyf9. all rights reserved. (?)
Co-authored-by: Vanilla Nahida - 新增捕捉退出事件，将退出脚本状态上报到服务器。新增音乐播放状态检测功能，将当前正在播放的音乐的歌曲名，歌手名，专辑名上报到服务器
Co-authored-by: makabaka-andy - Changed POST to GET requests
*/

// config start
var API_URL = 'https://api.url/device/set'; // 你的完整 API 地址，以 `/device/set` 结尾
var SECRET = 'secret'; // 你的 secret
var ID = 'deviceid'; // 你的设备 id, 唯一,自定义
var SHOW_NAME = 'devicename'; // 你的设备名称, 将显示在网页上
var CHECK_INTERVAL = '3000'; // 检查间隔 (毫秒, 1000ms=1s)
var MUSIC_STATUS_FILE = "/sdcard/脚本/音乐播放状态信息.json"; // 音乐状态文件路径，默认脚本所在目录
var MUSIC_STATUS_TIMEOUT = 5 * 60 * 1000; // 音乐状态未刷新超时时间（5分钟）
// config end

auto.waitFor(); 

// --- 工具函数 ---

function readMusicStatus() {
    try {
        if (!files.exists(MUSIC_STATUS_FILE)) return { isValid: false };
        return JSON.parse(files.read(MUSIC_STATUS_FILE));
    } catch (e) {
        return { isValid: false };
    }
}

function isMusicStatusValid(musicStatus) {
    if (!musicStatus || !musicStatus.isValid) return false;
    const currentTime = new Date().getTime();
    return (currentTime - musicStatus.updateTime <= MUSIC_STATUS_TIMEOUT);
}

function log(msg) {
    console.log(`[sleepyc] ${msg.replace(SECRET, '[REPLACED]')}`);
}

// --- 状态对比函数 ---

function getSavedStatus() {
    if (files.exists(LAST_STATUS_FILE)) {
        return files.read(LAST_STATUS_FILE);
    }
    return "";
}

function saveCurrentStatus(status) {
    files.write(LAST_STATUS_FILE, status);
}

// --- 核心逻辑 ---

function check_status() {
    if (!device.isScreenOn()) {
        return ''; // 屏幕关闭时上报空，代表空闲
    }

    let app_package = currentPackage();
    let app_name = app.getAppName(app_package);
    let battery = device.getBattery();
    let baseStatus = "";

    if (app_name) {
        let chargeIcon = device.isCharging() ? "⚡" : "";
        baseStatus = `[🔋${battery}%${chargeIcon}] 前台: ${app_name}`;
    }

    const musicStatus = readMusicStatus();
    if (isMusicStatusValid(musicStatus) && baseStatus) {
        return baseStatus + `\n【${musicStatus.appName}播放中】: ${musicStatus.musicTitle}`;
    }
    
    return baseStatus;
}

function main() {
    log('---------- Start Single Run');
    
    let current_status = check_status();
    let last_status = getSavedStatus();

    // 状态未改变，直接退出脚本，不浪费流量
    if (current_status === last_status) {
        log('Status unchanged, exiting...');
        return; 
    }

    let using = current_status !== '';
    log(`New Status: '${current_status}'`);

    try {
        let r = http.postJson(API_URL, {
            'secret': SECRET,
            'id': ID,
            'show_name': SHOW_NAME,
            'using': using,
            'app_name': current_status || "[Idle]" // 如果为空则上报空闲
        });
        
        if (r && r.statusCode == 200) {
            log(`Upload Success: ${r.body.string()}`);
            saveCurrentStatus(current_status); // 只有成功了才更新本地缓存
        } else {
            log(`Upload Failed, code: ${r ? r.statusCode : 'unknown'}`);
        }
    } catch (e) {
        console.error(`[sleepyc] Error: ${e}`);
    }
}

// 执行主程序
main();