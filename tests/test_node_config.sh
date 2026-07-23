#!/usr/bin/env bash
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }
find_toml_python(){
  local candidate
  for candidate in "${TOML_PYTHON:-}" python3 python3.13 python3.12 python3.11 python.exe; do
    [ -n "$candidate" ] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    "$candidate" -c 'import tomllib' >/dev/null 2>&1 || continue
    echo "$candidate"
    return
  done
  fail 'Python 3.11+ ba tomllib standard lazem ast'
}
TOML_PYTHON="$(find_toml_python)"
assert_toml(){
  local file="$1" toml_file="$1"
  if [[ "$TOML_PYTHON" == *.exe ]]; then
    toml_file="$(wslpath -w "$file")"
  fi
  "$TOML_PYTHON" - "$toml_file" <<'PY' || fail "TOML namotabar: $file"
import pathlib
import sys
import tomllib

with pathlib.Path(sys.argv[1]).open("rb") as config:
    tomllib.load(config)
PY
}

ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export RATHOLENODE_LIB_ONLY=1
source "${REPO_ROOT:?}/rathole-manager/ratholenode"
trap '_rth_cleanup || true; rm -rf "$ROOT"' EXIT INT TERM
ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
: > "$SVC_FILE"
gen_client
assert_toml "$CLIENT_TOML"
grep -qx '\[client.services\]' "$CLIENT_TOML" || fail 'jadval services khali peyda nashod'
ok 'config services khali parse shod va jadval darad'
printf 'n1|token123|2087\n' > "$SVC_FILE"
gen_client
assert_toml "$CLIENT_TOML"
grep -qx '\[client.services.n1\]' "$CLIENT_TOML" || fail 'jadval services tanzim-shode peyda nashod'
ok 'config services tanzim-shode parse shod va jadval darad'
