<#
.SYNOPSIS
    mkobi developer task runner (PowerShell 7+).
.DESCRIPTION
    Thin wrapper over `docker compose`. Every target is one docker compose
    invocation against an explicit project name. Run `.\Makefile.ps1 help`
    for the target list.

    Relative paths (`--env-file .env`, `-f docker/...`) are resolved against
    the current working directory, so run this script from the repo root.
#>

param()

if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Error "PowerShell 7+ is required (found $($PSVersionTable.PSVersion)). Re-run with: pwsh -File .\Makefile.ps1 $($args -join ' ')"
    exit 1
}

# A parameterless param() block keeps every token verbatim in $args. Declaring
# named parameters (e.g. -k) would make PowerShell try to bind them as parameter
# names and fail before the body runs.
$Target = if ($args.Count -gt 0) { [string]$args[0] } else { 'help' }
$Rest   = if ($args.Count -gt 1) { [string[]]$args[1..($args.Count - 1)] } else { [string[]]@() }

$DevProject  = 'mkobi'
$TestProject = 'mkobi-test'
$DevCompose  = @('-p', $DevProject,  '--env-file', '.env',
                 '-f', 'docker/docker-compose.yml',
                 '-f', 'docker/docker-compose.override.yml')
$TestCompose = @('-p', $TestProject, '-f', 'docker/docker-compose.test.yml')
$BackupDir   = 'backups'
$UpTimeout   = 180

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

function Show-Help {
    Write-Host "mkobi - Development Commands (PowerShell 7+)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\Makefile.ps1 <target> [args...]   (run from the repo root)"
    Write-Host ""
    Write-Host "Stack lifecycle (dev):" -ForegroundColor Yellow
    Write-Host "  up             Start dev stack and block until healthy"
    Write-Host "  down           Stop and remove dev containers + network"
    Write-Host "  restart        Restart code services (keeps volumes)"
    Write-Host "  build          Build dev images from cache"
    Write-Host "  rebuild        Rebuild from scratch, then start"
    Write-Host "  ps             Show dev container status"
    Write-Host "  logs [service] Follow logs (all services if omitted)"
    Write-Host "  shell          Interactive bash in a throwaway app container"
    Write-Host "  exec [cmd...]  Run a command in the running app container"
    Write-Host "  dev-watch      Run dev stack attached, streaming all logs"
    Write-Host ""
    Write-Host "Stack lifecycle (test):" -ForegroundColor Yellow
    Write-Host "  test-up        Start test-db + test-redis and wait for healthy"
    Write-Host "  test-down      Stop test stack, keep volumes"
    Write-Host "  test-reset     Destroy test volumes and recreate a clean test DB"
    Write-Host "  test-logs      Follow test service logs"
    Write-Host "  test-ps        Show test container status"
    Write-Host ""
    Write-Host "Tests:" -ForegroundColor Yellow
    Write-Host "  test           Default gate: full suite, DB auto-recreated by conftest"
    Write-Host "  test-all       Full suite with live coverage gate"
    Write-Host "  test-fresh     Wipe test volumes, recreate schema, run full suite"
    Write-Host "  test-select    Forward arbitrary args to pytest (verbatim)"
    Write-Host "  test-shell     Interactive bash inside the test image"
    Write-Host ""
    Write-Host "Quality gates:" -ForegroundColor Yellow
    Write-Host "  lint           Ruff check backend + tests"
    Write-Host "  format         Ruff auto-fix (incl. import sorting)"
    Write-Host "  typecheck      Mypy"
    Write-Host "  fe-lint        ESLint"
    Write-Host "  fe-test        Vitest with coverage"
    Write-Host "  check          Aggregate gate: lint + typecheck + fe-lint + fe-test"
    Write-Host ""
    Write-Host "Database:" -ForegroundColor Yellow
    Write-Host "  migrate        Run alembic upgrade head (one-shot migrate service)"
    Write-Host "  migration-new  Autogenerate a revision"
    Write-Host "  migration-status  Show current vs head"
    Write-Host "  psql           Interactive psql on the dev DB"
    Write-Host "  psql-c [sql]   One-shot SQL against the dev DB"
    Write-Host ""
    Write-Host "Backup:" -ForegroundColor Yellow
    Write-Host "  backup         pg_dump inside the container, cp out to ./backups/"
    Write-Host "  restore <file> Copy the dump in, then pg_restore"
    Write-Host "  prune-backups  Delete ./backups/*.dump older than 7 days"
    Write-Host ""
    Write-Host "Host-native:" -ForegroundColor Yellow
    Write-Host "  uv-sync        Sync the host Python venv from the lockfile"
    Write-Host "  fe-install     Deterministic frontend install (npm ci)"
    Write-Host "  open           Open the Vite dev URL in the default browser"
    Write-Host ""
    Write-Host "Diagnostics and cleanup:" -ForegroundColor Yellow
    Write-Host "  config         Print resolved dev config"
    Write-Host "  config-test    Print resolved test config"
    Write-Host "  doctor         Print Docker/Compose/PS versions and service lists"
    Write-Host "  clean          Remove dev + test containers and networks, keep volumes"
    Write-Host "  fullclean      Same, plus remove both projects' volumes (prompts first)"
    Write-Host "  nuke           fullclean + build-cache and unused-image prune (prompts)"
    Write-Host "  help           Print this target list"
}

