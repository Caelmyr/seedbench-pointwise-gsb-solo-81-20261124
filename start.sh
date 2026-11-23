#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
docker compose up --detach --build --wait
printf '\nSeedbench is ready at http://127.0.0.1:%s/\n' "${SEEDBENCH_PORT:-19884}"
printf 'Stop with docker compose down. Saved trays remain in the named volume.\n'
