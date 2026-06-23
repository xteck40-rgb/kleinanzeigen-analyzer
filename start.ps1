# ============================================================================
#  Kleinanzeigen Analyzer - Starten (Ein-Prozess-Modus)
# ----------------------------------------------------------------------------
#  Startet das Backend, das auch das fertige Frontend ausliefert.
#  Danach ist ALLES unter EINER Adresse erreichbar - kein zweites Fenster:
#
#     dieser PC:         http://localhost:8000
#     im Netz/Tailscale: http://<diese-IP>:8000
#
#  Falls noch nicht eingerichtet, zuerst:  .\setup.ps1
#
#  Aufruf:  .\start.ps1     (Fenster offen lassen, Beenden mit Strg+C)
# ============================================================================
$ErrorActionPreference = "Stop"
$Root    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$VenvPy  = Join-Path $Backend "venv\Scripts\python.exe"
$Dist    = Join-Path $Root "frontend\dist"

# venv vorhanden + korrekt (Python 3.11)?
$ok = $false
if (Test-Path $VenvPy) {
    $ver = & $VenvPy -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($ver -eq "3.11") { $ok = $true }
}
if (-not $ok) {
    Write-Host "venv fehlt oder falsche Python-Version. Bitte zuerst:  .\setup.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Dist)) {
    Write-Host "frontend\dist fehlt - Frontend nicht gebaut. Bitte:  .\setup.ps1" -ForegroundColor Yellow
}

# Tailscale-IP zur Info (falls vorhanden)
$tsIp = ""
$tsExe = "C:\Program Files\Tailscale\tailscale.exe"
if (Test-Path $tsExe) { try { $tsIp = (& $tsExe ip -4 2>$null | Select-Object -First 1).Trim() } catch {} }

Write-Host "`n=== Kleinanzeigen Analyzer laeuft ===" -ForegroundColor Green
Write-Host "  Lokal:      http://localhost:8000" -ForegroundColor White
if ($tsIp) { Write-Host "  Tailscale:  http://$($tsIp):8000   (von ueberall, mit Tailscale-App)" -ForegroundColor White }
Write-Host "  Beenden:    Strg+C`n" -ForegroundColor DarkGray

Set-Location $Backend
# WICHTIG: uvicorn loggt auf stderr. Mit ErrorActionPreference=Stop wuerde PS die
# erste Log-Zeile als fatalen Fehler werten und das Skript (samt uvicorn) sofort
# beenden. Daher hier auf Continue zuruecksetzen.
$ErrorActionPreference = "Continue"
# Kein --reload: ProactorEventLoop (noetig fuer Agenten), 0.0.0.0 = im Netz erreichbar.
& $VenvPy -m uvicorn main:app --host 0.0.0.0 --port 8000
