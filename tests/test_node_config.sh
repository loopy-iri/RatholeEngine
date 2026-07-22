#!/usr/bin/env bash
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export RATHOLENODE_LIB_ONLY=1
source "${REPO_ROOT:?}/rathole-manager/ratholenode"
ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
: > "$SVC_FILE"
gen_client
grep -qx '\[client.services\]' "$CLIENT_TOML" || fail 'missing empty services table'
ok 'empty services config has a services table'
printf 'n1|token123|2087\n' > "$SVC_FILE"
gen_client
grep -qx '\[client.services.n1\]' "$CLIENT_TOML" || fail 'missing configured service table'
ok 'configured service has a service table'
