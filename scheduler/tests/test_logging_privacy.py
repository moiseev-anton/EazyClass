"""Security regressions: sensitive inputs must not reach application LogRecords."""
import hashlib
import hmac
import logging
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import APIException

from scheduler.middleware import RequestLoggingMiddleware
from scheduler.authentication import CustomRefreshToken, HMACAuthentication
from scheduler.api.v1.serializers import nonce_serializers, token_serializers
from scheduler.api.v1.views import auth_views, deeplink_views
from scheduler.api.v1.views.token_views import logout_view


NONCE = "a32d1e4b-6c91-4aac-981a-a7489392bc7f"
SECRET = "sensitive-marker-do-not-log"


def assert_private(caplog, *values):
    # Include extra/args/exc_info as well as rendered text: a future JSON
    # formatter must not expose data hidden by today's text formatter.
    captured = caplog.text + repr([record.__dict__ for record in caplog.records])
    for value in values:
        assert value not in captured


@pytest.mark.parametrize("resolved", [True, False])
def test_http_logs_only_route_and_result(caplog, resolved):
    caplog.set_level(logging.DEBUG)
    request = RequestFactory().post(
        f"/auth/{SECRET}/?nonce={NONCE}",
        data={"refresh": SECRET}, content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {SECRET}", HTTP_COOKIE=f"session={SECRET}",
        HTTP_X_SIGNATURE=SECRET,
    )
    request.resolver_match = SimpleNamespace(route="auth/<str:value>/") if resolved else None
    response = HttpResponse(status=401)
    assert RequestLoggingMiddleware(lambda _: response)(request) is response
    assert "status_code=401" in caplog.text
    assert ("auth/<str:value>/" if resolved else "<unresolved>") in caplog.text
    assert_private(caplog, SECRET, NONCE)


@override_settings(BOT_HMAC_SECRETS={"telegram": SECRET})
def test_hmac_verification_does_not_log_signing_input(caplog):
    caplog.set_level(logging.DEBUG)
    request = RequestFactory().post(f"/auth/?nonce={NONCE}", {"value": SECRET})
    timestamp, social_id = "1234567890", "private-social-id"
    data = (
        f"POST\n{request.get_full_path()}\n{timestamp}\ntelegram\n{social_id}\n"
        f"{hashlib.sha256(request.body).hexdigest()}"
    ).encode()
    signature = hmac.new(SECRET.encode(), data, hashlib.sha256).hexdigest()
    assert HMACAuthentication._verify_hmac_signature(
        request, "telegram", social_id, timestamp, signature
    )
    assert_private(caplog, SECRET, NONCE, social_id, signature, timestamp)


@pytest.mark.parametrize("failed", [False, True])
def test_nonce_result_without_nonce_or_exception_payload(caplog, monkeypatch, failed):
    caplog.set_level(logging.DEBUG)
    cache = Mock()
    if failed:
        cache.set.side_effect = RuntimeError(f"redis://{SECRET}/{NONCE}")
    monkeypatch.setattr(nonce_serializers, "cache", cache)
    serializer = nonce_serializers.NonceSerializer(data={"nonce": NONCE})
    assert serializer.is_valid()
    assert serializer.save_nonce("42") == ("failed" if failed else "authenticated")
    cache.set.assert_called_once_with(NONCE, "42", timeout=300)
    records = [r for r in caplog.records if r.name == nonce_serializers.__name__]
    assert len(records) == 1
    assert records[0].levelno == (logging.ERROR if failed else logging.INFO)
    if failed:
        assert "RuntimeError" in caplog.text
    assert_private(caplog, SECRET, NONCE)


def test_auth_service_error_does_not_log_exception_chain(caplog):
    caplog.set_level(logging.DEBUG)
    serializer = token_serializers.BaseTokenSerializer()
    with pytest.raises(APIException):
        try:
            raise ValueError(SECRET)
        except ValueError:
            try:
                raise RuntimeError(NONCE)
            except RuntimeError as exc:
                serializer._handle_service_exception(exc)
    assert "RuntimeError" in caplog.text
    assert_private(caplog, SECRET, NONCE)


def test_nonce_ttl_error_does_not_log_cache_key(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    cache = Mock()
    cache.expire.side_effect = RuntimeError(f"{NONCE}: {SECRET}")
    monkeypatch.setattr(token_serializers, "cache", cache)
    token_serializers.CustomTokenObtainPairSerializer()._reduce_nonce_ttl(NONCE)
    assert "RuntimeError" in caplog.text
    assert_private(caplog, SECRET, NONCE)


def test_refresh_whitelist_does_not_log_jti(caplog):
    caplog.set_level(logging.DEBUG)
    token = CustomRefreshToken()
    token["jti"] = SECRET
    token.add_to_whitelist()
    token.check_whitelist()
    token.remove_from_whitelist()
    assert_private(caplog, SECRET)


@override_settings(AUTH_PLATFORMS={"telegram": {
    "deeplink_template": "https://t.me/test?start={nonce}",
    "bot_url": "https://t.me/test", "bot_username": "test",
}})
def test_deeplink_does_not_put_nonce_in_extra(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(deeplink_views.uuid, "uuid4", lambda: UUID(NONCE))
    response = deeplink_views.DeeplinkView().get(Mock(), "telegram")
    assert response.status_code == 200
    assert NONCE in str(response.data)
    assert_private(caplog, NONCE)


def test_auth_response_is_returned_but_not_logged(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    account = SimpleNamespace()
    user = SimpleNamespace(id=42, is_authenticated=False)
    input_serializer = Mock()
    input_serializer.save.return_value = SimpleNamespace(
        user=user, social_account=account, created=True, status_code=201,
    )
    monkeypatch.setattr(auth_views, "AuthSerializer", Mock(return_value=input_serializer))
    view = auth_views.AuthView()
    payload = {"profile": SECRET, "nonce": NONCE}
    view.serializer_class = Mock(return_value=SimpleNamespace(data=payload))
    response = view.post(SimpleNamespace(user=user, data={}))
    assert response.status_code == 201
    assert response.data == payload
    assert_private(caplog, SECRET, NONCE)


@pytest.mark.parametrize("stage", ["construct", "remove"])
def test_logout_errors_do_not_log_credentials(caplog, monkeypatch, stage):
    caplog.set_level(logging.DEBUG)
    factory = Mock()
    error = RuntimeError(f"{SECRET}/{NONCE}")
    if stage == "construct":
        factory.side_effect = error
    else:
        factory.return_value.remove_from_whitelist.side_effect = error
    monkeypatch.setattr(logout_view, "CustomRefreshToken", factory)
    view = logout_view.LogoutView()
    view._clear_refresh_cookie = Mock()
    response = view.post(SimpleNamespace(COOKIES={"refresh_token": SECRET}))
    assert response.status_code == (500 if stage == "construct" else 200)
    assert "RuntimeError" in caplog.text
    assert_private(caplog, SECRET, NONCE)
