import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import Settings
from app.services.auth_errors import DeliveryError

logger = logging.getLogger(__name__)


def sms_payload(phone: str, message: str) -> dict[str, str]:
    return {"to": phone, "message": message}


class SmtpSmsSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send_email(self, address: str, message: str) -> None:
        if not self._settings.smtp_host.strip() or not self._settings.smtp_from.strip():
            raise DeliveryError("email")
        email = EmailMessage()
        email["To"] = address
        email["From"] = self._settings.smtp_from
        email["Subject"] = "Password reset code"
        email.set_content(message)
        try:
            with smtplib.SMTP(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=10,
            ) as client:
                if self._settings.smtp_username:
                    client.starttls()
                    client.login(self._settings.smtp_username, self._settings.smtp_password)
                client.send_message(email)
        except (OSError, smtplib.SMTPException) as exc:
            logger.error("email delivery failed")
            raise DeliveryError("email") from exc

    def send_sms(self, phone: str, message: str) -> None:
        if not self._settings.sms_api_url.strip():
            raise DeliveryError("sms")
        payload = json.dumps(sms_payload(phone, message)).encode()
        request = urllib.request.Request(
            self._settings.sms_api_url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        if self._settings.sms_api_token.strip():
            request.add_header("Authorization", f"Bearer {self._settings.sms_api_token}")
        try:
            with urllib.request.urlopen(request, timeout=10):
                return
        except (OSError, urllib.error.URLError) as exc:
            logger.error("sms delivery failed")
            raise DeliveryError("sms") from exc
