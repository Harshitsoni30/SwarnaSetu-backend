from app.core.config import Settings
from app.services.auth_errors import DeliveryError
from app.services.messages import SmtpSmsSender, msg91_mobile, sms_payload


def test_sms_payload_names_the_recipient_and_message() -> None:
    assert sms_payload("+15550101000", "code 123456") == {
        "to": "+15550101000",
        "message": "code 123456",
    }


def test_msg91_mobile_adds_the_india_code() -> None:
    assert msg91_mobile("9876543210") == "919876543210"
    assert msg91_mobile("+91 98765 43210") == "919876543210"


def test_sms_requires_the_msg91_template() -> None:
    sender = SmtpSmsSender(Settings(sms_api_token="test-token"))

    try:
        sender.send_sms("9876543210", "Your SwarnaSetu login code is 123456.")
        raise AssertionError("sms should fail")
    except DeliveryError as exc:
        assert exc.channel == "sms"
        assert "template" in exc.detail.lower()


def test_delivery_fails_closed_when_unconfigured() -> None:
    sender = SmtpSmsSender(Settings())

    try:
        sender.send_email("person@example.com", "code 123456")
        raise AssertionError("email should fail")
    except DeliveryError as exc:
        assert exc.channel == "email"

    try:
        sender.send_sms("+15550101000", "code 123456")
        raise AssertionError("sms should fail")
    except DeliveryError as exc:
        assert exc.channel == "sms"
