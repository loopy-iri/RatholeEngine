#!/usr/bin/env bash
# install-panel.sh — nasab kamel va khodkar samt server Iran
# karha: nasb rathole + nginx + jq + certbot, nasb ratholectl, systemd,
#        shnasaii va backup kanfighai mtdakhl nginx rooye 443, va ejra-ye khodkar init.
# ejra: sudo bash install-panel.sh
set -euo pipefail

RATHOLE_VERSION="${RATHOLE_VERSION:-v0.5.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }
ask_yn(){ local p="$1" a; read -rp "$p [y/N]: " a; [[ "$a" =~ ^[Yy]$ ]]; }

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (sudo bash install-panel.sh)."

# ---------- memari ----------
case "$(uname -m)" in
  x86_64)  RH_ARCH="x86_64-unknown-linux-gnu" ;;
  aarch64) RH_ARCH="aarch64-unknown-linux-musl" ;;
  *) die "memari poshtibani-nashode: $(uname -m)" ;;
esac

# ---------- pish-niazha ----------
log "nasb pish-niazha (nginx, jq, curl, unzip, openssl, certbot, sshpass)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
# sshpass baraye provision-e khodkar-e node-ha az panel/hub (nasb-e kelid ba ramz) lazem ast.
apt-get install -y nginx jq curl unzip openssl ca-certificates certbot python3-certbot-nginx sshpass

# ---------- nasb rathole ----------
# esteratezhi (moshkel-e asli-ye Iran: GitHub filtr ast):
#   1) agar rathole az ghabl nasb ast → rad shv (magar darkhast-e beroozresani).
#   2) binary-e mahalli kenar-e script (rathole / bin/rathole / rathole-*.zip) → bedoon-e shabake.
#   3) download az GitHub va chand mirror (ghproxy/...) ba fallback.
#   4) agar hich → payam-e vazeh + kmk baraye nasb-e dasti (exit).
try_extract_bin(){
  # vorodi: masir-e file (binary-e straight ya zip). khrooji: nasb dar /usr/local/bin/rathole
  local f="$1" tmp; tmp="$(mktemp -d)"
  if head -c2 "$f" 2>/dev/null | grep -q "PK"; then
    unzip -o "$f" -d "$tmp" >/dev/null 2>&1 || { rm -rf "$tmp"; return 1; }
    local b; b="$(find "$tmp" -type f -name rathole -print -quit 2>/dev/null)"
    [ -n "$b" ] || { rm -rf "$tmp"; return 1; }
    install -m 755 "$b" /usr/local/bin/rathole
  else
    install -m 755 "$f" /usr/local/bin/rathole
  fi
  rm -rf "$tmp"
  # aatbarsnji: binary bayad ejra shavad (tashkhis-e nasazgari-ye memari/glibc)
  /usr/local/bin/rathole --version >/dev/null 2>&1
}

find_local_rathole(){
  local d f
  for d in "$SCRIPT_DIR" "$SCRIPT_DIR/bin" "$PWD"; do
    [ -x "$d/rathole" ] && { echo "$d/rathole"; return 0; }
    for f in "$d"/rathole-*.zip "$d"/rathole.zip; do
      [ -f "$f" ] && { echo "$f"; return 0; }
    done
  done
  return 1
}

