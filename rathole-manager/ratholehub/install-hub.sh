#!/usr/bin/env bash
# install-hub.sh — nasb ratholehub rooye server mdirit (maamoolan haman rp01)
# panel rooye 127.0.0.1 mishnvd; amntrin dstrsi = SSH local-forward (bedoon baz kardan hich port).
# ejra:  sudo bash install-hub.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
die(){ printf '[!] %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "ba root ejra kon (sudo)."
command -v python3 >/dev/null 2>&1 || die "python3 lazem ast (apt install -y python3)."

APP_DIR=/opt/ratholehub
CONF_DIR=/etc/ratholehub
PORT="${HUB_PORT:-8088}"

BUNDLE_DIR="$APP_DIR/bundle"
mkdir -p "$APP_DIR" "$CONF_DIR" "$BUNDLE_DIR"
install -m755 "$SCRIPT_DIR/hub.py" "$APP_DIR/hub.py"
log "hub.py nasb shod: $APP_DIR/hub.py"

# astij kardan bainriha baraye ghablit deploy (apdit az rah dvr nodeha)
for f in ratholectl ratholenode common.sh update.sh kcptest-iran.sh kcptest-node.sh; do
  [ -f "$SCRIPT_DIR/../$f" ] && install -m755 "$SCRIPT_DIR/../$f" "$BUNDLE_DIR/$f"
done
log "bundle baraye deploy amade shod: $BUNDLE_DIR"

# tvlid config fght agar naboodan (ta token/ramz mojood pak nshvd)
if [ ! -f "$CONF_DIR/config.json" ]; then
  API_TOKEN="$(openssl rand -hex 24 2>/dev/null || head -c24 /dev/urandom | xxd -p | tr -d '\n')"
  read -rsp "ramz mdirit panel ra vared kon: " PW; echo
  [ -n "$PW" ] || die "ramz khali nemishavad."
  PWHASH="$(printf '%s' "$PW" | sha256sum | cut -d' ' -f1)"
  cat > "$CONF_DIR/config.json" <<EOF
{
  "api_token": "$API_TOKEN",
  "admin_password_sha256": "$PWHASH",
  "listen_host": "127.0.0.1",
  "listen_port": $PORT,
  "ssh_key_path": "/root/.ssh/id_ed25519",
  "ssh_opts": ["-o","BatchMode=yes","-o","ConnectTimeout=8","-o","StrictHostKeyChecking=accept-new"],
  "bundle_dir": "$BUNDLE_DIR"
}
EOF
  chmod 600 "$CONF_DIR/config.json"
  log "config sakhte shod: $CONF_DIR/config.json"
  echo "  $(c_y 'API TOKEN:') $API_TOKEN   (baraye atsal abzarhaye digar nghdar)"
else
  warn "config mojood ast; dst nkhvrd."
fi
[ -f "$CONF_DIR/inventory.json" ] || { echo "[]" > "$CONF_DIR/inventory.json"; chmod 600 "$CONF_DIR/inventory.json"; }

cat > /etc/systemd/system/ratholehub.service <<UNIT
[Unit]
Description=ratholehub web panel (REST API + UI)
After=network.target

[Service]
Type=simple
Environment=RATHOLEHUB_CONF=$CONF_DIR/config.json
Environment=RATHOLEHUB_INV=$CONF_DIR/inventory.json
ExecStart=/usr/bin/python3 $APP_DIR/hub.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now ratholehub
systemctl restart ratholehub

sleep 1
if systemctl is-active --quiet ratholehub; then
  log "ratholehub faal shod rooye 127.0.0.1:$PORT"
else
  die "ratholehub bala niamd; journalctl -u ratholehub -n 30"
fi

# ---------- kelid SSH baraye atsal hab be serverha ----------
KEY=/root/.ssh/id_ed25519
if [ ! -f "$KEY" ]; then
  mkdir -p /root/.ssh; chmod 700 /root/.ssh
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "ratholehub@$(hostname)" >/dev/null
  log "kelid SSH hab sakhte shod: $KEY"
else
  log "kelid SSH mojood estefade mishavad: $KEY"
fi
echo
echo "$(c_y '⚠ hab fght ba kelid SSH vsl mishavad (bedoon ramz). in kelid amvmi ra rooye har server authorize kon:')"
echo "───────────────────────────────────────────────"
cat "$KEY.pub"
echo "───────────────────────────────────────────────"
echo "$(c_y 'baraye har server ikbar ejra kon (rmze an server ra ikbar miporsad):')"
echo "  ssh-copy-id -i $KEY.pub -p 22 root@<server_ip>"
echo "  (ya dasti: mohtava-ye bala ra be /root/.ssh/authorized_keys an server ezafe kon)"
echo "baad az kpi, tst:  ssh -i $KEY root@<server_ip> 'ratholenode show || ratholectl ls'"

# ---------- ikparchgi khodkar ba nginx (agar hamin server panel Iran ast) ----------
if command -v ratholectl >/dev/null 2>&1 && [ -f /etc/rathole-manager/state.json ]; then
  if ratholectl hub on "$PORT" >/dev/null 2>&1; then
    DOMAIN="$(sed -n 's/.*"domain"[^"]*"\([^"]*\)".*/\1/p' /etc/rathole-manager/state.json | head -1)"
    log "panel khodkar psht nginx gharar grft: https://${DOMAIN:-<domain>}/hub/"
    warn "chvn panel hala amvmi ast, motmaen shv ramz ghvi gzashti."
  else
    warn "faalsazi khodkar nginx nshd; dasti: ratholectl hub on $PORT"
  fi
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "$(c_g '──────── dstrsi be panel ────────')"
echo "$(c_y 'rvsh amn (bedoon baz kardan port) — SSH local-forward az system khvdt:')"
echo "  ssh -L ${PORT}:127.0.0.1:${PORT} root@${IP:-<SERVER_IP>}"
echo "  sps mrvrgr:  http://localhost:${PORT}"
echo
echo "$(c_y 'ya psht nginx zir haman damnh (ekhtiari):') in blak ra dakhl server{} damnhat bgzar:"
cat <<NGINX
  location /hub/ {
      proxy_pass http://127.0.0.1:${PORT}/;
      proxy_set_header Host \$host;
      proxy_set_header X-Real-IP \$remote_addr;
  }
NGINX
echo "$(c_g '───────────────────────────────')"
echo "pish-niaz: az in server be baghie serverha SSH ba kelid st bashad (ssh-copy-id root@<node>)."
echo "SSH-agente service ndard; agar kelid ramz dard, dar config masir ssh_key_path bdh."
