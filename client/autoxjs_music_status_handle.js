/* -*- Mode: java; tab-width: 8; indent-tabs-mode: nil; c-basic-offset: 4 -*-
 *
 * By @Vanilla Nahida
 * 音乐通知监听脚本 - 将音乐播放状态写入文件
 * 支持网易云音乐、QQ音乐、酷狗音乐、酷我音乐等主流音乐软件的通知栏音乐状态信息
 * 需要授予 Auto JS 读取通知的权限和存储权限
 * 前台默认输出的格式为：歌曲名 - 歌手名 - 专辑名
 * 你可以根据需要修改输出格式
 */

// config start
// 常用音乐软件的包名白名单
var musicAppWhitelist = {
    "网易云音乐": "com.netease.cloudmusic",
    "QQ音乐": "com.tencent.qqmusic", 
    "酷狗音乐": "com.kugou.android",
    "酷我音乐": "cn.kuwo.player",
    "Spotify": "com.spotify.music",
    "Apple Music": "com.apple.android.music",
    "YouTube Music": "com.google.android.youtube",
    "咪咕音乐": "cmccwm.mobilemusic",
    "LX Music": "cn.toside.music.mobile"
    // 可以根据需要添加更多音乐应用，格式为"应用名称": "包名"
    // 其中应用名称会在前台中显示
};

// 音乐状态文件路径
const MUSIC_STATUS_FILE = "/sdcard/脚本/音乐播放状态信息.json";
// config end

// 检查目录是否存在
files.ensureDir(files.path(MUSIC_STATUS_FILE));

// 初始化音乐状态文件
function initMusicStatusFile() {
    var initialStatus = {
        appName: "",
        musicTitle: "",
        updateTime: 0,
        isValid: false
    };
    files.write(MUSIC_STATUS_FILE, JSON.stringify(initialStatus));
}

// 写入音乐状态到文件
function writeMusicStatus(appName, musicTitle) {
    var status = {
        appName: appName,
        musicTitle: musicTitle,
        updateTime: new Date().getTime(),
        isValid: true
    };
    
    try {
        files.write(MUSIC_STATUS_FILE, JSON.stringify(status));
        console.log("写入音乐状态: " + appName + " - " + musicTitle);
    } catch (e) {
        console.error("写入音乐状态文件失败: " + e);
    }
}

// 启用通知监听，需要授予 Auto JS 读取通知的权限
events.observeNotification();

// 监听通知事件
events.onNotification(function(notification) {
    // 检查是否为媒体通知
    if (notification.category === "transport") {
        // 获取通知的包名
        var packageName = notification.getPackageName();
        // 检查是否在白名单中
        if (isInMusicWhitelist(packageName)) {
            processMusicNotification(notification);
        }
    }
});

function isInMusicWhitelist(packageName) {
    // 遍历白名单检查包名
    for (var appName in musicAppWhitelist) {
        if (musicAppWhitelist[appName] === packageName) {
            return true;
        }
    }
    return false;
}

function processMusicNotification(notification) {
    // 获取应用名称
    var appName = getAppNameFromPackage(notification.getPackageName());
    
    // console.log("音乐应用: " + appName);
    // console.log("通知标题: " + notification.getTitle());
    // console.log("通知内容: " + notification.getText());

    // 获取音乐标题（优先使用标题，否则使用通知文本）
    var musicTitle = `${notification.getTitle()} - ${notification.getText()}` || notification.getTitle() || notification.getText() ||  '';
    
    if (musicTitle && appName) {
        console.log("成功提取音乐信息: " + appName + " - " + musicTitle);
        // 写入到文件
        writeMusicStatus(appName, musicTitle);
    } else {
        console.log("无法提取有效的音乐信息");
    }

    console.log("========================\n");
}

function getAppNameFromPackage(packageName) {
    // 从白名单中查找对应的应用名称
    for (var appName in musicAppWhitelist) {
        if (musicAppWhitelist[appName] === packageName) {
            return appName;
        }
    }
    return packageName; // 如果未找到，返回包名本身
}
events.on("exit", function () {
    console.log("脚本退出，清理音乐状态文件");
    toast("脚本已停止, 清理音乐状态文件");
    // 清理音乐状态文件
    initMusicStatusFile();
    console.log("音乐状态文件已清理");
    toast("音乐状态文件已清理");
});

// 初始化
// console.log("初始化音乐状态文件");
initMusicStatusFile();
toast("音乐通知监听已启动");
console.log("开始监听音乐播放通知...");

// console.log("音乐软件白名单已加载: " + Object.keys(musicAppWhitelist).join(", "));
// console.log("音乐状态文件: " + MUSIC_STATUS_FILE);

// 保持脚本运行
setInterval(() => {}, 1000);
