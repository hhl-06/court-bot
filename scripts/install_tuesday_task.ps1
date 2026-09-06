# Court Bot - install "Monday 07:00 -> book Tuesday evening" scheduled task
# Runs alongside the existing CourtBot_AutoBook (Thursday -> Friday), no conflict.
$ErrorActionPreference = 'Stop'

$taskName = 'CourtBot_AutoBook_Tuesday'
$py       = 'C:\Users\hhl-06\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe'
$workDir  = 'D:\Projects\court-bot'

$arg = '-m court_bot.cli.main --config "D:\Projects\court-bot\config\config.yaml" run --target-day Tuesday'

$action    = New-ScheduledTaskAction -Execute $py -Argument $arg -WorkingDirectory $workDir
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '06:58:30'
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host ("OK created " + $taskName + " : every Monday 07:00 -> book Tuesday 18:30-20:30")
