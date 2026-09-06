# Court Bot - Install wake-up campus network auto-login task
# Run as Administrator: Win+X -> Terminal(Admin) -> paste this command

$ErrorActionPreference = "Stop"

$TaskName = "CourtBot-WakeUpLogin"
$PythonPath = (Get-Command python).Source
$ScriptPath = "$PSScriptRoot\wakeup_login.py"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Court Bot - WakeUp Campus Login" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Triggers: System Resume | Screen Unlock | User Logon"
Write-Host "Action:   Auto-login Dr.COM campus network"
Write-Host ""

# Remove old task if exists
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create new task
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument $ScriptPath
$Trigger1 = New-ScheduledTaskTrigger -AtLogon
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger1 -Settings $Settings -Force

Write-Host "SUCCESS: Task installed!" -ForegroundColor Green
Write-Host "Auto-login on: Windows logon / wake / unlock"
Write-Host "Verify: taskschd.msc -> search '$TaskName'"
Write-Host ""

pause
