"""Run shell scripts on Linux with fake docker/sudo; never contact Let's Encrypt."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Production scripts require Linux/bash')
SOURCE = Path(__file__).resolve().parents[2] / 'certbot'


@pytest.fixture
def scripts(tmp_path):
    folder = tmp_path / 'project' / 'certbot'
    folder.mkdir(parents=True)
    for name in ('renew_tls.sh', 'install_renewal.sh', 'logrotate.conf', 'bootstrap_tls.sh'):
        shutil.copyfile(SOURCE / name, folder / name)
    binary = tmp_path / 'bin'
    binary.mkdir()
    (binary / 'docker').write_text('''#!/bin/bash
echo "$*" >> "$AUDIT_OUTPUT/calls"
case "$*" in
  *"certbot renew"*) exit "${RENEW_EXIT:-0}" ;;
  *"nginx -t"*) exit "${CHECK_EXIT:-0}" ;;
  *"nginx -s reload"*) exit "${RELOAD_EXIT:-0}" ;;
  *) exit 99 ;;
esac
''')
    (binary / 'sudo').write_text('''#!/bin/bash
[[ "$1" == install ]] || exit 99
source_file="${@: -2:1}"
case "${@: -1}" in
  /etc/cron.d/eazyclass-certbot) cp "$source_file" "$AUDIT_OUTPUT/cron" ;;
  /etc/logrotate.d/eazyclass-certbot) cp "$source_file" "$AUDIT_OUTPUT/rotation" ;;
  *) exit 99 ;;
esac
''')
    for executable in binary.iterdir():
        executable.chmod(0o755)
    env = {**os.environ, 'PATH': f'{binary}:{os.environ["PATH"]}', 'AUDIT_OUTPUT': str(tmp_path)}
    return folder, tmp_path, env


@pytest.mark.parametrize('variable,stage,calls', [
    (None, None, 3), ('RENEW_EXIT', 'renew', 1),
    ('CHECK_EXIT', 'nginx_config_check', 2), ('RELOAD_EXIT', 'nginx_reload', 3),
])
def test_renew_exit_status_and_stages(scripts, variable, stage, calls):
    folder, output, env = scripts
    if variable:
        env[variable] = '7'
    result = subprocess.run(['bash', str(folder / 'renew_tls.sh')], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == (7 if variable else 0)
    assert len((output / 'calls').read_text().splitlines()) == calls
    if variable:
        assert f'этап={stage} код=7' in result.stderr
        assert 'выполнена успешно' not in result.stdout
    else:
        assert 'команда reload nginx выполнена успешно' in result.stdout
    assert result.stdout[:4].isdigit()  # timestamp on start line


def test_installer_replaces_same_cron_without_running_docker(scripts):
    folder, output, env = scripts
    for schedule in ('0 3 * * *', '30 4 * * *'):
        (folder / '.env').write_text(f'TLS_CRON_SCHEDULE="{schedule}"\n')
        result = subprocess.run(['bash', str(folder / 'install_renewal.sh')], env=env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        cron = (output / 'cron').read_text()
        assert cron.count('renew_tls.sh') == 1
        assert f'{schedule} root /bin/bash "{folder}/renew_tls.sh"' in cron
        assert '/var/log/certbot-renew.log 2>&1' in cron
        assert (output / 'rotation').read_text() == (folder / 'logrotate.conf').read_text()
    assert not (output / 'calls').exists()


def test_invalid_schedule_does_not_replace_cron(scripts):
    folder, output, env = scripts
    (folder / '.env').write_text('TLS_CRON_SCHEDULE="invalid"\n')
    result = subprocess.run(['bash', str(folder / 'install_renewal.sh')], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not (output / 'cron').exists()