install_rathole(){
  if command -v rathole >/dev/null 2>&1; then
    log "rathole az ghabl nasb ast: $(command -v rathole) ($(rathole --version 2>/dev/null || echo '?'))"
    ask_yn "dvbarh nasb/beroozresani shvd?" || return 0
  fi

  # (2) binary-e mahalli — behtarin rah baraye Iran (bedoon-e shabake)
  local lb
  if lb="$(find_local_rathole)"; then
    log "binary/baste-ye rathole-e mahalli peyda shod: $(c_y "$lb")"
    if try_extract_bin "$lb"; then
      log "rathole az mahal nasb shod: $(/usr/local/bin/rathole --version 2>/dev/null || echo ok)"
      return 0
    fi
    warn "nasb az file-e mahalli shekast khord (nasazgari?), soraghe download miravam."
  fi

  # (3) download ba fallback-e chand mirror
  log "download rathole ${RATHOLE_VERSION} (${RH_ARCH})..."
  local tmp gh urls u; tmp="$(mktemp -d)"
  gh="rapiz1/rathole/releases/download/${RATHOLE_VERSION}/rathole-${RH_ARCH}.zip"
  urls=(
    "https://github.com/${gh}"
    "https://ghproxy.net/https://github.com/${gh}"
    "https://gh-proxy.com/https://github.com/${gh}"
    "https://mirror.ghproxy.com/https://github.com/${gh}"
  )
  local ok=0
  for u in "${urls[@]}"; do
    log "talash: $u"
    if curl -fsSL --connect-timeout 20 --retry 2 "$u" -o "$tmp/rathole.zip" 2>/dev/null; then
      if try_extract_bin "$tmp/rathole.zip"; then ok=1; break; fi
    fi
    warn "in mnba javab nadad, mnba-ye badi..."
  done
  rm -rf "$tmp"

  if [ "$ok" -ne 1 ]; then
    err "download rathole az hameye mnaba shekast khord (ehtemal filtr/thrim az dakhl Iran)."
    err "rahhl-e dasti: binary ya zip-e rathole ra rooye server-e kharej begir va kenar-e in script bgzar:"
    err "   scp rathole-${RH_ARCH}.zip root@<iran-ip>:$SCRIPT_DIR/"
    err "sps dvbarh in askript ra ejra kon (khodkar peyda-sh mikonad)."
    exit 1
  fi
  log "rathole nasb shod: $(/usr/local/bin/rathole --version 2>/dev/null || echo ok)"
}
install_rathole


# ---------- dairktvriha va ratholectl ----------
mkdir -p /etc/rathole /etc/rathole-manager
[ -f "$SCRIPT_DIR/ratholectl" ] || die "ratholectl knar in askript peyda nashod."
install -m 755 "$SCRIPT_DIR/ratholectl" /usr/local/bin/ratholectl
[ -f "$SCRIPT_DIR/common.sh" ] && { install -m 644 "$SCRIPT_DIR/common.sh" /usr/local/share/rathole/common.sh; log "common.sh nasb shod."; }
log "ratholectl dar /usr/local/bin nasb shod."

# ---------- systemd ----------
log "nasb service systemd baraye rathole-server..."
cat > /etc/systemd/system/rathole-server.service <<'UNIT'
[Unit]
Description=rathole server (Iran panel)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/rathole /etc/rathole/server.toml
Restart=always
RestartSec=2
Environment=RUST_LOG=info
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload

# ---------- map erteghaye websocket (ikbar, http context) ----------
if [ ! -f /etc/nginx/conf.d/rathole-upgrade-map.conf ]; then
  log "nasb map erteghaye websocket..."
  cat > /etc/nginx/conf.d/rathole-upgrade-map.conf <<'MAP'
# lazem baraye WebSocket/HTTPUpgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAP
fi

# ---------- shnasaii va backup kanfighai mtdakhl nginx rooye 443 ----------
# argument 1: masir file config rathole ke bayad nadidh grfth shavad (haman faili ke riplis mikonim)
handle_conflicts(){
  local self="${1:-}"
  log "barresi tadakhol config nginx rooye port 443..."
  local found=() f
  while IFS= read -r f; do
    case "$(basename "$f")" in
      rathole.conf|rathole-upgrade-map.conf) continue ;;
    esac
    # file hdf ma (haman ke jaish config nvshtim) ra nadidh begir
    [ -n "$self" ] && [ "$f" = "$self" ] && continue
    found+=("$f")
  done < <(grep -rlE 'listen[[:space:]]+(\[::\]:)?443' \
            /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | sort -u)

  if [ "${#found[@]}" -eq 0 ]; then
    log "hich config mtdakhl digari rooye 443 nist."
    return 0
  fi

  warn "in filehaye digar ham rooye 443 listen darand va ba rathole tadakhol mikonand:"
  printf '    %s\n' "${found[@]}"
  warn "agar gheyre-faal nshvnd, nginx -t ba khtai duplicate bala nmiaid."
  if ask_yn "in fileha be pvshh backup mntghl shvnd?"; then
    local bdir="/etc/nginx/rathole-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$bdir"
    for f in "${found[@]}"; do
      mv "$f" "$bdir/"
      log "mntghl shod: $f → $bdir/"
    done
    warn "backup dar: $bdir (agar khrab shod brgrdan)."
  else
    warn "rad shod. khvdt bayad dasti tadakhol 443 ra hl kni vagarna reload shekast mikhvrd."
  fi
}