# ---------------------------------------------------------------------------
# Stack lifecycle (dev)
# ---------------------------------------------------------------------------

function Invoke-Up {
    docker compose @DevCompose rm -sf migrate
    docker compose @DevCompose up -d --wait --wait-timeout $UpTimeout
}

function Invoke-Down {
    docker compose @DevCompose down --remove-orphans
}

function Invoke-Restart {
    docker compose @DevCompose restart app rq-worker frontend
}

function Invoke-Build {
    docker compose @DevCompose build
}

function Invoke-Rebuild {
    docker compose @DevCompose build --no-cache
    Invoke-Up
}

function Invoke-Ps {
    docker compose @DevCompose ps
}

function Invoke-Logs {
    docker compose @DevCompose logs -f --tail=200 @Rest
}

function Invoke-Shell {
    docker compose @DevCompose run --rm --no-deps app bash
}

function Invoke-Exec {
    docker compose @DevCompose exec app @Rest
}

function Invoke-DevWatch {
    docker compose @DevCompose up --remove-orphans
}

# ---------------------------------------------------------------------------
# Stack lifecycle (test)
# ---------------------------------------------------------------------------

function Invoke-TestUp {
    docker compose @TestCompose rm -sf test-migrate test-app
    docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
}

function Invoke-TestDown {
    docker compose @TestCompose down --remove-orphans
}

function Invoke-TestReset {
    docker compose @TestCompose down -v --remove-orphans
    docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
}

function Invoke-TestLogs {
    docker compose @TestCompose logs -f --tail=200 test-db test-redis
}

