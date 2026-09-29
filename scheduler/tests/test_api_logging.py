import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rest_framework import exceptions
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework_json_api.renderers import JSONRenderer as JSONAPIRenderer
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from eazyclass.logging_config import EventFormatter
from scheduler.api.exceptions import logging_exception_handler, json_api_exception_handler
from scheduler.api.v1.serializers import token_serializers as tokens
from scheduler.authentication.hmac_authentication import HMACAuthentication
from scheduler.authentication.twa_authentication import TelegramWebAppAuthentication
from scheduler.api.mixins import ETagMixin


def context(renderer=JSONRenderer):
    view = APIView()
    view.renderer_classes = [renderer]
    request = Request(APIRequestFactory().get("/test/?secret=private-query"))
    request._user = SimpleNamespace(pk=42)
    view.request = request
    return {"view": view, "request": request}


@pytest.mark.parametrize("renderer", [JSONRenderer, JSONAPIRenderer])
@pytest.mark.parametrize("exception", [
    exceptions.ValidationError({"nonce": "private-value"}),
    exceptions.PermissionDenied("private-value"),
    exceptions.NotAuthenticated("private-value"),
    exceptions.Throttled(wait=12, detail="private-value"),
    exceptions.APIException("private-value"),
])
def test_error_handler_keeps_response_contract_without_logging_details(caplog, renderer, exception):
    caplog.set_level(logging.INFO)
    ctx = context(renderer)
    expected = json_api_exception_handler(exception, ctx)
    actual = logging_exception_handler(exception, ctx)
    assert actual.status_code == expected.status_code
    assert actual.data == expected.data
    assert dict(actual.headers) == dict(expected.headers)
    record, = [r for r in caplog.records if r.name == "scheduler.api.exceptions"]
    assert record.levelno == (logging.ERROR if actual.status_code >= 500 else logging.INFO)
    for style in ("json", "text", "text_verbose"):
        assert "private" not in EventFormatter(style=style).format(record)


def test_unhandled_error_is_left_for_django(caplog):
    assert logging_exception_handler(RuntimeError("private"), context()) is None
    assert not caplog.records


@pytest.mark.parametrize("active", [True, False])
def test_nonce_user_refusal_is_not_a_service_failure(monkeypatch, caplog, active):
    from django.contrib.auth import get_user_model
    user = SimpleNamespace(pk=42, is_active=active)
    get_user = Mock(return_value=user)
    if active:
        get_user.side_effect = get_user_model().DoesNotExist()
    monkeypatch.setattr(get_user_model().objects, "get", get_user)
    monkeypatch.setattr(tokens, "cache", Mock(get=Mock(return_value=42)))
    monkeypatch.setattr(tokens.api_settings, "USER_AUTHENTICATION_RULE", lambda u: u.is_active)
    with pytest.raises(AuthenticationFailed) as error:
        tokens.CustomTokenObtainPairSerializer().validate({"nonce": "private-nonce"})
    caplog.set_level(logging.INFO)
    logging_exception_handler(error.value, context())
    assert not any(getattr(r, "event", "") == "auth.service.failed" for r in caplog.records)
    assert caplog.records[-1].reason == "no_active_account"


def test_nested_service_failure_is_logged_once(monkeypatch, caplog):
    from django.contrib.auth import get_user_model
    monkeypatch.setattr(tokens, "cache", Mock(get=Mock(return_value=42)))
    monkeypatch.setattr(get_user_model().objects, "get", Mock(side_effect=RuntimeError("private-password")))
    with pytest.raises(exceptions.APIException) as error:
        tokens.CustomTokenObtainPairSerializer().validate({"nonce": "private-nonce"})
    logging_exception_handler(error.value, context())
    assert len(caplog.records) == 1
    assert caplog.records[0].event == "auth.service.failed"
    assert "private" not in caplog.text


def test_hmac_missing_headers_is_not_an_info_failure(caplog):
    caplog.set_level(logging.INFO)
    assert HMACAuthentication().authenticate(SimpleNamespace(headers={})) is None
    assert not caplog.records


