/*

这个版本的预期是在autox.js设定为“更多-定时任务-特定事件-亮屏（解锁或者其他）”时启动
每次启动时检查是不是已经有脚本在启动了，如果没有，则启动，有则退出，意在解决我这种喜欢清后台的用户后台清理后脚本失效的问题

autoxjs_device.js
使用 Autox.js 编写的安卓自动更新状态脚本 - 集成音乐状态读取
需要配合 autoxjs_music_status_handle.js 一起使用
by wyf9. all rights reserved. (?)
Co-authored-by: Vanilla Nahida - 新增捕捉退出事件，将退出脚本状态上报到服务器。新增音乐播放状态检测功能，将当前正在播放的音乐的歌曲名，歌手名，专辑名上报到服务器
Co-authored-by: makabaka-andy - Changed POST to GET requests
*/

// config start
const API_URL = 'https://api.url/device/set'; // 你的完整 API 地址，以 `/device/set` 结尾
const SECRET = 'secret'; // 你的 secret
const ID = 'deviceid'; // 你的设备 id, 唯一
const SHOW_NAME = 'devicename'; // 你的设备名称, 将显示在网页上
const CHECK_INTERVAL = '3000'; // 检查间隔 (毫秒, 1000ms=1s)
const MUSIC_STATUS_FILE = "/sdcard/脚本/音乐播放状态信息.json"; // 音乐状态文件路径，默认脚本所在目录
const MUSIC_STATUS_TIMEOUT = 5 * 60 * 1000; // 音乐状态未刷新超时时间（5分钟）
// config end

auto.waitFor(); // 等待无障碍

// --- 新增：检查脚本是否已经在运行 ---
var allEngines = engines.all();
var runningCount = 0;
var currentEngine = engines.myEngine();
for (var i = 0; i < allEngines.length; i++) {
    // 根据脚本源文件路径判断是否为同一个脚本
    if (allEngines[i].getSource().toString() == currentEngine.getSource().toString()) {
        runningCount++;
    }
}
if (runningCount > 1) {
    log("检测到脚本已在运行，退出当前启动。");
    exit();
}
// --- 检查结束 ---

// 读取音乐状态文件
function readMusicStatus() {
    try {
        if (!files.exists(MUSIC_STATUS_FILE)) {
            return {
                appName: "",
                musicTitle: "",
                updateTime: 0,
                isValid: false
            };
        }
        
        const content = files.read(MUSIC_STATUS_FILE);
        return JSON.parse(content);
    } catch (e) {
        console.error("[sleepyc] 读取音乐状态文件失败: " + e);
        return {
            appName: "",
            musicTitle: "",
            updateTime: 0,
            isValid: false
        };
    }
}

// 检查音乐状态是否有效
function isMusicStatusValid() {
    const musicStatus = readMusicStatus();
    
    if (!musicStatus.isValid) {
        return false;
    }
    
    const currentTime = new Date().getTime();
    if (currentTime - musicStatus.updateTime > MUSIC_STATUS_TIMEOUT) {
        log("[check] 音乐状态已超时");
        return false;
    }
    
    return true;
}

// 替换了 secret 的日志, 同时添加前缀
function log(msg) {
    try {
        console.log(`[sleepyc] ${msg.replace(SECRET, '[REPLACED]')}`);
    } catch (e) {
        console.log(`[sleepyc] ${msg}`);
    }
}
function error(msg) {
    try {
        console.error(msg.replace(SECRET, '[REPLACED]'));
    } catch (e) {
        console.error(msg);
    }
}

let last_status = '';

function check_status() {
    /*
    检查状态并返回 app_name (如未在使用则返回空)
    [Tip] 如有调试需要可自行取消 log 注释
    */
    // log(`[check] screen status: ${device.isScreenOn()}`);
    if (!device.isScreenOn()) {
        return ('');
    }
    let app_package = currentPackage(); // 应用包名
    // log(`[check] app_package: '${app_package}'`);
    let app_name = app.getAppName(app_package); // 应用名称
    // log(`[check] app_name: '${app_name}'`);
    let battery = device.getBattery(); // 电池百分比
    // log(`[check] battery: ${battery}%`);
    // 判断设备充电状态
    let baseStatus = '';
    if (device.isCharging()) {
        baseStatus = `[🔋${battery}%⚡] 前台应用: ${app_name}`;
    } else {
        baseStatus = `[🔋${battery}%] 前台应用: ${app_name}`;
    }
    if (!app_name) {
        baseStatus = '';
    }
    
    // 检查是否有有效的音乐信息
    if (isMusicStatusValid() && baseStatus) {
        const musicStatus = readMusicStatus();
        // 组合基础状态和音乐信息
        const finalStatus = baseStatus + `\n【${musicStatus.appName}正在播放】` + '：' + musicStatus.musicTitle;
        log(`[sleepyc] 组合状态: ${finalStatus}`);
        return finalStatus;
    }
    
    return baseStatus;
}

function send_status() {
    /*
    发送 check_status() 的返回
    */
    let app_name = check_status();
    log(`ret app_name: '${app_name}'`);

    // 判断是否与上次相同
    if (app_name == last_status) {
        log('same as last status, bypass request');
        return;
    }
    last_status = app_name;
    // 判断 using
    let using = app_name !== '';
    log('[sleepyc] using: ' + using);

    // POST to api
    log(`[sleepyc] status: '${app_name}'`);
    log(`[sleepyc] POST ${API_URL}`);
    try {
        r = http.postJson(API_URL, {
            'secret': SECRET,
            'id': ID,
            'show_name': SHOW_NAME,
            'using': using,
            'app_name': app_name
        });
        log(`response: ${r.body.string()}`);
    } catch (e) {
        error(`[sleepyc] 发送状态请求出错: ${e}`);
    }
}

// 程序退出后上报停止事件
events.on("exit", function () {
    log("Script exits, uploading using = false");
    toast("[sleepy] 脚本已停止, 上报中");
    // POST to api
    log(`POST ${API_URL}`);
    try {
        r = http.postJson(API_URL, {
            'secret': SECRET,
            'id': ID,
            'show_name': SHOW_NAME,
            'using': false,
            'app_name': '[Client Exited]'
        });
        log(`发送内容：${SHOW_NAME}`)
        log(`response: ${r.body.string()}`);
        toast("[sleepy] 上报成功");
    } catch (e) {
        error(`Error when uploading: ${e}`);
        toast(`[sleepy] 上报失败! 请检查控制台日志`);
    }
});

while (true) {
    log('---------- Run\n');
    try {
        send_status();
    } catch (e) {
        error(`ERROR sending status: ${e}`);
    }
    sleep(CHECK_INTERVAL);
}