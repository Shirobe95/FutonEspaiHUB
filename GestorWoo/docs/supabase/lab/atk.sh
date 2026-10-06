#!/bin/bash
# uso: atk.sh ROLE UID "SQL"   -> ejecuta en transaccion con ROLLBACK
export PGPASSWORD=audit
psql -h localhost -U audit -d ${DB:-lab_before} -X -At <<SQL 2>&1 | sed 's/^/    /'
BEGIN;
SET LOCAL ROLE $1;
SELECT set_config('request.jwt.claim.sub', CASE WHEN '$2'='NONE' THEN '' ELSE '$2' END, true);
$3
ROLLBACK;
SQL
