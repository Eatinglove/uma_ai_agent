<#
  Aoharu Sim Sandbox - One-click Launcher
  =======================================
  Starts only the Flask web UI for the aoharu simulation sandbox at
  http://127.0.0.1:5000/sim. No mitmproxy / system proxy needed.
  For "live" mode, run the main launcher once first (watcher writes current_turn.json).
#>
param(
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  Aoharu Sim Sandbox" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan

# --- 1. Check dependencies ---
Write-Host "`n[1/2] Checking dependencies..." -ForegroundColor Yellow
python -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing flask ..." -ForegroundColor Yellow
    pip install flask --quiet
}

# --- 2. Start Flask and open browser ---
Write-Host "[2/2] Starting Flask UI on http://127.0.0.1:$Port/sim ..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:$Port/sim" -ErrorAction SilentlyContinue
Write-Host ("  If the browser did not open, visit http://127.0.0.1:{0}/sim" -f $Port) -ForegroundColor DarkGray
Write-Host "  Close this window to stop." -ForegroundColor DarkGray

$flaskPy = Join-Path $Root "app.py"
python $flaskPy --port $Port
Write-Host "`nDone." -ForegroundColor Cyan