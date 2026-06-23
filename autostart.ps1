# ============================================================================
#  Kleinanzeigen Analyzer - Autostart nach Windows-Anmeldung
# ----------------------------------------------------------------------------
#  Richtet eine geplante Aufgabe ein, die start.ps1 automatisch startet,
#  sobald du dich an Windows anmeldest.
#
#  Einrichten:  .\autostart.ps1 -Install
#  Entfernen:   .\autostart.ps1 -Uninstall
#  Status:      .\autostart.ps1 -Status
#
#  Tipp fuer echten Server: Auto-Anmeldung aktivieren (netplwiz), dann faehrt
#  die App nach jedem Neustart komplett von selbst hoch.
# ============================================================================
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status
)
$ErrorActionPreference = "Stop"
$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartPs  = Join-Path $Root "start.ps1"
$TaskName = "KleinanzeigenAnalyzer"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Autostart entfernt." -ForegroundColor Green
    return
}
if ($Status) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { Write-Host "Autostart aktiv (Status: $($t.State))." -ForegroundColor Green }
    else    { Write-Host "Kein Autostart eingerichtet." -ForegroundColor Yellow }
    return
}
if (-not $Install) {
    Write-Host "Nutzung: .\autostart.ps1 -Install | -Uninstall | -Status" -ForegroundColor Yellow
    return
}

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Startet Kleinanzeigen Analyzer beim Anmelden" -Force | Out-Null

Write-Host "Autostart eingerichtet - App startet kuenftig bei jeder Windows-Anmeldung." -ForegroundColor Green
Write-Host "Sofort testen:  Start-ScheduledTask -TaskName $TaskName" -ForegroundColor White
