$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$tool = $PSScriptRoot
$exportDir = Join-Path $tool "uma_export"

$default = "C:\Program Files\KOMOE Game\komoemumamusume\komoemumamusume Game\komoeumamusume_Data\Persistent\master\master.mdb"
$mdb = if ($args.Count -gt 0) { $args[0] } else { $default }

if (-not (Test-Path -LiteralPath $mdb)) {
    Write-Host "ERROR: master.mdb not found at: $mdb" -ForegroundColor Red
    Write-Host "Please pass the full path to your copy of master.mdb."
    exit 1
}

Push-Location $exportDir
try {
    python main.py $mdb | Out-File -FilePath "$exportDir\export.log" -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "export failed (see export.log)" }
    $copy = @("cardDB.json", "umaDB.json")
    foreach ($f in $copy) {
        $src = Join-Path $exportDir $f
        $dst = Join-Path "$proj\data" $f
        if (Test-Path -LiteralPath $dst) {
            Copy-Item -LiteralPath $dst "$dst.bak" -Force
        }
        Copy-Item -LiteralPath $src $dst -Force
    }
    Write-Host "OK: cardDB.json + umaDB.json refreshed -> $proj\data" -ForegroundColor Green
}
finally {
    Pop-Location
}