function Invoke-TestPs {
    docker compose @TestCompose ps
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

function Invoke-Test {
    docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
    docker compose @TestCompose run --rm --no-deps test-app pytest
}

function Invoke-TestAll {
    docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
    docker compose @TestCompose run --rm --no-deps test-app pytest --cov=src/mkobi --cov-report=term-missing
}

function Invoke-TestFresh {
    Invoke-TestReset
    Invoke-Test
}

function Invoke-TestSelect {
    docker compose @TestCompose run --rm --no-deps test-app pytest @Rest
}

function Invoke-TestShell {
    docker compose @TestCompose run --rm -it --no-deps test-app bash
}

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

function Invoke-Lint {
    docker compose @DevCompose run --rm --no-deps app ruff check src/ tests/
}

function Invoke-Format {
    docker compose @DevCompose run --rm --no-deps app ruff check --fix src/ tests/
}

function Invoke-Typecheck {
    docker compose @DevCompose run --rm --no-deps app mypy src/
}

function Invoke-FeLint {
    npm --prefix frontend run lint
}

function Invoke-FeTest {
    npm --prefix frontend run test
}

function Invoke-Check {
    Invoke-Lint
    if ($LASTEXITCODE -ne 0) { return }
    Invoke-Typecheck
    if ($LASTEXITCODE -ne 0) { return }
    Invoke-FeLint
    if ($LASTEXITCODE -ne 0) { return }
    Invoke-FeTest
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

function Invoke-Migrate {
    docker compose @DevCompose run --rm migrate
}

function Invoke-MigrationNew {
    docker compose @DevCompose run --rm app alembic revision --autogenerate -m @Rest
}

function Invoke-MigrationStatus {
    docker compose @DevCompose run --rm app alembic current
}

function Invoke-Psql {
    docker compose @DevCompose exec db psql -U postgres -d bidb
}

function Invoke-PsqlC {
    docker compose @DevCompose exec -T db psql -U postgres -d bidb -c @Rest
}

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

function Invoke-Backup {
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $dest = Join-Path $BackupDir "bidb-$stamp.dump"
    docker compose @DevCompose exec -T db pg_dump -U postgres -d bidb -F c -f /tmp/mkobi.dump
    if ($LASTEXITCODE -ne 0) { return }
    docker compose @DevCompose cp db:/tmp/mkobi.dump $dest
    docker compose @DevCompose exec -T db rm -f /tmp/mkobi.dump
    Write-Host "Backup created: $dest" -ForegroundColor Green
}

function Invoke-Restore {
    if (-not $Rest -or -not $Rest[0]) {
        Write-Host "Usage: .\Makefile.ps1 restore <file>" -ForegroundColor Red
        return
    }
    $source = $Rest[0]
    if (-not (Test-Path $source)) {
        Write-Host "Error: backup file not found: $source" -ForegroundColor Red
        return
    }
    docker compose @DevCompose cp $source db:/tmp/mkobi-restore.dump
    if ($LASTEXITCODE -ne 0) { return }
    docker compose @DevCompose exec -T db pg_restore -U postgres -d bidb --clean --if-exists /tmp/mkobi-restore.dump
    docker compose @DevCompose exec -T db rm -f /tmp/mkobi-restore.dump
}

function Invoke-PruneBackups {
    if (-not (Test-Path $BackupDir)) {
        Write-Host "No backups directory found" -ForegroundColor Yellow
        return
    }
    $cutoff = (Get-Date).AddDays(-7)
    Get-ChildItem -Path $BackupDir -Filter '*.dump' |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            Write-Host "Pruned old backup: $($_.Name)" -ForegroundColor Yellow
        }
}

# ---------------------------------------------------------------------------
# Host-native
# ---------------------------------------------------------------------------

function Invoke-UvSync {
    uv sync --frozen
}

function Invoke-FeInstall {
    npm --prefix frontend ci
}

function Invoke-Open {
    Start-Process 'http://localhost:5173'
}

# ---------------------------------------------------------------------------
# Diagnostics and cleanup
# ---------------------------------------------------------------------------

function Invoke-Config {
    docker compose @DevCompose config
}

function Invoke-ConfigTest {
    docker compose @TestCompose config
}

function Invoke-Doctor {
    docker version --format '{{.Server.Version}}'
    docker compose version
    Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
    Write-Host "Dev project: $DevProject (services below)"
    docker compose @DevCompose config --services
    Write-Host "Test project: $TestProject (services below)"
    docker compose @TestCompose config --services
}

function Invoke-Clean {
    docker compose @DevCompose down --remove-orphans
    docker compose @TestCompose down --remove-orphans
}

function Invoke-FullClean {
    Write-Host "This removes volumes for the '$DevProject' and '$TestProject' projects only." -ForegroundColor Yellow
    $answer = Read-Host "Type 'yes' to continue"
    if ($answer -ne 'yes') {
        Write-Host "Aborted." -ForegroundColor Yellow
        return
    }
    docker compose @DevCompose down -v --remove-orphans
    docker compose @TestCompose down -v --remove-orphans
    Write-Host "Volumes for '$DevProject' and '$TestProject' removed." -ForegroundColor Green
}

function Invoke-Nuke {
    Invoke-FullClean
    if ($LASTEXITCODE -ne 0) { return }
    Write-Host "Pruning build cache and unused images (daemon-global)." -ForegroundColor Yellow
    docker builder prune -af
    docker image prune -af
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

switch ($Target.ToLower()) {
    'help'             { Show-Help }
    'up'               { Invoke-Up }
    'down'             { Invoke-Down }
    'restart'          { Invoke-Restart }
    'build'            { Invoke-Build }
    'rebuild'          { Invoke-Rebuild }
    'ps'               { Invoke-Ps }
    'logs'             { Invoke-Logs }
    'shell'            { Invoke-Shell }
    'exec'             { Invoke-Exec }
    'dev-watch'        { Invoke-DevWatch }
    'test-up'          { Invoke-TestUp }
    'test-down'        { Invoke-TestDown }
    'test-reset'       { Invoke-TestReset }
    'test-logs'        { Invoke-TestLogs }
    'test-ps'          { Invoke-TestPs }
    'test'             { Invoke-Test }
    'test-all'         { Invoke-TestAll }
    'test-fresh'       { Invoke-TestFresh }
    'test-select'      { Invoke-TestSelect }
    'test-shell'       { Invoke-TestShell }
    'lint'             { Invoke-Lint }
    'format'           { Invoke-Format }
    'typecheck'        { Invoke-Typecheck }
    'fe-lint'          { Invoke-FeLint }
    'fe-test'          { Invoke-FeTest }
    'check'            { Invoke-Check }
    'migrate'          { Invoke-Migrate }
    'migration-new'    { Invoke-MigrationNew }
    'migration-status' { Invoke-MigrationStatus }
    'psql'             { Invoke-Psql }
    'psql-c'           { Invoke-PsqlC }
    'backup'           { Invoke-Backup }
    'restore'          { Invoke-Restore }
    'prune-backups'    { Invoke-PruneBackups }
    'uv-sync'          { Invoke-UvSync }
    'fe-install'       { Invoke-FeInstall }
    'open'             { Invoke-Open }
    'config'           { Invoke-Config }
    'config-test'      { Invoke-ConfigTest }
    'doctor'           { Invoke-Doctor }
    'clean'            { Invoke-Clean }
    'fullclean'        { Invoke-FullClean }
    'nuke'             { Invoke-Nuke }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Show-Help
        exit 1
    }
}

exit $LASTEXITCODE
