#!/usr/bin/env bash
# kcptest-node.sh — klaint tst kcptun (UDP+FEC) rooye node kharej
# yek tunnel kcp be Iran miznd va port lvkal 127.0.0.1:5201 ra misazad.
# baad ba iperf3 az dakhl tunnel tst mikni va ba masir mstghim (lossy) mghaish mikni.
#   sudo bash kcptest-node.sh start <IRAN_IP>:<udp_port>
#   sudo bash kcptest-node.sh stop
set -euo pipefail

ACTION="${1:-start}"
REMOTE="${2:-}"
KEY="${KCP_KEY:-rh-kcp-test-key}"
KCPTUN_VER="${KCPTUN_VER:-v20260129}"
KCPTUN_BASE="${KCPTUN_BASE:-https://github.com/ossfork/kcptun/releases/download}"
BIN=/usr/local/bin/kcptun-client
PIDF=/run/kcptest-client.pid

log(){ printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }
die(){ err "$*"; exit 1; }
[ "$(id -u)" -eq 0 ] || die "ba root ejra kon."

case "$(uname -m)" in
  x86_64) ARCH=amd64 ;; aarch64) ARCH=arm64 ;; *) die "mamari?" ;;
esac

stop_all(){
  [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null || true
  rm -f "$PIDF"; pkill -f 'kcptun-client' 2>/dev/null || true
  log "kcptest node motevaghef shod."
}
[ "$ACTION" = "stop" ] && { stop_all; exit 0; }

[ -n "$REMOTE" ] || die "estefade: kcptest-node.sh start <IRAN_IP>:<udp_port>"
command -v iperf3 >/dev/null 2>&1 || { apt-get update -y && apt-get install -y iperf3; }

if [ ! -x "$BIN" ]; then
  log "download kcptun ${KCPTUN_VER}..."
  tmp="$(mktemp -d)"
  url="${KCPTUN_BASE}/${KCPTUN_VER}/kcptun_linux_${ARCH}.tar.gz"
  curl -fsSL "$url" -o "$tmp/k.tgz" || die "download kcptun shekast khord."
  tar -xzf "$tmp/k.tgz" -C "$tmp"
  install -m755 "$tmp"/client_linux_${ARCH} "$BIN"
  rm -rf "$tmp"
fi

stop_all
log "rahandazi kcptun client → ${REMOTE} (lvkal 127.0.0.1:5201)..."
setsid "$BIN" -r "${REMOTE}" -l "127.0.0.1:5201" \
  -key "$KEY" -crypt aes-128 -mode manual -mtu 1350 \
  -sndwnd 2048 -rcvwnd 2048 -datashard 10 -parityshard 3 -dscp 46 -nocomp \
  >/var/log/kcptest-client.log 2>&1 &
echo $! > "$PIDF"
sleep 2

echo
log "hala tst kon va mghaish kon:"
echo "  1) az dakhl tunnel FEC (kcp):   iperf3 -c 127.0.0.1 -t 15"
echo "  2) mstghim (masir lossy fali): iperf3 -c <IRAN_IP> -t 15"
echo
echo "agar (1) paidartr va ba Retr kmtr/throughput iknvakhttr bood → FEC mshkl 9% loss ra hl mikonad."
echo "tavaghof:  sudo bash kcptest-node.sh stop   (va rooye Iran ham stop)"
