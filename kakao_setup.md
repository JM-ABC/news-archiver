# 카톡 브리핑 자동 발송 — 작업 스케줄러 등록 가이드

`cron_setup.md`와 동일한 방식이지만, 화면 팝업을 사람이 봐야 하므로
**"사용자가 로그온했을 때만 실행"** 옵션을 반드시 사용합니다 (백그라운드/무인 실행 금지).

## 사전 준비

1. `pip install -r requirements-kakao.txt`
2. `.env`에 `KAKAO_CHATROOM_NAME`, `KAKAO_APPROVAL_TIMEOUT_MIN` 설정
3. 카카오톡 PC 앱 로그인 상태 유지
4. 대상 오픈채팅방을 더블클릭해 별도 창으로 열어두기 (최소화는 가능)
5. **실행 직전, 그 채팅방 입력창에 쓰다 만 메시지를 남겨두지 마세요** — 스크립트가 발송 전 입력창을 전부 지우고 시작하므로, 쓰던 내용이 있으면 그대로 사라집니다.

## PowerShell로 등록

```powershell
$action  = New-ScheduledTaskAction `
    -Execute "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe" `
    -Argument "kakao_notify.py" `
    -WorkingDirectory "C:\Users\USER\Desktop\projects\뉴스아카이빙"

# GitHub Actions 예약 실행이 지연되면(실제로 몇 시간까지 지연된 사례 있음) 08:20에
# 아직 그날 리포트가 GitHub에 안 올라와 있을 수 있다. kakao_notify.py는 이 경우
# 조용히 종료하도록 설계돼 있으므로(오류·팝업 없음), 08:20부터 30분 간격으로
# 3시간(11:20까지) 재시도하도록 트리거를 반복 설정한다. 이미 발송했으면 마커
# 파일 덕분에 재시도 때 그냥 조용히 넘어간다.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Wednesday,Friday -At "08:20AM"
$repeatSource = New-ScheduledTaskTrigger -Once -At "08:20AM" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 3)
$trigger.Repetition = $repeatSource.Repetition

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 40) `
    -RestartCount 0

Register-ScheduledTask `
    -TaskName  "커머스카톡봇" `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Limited `
    -Force
```

> `-RunLevel Limited`와 기본 로그온 트리거 조합을 쓰면 사용자가 로그온해 있을 때
> 화면이 보이는 상태로 실행됩니다. "가장 높은 권한으로 실행"이나
> "사용자가 로그온하지 않았어도 실행"은 체크하지 마세요 — 팝업이 안 보이면
> 승인을 못 해서 항상 타임아웃으로 취소됩니다.
>
> `-Execute`는 `python`이 아니라 python.exe 전체 경로를 씁니다 — 작업 스케줄러가
> 실행될 때 PATH가 대화형 셸과 다를 수 있어, "python을 찾을 수 없음"으로 조용히
> 실패하는 걸 방지합니다. 정확한 경로는 `(Get-Command python).Source`로 확인하세요.

## 즉시 테스트

```powershell
cd "C:\Users\USER\Desktop\projects\뉴스아카이빙"
python kakao_notify.py --dry-run   # 실제 전송 없이 메시지만 확인
python kakao_notify.py             # 실제 팝업 + 전송까지
```

## 문제 해결

- **팝업이 안 뜬다**: 작업 스케줄러 트리거가 "사용자가 로그온했을 때"로 되어 있는지 확인
- **채팅방 창을 못 찾는다**: 오픈채팅방을 더블클릭해 별도 창으로 열어뒀는지, `KAKAO_CHATROOM_NAME`이 창 제목과 정확히 일치하는지 확인. 안 읽은 메시지가 있으면 카카오톡이 창 제목 앞에 `[숫자]`를 붙이는 경우가 있어 정확히 일치하지 않을 수 있습니다 — 이 경우 창을 한 번 클릭해서 읽음 처리한 뒤 다시 시도하세요.
- **매번 이메일로 실패 알림이 온다**: 카카오톡 UI 업데이트로 자동화가 깨졌을 가능성 — `kakao_notify.py`의 `send_via_kakao` 캘리브레이션을 다시 확인
- **"Enter 입력 후 ... 확인할 수 없습니다" 실패 메일을 받았다**: 이 경우는 실제로는 정상 전송됐는데 확인만 못 했을 수도 있습니다. 곧바로 재시도(수동 발송 포함)하지 말고, 먼저 채팅방에 들어가 실제로 메시지가 갔는지 눈으로 확인한 뒤 필요할 때만 재시도하세요 — 아니면 같은 브리핑이 중복으로 올라갈 수 있습니다.
- **그날 팝업도 실패 메일도 아예 안 왔다**: GitHub Actions가 지연돼 08:20에 아직 그날 리포트가 안 올라와 있었을 가능성이 큽니다 (2026-09-04에 실제로 발생 — GitHub Actions가 09:59에야 리포트를 올려서, 08:20 실행분은 조용히 종료됨). 위 트리거 설정대로면 30분 간격으로 11:20까지 자동 재시도하니 보통은 그 안에 뜹니다. 그래도 안 왔다면 GitHub Actions 탭에서 그날 실행이 몇 시에 끝났는지 확인하세요 — 11:20을 넘겨 끝났다면 재시도 구간을 늘려야 합니다.
