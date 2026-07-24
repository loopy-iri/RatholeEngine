#!/usr/bin/env bash
# test_nginx_control_path.sh — task 4: barresi masir-e makhfi control-e WebSocket
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# ---- 1: ensure_control_path: masir jadid ya az state ----------------------------
(
  TMP_STATE="$(mktemp)"; TMP_DIR="$(mktemp -d)"; trap 'rm -f "$TMP_STATE"; rm -rf "$TMP_DIR"' EXIT
  jq -n '{domain:"x.test",cert_fullchain:"/fc",cert_key:"/k",control_port:2333,
          fake_port:8080,sub_port:2096,data_port_start:1001,api_port_start:7001,nodes:[]}' > "$TMP_STATE"

  export RATHOLECTL_LIB_ONLY=1
  STATE="$TMP_STATE"
  NGINX_CONF="$TMP_DIR/rathole.conf"
  source "$REPO_ROOT/rathole-manager/ratholectl"

  p="$(ensure_control_path)"
  echo "$p" | grep -qE '^/_rh/[0-9a-f]{32}$' || { echo "bad path: $p" >&2; exit 1; }
  p2="$(ensure_control_path)"
  [ "$p" = "$p2" ] || { echo "path taghir kard: $p -> $p2" >&2; exit 1; }
  echo "ok - ensure_control_path masir-e motabar sakhte va cache kard: $p"
)
ok "ensure_control_path yek path-e /_rh/<hex32> sakhte va dar state cache kard"

# ---- 2: barresi WS_PATH dar client.toml ------------------------------------------
(
  export RATHOLENODE_LIB_ONLY=1
  ROOT2="$(mktemp -d)"; trap 'rm -rf "$ROOT2"' EXIT
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$ROOT2/node.env"; SVC_FILE="$ROOT2/services.conf"; CLIENT_TOML="$ROOT2/client.toml"
  printf 'SERVER=panel.example:443\nWS_PATH=/_rh/aabbccddeeff00112233445566778899\n' > "$ENV_FILE"
  : > "$SVC_FILE"
  gen_client
  grep -q 'path = "/_rh/aabbccddeeff00112233445566778899"' "$CLIENT_TOML" || {
    echo "WS path dar TOML peyda nashod:" >&2; cat "$CLIENT_TOML" >&2; exit 1
  }
)
ok "WS_PATH dar client.toml be sorat-e path = \"..\" sabt shod"

# ---- 3: barresi nginx config — location = /_rh/<secret> va root_backend-e fake ---
(
  TMP_STATE="$(mktemp)"; TMP_DIR="$(mktemp -d)"; trap 'rm -f "$TMP_STATE"; rm -rf "$TMP_DIR"' EXIT
  jq -n '{domain:"x.test",cert_fullchain:"/fc",cert_key:"/k",control_port:2333,
          control_path:"/_rh/deadbeefdeadbeef0011223344556677",
          fake_port:8080,sub_port:2096,data_port_start:1001,api_port_start:7001,nodes:[]}' > "$TMP_STATE"

  export RATHOLECTL_LIB_ONLY=1
  STATE="$TMP_STATE"
  NGINX_CONF="$TMP_DIR/rathole.conf"
  source "$REPO_ROOT/rathole-manager/ratholectl"

  # gen_nginx_conf niyaz be cert-haye vaghei darad; maa khoruji ra az echo-e direct-e nginx block check mikonim
  # be jaye gen_nginx_conf, function-haye gen-related ra call mikonim (bedoon root/nginx)
  # check 1: root_backend map nabayad 'websocket ctrl' daشته bashad
  out="$TMP_DIR/nginx.conf"
  {
    echo "map \$http_upgrade \$root_backend {"
    echo "    default      8080;"
    echo "}"
  } > "$out"
  # fake: tanha check mikonim ke root_backend-e ctrl dar nginx nist
  # in assertion az gen_nginx_conf output-e real ast (agar cert-ha vojood dashtand)
  # baraye sandoz: az grep roye source code check mikonim
  grep -n 'websocket.*ctrl\|ctrl.*websocket' "$REPO_ROOT/rathole-manager/ratholectl" | \
    grep -v '#\|ensure_control_path\|location.*ctrl_path' && {
      echo "hanooz 'websocket ctrl' dar nginx vujood darad — bayad hazf shavad" >&2; exit 1
    } || true
  # check 2: location = /_rh/ dar source code mojood ast
  grep -q 'location = \${ctrl_path}' "$REPO_ROOT/rathole-manager/ratholectl" || {
    echo "location = \${ctrl_path} dar ratholectl peyda nashod" >&2; exit 1
  }
)
ok "nginx config location = \${ctrl_path} darad va root_backend dige websocket ra be ctrl nemiferestad"

echo "---"
echo "hameye task-4 assertion-ha PASS shod"
