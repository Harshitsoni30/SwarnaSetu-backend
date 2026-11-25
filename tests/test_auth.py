import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth import FORGOT_MESSAGE
from app.services.auth_errors import AuthError
from app.services.google_accounts import GoogleIdentity, identity_from_claims
from app.services.passwords import verify_password
from app.services.tokens import read_token
from tests.support import (
    SECRET,
    FailingSender,
    FixedGoogle,
    FrozenClock,
    RecordingSender,
    make_service,
)

NOW = datetime(2026, 11, 24, tzinfo=UTC)
PASSWORD = "password12"


def _code(message: str) -> str:
    match = re.search(r"\b(\d{6})\b", message)
    assert match is not None
    return match.group(1)


def test_register_with_email_only() -> None:
    service, users, _codes, sender = make_service()

    pair = service.register("Person@Example.com", None, PASSWORD, "Asha")

    user = users.get_by_email("person@example.com")
    assert user is not None
    assert user.phone is None
    assert user.password_hash != PASSWORD
    assert user.password_hash is not None
    assert verify_password(PASSWORD, user.password_hash)
    assert read_token(SECRET, pair.access_token, "access", NOW) == user.id
    assert isinstance(sender, RecordingSender)
    assert sender.emails[0][0] == "person@example.com"
    assert "Welcome, Asha" in sender.emails[0][1]
    assert "account has been created" in sender.emails[0][1]


def test_register_with_phone_only() -> None:
    service, users, _codes, _sender = make_service()

    service.register(None, "+1 555 010 1999", PASSWORD)

    assert users.get_by_phone("+15550101999") is not None


def test_register_requires_a_contact() -> None:
    service, _users, _codes, _sender = make_service()

    with pytest.raises(AuthError) as caught:
        service.register("  ", "", "password12")

    assert caught.value.code == "validation_error"


def test_register_rejects_short_password_and_duplicates() -> None:
    service, _users, _codes, _sender = make_service()
    service.register("a@example.com", None, PASSWORD)

    with pytest.raises(AuthError) as short_password:
        service.register("b@example.com", None, "short")
    with pytest.raises(AuthError) as duplicate_email:
        service.register("a@example.com", None, PASSWORD)
    service.register(None, "+15550101999", PASSWORD)
    with pytest.raises(AuthError) as duplicate_phone:
        service.register("c@example.com", "+15550101999", PASSWORD)

    assert short_password.value.status_code == 422
    assert duplicate_email.value.code == "identifier_taken"
    assert duplicate_phone.value.code == "identifier_taken"
    service.register("d@example.com", "+91 98765 43210", PASSWORD)
    with pytest.raises(AuthError) as formatted_mobile:
        service.register("e@example.com", "09876543210", PASSWORD)
    with pytest.raises(AuthError) as plain_mobile:
        service.register("f@example.com", "9876543210", PASSWORD)

    assert formatted_mobile.value.message == "An account already uses that phone number."
    assert plain_mobile.value.message == "An account already uses that phone number."


def test_login_and_refresh() -> None:
    service, users, _codes, _sender = make_service()
    service.register("a@example.com", "+15550101000", PASSWORD)

    pair = service.login("A@Example.com", PASSWORD)
    refreshed = service.refresh(pair.refresh_token)
    user = users.get_by_email("a@example.com")

    assert user is not None
    assert read_token(SECRET, refreshed.access_token, "access", NOW) == user.id
    with pytest.raises(AuthError):
        service.login("a@example.com", "wrong-password")
    with pytest.raises(AuthError):
        service.login("missing@example.com", PASSWORD)
    with pytest.raises(AuthError):
        service.refresh(pair.access_token)


def test_forgot_password_sends_the_same_code_to_each_contact() -> None:
    service, _users, codes, sender = make_service()
    service.register("a@example.com", "+15550101000", PASSWORD)

    message = service.forgot_password("a@example.com")

    assert message == FORGOT_MESSAGE
    assert isinstance(sender, RecordingSender)
    assert sender.emails[-1][0] == "a@example.com"
    assert sender.texts[0][0] == "+15550101000"
    assert _code(sender.emails[-1][1]) == _code(sender.texts[0][1])
    assert len(codes.rows) == 1


def test_forgot_password_hides_unknown_accounts_and_delivery_failures() -> None:
    service, _users, _codes, sender = make_service()
    failing, _users2, codes, _sender = make_service(sender=FailingSender())
    failing.register("a@example.com", None, PASSWORD)

    assert service.forgot_password("missing@example.com") == FORGOT_MESSAGE
    assert isinstance(sender, RecordingSender)
    assert sender.emails == []
    assert failing.forgot_password("a@example.com") == FORGOT_MESSAGE
    assert len(codes.rows) == 1


def test_reset_password_requires_otp_and_current_password() -> None:
    service, users, _codes, sender = make_service()
    service.register("a@example.com", "+15550101000", PASSWORD)
    service.forgot_password("+15550101000")
    assert isinstance(sender, RecordingSender)
    code = _code(sender.texts[0][1])
    wrong_code = "111111" if code != "111111" else "222222"

    with pytest.raises(AuthError) as bad_otp:
        service.reset_password("a@example.com", wrong_code, PASSWORD, "new-password")
    with pytest.raises(AuthError) as bad_password:
        service.reset_password("a@example.com", code, "wrong-password", "new-password")

    service.reset_password("a@example.com", code, PASSWORD, "new-password")
    service.login("a@example.com", "new-password")

    assert bad_otp.value.code == "invalid_otp"
    assert bad_password.value.code == "password_mismatch"
    stored = users.get_by_email("a@example.com")
    assert stored is not None
    assert stored.password_hash is not None
    assert verify_password("new-password", stored.password_hash)
    with pytest.raises(AuthError):
        service.reset_password("a@example.com", code, "new-password", "another-password1")


