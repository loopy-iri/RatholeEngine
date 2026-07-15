#!/usr/bin/env bash
# uninstall-panel.sh — hazf kamel samt server Iran va riastvr backup nginx
# ejra: sudo bash uninstall-panel.sh [--purge] [--yes]
#   --purge : bainri rathole va bsthhai nasb-shode ham hazf shavand (ba ahtiat)
#   --yes   : bedoon prssh
set -uo pipefail

STATE="/etc/rathole-manager/state.json"
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

warn "in askript service rathole-server, configha va state ra hazf mikonad."
ask_yn "adamh?" || { log "lghv shod."; exit 0; }

# ---------- tavaghof va hazf service ----------
log "tavaghof va ghirfaalsazi rathole-server..."
systemctl disable --now rathole-server 2>/dev/null || true
rm -f /etc/systemd/system/rathole-server.service
# instans-e noise (agar sakhte shode bood)
systemctl disable --now rathole-noise 2>/dev/null || true
rm -f /etc/systemd/system/rathole-noise.service /etc/rathole/noise-server.toml
systemctl daemon-reload 2>/dev/null || true

# ---------- riastvr config nginx ----------
NGINX_CONF="/etc/nginx/conf.d/rathole.conf"
if [ -f "$STATE" ] && command -v jq >/dev/null 2>&1; then
  NGINX_CONF="$(jq -r '.nginx_conf // "/etc/nginx/conf.d/rathole.conf"' "$STATE" 2>/dev/null)"
fi

if [ -f "$NGINX_CONF.rathole-orig.bak" ]; then
  log "riastvr config nginx az backup: $NGINX_CONF.rathole-orig.bak"
  mv -f "$NGINX_CONF.rathole-orig.bak" "$NGINX_CONF"
else
  if [ -f "$NGINX_CONF" ] && grep -q 'tvlid khodkar tvst ratholectl' "$NGINX_CONF" 2>/dev/null; then
    warn "backup peyda nshd; config tvlidi rathole hazf mishavad: $NGINX_CONF"
    ask_yn "hazf shvd?" && rm -f "$NGINX_CONF"
  else
    warn "config nginx ($NGINX_CONF) dstnkhvrdh baghi mimanad (backup naboodan ya file karbar ast)."
  fi
fi

# backup pvshhai tdakhlha (rathole-backup-*) ra atlaa bdh
shopt -s nullglob
for d in /etc/nginx/rathole-backup-*; do
  warn "backup kanfighai mtdakhl ghabli hnvz ainjast: $d (dar soorat niaz dasti brgrdan)."
done
shopt -u nullglob

# map erteghaye websocket ra fght agar chiz digari astfadhash nemikonad hazf kon
if [ -f /etc/nginx/conf.d/rathole-upgrade-map.conf ]; then
  if ask_yn "file map erteghaye websocket hazf shvd? (agar service digari az \$connection_upgrade estefade miknd, nghdar)"; then
    rm -f /etc/nginx/conf.d/rathole-upgrade-map.conf
  fi
fi

# tst va reload nginx
if command -v nginx >/dev/null 2>&1; then
  if nginx -t 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
    log "nginx reload shod."
  else
    err "nginx -t baad az hazf khata dad; dasti barresi kon."
  fi
fi

# ---------- hazf state va rathole config ----------
log "hazf server.toml va state..."
rm -f /etc/rathole/server.toml
if ask_yn "pvshh state mdir (/etc/rathole-manager) ham hazf shvd? (shaml list nodeha va tokenha)"; then
  rm -rf /etc/rathole-manager
fi

# ---------- hazf abzar ----------
rm -f /usr/local/bin/ratholectl
log "ratholectl hazf shod."
# common.sh-e eshteraki (agar node/hub-e digari rooye hamin server nist, hazf kon)
if [ -f /usr/local/share/rathole/common.sh ] \
   && [ ! -f /etc/systemd/system/rathole-client.service ] \
   && [ ! -f /opt/ratholehub/hub.py ]; then
  rm -f /usr/local/share/rathole/common.sh
  rmdir /usr/local/share/rathole 2>/dev/null || true
  log "common.sh hazf shod."
fi
# config-e stream/SNI (game mode) agar sakhte shode bood
rm -f /etc/nginx/stream.d/rathole-stream.conf 2>/dev/null || true

# ---------- purge ekhtiari ----------
if [ "$PURGE" -eq 1 ]; then
  warn "purge faal ast."
  if ask_yn "bainri /usr/local/bin/rathole hazf shvd?"; then rm -f /usr/local/bin/rathole; fi
  if [ -d /etc/rathole ] && [ -z "$(ls -A /etc/rathole 2>/dev/null)" ]; then rmdir /etc/rathole; fi
  warn "bsthhai nginx/jq/certbot amdan hazf nshdnd (mmkn ast servicehaye digar estefade knnd)."
fi

echo
log "hazf samt panel kamel shod."
warn "agar gvahi Let's Encrypt digar lazem nist, dasti ba 'certbot delete' paksh kon."
