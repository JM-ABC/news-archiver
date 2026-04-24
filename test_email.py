import os
from dotenv import load_dotenv
import resend

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")
recipients = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]
print(f"발송 대상: {recipients}")

params = {
    "from":    os.getenv("EMAIL_FROM"),
    "to":      recipients,
    "subject": "[테스트] 이커머스/FMCG 뉴스 리포트 수신 확인",
    "html":    "<p>안녕하세요,<br>뉴스 리포트 이메일 수신 테스트입니다.<br>이 메일이 보이시면 정상 수신된 것입니다.</p>",
}
result = resend.Emails.send(params)
print(f"발송 완료 → id: {result.get('id', '-')}")
