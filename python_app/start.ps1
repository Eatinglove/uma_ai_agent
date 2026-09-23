<#
  UMA MCTS Assistant - One-click Launcher
  ======================================
  啟動 mitmproxy + 系統代理 + Flask UI，Ctrl-C 停止並還原代理。
#>
param(
    [int]$Port = 5000,
    [int]$ProxyPort = 8080,
    [switch]$NoProxy   # 跳過系統代理設定 (用於測試)
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  UMA MCTS Assistant" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan

# --- 1. 安裝依賴 ---
Write-Host "`n[1/4] Checking dependencies..." -ForegroundColor Yellow
$pkgs = @{
    "flask"       = "flask"
    "msgpack"     = "msgpack"
    "lz4"         = "lz4"
    "pycryptodome" = "Crypto"
    "mitmproxy"   = "mitmproxy"
}
$missing = @()
foreach ($pipName in $pkgs.Keys) {
    $importName = $pkgs[$pipName]
    python -c "import $importName" 2>$null
    if ($LASTEXITCODE -ne 0) { $missing += $pipName }
}
if ($missing.Count -gt 0) {
    Write-Host "  Installing: $($missing -join ', ')" -ForegroundColor Yellow
    pip install $missing --quiet
}

# --- 2. 啟動 mitmdump ---
Write-Host "[2/4] Starting mitmproxy on port $ProxyPort ..." -ForegroundColor Yellow
$addon = Join-Path $Root "watcher\mitm_addon.py"
$scriptsDir = (python -c "import sysconfig; print(sysconfig.get_path('scripts'))").Trim()
$mitmdumpExe = Join-Path $scriptsDir "mitmdump.exe"
if (-not (Test-Path -LiteralPath $mitmdumpExe)) { $mitmdumpExe = "mitmdump" }

# 清除先前殘留的 mitmdump (避免 Port 被舊程序佔用)
$oldPort = Get-NetTCPConnection -LocalPort $ProxyPort -State Listen -ErrorAction SilentlyContinue
if ($oldPort) {
    foreach ($c in $oldPort | Select-Object -Unique OwningProcess) {
        if ($c.OwningProcess -eq $PID) { continue }
        $oldProc = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
        if ($oldProc -and $oldProc.CommandLine -like "*mitmdump*") {
            Write-Host "  Killing leftover mitmdump (PID $($c.OwningProcess)) on port $ProxyPort ..." -ForegroundColor Yellow
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Milliseconds 500
}

$mitmdumpProc = Start-Process -FilePath $mitmdumpExe `
    -ArgumentList "-s", $addon, "--listen-port", $ProxyPort, "-q" `
    -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 1
if ($mitmdumpProc.HasExited) {
    Write-Host "  ERROR: mitmdump failed to start. Is mitmproxy installed?" -ForegroundColor Red
    exit 1
}
Write-Host "  mitmdump PID: $($mitmdumpProc.Id)" -ForegroundColor DarkGray
if (-not $NoProxy) {
    Write-Host "  IMPORTANT: 若遊戲首次跑 https，你需要信任 mitmproxy 憑證 (證書在 ~\.mitmproxy\)" -ForegroundColor Magenta
}

# --- 3. 設定系統代理 ---
$proxySet = $false
if (-not $NoProxy) {
    Write-Host "[3/4] Setting Windows system proxy -> 127.0.0.1:$ProxyPort ..." -ForegroundColor Yellow
    $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    Set-ItemProperty -Path $regPath -Name ProxyEnable -Value 1
    Set-ItemProperty -Path $regPath -Name ProxyServer  -Value "127.0.0.1:$ProxyPort"
    $proxySet = $true
    Write-Host "  Proxy ON" -ForegroundColor DarkGray
    Write-Host "  首次使用: 若遊戲無法連線，請安裝並信任 ~\.mitmproxy\mitmproxy-ca-cert.cer 憑證" -ForegroundColor Magenta
} else {
    Write-Host "[3/4] Skipping proxy (--NoProxy)" -ForegroundColor Yellow
}

# --- 4. 啟動 Flask UI ---
Write-Host "[4/4] Starting Flask UI on http://127.0.0.1:$Port ..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:$Port" -ErrorAction SilentlyContinue

$flaskPy = Join-Path $Root "app.py"
try {
    python $flaskPy --port $Port
} finally {
    # --- Cleanup ---
    Write-Host "`nShutting down..." -ForegroundColor Yellow
    if ($proxySet) {
        Set-ItemProperty -Path $regPath -Name ProxyEnable -Value 0
        Write-Host "  Proxy OFF" -ForegroundColor DarkGray
    }
    if (-not $mitmdumpProc.HasExited) {
        Stop-Process -Id $mitmdumpProc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  mitmdump stopped" -ForegroundColor DarkGray
    }
    Write-Host "Done." -ForegroundColor Cyan
}