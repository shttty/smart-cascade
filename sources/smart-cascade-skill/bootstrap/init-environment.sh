#!/usr/bin/env bash
set -euo pipefail

project_root=${SMART_CASCADE_PROJECT_ROOT:-$PWD}
create_state=()
[[ ${SMART_CASCADE_CREATE_STATE:-0} == 1 ]] && create_state=(--create-state)
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/initialize.py" --project-root "$project_root" "${create_state[@]}"
