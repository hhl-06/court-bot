$action = New-ScheduledTaskAction -Execute 'python3.13' `
    -Argument '-m court_bot.cli.main run' `
    -WorkingDirectory 'C:\Users\27143\court-bot'

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At '06:58:00'

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName 'CourtBot-FridayBooking' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description '周四早7点自动抢周五羽毛球场' `
    -TaskPath '\CourtBot\' `
    -Force

Write-Host 'Done! Scheduled every Thursday at 6:58 AM.'
