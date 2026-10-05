#!/bin/bash
# =============================================================================
# Create dedicated application role.
# This script is run on PostgreSQL container initialization (first volume start).
#
# The role definition and every grant live in ONE referenced artefact,
# shared/app-role-grants.sql. This script only supplies its psql variables
# (`app_password`, `dbname`) and loads it; it does not transcribe the grants, so
# the artefact and this load cannot drift.
#
# NOTE: PostgreSQL 18+ uses the 'builtin' locale provider with C.UTF-8, which
# provides immutable collation that never changes across OS updates. No template1
# locale fix is needed.
# =============================================================================

set -e

echo "Creating application role mkobi_app..."

# Load the single referenced definition of the role and its grants.
# psql -v passes variables safely (avoids shell expansion issues with $$ heredoc
# patterns that caused PID-based garbage passwords). ON_ERROR_STOP makes any
# failure abort container initialisation loudly rather than silently.
psql -v ON_ERROR_STOP=1 \
     -v app_password="${MKOBI_APP_PASSWORD}" \
     -v dbname="${POSTGRES_DB}" \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     --file /docker-entrypoint-initdb.d/shared/app-role-grants.sql

echo "Application role mkobi_app created successfully."
