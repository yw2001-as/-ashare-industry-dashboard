[CmdletBinding(SupportsShouldProcess=$true)]
param()
$ErrorActionPreference = 'Stop'
$dashboardFolder = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskName = 'AshareIndustryDashboard_ClosingHTML'
$batch = Join-Path $dashboardFolder '保存收盘看板.bat'
if (-not (Test-Path -LiteralPath $batch)) { throw 'Closing archive BAT is missing.' }
if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'This 15:00 task requires the Windows Beijing time zone.' }
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions[0].WorkingDirectory -ne $dashboardFolder) {
    throw 'A task with this name belongs to another folder. It has not been changed.'
}
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -Command "& ''{0}''; exit $LASTEXITCODE"' -f $batch.Replace("'", "''")
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $arguments -WorkingDirectory $dashboardFolder
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '15:00'
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 1)
if ($PSCmdlet.ShouldProcess($taskName, 'Install weekday 15:00 closing archive task')) {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -Description 'Weekday 15:00 closing HTML archive. Existing HTML is never overwritten.' | Out-Null
    Get-ScheduledTaskInfo -TaskName $taskName | Select-Object NextRunTime,LastTaskResult
}
