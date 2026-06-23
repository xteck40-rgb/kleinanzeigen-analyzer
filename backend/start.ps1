# Idempotent bootstrap + start for kleinanzeigen-analyzer backend.
# Creates venv with Python 3.11 if missing, installs deps + Playwright browser
# on first run, then launches uvicorn. Subsequent runs only activate + start.
#
# Usage:
#   .\start.ps1            # start uvicorn (default)
#   .\start.ps1 -Setup     # force reinstall deps + browsers
#   .\start.ps1 -Shell     # activate venv into current shell, no server

param(
    [switch]$Setup,
    [switch]$Shell,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvDir   = Join-Path $ScriptDir "venv"
$VenvPy    = Join-Path $VenvDir "Scripts\python.exe"
$Activate  = Join-Path $VenvDir "Scripts\Activate.ps1"
$Marker    = Join-Path $VenvDir ".deps_installed"
$ReqFile   = Join-Path $ScriptDir "requirements.txt"
$PyVersion = "3.11"

function Test-VenvValid {
    if (-not (Test-Path $VenvPy)) { return $false }
    $ver = & $VenvPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    return ($ver -eq $PyVersion)
}

if (-not (Test-VenvValid)) {
    Write-Host "[start] Creating venv with Python $PyVersion..." -ForegroundColor Cyan
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
    & py "-$PyVersion" -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "py -$PyVersion -m venv failed. Install Python $PyVersion from python.org." }
    $Setup = $true
}

& $Activate

if ($Setup -or -not (Test-Path $Marker)) {
    Write-Host "[start] Installing dependencies..." -ForegroundColor Cyan
    & $VenvPy -m pip install --upgrade pip
    & $VenvPy -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

    Write-Host "[start] Installing Playwright chromium..." -ForegroundColor Cyan
    & $VenvPy -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "playwright install failed." }

    New-Item -ItemType File -Path $Marker -Force | Out-Null
    Write-Host "[start] Setup complete." -ForegroundColor Green
}

if ($Shell) {
    Write-Host "[start] venv activated. Exit shell to leave." -ForegroundColor Green
    return
}

Write-Host "[start] Launching uvicorn on http://127.0.0.1:8000 ..." -ForegroundColor Green
if ($Reload) {
    Write-Host "[start] WARNING: --reload uses SelectorEventLoop on Windows; agent pipeline (claude CLI subprocess) will fail. Use only for non-pipeline work." -ForegroundColor Yellow
    & $VenvPy -m uvicorn main:app --reload
} else {
    & $VenvPy -m uvicorn main:app
}
