param(
    [ValidateSet('start', 'stop', 'status', 'logs')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $projectRoot 'data/tableparser-sandbox/compose.secret'
if (-not (Test-Path -LiteralPath $envPath)) {
    throw 'Sandbox has not been initialized. See docs/tableparser-local-sandbox.md.'
}
$composeArgs = @('compose', '--env-file', $envPath, '-f', (Join-Path $projectRoot 'docker-compose.parser-sandbox.yml'))
switch ($Action) {
    'start' { & docker @composeArgs up -d --no-build }
    'stop' { & docker @composeArgs stop }
    'status' { & docker @composeArgs ps }
    'logs' { & docker @composeArgs logs --tail 100 web worker }
}
exit $LASTEXITCODE
