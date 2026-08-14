#!/usr/bin/env bash
# Testes de integração da API Go contra um Postgres (pgvector) descartável.
# Uso: apps/api/scripts/test-integration.sh  (de qualquer diretório)
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${TEST_PG_PORT:-5599}"
NAME=menuai-test-pg

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "${PORT}:5432" \
  -e POSTGRES_USER=menuai -e POSTGRES_PASSWORD=menuai -e POSTGRES_DB=menuai_test \
  pgvector/pgvector:pg16 >/dev/null

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "aguardando postgres em :${PORT}..."
for i in $(seq 1 30); do
  if docker exec "$NAME" pg_isready -U menuai -d menuai_test >/dev/null 2>&1; then break; fi
  sleep 1
done

export TEST_DATABASE_URL="postgres://menuai:menuai@localhost:${PORT}/menuai_test?sslmode=disable"
go test -tags integration -count=1 -v ./internal/store/