def test_expired_code_is_rejected() -> None:
    clock = FrozenClock(NOW)
    service, _users, _codes, sender = make_service(clock=clock)
    service.register("a@example.com", None, PASSWORD)
    service.forgot_password("a@example.com")
    assert isinstance(sender, RecordingSender)
    code = _code(sender.emails[-1][1])
    clock.moment = NOW + timedelta(minutes=11)

    with pytest.raises(AuthError) as caught:
        service.reset_password("a@example.com", code, PASSWORD, "new-password")

    assert caught.value.code == "invalid_otp"


def test_google_sign_in_creates_links_and_rejects_conflicts() -> None:
    created, users, _codes, _sender = make_service(
        google=FixedGoogle(GoogleIdentity("google-1", "person@example.com")),
    )
    pair = created.login_with_google("token")
    user = users.get_by_google_sub("google-1")
    assert user is not None
    assert user.password_hash is None
    assert read_token(SECRET, pair.access_token, "access", NOW) == user.id

    again = created.login_with_google("token")
    assert read_token(SECRET, again.access_token, "access", NOW) == user.id

    linked, linked_users, _codes2, _sender2 = make_service(
        google=FixedGoogle(GoogleIdentity("google-2", "member@example.com")),
    )
    linked.register("member@example.com", None, PASSWORD)
    linked.login_with_google("token")
    linked_user = linked_users.get_by_email("member@example.com")
    assert linked_user is not None
    assert linked_user.google_sub == "google-2"

    conflict, _users3, _codes3, _sender3 = make_service(
        google=FixedGoogle(GoogleIdentity("google-3", "member@example.com")),
    )
    conflict.register("member@example.com", None, PASSWORD)
    existing = conflict.users.get_by_email("member@example.com")
    assert existing is not None
    conflict.users.link_google(existing.id, "other")
    with pytest.raises(AuthError) as caught:
        conflict.login_with_google("token")
    assert caught.value.code == "google_account_conflict"

    with pytest.raises(AuthError) as reset:
        created.reset_password("person@example.com", "123456", PASSWORD, "new-password")
    assert reset.value.code == "password_not_set"


def test_google_claim_rules() -> None:
    audiences = {"client-web"}

    identity = identity_from_claims(
        {"aud": "client-web", "email_verified": True, "email": "A@Example.com", "sub": "abc"},
        audiences,
    )

    assert identity.email == "a@example.com"
    with pytest.raises(AuthError) as unverified:
        identity_from_claims(
            {"aud": "client-web", "email_verified": False, "email": "a@example.com", "sub": "abc"},
            audiences,
        )
    with pytest.raises(AuthError):
        identity_from_claims(
            {"aud": "other", "email_verified": True, "email": "a@example.com", "sub": "abc"},
            audiences,
        )
    assert unverified.value.code == "unverified_email"


def test_auth_routes_are_public_and_use_the_error_format() -> None:
    service, _users, _codes, _sender = make_service()
    client = TestClient(create_app(Settings(), auth_service=service))

    created = client.post(
        "/auth/register",
        json={"name": "Asha", "email": "a@example.com", "phone": None, "password": PASSWORD},
    )
    duplicate = client.post(
        "/auth/register",
        json={"name": "Asha", "email": "a@example.com", "phone": None, "password": PASSWORD},
    )
    logged_in = client.post(
        "/auth/login",
        json={"identifier": "a@example.com", "password": PASSWORD},
    )

    assert created.status_code == 201
    assert "access_token" in created.json()
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "identifier_taken"
    assert logged_in.status_code == 200


def test_login_with_otp_uses_the_sent_code() -> None:
    service, _users, _codes, sender = make_service()
    service.register("a@example.com", "+15550101000", PASSWORD)

    service.request_login_otp("+1 555 010 1000")

    assert isinstance(sender, RecordingSender)
    code = _code(sender.texts[0][1])
    pair = service.login_with_otp("15550101000", code)
    assert pair.access_token
    with pytest.raises(AuthError) as reused:
        service.login_with_otp("+15550101000", code)
    assert reused.value.code == "invalid_otp"


def test_login_otp_is_not_shown_when_email_fails() -> None:
    service, _users, _codes, _sender = make_service(sender=FailingSender())
    service.register("a@example.com", None, PASSWORD)

    with pytest.raises(AuthError) as failed:
        service.request_login_otp("a@example.com")

    assert failed.value.message == "This account has no phone number for a login code."
    assert service.request_login_otp("missing@example.com") is None


def test_password_reset_code_cannot_be_used_to_log_in() -> None:
    service, _users, _codes, sender = make_service()
    service.register("a@example.com", None, PASSWORD)
    service.forgot_password("a@example.com")
    assert isinstance(sender, RecordingSender)

    with pytest.raises(AuthError) as caught:
        service.login_with_otp("a@example.com", _code(sender.emails[-1][1]))

    assert caught.value.code == "invalid_otp"
