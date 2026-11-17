#!/bin/sh
# =============================================================================
# TokTracker - Grants für die Test-Datenbanken
# =============================================================================
# Die Testsuite (tests/_bootstrap.py) legt pro Lauf eine eigene Datenbank
# `toktracker_test_<pid>_<token>` an und droppt sie danach wieder. Damit das
# auch mit dem regulären App-User funktioniert (run_tests.sh läuft im
# app-Container), braucht er CREATE/DROP für genau dieses Namensschema.
#
# Dieses Script läuft beim ersten Start mit leerem Volume
# (/docker-entrypoint-initdb.d). Für bestehende Volumes einmalig manuell:
#
#   docker exec -i toktracker_db sh /docker-entrypoint-initdb.d/10-test-grants.sh
#
# oder ohne Mount:
#
#   docker exec -e MYSQL_USER=toktracker_user toktracker_db sh -c \
#     'mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" -e "GRANT ALL PRIVILEGES ON `toktracker\_test\_%`.* TO '"'"'"$MYSQL_USER"'"'"'@'"'"'%'"'"'"'
# =============================================================================
set -eu

APP_USER="${MYSQL_USER:-toktracker_user}"
ROOT_PW="${MARIADB_ROOT_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}"

mariadb --protocol=socket -uroot -p"$ROOT_PW" <<SQL
GRANT ALL PRIVILEGES ON \`toktracker\_test\_%\`.* TO '${APP_USER}'@'%';
FLUSH PRIVILEGES;
SQL
