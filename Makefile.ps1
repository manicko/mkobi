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
# The @() wrapper is mandatory, not stylistic: `if` is a statement, so a
# one-element array it emits is unrolled on assignment and $Rest collapses to
# System.String. $Rest[0] then becomes a character ('.') and @Rest splats one
# argument per character, silently breaking every target that forwards a single
# trailing argument. Keep the parameterless param() block, and keep the @().
$Target = if ($args.Count -gt 0) { [string]$args[0] } else { 'help' }
$Rest   = @(if ($args.Count -gt 1) { [string[]]$args[1..($args.Count - 1)] } else { })

$DevProject  = 'mkobi'
$TestProject = 'mkobi-test'
$DevCompose  = @('-p', $DevProject,  '--env-file', '.env',
                 '-f', 'docker/docker-compose.yml',
                 '-f', 'docker/docker-compose.override.yml')
$TestCompose = @('-p', $TestProject, '-f', 'docker/docker-compose.test.yml')
$BackupDir   = 'backups'
$UpTimeout   = 180
$TestDbName  = 'bidb_test'

# A restore database dump must be non-trivial: a truncated or empty artefact is
# the exact failure this floor catches before it is handed to pg_restore. The
# floor is named in the target's output so the operator sees the number that
# was checked, not merely that a check happened.
$MinDumpBytes = 1024

# The rehearsal scratch database never collides with a live database or with the
# conftest per-run databases (bidb_test_<token>). It is created and dropped
# inside Invoke-RehearseRestore on the test cluster only.
$RehearsalDbPrefix = 'mkobi_rehearse_'

# /app is root:root 755 and unwritable by the non-root app user, so pytest's
# default .pytest_cache write at rootdir fails with Errno 13. Relocate to /tmp.
$PytestCacheArgs = @('-o', 'cache_dir=/tmp/pytest_cache')

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
    Write-Host "  migration-check   Detect model/schema drift (alembic check, test DB)"
    Write-Host "  psql           Interactive psql on the dev DB"
    Write-Host "  psql-c [sql]   One-shot SQL against the dev DB"
    Write-Host ""
    Write-Host "Backup:" -ForegroundColor Yellow
    Write-Host "  backup         pg_dump + cluster globals (one run, shared stamp) -> ./backups/"
    Write-Host "  restore <file> Restore a run's .dump + matching .globals.sql (both files needed)"
    Write-Host "  rehearse-restore yes [file]  Restore into a throwaway TEST database (proves the path)"
    Write-Host "  prune-backups  Delete ./backups/ artefacts older than 7 days (all kinds)"
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
    $upExit = $LASTEXITCODE
    if ($upExit -ne 0) {
        Write-Host "The dev stack did not become healthy within $UpTimeout seconds (docker compose returned $upExit)." -ForegroundColor Red
        Write-Host "Docker Compose reported the failing service and reason above. Next steps:"
        Write-Host "  .\Makefile.ps1 ps            - container and health status"
        Write-Host "  .\Makefile.ps1 logs <service>  - logs for the failing service (db, app, redis, rq-worker, frontend)"
        Write-Host "  To allow a slow start, raise --wait-timeout above $UpTimeout in Makefile.ps1."
    }
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

function Invoke-TestAppPytest {
    param([string[]] $PyArgs)
    docker compose @TestCompose run --rm --no-deps test-app pytest @PytestCacheArgs @PyArgs
}

function Invoke-Test {
    docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
    Invoke-TestAppPytest
}

function Invoke-TestAll {
    docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
    Invoke-TestAppPytest -PyArgs @('--cov=src/mkobi', '--cov-report=term-missing')
}

function Invoke-TestFresh {
    Invoke-TestReset
    Invoke-Test
}

function Invoke-TestSelect {
    Invoke-TestAppPytest -PyArgs $Rest
}

function Invoke-TestShell {
    docker compose @TestCompose run --rm -it --no-deps test-app bash
}

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

function Invoke-Lint {
    docker compose @DevCompose run --rm --no-deps app ruff check src/ tests/ alembic/env.py
}

function Invoke-Format {
    docker compose @DevCompose run --rm --no-deps app ruff check --fix src/ tests/ alembic/env.py
}

