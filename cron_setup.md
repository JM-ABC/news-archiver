# Cron 등록 가이드

## Windows — 작업 스케줄러 (권장)

### 방법 A: PowerShell로 등록 (한 번만 실행)
```powershell
$action  = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "C:\Users\USER\Desktop\뉴스아카이빙\news_archiver.py" `
    -WorkingDirectory "C:\Users\USER\Desktop\뉴스아카이빙"

$trigger = New-ScheduledTaskTrigger -Daily -At "08:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 1

Register-ScheduledTask `
    -TaskName  "뉴스아카이버" `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force
```

> 매일 오전 8시에 자동 실행됩니다.

### 방법 B: GUI로 등록
1. `Win + R` → `taskschd.msc` 실행
2. 오른쪽 패널 → **기본 작업 만들기**
3. 트리거: **매일** → 오전 8:00
4. 동작: **프로그램 시작**
   - 프로그램: `python`
   - 인수: `C:\Users\USER\Desktop\뉴스아카이빙\news_archiver.py`
   - 시작 위치: `C:\Users\USER\Desktop\뉴스아카이빙`

---

## macOS / Linux — crontab

```bash
# crontab 편집
crontab -e

# 매일 오전 8시 실행 (아래 줄 추가)
0 8 * * * cd /path/to/뉴스아카이빙 && python3 news_archiver.py >> ~/trends/cron.log 2>&1
```

### 로그 확인
```bash
tail -f ~/trends/cron.log
```

---

## WSL2 (Windows에서 Linux 크론 사용 시)

WSL2는 부팅 시 크론 데몬이 꺼져 있으므로 **시작 스크립트**에 추가:

```bash
# ~/.bashrc 또는 ~/.profile 끝에 추가
if ! pgrep -x cron > /dev/null; then
    sudo service cron start
fi
```

```bash
# crontab -e
0 8 * * * cd ~/Desktop/뉴스아카이빙 && python3 news_archiver.py >> ~/trends/cron.log 2>&1
```

---

## 즉시 테스트

```bash
# 디렉토리 이동 후 실행
cd "C:\Users\USER\Desktop\뉴스아카이빙"
python news_archiver.py
```

결과 확인:
```bash
cat ~/trends/trend_$(date +%Y-%m-%d).txt
```