# sait pishfarz nginx rooye 80 maamoolan mzahm nist, vli default_server gahi hst
if [ -f /etc/nginx/sites-enabled/default ]; then
  warn "sait pishfarz nginx faal ast (/etc/nginx/sites-enabled/default)."
  ask_yn "gheyre-faal shvd?" && { rm -f /etc/nginx/sites-enabled/default; log "gheyre-faal shod."; }
fi

# ---------- ejra-ye init (flghai vrvdi hamin askript be init pas dade mishavand) ----------
log "nasb sthsistm tmam shod. hala tanzimat avlih (init)..."
if [ -f /etc/rathole-manager/state.json ]; then
  warn "state.json az ghabl vojood dard; az init rad mishvim. baraye taghir: ratholectl init ..."
else
  /usr/local/bin/ratholectl init "$@" || die "init shekast khord."
fi

# masir file nginx ke init tvlid/riplis krd ra az state bkhvan va az tadakhol mstsni kon
SELF_CONF="$(jq -r '.nginx_conf // "/etc/nginx/conf.d/rathole.conf"' /etc/rathole-manager/state.json 2>/dev/null)"
handle_conflicts "$SELF_CONF"

# tst va reload nhaii nginx
if nginx -t; then
  systemctl reload nginx || systemctl restart nginx
  log "nginx reload shod."
else
  err "nginx -t khata dad; tadakhol/gvahi ra barresi kon (bkapha dar /etc/nginx/rathole-backup-* va *.rathole-orig.bak)."
fi

# ---------- faalsazi service ----------
log "faalsazi va start rathole-server..."
# pish-shart: server.toml bayad vojood dashte bashad (init/regenerate an ra misazad)
if [ ! -f /etc/rathole/server.toml ]; then
  warn "server.toml peyda nashod; yekbar regenerate mikonam..."
  /usr/local/bin/ratholectl regen 2>/dev/null || true
fi
systemctl enable rathole-server >/dev/null 2>&1 || true
systemctl restart rathole-server 2>/dev/null || systemctl start rathole-server 2>/dev/null || true
sleep 1
if systemctl is-active --quiet rathole-server; then
  log "rathole-server faal shod va enable ast (start-e khodkar posht-e reboot)."
else
  err "rathole-server start nashod. tashkhis:"
  systemctl status rathole-server --no-pager -l 2>/dev/null | sed -n '1,8p' >&2 || true
  err "--- akharin log-ha ---"
  journalctl -u rathole-server --no-pager -n 15 2>/dev/null >&2 || true
  err "elat-e shayea: binary-e rathole nasazgar (memari/glibc) ya server.toml-e naghes."
  err "barresi: /usr/local/bin/rathole --version   va   cat /etc/rathole/server.toml"
fi

echo
log "nasb kamel shod!"

echo "gamhai badi:"
echo "  afzoodan node:   $(c_y 'sudo ratholectl add <name> <inbound_port> [--api-port <p>]')"
echo "  list nodeha:   $(c_y 'sudo ratholectl ls')"
echo "  mnvi kamel:    $(c_y 'sudo ratholectl menu')"
echo "  barresi slamt:  $(c_y 'sudo ratholectl doctor')"
