import importlib
import logging
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.management.base import CommandError
from django.db import transaction

from scheduler.activities import admin_query_actions as actions
from scheduler.models import Group


@pytest.mark.django_db
@pytest.mark.parametrize('rollback', [True, False])
def test_admin_log_waits_for_commit(caplog, django_capture_on_commit_callbacks, rollback):
    caplog.set_level(logging.INFO)
    group = Group.objects.create(title='private-title', is_active=False)
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                actions.make_active(None, SimpleNamespace(user=SimpleNamespace(pk=42)),
                                    Group.objects.filter(pk=group.pk))
                assert not caplog.records
                if rollback:
                    raise RuntimeError('rollback')
        except RuntimeError:
            pass
    assert len(caplog.records) == (0 if rollback else 1)
    if not rollback:
        record = caplog.records[0]
        assert record.user_id == 42 and record.count == 1 and record.model == 'Group'
        assert 'private-title' not in repr(record.__dict__)


@pytest.mark.django_db
def test_toggle_failure_rolls_back_prior_changes(monkeypatch, caplog):
    first = Group.objects.create(title='A1', is_active=False)
    second = Group.objects.create(title='A2', is_active=False)
    original = Group.save
    def save(instance, *args, **kwargs):
        if instance.pk == second.pk:
            raise RuntimeError('failed')
        return original(instance, *args, **kwargs)
    monkeypatch.setattr(Group, 'save', save)
    with pytest.raises(RuntimeError):
        actions.toggle_active(None, SimpleNamespace(user=SimpleNamespace(pk=42)),
                              Group.objects.order_by('pk'))
    first.refresh_from_db()
    assert first.is_active is False
    assert not caplog.records


@pytest.mark.parametrize('name', ['filltemplate', 'runscheduler'])
@pytest.mark.parametrize('failed', [False, True])
def test_commands_report_safe_success_or_failure(monkeypatch, caplog, name, failed):
    caplog.set_level(logging.INFO)
    module = importlib.import_module(f'scheduler.management.commands.{name}')
    monkeypatch.setattr(module, 'fill_default_period_template',
                        Mock(side_effect=RuntimeError('private-credentials') if failed else None))
    out, err = StringIO(), StringIO()
    command = module.Command(stdout=out, stderr=err)
    if failed:
        with pytest.raises(CommandError):
            command.handle()
    else:
        command.handle()
    assert caplog.records[-1].event == ('maintenance.template.failed' if failed else 'maintenance.template.completed')
    assert 'private-credentials' not in out.getvalue() + err.getvalue() + repr([r.__dict__ for r in caplog.records])