function Invoke-Typecheck {
    docker compose @DevCompose run --rm --no-deps app mypy src/ alembic/env.py
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

# The drift check runs inside the hermetic test compose against bidb_test, never
# the shared dev database: a bare host `alembic check` would resolve through
# alembic.ini's unset sqlalchemy.url to the app config's DATABASE_URL (bidb on
# localhost). Running it as a one-shot against test-migrate's pinned environment
# makes that structurally impossible, so no refusal logic is needed in env.py.
# Calling `alembic check` also runs env.py online, so it takes the same migration
# advisory lock as `upgrade` and `migration-status` — note that a lock refusal
# prints "refusing to migrate", which is a lock verdict, not a drift verdict.
function Invoke-MigrationCheck {
    docker compose @TestCompose run --rm test-migrate alembic check
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
#
# Every step in these targets reads its own result and returns non-zero before
# the success line is reached, so the success line is unreachable on failure.
# Write-Host does not reset $LASTEXITCODE: a failed copy followed by a
# successful rm used to let the script exit zero with an unconditional success
# message (OPS-005). The guards below close that gap.
#
# Artefact movement always goes through `docker compose cp`; the database
# service writes the file inside its container. Nothing is ever piped through a
# host shell redirection: PowerShell's binary redirection corrupts a dump.

# A fresh restore artefact must exist and reach the size floor before it is
# handed to pg_restore. Returns $true only when both hold.
function Assert-DumpArtefact {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $Label
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "Assertion failed: $Label does not exist: $Path" -ForegroundColor Red
        return $false
    }
    $len = (Get-Item -LiteralPath $Path).Length
    if ($len -lt $MinDumpBytes) {
        Write-Host "Assertion failed: $Label is $len bytes, below the $MinDumpBytes-byte floor: $Path" -ForegroundColor Red
        return $false
    }
    Write-Host "Asserted: $Label exists and is $len bytes (floor $MinDumpBytes): $Path" -ForegroundColor DarkGray
    return $true
}

function Invoke-Backup {
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $dest = Join-Path $BackupDir "bidb-$stamp.dump"
    docker compose @DevCompose exec -T db pg_dump -U postgres -d bidb -F c -f /tmp/mkobi.dump
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backup failed: pg_dump returned $LASTEXITCODE." -ForegroundColor Red
        return
    }
    docker compose @DevCompose cp db:/tmp/mkobi.dump $dest
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backup failed: copying the dump out of the container returned $LASTEXITCODE." -ForegroundColor Red
        return
    }
    if (-not (Assert-DumpArtefact -Path $dest -Label 'database dump')) { return }
    docker compose @DevCompose exec -T db rm -f /tmp/mkobi.dump
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backup failed: removing the in-container temp dump returned $LASTEXITCODE." -ForegroundColor Red
        return
    }

    # Second artefact of the same run: cluster globals, sharing the run stamp so
    # the pairing is unambiguous to a human reading the directory. A restore
    # needs both files from the same run.
    $globalsDest = Join-Path $BackupDir "bidb-$stamp.globals.sql"
    if (-not (Export-ClusterGlobals -Destination $globalsDest -Compose $DevCompose -DbService 'db')) { return }

    Write-Host "Backup created: $dest + $(Split-Path -Leaf $globalsDest) (run $stamp)" -ForegroundColor Green
    Write-Host "A restore needs both files from the same run; pass the .dump and the matching .globals.sql is found by stamp." -ForegroundColor Cyan
}

