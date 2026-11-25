import json
import logging
import re
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from urllib.parse import urlencode, urlparse

from app.core.config import Settings
from app.services.auth_errors import DeliveryError

logger = logging.getLogger(__name__)

MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"
_CODE = re.compile(r"\b(\d{4,9})\b")
_NON_DIGITS = re.compile(r"\D")


def sms_payload(phone: str, message: str) -> dict[str, str]:
    return {"to": phone, "message": message}


def msg91_mobile(phone: str) -> str:
    """MSG91 expects the country code. A 10-digit Indian number gets 91."""

    digits = _NON_DIGITS.sub("", phone)
    if len(digits) == 10:
        return f"91{digits}"
    return digits


class SmtpSmsSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send_email(
        self,
        address: str,
        message: str,
        subject: str = "SwarnaSetu",
        html: str | None = None,
    ) -> None:
        if not self._settings.smtp_host.strip() or not self._settings.smtp_from.strip():
            raise DeliveryError("email")
        email = EmailMessage()
        email["To"] = address
        email["From"] = self._settings.smtp_from
        email["Subject"] = subject
        email.set_content(message)
        if html:
            email.add_alternative(html, subtype="html")
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
        if not self._settings.sms_api_token.strip():
            raise DeliveryError("sms")
        template_id = self._settings.sms_template_id.strip()
        if not template_id:
            raise DeliveryError("sms", "Add the MSG91 OTP template id in APP_SMS_TEMPLATE_ID.")
        self._post_msg91(msg91_mobile(phone), _code_in(message), template_id)

    def _post_msg91(self, mobile: str, code: str, template_id: str) -> None:
        query = urlencode(
            {
                "template_id": template_id,
                "mobile": mobile,
                "otp": code,
                "otp_expiry": "10",
                "otp_length": str(len(code)),
            }
        )
        request = urllib.request.Request(
            f"{_otp_url(self._settings.sms_api_url)}?{query}",
            data=b"{}",
            headers={
                "authkey": self._settings.sms_api_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode() or "{}")
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            logger.error("sms delivery failed")
            raise DeliveryError("sms", "MSG91 could not send the text message.") from exc
        if isinstance(payload, dict) and payload.get("type") == "success":
            return
        logger.error("sms delivery failed")
        raise DeliveryError("sms", _msg91_detail(payload))


def _code_in(message: str) -> str:
    match = _CODE.search(message)
    if match is None:
        raise DeliveryError("sms", "The text message has no login code.")
    return match.group(1)


def _otp_url(configured: str) -> str:
    host = (urlparse(configured).hostname or "").lower()
    if not configured.strip() or host == "api.sms.com" or host.endswith("msg91.com"):
        return MSG91_OTP_URL
    return configured


def _msg91_detail(payload: object) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        return payload["message"][:160]
    return "MSG91 rejected the text message."
