# Court Bot - install BOTH weekly auto-book tasks with precise 07:00 firing.
# Optimized timing: trigger early (06:58:30), let the scheduler pre-fetch and
# pre-warm (user info + goodsId), then fire the create request at ~07:00:00.
# No "--now" flag: the scheduler handles the sub-second timing internally.
$ErrorActionPreference = 'Stop'

$py      = 'C:\Users\hhl-06\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe'
$workDir = 'D:\Projects\court-bot'
$cfg     = 'D:\Projects\court-bot\config\config.yaml'

# name, weekly day-of-week (enum), target booking day
$tasks = @(
    @{ Name = 'CourtBot_AutoBook';         Dow = 'Thursday'; Target = 'Friday'  },
    @{ Name = 'CourtBot_AutoBook_Tuesday'; Dow = 'Monday';   Target = 'Tuesday' }
)

foreach ($t in $tasks) {
    $arg = "-m court_bot.cli.main --config `"$cfg`" run --target-day $($t.Target)"
    $action    = New-ScheduledTaskAction -Execute $py -Argument $arg -WorkingDirectory $workDir
    $trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $t.Dow -At '06:58:30'
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings  = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host ("OK " + $t.Name + " : every " + $t.Dow + " 06:58:30 -> book " + $t.Target + " 18:30-20:30")
}
