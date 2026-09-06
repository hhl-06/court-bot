# Quick fix: switch wake-up task to pythonw.exe (no console popup)
$task = Get-ScheduledTask -TaskName 'CourtBot-WakeUpLogin'
$action = New-ScheduledTaskAction `
    -Execute 'C:\Users\hhl-06\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe' `
    -Argument 'D:\Projects\court-bot\scripts\wakeup_login.py' `
    -WorkingDirectory 'D:\Projects\court-bot'
Set-ScheduledTask -TaskName 'CourtBot-WakeUpLogin' -Action $action
Write-Host 'Done - no more popup windows'
Read-Host
