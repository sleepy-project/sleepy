#!/system/bin/sh

# ========== 读取配置文件 ==========
SCRIPT_DIR=${0%/*}
CONFIG_FILE="${SCRIPT_DIR}/config.cfg"
. "$CONFIG_FILE"

# 清理变量中的换行符
SECRET=$(echo "$SECRET" | tr -d '\r\n')
DEVICE_ID=$(echo "$DEVICE_ID" | tr -d '\r\n')
URL=$(echo "$URL" | tr -d '\r\n')
LOG_NAME=$(echo "$LOG_NAME" | tr -d '\r\n')
DEVICE_NAME=$(echo "$DEVICE_NAME" | tr -d '\r\n')
CACHE=$(echo "$CACHE" | tr -d '\r\n')

# ========== 日志系统 ==========
LOG_PATH="${SCRIPT_DIR}/${LOG_NAME}"
log() {
  message="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "$message" >> "$LOG_PATH"
}
sleepy=0
# ========== 判断是否为游戏 ==========
is_game() {
  pkg="$1"
  for game in $GAME_PACKAGES; do
    if [ "$game" = "$pkg" ]; then
      #log "检测到游戏进程: $pkg，延长监测间隔 600 秒"
      sleep 600
      return 0
    fi
  done
  #log "非游戏进程: $pkg，默认监测间隔 30 秒"
  sleep 30
}

# ========== 解析应用名称 ==========
get_app_name() {
  package_name="$1"

  # 如果是锁屏状态，直接返回
  if [ "$package_name" = "NotificationShade" ]; then
    echo "锁屏了"
    return
  fi

  cached_name=$(awk -F '=' -v pkg="$package_name" '$1 == pkg {print $2; exit}' "$CACHE")
  if [ -n "$cached_name" ]; then
    echo "$cached_name"
    #log "缓存命中: $package_name=$cached_name"
    return
  fi

  # 请求应用商店获取名称
  temp_file="${SCRIPT_DIR}/temp.html"
  if curl --silent --show-error --fail -A "Mozilla/5.0" -o "$temp_file" "https://app.mi.com/details?id=$package_name"; then
    app_name=$(sed -n 's/.*<title>\(.*\)<\/title>.*/\1/p' "$temp_file" | sed 's/-[^-]*$//')
    rm -f "$temp_file"

    if [ -n "$app_name" ]; then
      echo "$app_name"
      echo "$package_name=$app_name" >> "$CACHE"
      log "已写入缓存: $package_name=$app_name"
      return
    else
      echo "$package_name"
      log "网页解析失败，回退到包名: $package_name"
    fi
  else
    echo "$package_name"
    log "网页请求失败，回退到包名: $package_name"
  fi
}

# ========== 发送状态请求 ==========
send_status() {
  package_name="$1"
  app_name=$(get_app_name "$package_name")
  
  battery_level=$(dumpsys battery | sed -n 's/.*level: \([0-9]*\).*/\1/p')
  dumpsys_charging="$(dumpsys deviceidle get charging)"
  
  if [ "$dumpsys_charging" = "true" ]; then
    res_up="$app_name[${battery_level}%]⚡"
  else
    res_up="$app_name[${battery_level}%]🔋"
  fi

  log "$res_up"
  
  # send_status调试用
  # log "尝试请求URL: $URL"
  # log "请求数据: {\"secret\": \"${SECRET}\", \"id\": \"${device_id}\", \"show_name\": \"${device_model}\", \"using\": ${using}, \"app_name\": \"$res_up\"}"

  http_code=$(curl -s --connect-timeout 35 --max-time 100 -w "%{http_code}" -o ./curl_body "$URL" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"secret": "'"${SECRET}"'", "id": "'"${DEVICE_ID}"'", "show_name": "'"${device_model}"'", "using": '"${using}"', "app_name": "'"$res_up"'"}')

  log "HTTP状态码: $http_code"

  if [ "$http_code" -ne 200 ]; then
    log "警告：请求失败，状态码 $http_code，响应内容：$(cat ./curl_body)"
  fi
}

# ========== 主流程 ==========
LAST_PACKAGE=""
> "$LOG_PATH"
log "===== 服务启动 ====="

# 获取设备信息
device_model=$(getprop ro.product.model)
android_version=$(getprop ro.build.version.release)
log "设备信息: ${device_model}, Android ${android_version}，等待一分钟"

# 覆盖设备显示名称
if [ -n "${DEVICE_NAME}" ]; then
  device_model="${DEVICE_NAME}"
fi

sleep 60
log "开！"

# ========== 核心逻辑 ==========
while true; do
  isLock=$(dumpsys window policy | sed -n 's/.*showing=\([a-z]*\).*/\1/p')
  echo "isLock: $isLock"
  if [ "$isLock" = "true" ]; then
    log "锁屏了"
    sleepy=$((sleepy + 1))
    log "锁屏计数器: $sleepy"
    PACKAGE_NAME="NotificationShade"
      # 休眠检测
      if [ "$sleepy" -ge 60 ]; then
         using="false"
         log "睡死了"
         send_status "$PACKAGE_NAME"
         sleepy=0
      else
        using="true"
      fi
  else
    sleepy=0
    using="true"
    CURRENT_FOCUS=$(dumpsys activity activities 2>/dev/null | grep -m 1 'ResumedActivity')
    PACKAGE_NAME=$(echo "$CURRENT_FOCUS" | sed -E 's/.*u0 ([^/]+).*/\1/')
  fi

  # 常规状态更新
  if [ -n "$PACKAGE_NAME" ] && [ "$PACKAGE_NAME" != "$LAST_PACKAGE" ]; then
    log "状态变化: ${LAST_PACKAGE:-none} → ${PACKAGE_NAME}"
    send_status "$PACKAGE_NAME"
    LAST_PACKAGE="$PACKAGE_NAME"
  fi
  
  is_game "$PACKAGE_NAME"
done