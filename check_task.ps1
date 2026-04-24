$t = Get-ScheduledTask -TaskPath "\" | Select-Object -Last 1
$i = $t | Get-ScheduledTaskInfo
Write-Host "TaskName: $($t.TaskName)"
Write-Host "State: $($t.State)"
Write-Host "LastRunTime: $($i.LastRunTime)"
Write-Host "LastTaskResult: $($i.LastTaskResult)"
Write-Host "NextRunTime: $($i.NextRunTime)"
$t.Actions | ForEach-Object { Write-Host "Action: $($_.Execute) $($_.Arguments)" }
$t.Triggers | ForEach-Object { Write-Host "Trigger: $($_.CimClass.CimClassName) Start: $($_.StartBoundary)" }
