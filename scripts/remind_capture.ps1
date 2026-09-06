# Court Bot — 抓包提醒 (9/9 晚 21:07 触发一次)
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show(
    "今晚要重新抓取球场预约的 token！`n`n明天周四早 7:00 会自动预约周五晚场。`n`n请打开 Claude Code，找 hhl-06 带你抓包（2 分钟）。",
    "球场预约提醒",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
