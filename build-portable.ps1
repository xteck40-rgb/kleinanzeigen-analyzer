# ============================================================================
#  Kleinanzeigen Analyzer - PORTABLE BUILD
# ----------------------------------------------------------------------------
#  Packt alles (Python, Browser, Backend, Frontend) in EINEN Ordner mit einer
#  .exe. Diesen Ordner 1:1 auf einen anderen Windows-PC kopieren und die .exe
#  starten - OHNE Python, Node oder sonst etwas zu installieren.
#
#  Ergebnis:  Desktop\KleinanzeigenAnalyzer-Portable\
#
#  Aufruf:  .\build-portable.ps1
# ============================================================================
$ErrorActionPreference = "Stop"
$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend  = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPy   = Join-Path $Backend "venv\Scripts\python.exe"
$OutName  = "KleinanzeigenAnalyzer"
$Desktop  = [Environment]::GetFolderPath("Desktop")
$OutDir   = Join-Path $Desktop "KleinanzeigenAnalyzer-Portable"
$PwDir    = Join-Path $Backend "pw-browsers"

if (-not (Test-Path $VenvPy)) { throw "venv fehlt - zuerst .\setup.ps1 ausfuehren." }

Write-Host "`n=== Portable Build ===`n" -ForegroundColor Cyan

# 1) Frontend bauen ----------------------------------------------------------
Write-Host "[1/5] Frontend bauen..." -ForegroundColor Cyan
Push-Location $Frontend
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { & npm install }
& npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm run build fehlgeschlagen" }
Pop-Location
Write-Host "  OK" -ForegroundColor Green

# 2) PyInstaller + Browser lokal --------------------------------------------
Write-Host "[2/5] Build-Werkzeuge + Browser vorbereiten..." -ForegroundColor Cyan
& $VenvPy -m pip install --upgrade pyinstaller -q
if ($LASTEXITCODE -ne 0) { throw "pyinstaller-Installation fehlgeschlagen" }
if (Test-Path $PwDir) { Remove-Item -Recurse -Force $PwDir }
$env:PLAYWRIGHT_BROWSERS_PATH = $PwDir
& $VenvPy -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install fehlgeschlagen" }
Write-Host "  OK" -ForegroundColor Green

# 3) Alten Build entfernen ---------------------------------------------------
Write-Host "[3/5] Alten Build entfernen..." -ForegroundColor Cyan
Get-Process $OutName -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false -ErrorAction SilentlyContinue
if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
if (Test-Path (Join-Path $Desktop $OutName)) { Remove-Item -Recurse -Force (Join-Path $Desktop $OutName) }
$work = Join-Path $Backend "build"; $spec = Join-Path $Backend "$OutName.spec"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
if (Test-Path $spec) { Remove-Item -Force $spec }
Write-Host "  OK" -ForegroundColor Green

# 4) PyInstaller -------------------------------------------------------------
Write-Host "[4/5] Exe bauen (dauert ein paar Minuten)..." -ForegroundColor Cyan
Push-Location $Backend
$distSrc = Join-Path $Frontend "dist"
& $VenvPy -m PyInstaller main.py `
    --name $OutName --onedir --noconfirm --clean --distpath $Desktop --paths . `
    --add-data "$distSrc;frontend_dist" `
    --add-data "$PwDir;pw-browsers" `
    --add-data "plz_coords.json;." `
    --collect-all playwright `
    --collect-all claude_agent_sdk `
    --collect-submodules uvicorn `
    --collect-data certifi `
    --hidden-import "uvicorn.loops.asyncio" `
    --hidden-import "uvicorn.protocols.http.h11_impl" `
    --hidden-import "uvicorn.protocols.websockets.websockets_impl" `
    --hidden-import "uvicorn.lifespan.on"
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { throw "PyInstaller fehlgeschlagen (Exit $code)" }
$built = Join-Path $Desktop $OutName
if (Test-Path $built) { Rename-Item -Path $built -NewName "KleinanzeigenAnalyzer-Portable" }
Write-Host "  OK" -ForegroundColor Green

# 5) Starthilfe + Daten beilegen --------------------------------------------
Write-Host "[5/5] Starthilfe beilegen..." -ForegroundColor Cyan
$bat = "@echo off`r`ntitle Kleinanzeigen Analyzer`r`nstart `"`" `"%~dp0KleinanzeigenAnalyzer.exe`"`r`ntimeout /t 5 >nul`r`nstart `"`" http://localhost:8000`r`n"
[IO.File]::WriteAllText((Join-Path $OutDir "Start.bat"), $bat, [Text.Encoding]::ASCII)
$srcDb = Join-Path $Backend "kleinanzeigen.db"
if (Test-Path $srcDb) { Copy-Item $srcDb (Join-Path $OutDir "kleinanzeigen.db") -Force }
Write-Host "  OK" -ForegroundColor Green

Write-Host "`n=== FERTIG ===" -ForegroundColor Green
Write-Host "Ordner: $OutDir" -ForegroundColor White
Write-Host "Diesen Ordner auf den anderen PC kopieren, Start.bat doppelklicken.`n" -ForegroundColor White
