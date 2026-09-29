import json
import logging
from types import SimpleNamespace

import pytest
from django.db import transaction
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_json_api.django_filters.backends import DjangoFilterBackend

from scheduler.api.exceptions import logging_exception_handler
from scheduler.api.filters import LessonByPeriodFilter
from scheduler.api.v1.serializers import UserSerializer
from scheduler.api.v1.views.lesson_views import LessonViewSet
from scheduler.api.v1.views.user_views import UserViewSet
from scheduler.middleware import RequestLoggingMiddleware
from scheduler.models import Group, GroupSubscription, Teacher, TeacherSubscription, User
from eazyclass.logging_config import EventFormatter


def request_lessons(action, params, user=None, etag=None, **kwargs):
    request = APIRequestFactory().get('/lessons/', params,
                                      **({'HTTP_IF_NONE_MATCH': etag} if etag else {}))
    if user:
        force_authenticate(request, user=user)
    options = {'filter_backends': [DjangoFilterBackend], 'authentication_classes': []}
    if action == 'by_period':
        options['filterset_class'] = LessonByPeriodFilter
    view = LessonViewSet.as_view({'get': action}, basename='lessons', **options)
    request.resolver_match = SimpleNamespace(route='api/v1/lessons/', func=view)
    return RequestLoggingMiddleware(lambda req: view(req, **kwargs))(request)


@pytest.mark.django_db
def test_schedule_access_context_survives_etag_and_omits_raw_query(caplog):
    caplog.set_level(logging.INFO)
    group = Group.objects.create(title='A1')
    params = {'filter[group]': group.pk, 'filter[date_from]': '2026-09-01',
              'filter[date_to]': '2026-09-07', 'filter[subgroup]': '1',
              'secret': 'private-query'}
    first = request_lessons('list', params)
    assert first.status_code == 200
    second = request_lessons('list', params, etag=first['ETag'])
    assert second.status_code == 304
    events = [r for r in caplog.records if getattr(r, 'event', '') == 'http.request.completed']
    assert len(events) == 2
    for record in events:
        assert record.query['filter[group]'] == str(group.pk)
        assert not hasattr(record, 'group_id')
        assert 'private' not in str(record.__dict__)
    assert not any(r.name.endswith('lesson_views') for r in caplog.records)


@pytest.mark.django_db
@pytest.mark.parametrize('kind', ['group', 'teacher'])
def test_my_schedule_logs_subscription_target(caplog, kind):
    caplog.set_level(logging.INFO)
    user = User.objects.create(username='test')
    if kind == 'group':
        target = Group.objects.create(title='A1')
        GroupSubscription.objects.create(user=user, group=target)
    else:
        target = Teacher.objects.create(full_name='Иванов Иван Иванович')
        TeacherSubscription.objects.create(user=user, teacher=target)
    response = request_lessons('get_me', {'filter[date_from]': '2026-09-01',
                                        'filter[date_to]': '2026-09-07'}, user=user)
    assert response.status_code == 200
    record = next(r for r in caplog.records if getattr(r, 'event', '') == 'api.lessons.subscription')
    assert getattr(record, f'{kind}_id') == target.pk
    assert record.user_id == user.pk


@pytest.mark.django_db
def test_period_schedule_context(caplog):
    caplog.set_level(logging.INFO)
    response = request_lessons('by_period', {'filter[date]': '2026-09-01',
                                           'filter[lesson_number]': '3'})
    assert response.status_code == 200
    record = caplog.records[-1]
    assert record.query['filter[lesson_number]'] == '3'
    assert record.query['filter[date]'] == '2026-09-01'


@pytest.mark.django_db
def test_invalid_dates_appear_only_in_request_parameters(monkeypatch, caplog):
    from rest_framework.settings import api_settings
    monkeypatch.setattr(api_settings, 'EXCEPTION_HANDLER', logging_exception_handler)
    caplog.set_level(logging.INFO)
    response = request_lessons('list', {'filter[date_from]': 'invalid-date',
                                      'filter[date_to]': '2026-09-07'})
    assert response.status_code == 400
    assert not hasattr(caplog.records[-1], 'start_date')
    assert caplog.records[-1].query['filter[date_from]'] == 'invalid-date'
    assert not any(getattr(r, 'event', '') == 'api.lessons.subscription' for r in caplog.records)


