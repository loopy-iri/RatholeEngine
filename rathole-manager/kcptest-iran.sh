#!/usr/bin/env bash
# kcptest-iran.sh — tst A/B ba kcptun (UDP+FEC) rooye server Iran
# server kcp rooye UDP mishnvd va be iperf3 lvkal fvrvard mikonad ta asr FEC ra bsnji.
# mvazi va bikhtr; be tunnel rathole/nginx dst nmiznd.
#   sudo bash kcptest-iran.sh start [udp_port=29000]
#   sudo bash kcptest-iran.sh stop
set -euo pipefail

ACTION="${1:-start}"
UDP_PORT="${2:-29000}"
KEY="${KCP_KEY:-rh-kcp-test-key}"
KCPTUN_VER="${KCPTUN_VER:-v20260129}"
KCPTUN_BASE="${KCPTUN_BASE:-https://github.com/ossfork/kcptun/releases/download}"
BIN=/usr/local/bin/kcptun-server
PIDF=/run/kcptest-server.pid

log(){ printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }
die(){ err "$*"; exit 1; }
[ "$(id -u)" -eq 0 ] || die "ba root ejra kon."

case "$(uname -m)" in
  x86_64) ARCH=amd64 ;; aarch64) ARCH=arm64 ;; *) die "mamari?" ;;
esac

stop_all(){
  [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null || true
  rm -f "$PIDF"
  pkill -f 'kcptun-server' 2>/dev/null || true
  pkill -f 'iperf3 -s'    2>/dev/null || true
  log "kcptest Iran motevaghef shod."
}

[ "$ACTION" = "stop" ] && { stop_all; exit 0; }

# nasb iperf3
command -v iperf3 >/dev/null 2>&1 || { apt-get update -y && apt-get install -y iperf3; }

# download kcptun
if [ ! -x "$BIN" ]; then
  log "download kcptun ${KCPTUN_VER}..."
  tmp="$(mktemp -d)"
  url="${KCPTUN_BASE}/${KCPTUN_VER}/kcptun_linux_${ARCH}.tar.gz"
  curl -fsSL "$url" -o "$tmp/k.tgz" || die "download kcptun shekast khord (link/nskhh ra check kon)."
  tar -xzf "$tmp/k.tgz" -C "$tmp"
  install -m755 "$tmp"/server_linux_${ARCH} "$BIN"
  rm -rf "$tmp"
fi

stop_all
log "rahandazi iperf3 server rooye 127.0.0.1:5201..."
setsid iperf3 -s -1 >/var/log/kcptest-iperf.log 2>&1 &

log "rahandazi kcptun server rooye UDP :${UDP_PORT} (FEC: datashard=10 parity=3 ~30%)..."
setsid "$BIN" -t "127.0.0.1:5201" -l ":${UDP_PORT}" \
  -key "$KEY" -crypt aes-128 -mode manual -mtu 1350 \
  -sndwnd 2048 -rcvwnd 2048 -datashard 10 -parityshard 3 -dscp 46 -nocomp \
  >/var/log/kcptest-server.log 2>&1 &
echo $! > "$PIDF"

echo
log "amade shod."
echo "  • firewall: port UDP ${UDP_PORT} ra baz kon (ufw allow ${UDP_PORT}/udp ya security group)."
echo "  • rooye node ejra kon:  sudo bash kcptest-node.sh start <IRAN_IP>:${UDP_PORT}"
echo "  • iperf3 -s ba -1 fght yek atsal mipzird; baraye tst mjdd dvbarh start bezan."
echo "  • tavaghof:  sudo bash kcptest-iran.sh stop"
