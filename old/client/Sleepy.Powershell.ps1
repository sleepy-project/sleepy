# Sleepy.Powershell
# A PowerShell script to send device status to Sleepy server.
# Author: NT_AUTHORITY

# CONFIGURATION
$SERVER = "http://localhost:9010" # Your sever address, e.g., https://sleepy.wyf9.top don't use / at the end!
$SECRET = "Your_Secret_Password" # Don't leak this!
$DEVICE_ID = "your_device_id" # Your device ID, don't contain sensitive information, like password, etc.
$DEVICE_SHOW_NAME = "Your Device Display Name" # Displays on the webpage, can be anything you want. e.g., "My PC", "My Laptop", etc.
$CHECK_INTERVAL = 2 # Check interval in seconds
$BYPASS_SAME_REQUEST = $true # Whether to bypass sending the same request multiple times
$MOUSE_IDLE_TIME = 15
$MOUSE_MOVE_THRESHOLD = 10
$DEBUG = $true
$PROXY = "" # Using system proxy instead of this, leave it empty. Changing this will not work.
$SKIPPED_NAMES = @("", "系统托盘溢出窗口。", "新通知", "任务切换", "快速设置", "通知中心", "搜索", "Flow.Launcher") # What is this?
$NOT_USING_NAMES = @("我们喜欢这张图片，因此我们将它与你共享。", "启动")

Add-Type -AssemblyName System.Windows.Forms

# GET WINDOW TITLE
function Get-ForegroundWindowTitle {
    Add-Type @"
    using System;
    using System.Text;
    using System.Runtime.InteropServices;
    public class WinAPI {
        [DllImport("user32.dll")]
        public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")]
        public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
        public static string GetWindowTitle() {
            const int nChars = 256;
            StringBuilder Buff = new StringBuilder(nChars);
            IntPtr handle = GetForegroundWindow();
            if (GetWindowText(handle, Buff, nChars) > 0) {
                return Buff.ToString();
            }
            return "";
        }
    }
"@
    return [WinAPI]::GetWindowTitle()
}

# SEND HTTP REQUEST
function Send-DeviceStatus {
    param (
        [bool]$Using,
        [string]$AppName
    )
    $Body = @{
        secret = $SECRET
        id = $DEVICE_ID
        show_name = $DEVICE_SHOW_NAME
        using = $Using
        status = $AppName
    } | ConvertTo-Json
    $Headers = @{
        "Content-Type" = "application/json"
    }
    try {
        $Response = Invoke-RestMethod -Uri "$SERVER/api/device/set" -Method Post -Headers $Headers -Body $Body
        if ($DEBUG) {
            Write-Host "Response: $($Response | ConvertTo-Json)"
        }
    } catch {
        Write-Host "Error: $_"
    }
}

# GET MOUSE CURSOR POSITION
$LastMousePos = [System.Windows.Forms.Cursor]::Position
$LastMouseMoveTime = Get-Date
$IsMouseIdle = $false

function Check-MouseIdle {
    $CurrentPos = [System.Windows.Forms.Cursor]::Position
    $CurrentTime = Get-Date
    $Distance = [math]::Sqrt(([math]::Pow(($CurrentPos.X - $LastMousePos.X), 2)) + [math]::Pow(($CurrentPos.Y - $LastMousePos.Y), 2))
    
    if ($Distance -gt $MOUSE_MOVE_THRESHOLD) {
        $global:LastMousePos = $CurrentPos
        $global:LastMouseMoveTime = $CurrentTime
        if ($global:IsMouseIdle) {
            $global:IsMouseIdle = $false
            Write-Host "Mouse wake up."
        }
        return $false
    }

    $IdleTime = ($CurrentTime - $LastMouseMoveTime).TotalMinutes
    if ($IdleTime -gt $MOUSE_IDLE_TIME) {
        if (-not $global:IsMouseIdle) {
            $global:IsMouseIdle = $true
            Write-Host "Mouse entered idle state."
        }
        return $true
    }

    return $global:IsMouseIdle
}

# MAIN LOOP
$LastWindowTitle = ""

while ($true) {
    $CurrentWindow = Get-ForegroundWindowTitle
    $MouseIdle = Check-MouseIdle
    $Using = $true

    if ($MouseIdle) {
        $Using = $false
        $CurrentWindow = ""
    } else {
        if ($NOT_USING_NAMES -contains $CurrentWindow) {
            $Using = $false
        }
    }

    if (($MouseIdle -ne $IsMouseIdle) -or ($CurrentWindow -ne $LastWindowTitle) -or (-not $BYPASS_SAME_REQUEST)) {
        Write-Host "Sending update: using = $Using, status = '$CurrentWindow'"
        Send-DeviceStatus -Using $Using -AppName $CurrentWindow
        $global:LastWindowTitle = $CurrentWindow
    }

    Start-Sleep -Seconds $CHECK_INTERVAL
}
