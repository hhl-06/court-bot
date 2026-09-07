# Court Bot - install "Tuesday 06:58:30 -> book Wednesday evening" scheduled task
# Runs alongside CourtBot_AutoBook (Thursday->Friday) and CourtBot_AutoBook_Tuesday (Monday->Tuesday).
$ErrorActionPreference = 'Stop'

$taskName = 'CourtBot_AutoBook_Wednesday'
$py       = 'C:\Users\hhl-06\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe'
$workDir  = 'D:\Projects\court-bot'

$arg = '-m court_bot.cli.main --config "D:\Projects\court-bot\config\config.yaml" run --target-day Wednesday'

$action    = New-ScheduledTaskAction -Execute $py -Argument $arg -WorkingDirectory $workDir
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At '06:58:30'
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host ("OK created " + $taskName + " : every Tuesday 06:58:30 -> book Wednesday 18:30-20:30")
