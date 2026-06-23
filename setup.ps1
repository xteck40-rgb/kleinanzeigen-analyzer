# ============================================================================
#  Kleinanzeigen Analyzer - Einmal-Einrichtung (auch auf einem neuen PC)
# ----------------------------------------------------------------------------
#  Macht alles Noetige:
#    1. prueft Python 3.11  (Pflicht)
#    2. erstellt das venv im backend\ neu mit 3.11
#    3. installiert Python-Pakete + Playwright-Browser
#    4. baut das Frontend (falls Node installiert ist)
#
#  Aufruf:  .\setup.ps1
#  Danach:  .\start.ps1
# ============================================================================
$ErrorActionPreference = "Stop"
$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend   = Join-Path $Root "backend"
$Frontend  = Join-Path $Root "frontend"
$VenvPy    = Join-Path $Backend "venv\Scripts\python.exe"

Write-Host "`n=== Kleinanzeigen Analyzer Setup ===`n" -ForegroundColor Cyan

# 1) Python 3.11 finden ------------------------------------------------------
Write-Host "[1/4] Suche Python 3.11..." -ForegroundColor Cyan
$has311 = $false
try { & py -3.11 --version *> $null; if ($LASTEXITCODE -eq 0) { $has311 = $true } } catch {}
if (-not $has311) {
    Write-Host "  FEHLER: Python 3.11 nicht gefunden." -ForegroundColor Red
    Write-Host "  Installieren: https://www.python.org/downloads/release/python-3119/" -ForegroundColor Red
    Write-Host "  Beim Installieren 'Add python.exe to PATH' anhaken, dann erneut ausfuehren." -ForegroundColor Red
    exit 1
}
Write-Host "  OK" -ForegroundColor Green

# 2) venv neu erstellen ------------------------------------------------------
Write-Host "[2/4] Erstelle venv (backend\venv)..." -ForegroundColor Cyan
$venvDir = Join-Path $Backend "venv"
if (Test-Path $venvDir) { Remove-Item -Recurse -Force $venvDir }
Push-Location $Backend
& py -3.11 -m venv venv
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "venv-Erstellung fehlgeschlagen" }
$ver = & $VenvPy -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($ver -ne "3.11") { Pop-Location; throw "venv nutzt Python $ver statt 3.11" }
Write-Host "  OK (Python $ver)" -ForegroundColor Green

# 3) Python-Pakete + Playwright ---------------------------------------------
Write-Host "[3/4] Installiere Pakete + Playwright-Browser (dauert beim 1. Mal)..." -ForegroundColor Cyan
& $VenvPy -m pip install --upgrade pip -q
& $VenvPy -m pip install -r (Join-Path $Backend "requirements.txt") -q
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "pip install fehlgeschlagen" }
& $VenvPy -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "playwright install fehlgeschlagen" }
Pop-Location
Write-Host "  OK" -ForegroundColor Green

# 4) Frontend bauen ----------------------------------------------------------
Write-Host "[4/4] Baue Frontend..." -ForegroundColor Cyan
$npm = (Get-Command npm -ErrorAction SilentlyContinue)
if (-not $npm) {
    Write-Host "  HINWEIS: Node.js/npm nicht gefunden - Frontend wird NICHT gebaut." -ForegroundColor Yellow
    Write-Host "  Wenn frontend\dist bereits existiert, laeuft die App trotzdem." -ForegroundColor Yellow
    Write-Host "  Sonst Node installieren (https://nodejs.org) und erneut ausfuehren." -ForegroundColor Yellow
} else {
    Push-Location $Frontend
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
        Write-Host "  npm install..." -ForegroundColor DarkGray
        & npm install
        if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install fehlgeschlagen" }
    }
    & npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm run build fehlgeschlagen" }
    Pop-Location
    Write-Host "  OK" -ForegroundColor Green
}

Write-Host "`n=== Setup fertig! ===" -ForegroundColor Green
Write-Host "Starten mit:  .\start.ps1" -ForegroundColor White
Write-Host "Autostart einrichten:  .\autostart.ps1 -Install`n" -ForegroundColor White
