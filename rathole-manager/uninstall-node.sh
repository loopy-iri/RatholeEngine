#!/usr/bin/env bash
# uninstall-node.sh — hazf kamel samt node kharej (klaint rathole)
# ejra: sudo bash uninstall-node.sh [--purge] [--yes]
#   --purge : bainri rathole ham hazf shavad
#   --yes   : bedoon prssh
set -uo pipefail

PURGE=0; YES=0

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }
ask_yn(){ [ "$YES" -eq 1 ] && return 0; local a; read -rp "$1 [y/N]: " a; [[ "$a" =~ ^[Yy]$ ]]; }

while [ $# -gt 0 ]; do case "$1" in
  --purge) PURGE=1; shift;;
  --yes|-y) YES=1; shift;;
  *) shift;;
esac; done

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (sudo)."

warn "in askript service rathole-client va config node ra hazf mikonad."
warn "rooye nginx ya Xray node dst nmiznd (anha mstghland)."
ask_yn "adamh?" || { log "lghv shod."; exit 0; }

# ---------- tavaghof va hazf service ----------
log "tavaghof va ghirfaalsazi rathole-client..."
systemctl disable --now rathole-client 2>/dev/null || true
rm -f /etc/systemd/system/rathole-client.service
systemctl daemon-reload 2>/dev/null || true

# ---------- hazf config va state ----------
log "hazf client.toml va node.env..."
rm -f /etc/rathole/client.toml /etc/rathole/node.env
if [ -d /etc/rathole ] && [ -z "$(ls -A /etc/rathole 2>/dev/null)" ]; then rmdir /etc/rathole; fi

# ---------- hazf abzar ----------
rm -f /usr/local/bin/ratholenode
log "ratholenode hazf shod."
# common.sh-e eshteraki (agar panel/hub-e digari rooye hamin server nist, hazf kon)
if [ -f /usr/local/share/rathole/common.sh ] \
   && [ ! -f /etc/systemd/system/rathole-server.service ] \
   && [ ! -f /opt/ratholehub/hub.py ]; then
  rm -f /usr/local/share/rathole/common.sh
  rmdir /usr/local/share/rathole 2>/dev/null || true
  log "common.sh hazf shod."
fi

# ---------- purge ekhtiari ----------
if [ "$PURGE" -eq 1 ]; then
  if ask_yn "bainri /usr/local/bin/rathole hazf shvd?"; then rm -f /usr/local/bin/rathole; fi
fi

echo
log "hazf samt node kamel shod."
warn "inbound Xray rooye in node hmchnan faal ast; agar lazem nist, az panel/Xray jdaganh hzfsh kon."
