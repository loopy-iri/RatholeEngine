#!/usr/bin/env bash
# install-node.sh — nasab samt node kharej (rathole client)
# nasb tazh:
#   sudo bash install-node.sh --server btli.ir:443 --name trk01 --token <T> --inbound-port 2087 \
#        [--api-token <T> --api-inbound-port 62050]
# nasb az rooye backup:
#   sudo bash install-node.sh --restore /root/rathole-node-backup-....tar.gz
set -euo pipefail

RATHOLE_VERSION="${RATHOLE_VERSION:-v0.5.0}"
SERVER="" NAME="" TOKEN="" INBOUND="" API_TOKEN="" API_INBOUND="" RESTORE=""

log(){ printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }
die(){ err "$*"; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --server)            SERVER="$2"; shift 2;;
    --name)              NAME="$2"; shift 2;;
    --token)             TOKEN="$2"; shift 2;;
    --inbound-port)      INBOUND="$2"; shift 2;;
    --api-token)         API_TOKEN="$2"; shift 2;;
    --api-inbound-port)  API_INBOUND="$2"; shift 2;;
    --restore)           RESTORE="$2"; shift 2;;
    --version)           RATHOLE_VERSION="$2"; shift 2;;
    *) die "argument nashenakhte: $1";;
  esac
done

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (sudo)."
if [ -z "$RESTORE" ]; then
  [ -n "$SERVER" ] && [ -n "$NAME" ] && [ -n "$TOKEN" ] && [ -n "$INBOUND" ] || \
    die "argumenthaye lazem: --server --name --token --inbound-port  (ya --restore <file>)"
else
  [ -f "$RESTORE" ] || die "file backup peyda nashod: $RESTORE"
fi

case "$(uname -m)" in
  x86_64)  RH_ARCH="x86_64-unknown-linux-gnu" ;;
  aarch64) RH_ARCH="aarch64-unknown-linux-musl" ;;
  *) die "memari poshtibani-nashode: $(uname -m)" ;;
esac

# ---------- nasb rathole ----------
if ! command -v rathole >/dev/null 2>&1; then
  log "nasb pish-niazha va download rathole ${RATHOLE_VERSION}..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y && apt-get install -y curl unzip tar ca-certificates
  tmp="$(mktemp -d)"
  url="https://github.com/rapiz1/rathole/releases/download/${RATHOLE_VERSION}/rathole-${RH_ARCH}.zip"
  curl -fsSL "$url" -o "$tmp/rathole.zip" || die "download rathole shekast khord."
  unzip -o "$tmp/rathole.zip" -d "$tmp" >/dev/null
  install -m 755 "$tmp/rathole" /usr/local/bin/rathole
  rm -rf "$tmp"
fi

mkdir -p /etc/rathole

# ---------- nasb ratholenode ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/ratholenode" ] && { install -m 755 "$SCRIPT_DIR/ratholenode" /usr/local/bin/ratholenode; log "ratholenode nasb shod."; } || warn "ratholenode knar askript nist."
[ -f "$SCRIPT_DIR/common.sh" ] && { mkdir -p /usr/local/share/rathole; install -m 644 "$SCRIPT_DIR/common.sh" /usr/local/share/rathole/common.sh; log "common.sh nasb shod."; }

# ---------- service systemd (tunnel asli) ----------
log "nasb service systemd..."
cat > /etc/systemd/system/rathole-client.service <<'UNIT'
[Unit]
Description=rathole client (foreign node)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/rathole /etc/rathole/client.toml
Restart=always
RestartSec=2
Environment=RUST_LOG=info
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload

# ---------- halat restore az backup ----------
if [ -n "$RESTORE" ]; then
  log "restore node az backup: $RESTORE"
  if command -v ratholenode >/dev/null 2>&1; then
    ratholenode restore "$RESTORE"
  else
    tar -xzf "$RESTORE" -C / || die "baz kardan backup shekast khord."
    systemctl enable --now rathole-client 2>/dev/null || true
  fi
  log "nasb node az backup kamel shod."
  echo "barresi:  ratholenode ls   |   journalctl -u rathole-client -n 10 --no-pager"
  exit 0
fi

# ---------- nasb tazh ----------
log "neveshtan /etc/rathole/node.env va services.conf..."
{ echo "SERVER=${SERVER}"; echo "RATHOLE_VERSION=${RATHOLE_VERSION}"; } > /etc/rathole/node.env
chmod 600 /etc/rathole/node.env
{
  echo "${NAME}|${TOKEN}|${INBOUND}"
  [ -n "$API_TOKEN" ] && [ -n "$API_INBOUND" ] && echo "${NAME}_api|${API_TOKEN}|${API_INBOUND}"
} > /etc/rathole/services.conf
chmod 600 /etc/rathole/services.conf

if command -v ratholenode >/dev/null 2>&1; then
  ratholenode apply
else
  HOST="${SERVER%%:*}"
  {
    echo "[client]"; echo "remote_addr = \"${SERVER}\""; echo "retry_interval = 1"; echo "heartbeat_timeout = 40"; echo
    echo "[client.transport]"; echo "type = \"websocket\""; echo "[client.transport.websocket]"; echo "tls = true"
    echo "[client.transport.tls]"; echo "hostname = \"${HOST}\""; echo
    echo "[client.services.${NAME}]"; echo "token = \"${TOKEN}\""; echo "local_addr = \"127.0.0.1:${INBOUND}\""; echo "type = \"tcp\""
    if [ -n "$API_TOKEN" ] && [ -n "$API_INBOUND" ]; then
      echo; echo "[client.services.${NAME}_api]"; echo "token = \"${API_TOKEN}\""; echo "local_addr = \"127.0.0.1:${API_INBOUND}\""; echo "type = \"tcp\""
    fi
  } > /etc/rathole/client.toml
  systemctl enable --now rathole-client
fi

log "node '${NAME}' nasb va start shod."
echo
echo "gam baad rooye hamin node:"
echo "  inbound Xray:  path=/${NAME} | listen=127.0.0.1 | port=${INBOUND} | TLS=off  (ya TLS/Reality baraye service game)"
echo "afzoodan service/IP bishtar rooye hamin tunnel:  ratholenode add-svc <name> <token> <inbound>"
echo "afzoodan server Iran dovom:  ratholenode upstream add <id> <server:443> ; ratholenode upstream add-svc <id> <name> <token> <inbound>"
echo "backup node:  ratholenode backup"
echo "barresi log:  journalctl -u rathole-client -f"
