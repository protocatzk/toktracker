#!/usr/bin/env bash
# ==============================================================================
# TokTracker Test-Runner (Quotenfrei & Rückstandsfrei)
# Kopiert Tests temporär in den Container, führt sie aus und löscht sie garantiert.
#
# Die Tests laufen gegen eine isolierte SQLite-DB in /tmp (siehe tests/_bootstrap.py)
# und nutzen den Container-Redis für die Redis-Pfade (Bus, Leases, Rate-Limits).
# ==============================================================================
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-toktracker_app}"
TMP_DIR="/tmp/toktracker_tests_$$"

# Trap stellt sicher, dass /tmp/... im Container bei JEDEM Exit (auch Ctrl+C / Fehler) gelöscht wird
cleanup() {
    echo "🧹 Bereinige temporäre Test-Dateien aus Container..."
    docker exec -u root "$CONTAINER_NAME" rm -rf "$TMP_DIR" 2>/dev/null || true
}
trap cleanup EXIT

echo "📦 Kopiere Test-Suite temporär nach $CONTAINER_NAME:$TMP_DIR..."
docker exec "$CONTAINER_NAME" mkdir -p "$TMP_DIR"
docker cp tests/. "$CONTAINER_NAME:$TMP_DIR/"

echo "🚀 Starte Tests..."
docker exec \
    -e PYTHONPATH=/app \
    -e TOKTRACKER_TEST_REDIS_URL="${TOKTRACKER_TEST_REDIS_URL:-redis://redis:6379/0}" \
    "$CONTAINER_NAME" python "$TMP_DIR/run_tests.py"
