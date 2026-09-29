import logging
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry

from scheduler.tasks import backups


def test_commands_capture_output(monkeypatch):
    run = Mock()
    monkeypatch.setattr(backups.subprocess, 'run', run)
    backups.upload_to_remote_storage('private-path')
    backups.rotate_remote_backups()
    for call in run.call_args_list:
        assert call.kwargs['stdout'] == subprocess.PIPE
        assert call.kwargs['stderr'] == subprocess.PIPE
        assert call.kwargs['check'] is True


@pytest.mark.parametrize('stage', ['dump', 'upload', 'rotation'])
@pytest.mark.parametrize('retries', [0, 3])
def test_backup_failure_stage_and_retry(monkeypatch, caplog, stage, retries):
    caplog.set_level(logging.INFO)
    failure = subprocess.CalledProcessError(7, ['private-command'], stderr=b'private-secret')
    for name, step in [('create_pg_dump', 'dump'), ('upload_to_remote_storage', 'upload'),
                       ('rotate_remote_backups', 'rotation')]:
        monkeypatch.setattr(backups, name, Mock(side_effect=failure if stage == step else None,
                                              return_value='private-path'))
    cleanup = Mock()
    monkeypatch.setattr(backups, 'cleanup_local_file', cleanup)
    task = backups.periodic_database_backup
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(task, 'retry', retry)
    task.push_request(retries=retries)
    try:
        with pytest.raises(Retry if retries == 0 else subprocess.CalledProcessError):
            task.run()
    finally:
        task.pop_request()
    record = caplog.records[-1]
    assert record.event == ('backup.retry_requested' if retries == 0 else 'backup.failed')
    assert record.stage == stage and record.attempt == retries + 1
    assert record.exit_code == 7
    assert retry.call_count == (1 if retries == 0 else 0)
    assert cleanup.call_count == (0 if stage == 'dump' else 1)
    assert 'private' not in repr([r.__dict__ for r in caplog.records])


def test_failed_dump_removes_partial_file(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(backups, 'BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(backups, 'run_subprocess', Mock(side_effect=subprocess.CalledProcessError(
        1, 'private-command', stderr=b'private-secret')))
    with pytest.raises(subprocess.CalledProcessError):
        backups.create_pg_dump({'HOST': 'private-host', 'NAME': 'private-db',
                                'USER': 'private-user', 'PASSWORD': 'private-password'})
    assert not list(tmp_path.iterdir())
    assert 'private' not in repr([r.__dict__ for r in caplog.records])


def test_successful_backup_stages(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(backups, 'BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(backups, 'settings', SimpleNamespace(DATABASES={'default': {
        'HOST': 'private-host', 'NAME': 'private-db', 'USER': 'private-user', 'PASSWORD': 'private-password',
    }}))
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b'', b''))
    monkeypatch.setattr(backups, 'run_subprocess', run)
    assert backups.periodic_database_backup.run() == 'OK'
    events = [r.event for r in caplog.records]
    assert events == ['backup.started', 'backup.dump.started', 'backup.dump.completed',
                      'backup.upload.started', 'backup.upload.completed',
                      'backup.rotation.started', 'backup.rotation.completed', 'backup.completed']
    assert not list(tmp_path.iterdir())
    assert 'Нет файлов' not in caplog.text
    assert 'private' not in repr([r.__dict__ for r in caplog.records])


@pytest.mark.parametrize('failure,retry_expected', [
    (subprocess.TimeoutExpired('private-command', 42, stderr=b'private-secret'), True),
    (OSError('private-secret'), False),
])
def test_timeout_and_nonretryable_failure(monkeypatch, caplog, failure, retry_expected):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(backups, 'create_pg_dump', Mock(side_effect=failure))
    retry = Mock(side_effect=Retry())
    monkeypatch.setattr(backups.periodic_database_backup, 'retry', retry)
    with pytest.raises(Retry if retry_expected else OSError):
        backups.periodic_database_backup.run()
    assert retry.call_count == int(retry_expected)
    if retry_expected:
        assert caplog.records[-1].timeout_seconds == 42
    assert 'private' not in repr([r.__dict__ for r in caplog.records])


def test_cleanup_failure_is_safe_and_does_not_raise(monkeypatch, caplog):
    monkeypatch.setattr(backups.os.path, 'exists', lambda _: True)
    monkeypatch.setattr(backups.os, 'unlink', Mock(side_effect=OSError('private-secret')))
    backups.cleanup_local_file('private-path')
    assert caplog.records[-1].event == 'backup.cleanup.failed'
    assert 'private' not in repr(caplog.records[-1].__dict__)
