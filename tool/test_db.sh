#!/usr/bin/env bash
# A throwaway PostgreSQL for the queue tests. Nothing here touches the project stack.
#
#   ./tool/test_db.sh up     # start it and print the URL to export
#   ./tool/test_db.sh down   # remove it
set -euo pipefail
NAME=mnp-test-pg
PORT=${MNP_TEST_PG_PORT:-55432}
case "${1:-up}" in
  up)
    if ! docker inspect "$NAME" >/dev/null 2>&1; then
      docker run -d --name "$NAME" -e POSTGRES_PASSWORD=mnp -e POSTGRES_USER=mnp \
        -e POSTGRES_DB=mnp -p "$PORT:5432" postgres:17-alpine >/dev/null
    fi
    docker start "$NAME" >/dev/null 2>&1 || true
    for _ in $(seq 30); do
      docker exec "$NAME" pg_isready -U mnp -q && break
      sleep 1
    done
    echo "export MNP_DB_URL=postgresql://mnp:mnp@localhost:$PORT/mnp"
    ;;
  down) docker rm -f "$NAME" >/dev/null 2>&1 || true; echo "removed $NAME" ;;
  *) echo "usage: $0 {up|down}" >&2; exit 2 ;;
esac