def test_hmac_refusal_retains_response_and_has_fixed_reason(caplog):
    caplog.set_level(logging.INFO)
    request = SimpleNamespace(headers={"X-Signature": "private-signature", "X-Timestamp": "private-time",
                                       "X-Platform": "private-platform", "X-Social-ID": "private-id"})
    with pytest.raises(exceptions.AuthenticationFailed) as error:
        HMACAuthentication().authenticate(request)
    logging_exception_handler(error.value, context())
    assert caplog.records[-1].reason == "hmac_invalid_timestamp"
    assert "private" not in caplog.text


def test_twa_missing_signature_has_safe_reason(caplog):
    caplog.set_level(logging.INFO)
    with pytest.raises(exceptions.AuthenticationFailed) as error:
        TelegramWebAppAuthentication()._validate_init_data("user=private-profile")
    logging_exception_handler(error.value, context())
    assert caplog.records[-1].reason == "twa_missing_hash"
    assert "private" not in caplog.text


def test_etag_does_not_log_client_header(caplog):
    caplog.set_level(logging.DEBUG)
    view = ETagMixin()
    view.request = SimpleNamespace(META={"HTTP_IF_NONE_MATCH": "private-header"})
    view.generate_etag = Mock(return_value="server-etag")
    assert view.check_etag() == ("server-etag", False)
    assert caplog.records[-1].levelno == logging.DEBUG
    assert "private-header" not in caplog.text


def test_real_view_does_not_repeat_failed_authentication(monkeypatch, caplog):
    from rest_framework.authentication import BaseAuthentication
    from rest_framework.settings import api_settings
    from scheduler.authentication.logging import authentication_rejected
    caplog.set_level(logging.INFO)
    calls = []
    class Auth(BaseAuthentication):
        def authenticate(self, request):
            calls.append(True)
            raise authentication_rejected("Invalid signature", "hmac_signature_mismatch")
    class View(APIView):
        authentication_classes = [Auth]
        renderer_classes = [JSONRenderer]
    monkeypatch.setattr(api_settings, "EXCEPTION_HANDLER", logging_exception_handler)
    response = View.as_view()(APIRequestFactory().get("/test/"))
    assert response.status_code == 403  # Existing DRF behaviour without authenticate_header.
    assert len(calls) == 1
    assert caplog.records[-1].reason == "hmac_signature_mismatch"


def test_token_issue_logs_user_without_token_values(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    serializer = tokens.CustomTokenObtainPairSerializer()
    monkeypatch.setattr(tokens, "cache", Mock(get=Mock(return_value=42)))
    monkeypatch.setattr(serializer, "_validate_user", lambda _: SimpleNamespace(pk=42))
    monkeypatch.setattr(tokens.api_settings, "UPDATE_LAST_LOGIN", False)
    class Token:
        access_token = "private-access"
        def __str__(self):
            return "private-refresh"
    serializer.token_class = Mock(for_user=Mock(return_value=Token()))
    result = serializer.validate({"nonce": "private-nonce"})
    assert result["refresh"] == "private-refresh" and result["access"] == "private-access"
    record = next(r for r in caplog.records if getattr(r, "event", "") == "auth.tokens.issued")
    assert record.user_id == 42
    assert "private" not in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize("rollback", [True, False])
def test_subscription_event_waits_for_commit(monkeypatch, caplog, django_capture_on_commit_callbacks, rollback):
    from django.db import transaction
    from eazyclass.logging_context import logging_context
    from scheduler.api.v1.views.subscription_views import GroupSubscriptionViewSet
    caplog.set_level(logging.INFO)
    view = GroupSubscriptionViewSet()
    view.request = SimpleNamespace(user=SimpleNamespace(pk=42))
    serializer = Mock(save=Mock(return_value=SimpleNamespace(pk=7)))
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic(), logging_context({"request_id": "test-request"}):
                view.perform_create(serializer)
                assert not caplog.records
                if rollback:
                    raise RuntimeError("rollback")
        except RuntimeError:
            pass
    events = [r for r in caplog.records if getattr(r, "event", "") == "api.subscription.saved"]
    assert len(events) == (0 if rollback else 1)
    if events:
        assert events[0].user_id == 42 and events[0].subscription_id == 7
        assert events[0].request_id == "test-request"