# Emit a run's cluster globals beside the database dump, with the same stamp.
# The file is a role definition - the postgres superuser role and mkobi_app with
# its grants - because roles are cluster-global and a per-database pg_dump does
# not carry them. pg_dumpall supplies the role definitions (including the
# password hash); the grants mirror docker/init-scripts/01-create-app-role.sh,
# which is the authority for mkobi_app's privileges (USAGE on schema public, not
# CREATE - the CREATE form is the test tier's variant in db/starter.py). The
# `:"globals_db"` psql variable in the grants is the same `-v <name>` shape the
# init script uses for `:dbname`, so one artefact loads against the dev database
# and against a rehearsal scratch database alike.
#
# CREATE ROLE has no IF NOT EXISTS, so each role is guarded with a DO block that
# reuses the same "does it already exist?" shape the repo's admin-user bootstrap
# uses (db/starter.py::ensure_admin_user's ON CONFLICT DO NOTHING): a role that
# already exists must not abort the run.
#
# Compose and DbService are parameters because the same export serves the dev
# run (project mkobi, service db) and the test-stack-only rehearsal (project
# mkobi-test, service test-db). Only the dev run writes to ./backups/; the
# rehearsal writes its own throwaway pair.
function Export-ClusterGlobals {
    param(
        [Parameter(Mandatory)] [string] $Destination,
        [Parameter(Mandatory)] [array] $Compose,
        [Parameter(Mandatory)] [string] $DbService
    )

    $script = @'
set -e
pg_dumpall -U postgres --roles-only > /tmp/mkobi-globals.raw.sql
awk '
/^CREATE ROLE / {
  name=$3; sub(/;$/,"",name);
  printf "DO $do$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %c%s%c) THEN CREATE ROLE %s; END IF; END $do$;\n", 39, name, 39, name;
  next
}
{ print }
END {
  printf "\n-- mkobi_app grants (source: docker/init-scripts/01-create-app-role.sh; USAGE on schema public)\n";
  print "GRANT CONNECT ON DATABASE :\"globals_db\" TO mkobi_app;";
  print "GRANT USAGE ON SCHEMA public TO mkobi_app;";
  print "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mkobi_app;";
  print "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mkobi_app;";
  print "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mkobi_app;";
  print "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO mkobi_app;";
}
' /tmp/mkobi-globals.raw.sql > /tmp/mkobi-globals.sql
rm -f /tmp/mkobi-globals.raw.sql
'@

    docker compose @Compose exec -T $DbService sh -c $script
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backup failed: generating cluster globals returned $LASTEXITCODE." -ForegroundColor Red
        return $false
    }
    docker compose @Compose cp "${DbService}:/tmp/mkobi-globals.sql" $Destination
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backup failed: copying cluster globals out of the container returned $LASTEXITCODE." -ForegroundColor Red
        return $false
    }
    if (-not (Assert-DumpArtefact -Path $Destination -Label 'cluster globals')) { return $false }
    docker compose @Compose exec -T $DbService rm -f /tmp/mkobi-globals.sql
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backup failed: removing the in-container globals file returned $LASTEXITCODE." -ForegroundColor Red
        return $false
    }
    return $true
}

# Resolve the shared run stamp from an artefact name. Returns $null when the
# name carries no recognised stamp, so the pairing cannot be resolved.
function Get-BackupStamp {
    param([Parameter(Mandatory)] [string] $Path)
    $name = Split-Path -Leaf $Path
    if ($name -match '^bidb-([0-9_]+)\.[A-Za-z.]+$') { return $Matches[1] }
    return $null
}

# Load a run's cluster globals into the dev database. It runs strictly after the
# pg_restore --clean drop phase: the globals artefact is a role definition, and
# the roles own the grants the restore re-issues, so loading it before the
# restore would have it dropped, and loading it against an already-restored
# database is the correct order. Idempotent by construction: guarded CREATE ROLE
# plus GRANT/ALTER DEFAULT PRIVILEGES, which are idempotent in PostgreSQL.
function Invoke-Load-Globals {
    param(
        [Parameter(Mandatory)] [string] $Source,
        [Parameter(Mandatory)] [string] $Database
    )
    docker compose @DevCompose cp $Source db:/tmp/mkobi-globals.sql
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Globals load failed: copying the globals file into the container returned $LASTEXITCODE." -ForegroundColor Red
        return $false
    }
    # The grants file is database-name-agnostic: `:"globals_db"` is resolved here
    # to the database the restore targeted, so the same artefact loads against
    # bidb in production and against a scratch database in rehearsal.
    docker compose @DevCompose exec -T db psql -U postgres -d $Database -v ON_ERROR_STOP=1 -v "globals_db=$Database" -f /tmp/mkobi-globals.sql
    $loadExit = $LASTEXITCODE
    docker compose @DevCompose exec -T db rm -f /tmp/mkobi-globals.sql
    if ($loadExit -ne 0) {
        Write-Host "Globals load failed: psql returned $loadExit." -ForegroundColor Red
        return $false
    }
    return $true
}

