#!/bin/bash
# Laboratorio local (PostgreSQL, NUNCA produccion): reconstruye el esquema vivo de Supabase,
# lanza los ataques de la auditoria antes y despues de una propuesta SQL y muestra las diferencias.
# Uso: ./run_lab.sh ../proposals/S_hardening_001.sql
set -euo pipefail
cd "$(dirname "$0")"
export PGPASSWORD="${PGPASSWORD:-audit}"; H="${PGHOST:-localhost}"; U="${PGUSER:-audit}"
PROPOSAL="${1:?indica la propuesta .sql}"
for db in lab_before lab_after; do
  dropdb -h "$H" -U "$U" --if-exists "$db"; createdb -h "$H" -U "$U" "$db"
  for f in 00_supabase_sim.sql live_schema.sql seed.sql; do psql -h "$H" -U "$U" -d "$db" -X -q -v ON_ERROR_STOP=1 -f "$f" >/dev/null; done
done
psql -h "$H" -U "$U" -d lab_after -X -q -v ON_ERROR_STOP=1 -f "$PROPOSAL" >/dev/null
DB=lab_before ./attacks.sh > /tmp/attacks_before.txt 2>&1
DB=lab_after  ./attacks.sh > /tmp/attacks_after.txt  2>&1
diff <(grep -v '^ *[0-9a-f-]\{36\}$' /tmp/attacks_before.txt) <(grep -v '^ *[0-9a-f-]\{36\}$' /tmp/attacks_after.txt) || true
