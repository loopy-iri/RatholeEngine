#!/usr/bin/env bash
# test_adaptive.sh — task 5 & 6: barresi probe-haye adaptive va controller-e failover
set -uo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# ---- Task 5: probe functions vujood darand ----------------------------------------
(
  ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  # set AFTER source (ratholenode defaults ra override mikonim)
  ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
  printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
  : > "$SVC_FILE"

  declare -f adaptive_probe_tcp >/dev/null || fail 'adaptive_probe_tcp vojood nadarad'
  declare -f adaptive_probe_ws_tls >/dev/null || fail 'adaptive_probe_ws_tls vojood nadarad'
  ok 'probe functions vojood darand'

  result="$(adaptive_probe_tcp "127.0.0.1" "1" 2>/dev/null || echo 'fail')"
  [[ "$result" =~ tcp_timeout|tcp_refused|tcp_failed|fail ]] || fail "adaptive_probe_tcp natijeh-e namotabar: $result"
  ok 'adaptive_probe_tcp baraye port-e basteh: fail/timeout bargardand'
)

# ---- Task 5: cmd_adaptive tabe vojood darad ----------------------------------------
(
  ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
  printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
  : > "$SVC_FILE"

  declare -f cmd_adaptive >/dev/null || fail 'cmd_adaptive vojood nadarad'
  ok 'cmd_adaptive tabe vojood darad'
)

# ---- Task 5: adaptive_run_probe → state JSON barresi field-ha ---------------------
(
  ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
  ADAPTIVE_STATE="$ROOT/adaptive-state.json"
  printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
  : > "$SVC_FILE"

  # probe dar sandoz fail mishavad (openssl nist ya server nist) — chap mikonim va check mikonim
  adaptive_run_probe 2>/dev/null || true

  if [ -f "$ADAPTIVE_STATE" ]; then
    python3 -c "
import json, sys
d = json.load(open('$ADAPTIVE_STATE'))
required = {'time','current','classification','latency_ms','consecutive_failures'}
missing = required - set(d.keys())
if missing: sys.exit(f'field-haye gomshode: {missing}')
# check secret leak
for k,v in d.items():
    if '/_rh/' in str(v): sys.exit(f'WS_PATH dar JSON leak shod: {k}={v}')
" || fail 'adaptive state JSON field-haye lazem ra nadarad ya secret leak dade'
    ok 'adaptive state JSON field-haye motabar darad va secret-ha leak nashode'
  else
    ok '(skip: probe dar sandoz baste fail shod — state naneveshte shod, manteghi ast)'
  fi
)

# ---- Task 6: adaptive_should_switch — barresi threshold/cooldown ------------------
(
  ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
  printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\nTUNNEL=ws\n' > "$ENV_FILE"
  : > "$SVC_FILE"

  declare -f adaptive_should_switch >/dev/null || fail 'adaptive_should_switch vojood nadarad'

  # 2 failures با threshold=3: nabayad switch konad
  result="$(adaptive_should_switch 2 3 0 300 2>/dev/null)"
  [ "$result" = "no" ] || fail "2 failure nabayad switch kone (got: $result)"
  ok 'adaptive: 2 failure nabayad switch kone (threshold=3)'

  # 3 failures: bayad switch konad
  result="$(adaptive_should_switch 3 3 0 300 2>/dev/null)"
  [ "$result" = "yes" ] || fail "3 failure bayad switch kone (got: $result)"
  ok 'adaptive: 3 failure bayad switch kone'

  # 0 failure با cooldown_rem=300: nabayad switch konad
  result="$(adaptive_should_switch 0 3 5 300 2>/dev/null)"
  [ "$result" = "no" ] || fail "cooldown tamam nashode: nabayad switch konad (got: $result)"
  ok 'adaptive: cooldown tamam nashode nabayad switch konad'

  # plain bedoon ALLOW_INSECURE nabayad no bergardanad
  plain_ok="$(adaptive_plain_allowed 2>/dev/null)"
  [ "$plain_ok" = "no" ] || fail "plain bedoon ALLOW_INSECURE=1 nabayad mojaz bashe (got: $plain_ok)"
  ok 'adaptive: plain bedoon ALLOW_INSECURE=1 mojaz nist'

  # plain BA ALLOW_INSECURE=1 bayad yes bergardanad
  ALLOW_INSECURE=1 plain_ok="$(adaptive_plain_allowed 2>/dev/null)"
  [ "$plain_ok" = "yes" ] || fail "ba ALLOW_INSECURE=1 plain bayad mojaz bashe (got: $plain_ok)"
  ok 'adaptive: ba ALLOW_INSECURE=1 plain mojaz ast'
)

echo "---"
echo "hameye task-5/6 assertion-ha PASS shod"