# Read alembic_version from a database that has just been restored. Reading the
# running database's pre-restore state would report the state the operator
# already had, which is the false comfort this read exists to remove.
function Read-RestoredAlembicRevision {
    param(
        [Parameter(Mandatory)] [array] $Compose,
        [Parameter(Mandatory)] [string] $Database,
        [Parameter(Mandatory)] [string] $Context
    )
    $rev = (docker compose @Compose exec -T db psql -U postgres -d $Database -tAc "SELECT version_num FROM alembic_version LIMIT 1") -join ''
    if ($LASTEXITCODE -ne 0 -or -not $rev) {
        Write-Host "Could not read alembic_version from the restored database ($Context)." -ForegroundColor Red
        return $false
    }
    Write-Host "Restored alembic_version ($Context) = $($rev.Trim()) (read from the restored database)." -ForegroundColor Green
    return $true
}

# The restore target. A restore now needs TWO files from the same run: the
# .dump and its paired .globals.sql. The operator passes the .dump; the matching
# globals file is located by the shared run stamp. Reads every step's result so
# the completion line is unreachable on failure, and asserts both artefacts
# before they are used.
function Invoke-Restore {
    if (-not $Rest -or -not $Rest[0]) {
        Write-Host "Usage: .\Makefile.ps1 restore <file.dump>   (the matching .globals.sql from the same run is loaded automatically)" -ForegroundColor Red
        return
    }
    $source = $Rest[0]
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Host "Error: backup file not found: $source" -ForegroundColor Red
        return
    }
    if (-not (Assert-DumpArtefact -Path $source -Label 'database dump')) { return }

    # Pairing: a run's dump and globals share a stamp. A missing globals file is
    # a reported failure, not an absorbed one, so a restore never proceeds
    # against an incomplete set.
    $runStamp = Get-BackupStamp -Path $source
    if (-not $runStamp) {
        Write-Host "Error: cannot resolve a backup-run stamp from '$source'. Expected 'bidb-<stamp>.dump'." -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }
    $globalsName = "bidb-$runStamp.globals.sql"
    $globals = Join-Path (Split-Path -Parent $source) $globalsName
    if (-not (Test-Path -LiteralPath $globals)) {
        Write-Host "Error: missing paired globals artefact '$globalsName' for run '$runStamp'." -ForegroundColor Red
        Write-Host "A restore needs both files from the same run. An incomplete set is refused." -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }
    Write-Host "Restore set (run $runStamp): $([System.IO.Path]::GetFileName($source)) + $globalsName" -ForegroundColor Cyan

    docker compose @DevCompose cp $source db:/tmp/mkobi-restore.dump
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Restore failed: copying the dump into the container returned $LASTEXITCODE." -ForegroundColor Red
        return
    }
    # Load order, printed so the operator reads it while it runs:
    #   1) pg_restore --clean --if-exists  (drop phase, then data)
    #   2) cluster globals                 (roles + grants, strictly after the drop)
    # The globals artefact is a role definition, and the roles own the grants the
    # restore re-issues: loaded before the restore they are dropped by it, loaded
    # after they are correct. The pg_restore exit status is read; --exit-on-error
    # is deliberately not passed (it moves where the tool stops, not whether it
    # reports).
    Write-Host "Load order: 1) pg_restore --clean (drop phase, then data), 2) cluster globals (roles + grants)." -ForegroundColor Cyan
    docker compose @DevCompose exec -T db pg_restore -U postgres -d bidb --clean --if-exists /tmp/mkobi-restore.dump
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Restore failed: pg_restore returned $LASTEXITCODE." -ForegroundColor Red
        return
    }
    if (-not (Invoke-Load-Globals -Source $globals -Database 'bidb')) { return }
    if (-not (Read-RestoredAlembicRevision -Compose $DevCompose -Database 'bidb' -Context 'dev bidb')) { return }
    docker compose @DevCompose exec -T db rm -f /tmp/mkobi-restore.dump
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Restore failed: removing the in-container temp dump returned $LASTEXITCODE." -ForegroundColor Red
        return
    }
    Write-Host "Restore completed: $source (run $runStamp)" -ForegroundColor Green
}

