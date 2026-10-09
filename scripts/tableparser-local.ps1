param(
    [ValidateSet('start', 'stop', 'status', 'logs', 'check')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$composeArgs = @('compose', '--env-file', (Join-Path $projectRoot '.env.dev'),
    '-f', (Join-Path $projectRoot 'docker-compose.dev.yml'))
switch ($Action) {
    'start' { & docker @composeArgs up -d --build django celery-worker celery-beat }
    'stop' { & docker @composeArgs stop django celery-worker celery-beat }
    'status' { & docker @composeArgs ps }
    'logs' { & docker @composeArgs logs --tail 100 django celery-worker celery-beat }
    'check' { & docker @composeArgs exec -T django python manage.py check_tableparser_release /opt/tableparser-release/release.json --expected-sha256 e8251bda3a70b81596e4ffffba5570d9949966f85fb45b04fe850891d87427b1 --require-imported }
}
exit $LASTEXITCODE
