$taskName = (Get-ScheduledTask -TaskPath "\" | Where-Object { $_.TaskName -notlike "OneDrive*" -and $_.TaskName -ne "RtkAudUService64_BG" }).TaskName

$pythonPath = "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe"
$scriptPath = "C:\Users\USER\Desktop\뉴스아카이빙\news_archiver.py"
$workingDir = "C:\Users\USER\Desktop\뉴스아카이빙"

$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $scriptPath -WorkingDirectory $workingDir
Set-ScheduledTask -TaskName $taskName -TaskPath "\" -Action $action

Write-Host "수정 완료: $taskName"
Write-Host "실행 경로: $pythonPath $scriptPath"

# 확인
$t = Get-ScheduledTask -TaskName $taskName -TaskPath "\"
$t.Actions | ForEach-Object { Write-Host "Action: $($_.Execute) $($_.Arguments)" }
