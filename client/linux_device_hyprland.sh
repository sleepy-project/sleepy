#!/bin/bash

# linux_device_hyprland.sh
# 在 Linux (Hyprland) 上获取窗口名称
# by: @inoryxin

# --- config start
URL="http://10.0.0.123:9010/api/device/set" # API 地址, 以 /api/device/set 结尾
SECRET="114514" # 密钥
DEVICE_ID="desktop" # 设备 id, 唯一
DEVICE_SHOW_NAME="祈歆的电脑" # 设备显示名称
# --- config end

LASTWINDOW="inoryxin" # 这个变量是让电脑第一次开机进桌面不进行任何操作是变为未使用状态时

while true; do

    HYPRCTL_BIN=$(which hyprctl)

    PACKAGE_NAME=$($HYPRCTL_BIN activewindow | grep "title:" | sed 's/title://g' | sed 's/^[[:space:]]*//')

    echo "$PACKAGE_NAME"

    if [ "$PACKAGE_NAME" = "" ]; then
        STATUS=false
    else
        STATUS=true
    fi

    echo "$STATUS"

    json_data='{
    "secret": "'$SECRET'",
    "id": "'$DEVICE_ID'",
    "show_name": "'$DEVICE_SHOW_NAME'",
    "using": '$STATUS',
    "status": "'$PACKAGE_NAME'"
}'

    if [ "$PACKAGE_NAME" = "$LASTWINDOW" ]; then
        echo "window not change, bypass"
    else
        curl -X POST "$URL" -H "Content-Type: application/json" -d "$json_data"
    fi

    LASTWINDOW="$PACKAGE_NAME"

    sleep 10
done