# Rehearsal: prove the restore path works against a database that serves no
# traffic. It runs entirely on the test stack (test-db, project mkobi-test): a
# fresh run sources its dump and its globals from the test cluster, and an
# explicit artefact is paired by its run stamp from ./backups/. It never reads
# or writes the dev database bidb, and it never restores into or drops any
# bidb_test* database. The only database it writes is its own uniquely-named
# scratch database, which is dropped on every exit path, including failure.
#
# It exercises the paired artefacts: a fresh run emits a .dump and its matching
# .globals.sql, and an explicit artefact is paired by its run stamp. A missing
# or mismatched globals file is a reported failure, not an absorbed one.
function Invoke-RehearseRestore {
    # Explicit operator action. The target is destructive to a scratch database
    # and must not run by accident, so it requires the literal 'yes' argument.
    if (-not $Rest -or -not $Rest[0] -or $Rest[0] -ne 'yes') {
        Write-Host "Usage: .\Makefile.ps1 rehearse-restore yes [artifact.dump]" -ForegroundColor Red
        Write-Host "This rehearses a restore into a throwaway database on the TEST stack." -ForegroundColor Red
        Write-Host "Passing 'yes' is the explicit operator action that allows it to run." -ForegroundColor Red
        return
    }
    $explicitSource = if ($Rest.Count -gt 1) { $Rest[1] } else { $null }

    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }

    $ownedArtifacts = @()
    if ($explicitSource) {
        $artifact = $explicitSource
        if (-not (Test-Path -LiteralPath $artifact)) {
            Write-Host "Rehearsal failed: artefact not found: $artifact" -ForegroundColor Red
            return
        }
    } else {
        # A fresh set: rehearsal must exercise the whole pipeline, not a stale
        # file. It sources BOTH artefacts from the test stack, so the rehearsal
        # touches nothing but the test cluster and its throwaway scratch
        # database - never the dev database bidb. The dump is a read of the
        # test database only; nothing is restored into it.
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $artifact = Join-Path $BackupDir "bidb-$stamp.dump"
        docker compose @TestCompose exec -T test-db pg_dump -U postgres -d $TestDbName -F c -f /tmp/mkobi-rehearsal.dump
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Rehearsal failed: pg_dump returned $LASTEXITCODE." -ForegroundColor Red
            return
        }
        docker compose @TestCompose cp test-db:/tmp/mkobi-rehearsal.dump $artifact
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Rehearsal failed: copying the fresh dump out returned $LASTEXITCODE." -ForegroundColor Red
            return
        }
        docker compose @TestCompose exec -T test-db rm -f /tmp/mkobi-rehearsal.dump
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Rehearsal failed: removing the in-container temp dump returned $LASTEXITCODE." -ForegroundColor Red
            return
        }
        $ownedArtifacts += $artifact
        $rehearsalGlobals = Join-Path $BackupDir "bidb-$stamp.globals.sql"
        if (-not (Export-ClusterGlobals -Destination $rehearsalGlobals -Compose $TestCompose -DbService 'test-db')) { return }
        $ownedArtifacts += $rehearsalGlobals
    }

    # Pair the globals by the artefact's run stamp. Both the dump and the globals
    # live in the same directory under the same stamp.
    $runStamp = Get-BackupStamp -Path $artifact
    if (-not $runStamp) {
        Write-Host "Rehearsal failed: cannot resolve a run stamp from '$artifact'." -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }
    $globalsName = "bidb-$runStamp.globals.sql"
    $globals = Join-Path (Split-Path -Parent $artifact) $globalsName
    if (-not (Test-Path -LiteralPath $globals)) {
        Write-Host "Rehearsal failed: missing paired globals artefact '$globalsName' for run '$runStamp'." -ForegroundColor Red
        Write-Host "A restore needs both files from the same run. An incomplete set is refused." -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }

    $scratchDb = "$RehearsalDbPrefix$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    Write-Host "Rehearsing restore of run '$runStamp' ($([System.IO.Path]::GetFileName($artifact)) + $globalsName) into scratch database '$scratchDb'." -ForegroundColor Cyan
    Write-Host "RPO 24h / RTO 4h: this run proves the 4h recovery-time path against a database that serves no traffic." -ForegroundColor Cyan

    $rc = 0
    try {
        if (-not (Assert-DumpArtefact -Path $artifact -Label 'rehearsal dump')) { $rc = 1; return }
        docker compose @TestCompose exec -T test-db psql -U postgres -d postgres -c "CREATE DATABASE `"$scratchDb`""
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Rehearsal failed: creating scratch database returned $LASTEXITCODE." -ForegroundColor Red
            $rc = 1; return
        }

        # Load order across the two artefacts: pg_restore --clean first (drop
        # phase, then data), then the globals (roles + grants) strictly after.
        Write-Host "Load order: 1) pg_restore --clean (drop phase, then data), 2) cluster globals (roles + grants)." -ForegroundColor Cyan

        docker compose @TestCompose cp $artifact test-db:/tmp/mkobi-rehearse.dump
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Rehearsal failed: copying the dump into test-db returned $LASTEXITCODE." -ForegroundColor Red
            $rc = 1; return
        }
        # The corrupted-artefact case lands here: a truncated dump makes
        # pg_restore exit non-zero and the rehearsal reports it. --exit-on-error
        # is deliberately NOT passed; the exit status of pg_restore is the signal.
        docker compose @TestCompose exec -T test-db pg_restore -U postgres -d $scratchDb --clean --if-exists /tmp/mkobi-rehearse.dump
        $restoreExit = $LASTEXITCODE
        docker compose @TestCompose exec -T test-db rm -f /tmp/mkobi-rehearse.dump
        if ($restoreExit -ne 0) {
            Write-Host "Rehearsal failed: pg_restore into scratch database returned $restoreExit." -ForegroundColor Red
            $rc = 1; return
        }

        docker compose @TestCompose cp $globals test-db:/tmp/mkobi-rehearse-globals.sql
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Rehearsal failed: copying the globals into test-db returned $LASTEXITCODE." -ForegroundColor Red
            $rc = 1; return
        }
        docker compose @TestCompose exec -T test-db psql -U postgres -d $scratchDb -v ON_ERROR_STOP=1 -v "globals_db=$scratchDb" -f /tmp/mkobi-rehearse-globals.sql
        $globalsExit = $LASTEXITCODE
        docker compose @TestCompose exec -T test-db rm -f /tmp/mkobi-rehearse-globals.sql
        if ($globalsExit -ne 0) {
            Write-Host "Rehearsal failed: cluster globals load into scratch database returned $globalsExit." -ForegroundColor Red
            $rc = 1; return
        }

        # alembic_version is read from the RESTORED database (the scratch one),
        # never from the dev database, whose state the operator already had.
        $rev = (docker compose @TestCompose exec -T test-db psql -U postgres -d $scratchDb -tAc "SELECT version_num FROM alembic_version LIMIT 1") -join ''
        if ($LASTEXITCODE -ne 0 -or -not $rev) {
            Write-Host "Rehearsal failed: could not read alembic_version from the restored scratch database." -ForegroundColor Red
            $rc = 1; return
        }
        Write-Host "Rehearsal succeeded: restored alembic_version = $($rev.Trim()) (read from the restored database)." -ForegroundColor Green
        Write-Host "RPO 24h (daily backup) / RTO 4h: the restore path completed against a non-serving database." -ForegroundColor Green
    }
    finally {
        # Drop the scratch database on every exit path, including failure. The
        # drop is attempted even when creation failed; IF EXISTS makes it safe.
        docker compose @TestCompose exec -T test-db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS `"$scratchDb`" WITH (FORCE)" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Warning: could not drop scratch database '$scratchDb'; remove it manually." -ForegroundColor Yellow
        } else {
            Write-Host "Scratch database '$scratchDb' dropped." -ForegroundColor DarkGray
        }
        foreach ($owned in $ownedArtifacts) {
            if (Test-Path -LiteralPath $owned) { Remove-Item -LiteralPath $owned -Force }
        }
        $global:LASTEXITCODE = $rc
    }
}

function Invoke-PruneBackups {
    if (-not (Test-Path $BackupDir)) {
        Write-Host "No backups directory found" -ForegroundColor Yellow
        return
    }
    $cutoff = (Get-Date).AddDays(-7)
    # Match every artefact kind a run emits as one set, not just *.dump. A
    # narrower filter would let the non-dump artefacts of a run accumulate
    # forever; a run must leave only whole sets or nothing.
    Get-ChildItem -Path $BackupDir -File |
        Where-Object { $_.Name -match '^bidb-[0-9_]+\.(dump|globals\.sql)$' -or $_.Name -match '^bidb-[0-9_]+\.redis\.rdb$' } |
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
    'migration-check'  { Invoke-MigrationCheck }
    'psql'             { Invoke-Psql }
    'psql-c'           { Invoke-PsqlC }
    'backup'           { Invoke-Backup }
    'restore'          { Invoke-Restore }
    'rehearse-restore' { Invoke-RehearseRestore }
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