def test_query_logging_preserves_repeats_and_excludes_secrets(caplog):
    from django.http import HttpResponse
    caplog.set_level(logging.INFO)
    request = APIRequestFactory().get('/lessons/', {
        'filter[group]': ['12', '13'], 'filter[date_from]': 'bad\r\ndate',
        'include': 'x' * 500, 'token': 'private-token', 'nonce': 'private-nonce',
        'unknown': 'private-unknown',
    })
    request.resolver_match = SimpleNamespace(
        route='lessons/', func=SimpleNamespace(initkwargs={'basename': 'lessons'}))
    RequestLoggingMiddleware(lambda _: HttpResponse())(request)
    record = caplog.records[-1]
    assert record.query['filter[group]'] == ['12', '13']
    assert len(record.query['include']) == 100
    assert 'private' not in str(record.__dict__)
    rendered = EventFormatter(style='json').format(record)
    assert json.loads(rendered)['query'] == record.query
    assert '\n' not in rendered and '\r' not in rendered
    assert '\n' not in EventFormatter(style='text').format(record)


@pytest.mark.django_db
def test_me_without_subscription_has_no_selection(monkeypatch, caplog):
    from rest_framework.settings import api_settings
    monkeypatch.setattr(api_settings, 'EXCEPTION_HANDLER', logging_exception_handler)
    caplog.set_level(logging.INFO)
    user = User.objects.create(username='no-subscription')
    response = request_lessons('get_me', {'filter[date_from]': '2026-09-01',
                                        'filter[date_to]': '2026-09-07'}, user=user)
    assert response.status_code == 404
    assert not any(getattr(r, 'event', '') == 'api.lessons.subscription' for r in caplog.records)
    assert caplog.records[-1].query['filter[date_from]'] == '2026-09-01'


@pytest.mark.django_db
def test_detail_logs_id_without_list_filters(monkeypatch, caplog):
    from rest_framework.settings import api_settings
    monkeypatch.setattr(api_settings, 'EXCEPTION_HANDLER', logging_exception_handler)
    caplog.set_level(logging.INFO)
    response = request_lessons('retrieve', {}, pk='123')
    assert response.status_code == 404
    assert caplog.records[-1].event == 'http.request.completed'
    assert not any(r.name.endswith('lesson_views') for r in caplog.records)
    assert not any(getattr(r, 'event', '') == 'api.lessons.subscription' for r in caplog.records)


@pytest.mark.django_db
@pytest.mark.parametrize('rollback,changed', [(False, True), (True, True), (False, False)])
def test_profile_event_tracks_committed_changes_only(caplog, django_capture_on_commit_callbacks,
                                                   rollback, changed):
    caplog.set_level(logging.DEBUG)
    user = User.objects.create(username='test', first_name='private-before')
    serializer = UserSerializer(user, data={'first_name': 'private-after' if changed else 'private-before'},
                                partial=True)
    assert serializer.is_valid(), serializer.errors
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                UserViewSet().perform_update(serializer)
                assert not any(getattr(r, 'event', '').startswith('api.profile.') for r in caplog.records)
                if rollback:
                    raise RuntimeError('rollback')
        except RuntimeError:
            pass
    events = [r for r in caplog.records if getattr(r, 'event', '').startswith('api.profile.')]
    assert len(events) == (0 if rollback else 1)
    if events:
        assert events[0].event == ('api.profile.updated' if changed else 'api.profile.unchanged')
        assert events[0].changed_fields == ('first_name' if changed else '')
        assert events[0].levelno == (logging.INFO if changed else logging.DEBUG)
        assert 'private' not in str(events[0].__dict__)
