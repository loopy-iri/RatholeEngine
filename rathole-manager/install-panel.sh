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

is_tty(){ [ -t 0 ] || [ -r /dev/tty ]; }
# porsesh-e amn zir-e curl|bash: az /dev/tty bekhan agar stdin tty nabashad
ask_tty(){ local p="$1" a; if [ -t 0 ]; then read -rp "$p" a; else read -rp "$p" a </dev/tty; fi; printf '%s' "$a"; }

# ---------- halat-e nasb: takmil (resume) ya az-no (fresh) ----------
# flaghaye --fresh/--repair az argumenthaye init joda mishavand (baghi be `init` pass mishavad).
FRESH=0
INIT_ARGS=()
for a in "$@"; do
  case "$a" in
    --fresh|--reinstall|--scratch|--from-scratch) FRESH=1 ;;
    --repair|--resume|--complete)                 FRESH=0 ;;
    *) INIT_ARGS+=("$a") ;;
  esac
done

# asari az nasb-e ghabli (kamel ya naghes) hast?
detect_partial(){
  [ -x /usr/local/bin/rathole ] \
    || [ -x /usr/local/bin/ratholectl ] \
    || [ -f /etc/rathole-manager/state.json ] \
    || [ -f /etc/systemd/system/rathole-server.service ] \
    || [ -f /etc/nginx/conf.d/rathole.conf ]
}

# gozaresh-e ajza-ye mojood/gomshode-ye nasb-e ghabli
report_state(){
  local ok="$(c_g '✓')" no="$(c_r '✗')"
  local mark
  [ -x /usr/local/bin/rathole ]                        && mark="$ok" || mark="$no"; echo "    $mark binary rathole"
  [ -x /usr/local/bin/ratholectl ]                     && mark="$ok" || mark="$no"; echo "    $mark ratholectl"
  [ -f /usr/local/share/rathole/common.sh ]            && mark="$ok" || mark="$no"; echo "    $mark common.sh"
  [ -f /etc/systemd/system/rathole-server.service ]    && mark="$ok" || mark="$no"; echo "    $mark systemd unit"
  [ -f /etc/rathole-manager/state.json ]               && mark="$ok" || mark="$no"; echo "    $mark state.json (init)"
  [ -f /etc/rathole/server.toml ]                      && mark="$ok" || mark="$no"; echo "    $mark server.toml"
  [ -f /etc/nginx/conf.d/rathole.conf ]                && mark="$ok" || mark="$no"; echo "    $mark nginx rathole.conf"
}

# pak-sazi-e vaziat-e ghabli (ba backup) baraye nasb-e az-no. binary/gvahi dast nemikhorad.
fresh_reset(){
  local ts bdir p; ts="$(date +%Y%m%d-%H%M%S)"
  bdir="/var/backups/rathole-manager/fresh-reset-$ts"
  mkdir -p "$bdir"
  warn "backup-e vaziat-e ghabli dar: $bdir (agar lazem shod bargardan)."
  systemctl stop rathole-server 2>/dev/null || true
  for p in /etc/rathole-manager/state.json \
           /etc/rathole/server.toml \
           /etc/nginx/conf.d/rathole.conf \
           /etc/nginx/conf.d/rathole-stream.conf; do
    if [ -e "$p" ]; then cp -a "$p" "$bdir/" 2>/dev/null || true; rm -f "$p"; fi
  done
  log "vaziat-e ghabli pak shod; hameye ajza az no sakhte mishavand (init-e mojadad)."
}

if detect_partial; then
  warn "asari az nasb-e ghabli/naghes peyda shod:"
  report_state
  if [ "$FRESH" -eq 1 ]; then
    warn "halat: nasb-e AZ-NO (--fresh) → pak-sazi va sakht-e mojadad."
    fresh_reset
  elif is_tty; then
    echo
    echo "  1) $(c_g 'TAKMIL') — ajza-ye gomshode ra kamel kon، vaziat-e mojood hefz shavad (tosiye)"
    echo "  2) $(c_y 'AZ-NO')  — pak-sazi-e config/state (ba backup) va nasb-e kamel az avval"
    ans="$(ask_tty 'entekhab [1/2] (pishfarz 1): ')"
    if [ "$ans" = "2" ]; then FRESH=1; fresh_reset
    else log "halat: TAKMIL — nasb-e naghes edame/takmil mishavad."; fi
  else
    # bedoon-e terminal (curl|bash): amn-tarin = takmil (bedoon-e pak-sazi)
    log "halat: TAKMIL-e khodkar (bedoon-e terminal). baraye nasb-e az-no: --fresh"
  fi
fi

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

# agar core/SHA256SUMS vojood darad (bundle-e patched-e 1.5.0), az core-install estefade kon
# vagarna install_rathole (download-e upstream) ra ejra kon.
if [ -f "$SCRIPT_DIR/core/SHA256SUMS" ] && [ -f "$SCRIPT_DIR/core-install.sh" ]; then
  log "core-install.sh peyda shod — nasb binary-e patched..."
  bash "$SCRIPT_DIR/core-install.sh" || {
    warn "core-install shekast khord; fallback be download-e upstream..."
    install_rathole
  }
else
  install_rathole
fi


# ---------- dairktvriha va ratholectl ----------
mkdir -p /etc/rathole /etc/rathole-manager /usr/local/share/rathole
[ -f "$SCRIPT_DIR/ratholectl" ] || die "ratholectl knar in askript peyda nashod."
install -m 755 "$SCRIPT_DIR/ratholectl" /usr/local/bin/ratholectl
[ -f "$SCRIPT_DIR/common.sh" ] && { mkdir -p /usr/local/share/rathole; install -m 644 "$SCRIPT_DIR/common.sh" /usr/local/share/rathole/common.sh; log "common.sh nasb shod."; }
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
  local found=() f bn
  # faghat file-hayi ke nginx vaghean include mikonad: conf.d/*.conf va sites-enabled/*
  # (file-haye .bak/.orig/.save/.disabled/~ tvst nginx load NEMISHAVAND — hoshdar-e ghalat nadeh)
  while IFS= read -r f; do
    bn="$(basename "$f")"
    case "$bn" in
      rathole.conf|rathole-upgrade-map.conf) continue ;;
      *.bak|*.orig|*.save|*.disabled|*.dpkg-*|*.rpmsave|*~) continue ;;
    esac
    # file hdf ma (haman ke jaish config nvshtim) ra nadidh begir
    [ -n "$self" ] && [ "$f" = "$self" ] && continue
    found+=("$f")
  done < <( { grep -lE 'listen[[:space:]]+(\[::\]:)?443' \
                /etc/nginx/conf.d/*.conf 2>/dev/null
              grep -lE 'listen[[:space:]]+(\[::\]:)?443' \
                /etc/nginx/sites-enabled/* 2>/dev/null; } | sort -u)

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
  /usr/local/bin/ratholectl init "${INIT_ARGS[@]}" || die "init shekast khord."
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
  err "rathole-server start nashod. tashkhis-e daghigh (ejra-ye mostaghim-e binary):"
  # rathole be stdout log mikonad; dar halat-e auto-restart journal khali/dir mimanad.
  # pas binary ra mostaghim ba timeout ejra mikonim ta khata-ye vaghei ra bebinim.
  systemctl stop rathole-server 2>/dev/null || true
  # pish-barresi: binary vojood darad va ejrapazir ast?
  if [ ! -x /usr/local/bin/rathole ]; then
    err "-> /usr/local/bin/rathole vojood nadarad ya ejrapazir nist."
    ls -l /usr/local/bin/rathole 2>&1 | sed 's/^/    /' >&2 || true
    chmod +x /usr/local/bin/rathole 2>/dev/null || true
  fi
  RTH_DIAG="$(RUST_LOG=info timeout 3 /usr/local/bin/rathole /etc/rathole/server.toml 2>&1 | head -20)"
  printf '%s\n' "$RTH_DIAG" | sed 's/^/    /' >&2
  # tashkhis-e ellat-haye shayea az rooye khorooji
  if printf '%s' "$RTH_DIAG" | grep -qi "Address already in use\|Failed to listen"; then
    RTH_CTRL="$(jq -r '.control_port // 2333' /etc/rathole-manager/state.json 2>/dev/null)"
    err "-> port-e kontrol ($RTH_CTRL) eshghal ast (ehtemalan yek instans-e rathole-ye ghadimi hanoz balast)."
    err "   barresi: ss -ltnp | grep :$RTH_CTRL    va    pkill -f '/usr/local/bin/rathole'"
    pkill -f '/usr/local/bin/rathole' 2>/dev/null || true; sleep 1
  elif printf '%s' "$RTH_DIAG" | grep -qi "No such file\|cannot\|Exec format\|not found\|GLIBC"; then
    err "-> binary-e rathole nasazgar ast (memari/glibc) ya server.toml peyda nashod."
    err "   barresi: /usr/local/bin/rathole --version   va   uname -m"
  elif printf '%s' "$RTH_DIAG" | grep -qi "Listening at\|Control channel"; then
    err "-> binary salem start shod va listen kard؛ moshkel az systemd/environment ya race bood (retry mikonim)."
  elif [ -z "$RTH_DIAG" ]; then
    err "-> binary hich khorooji nadad (ehtemalan bi-seda crash kard ya timeout). server.toml ra barresi kon:"
    err "   /usr/local/bin/rathole /etc/rathole/server.toml   (dasti ejra kon va khata ra bebin)"
  fi
  # yek talash-e dobare baad az tashkhis
  systemctl daemon-reload 2>/dev/null || true
  systemctl start rathole-server 2>/dev/null || true; sleep 1
  if systemctl is-active --quiet rathole-server; then
    log "rathole-server dar talash-e dovom faal shod."
  else
    err "hanoz start nashod. khorooji-ye vaghei-ye systemd:"
    systemctl --no-pager --full status rathole-server 2>&1 | head -12 | sed 's/^/    /' >&2 || true
    journalctl -u rathole-server -n 20 --no-pager 2>&1 | sed 's/^/    /' >&2 || true
    err "baad az raf-e moshkel: sudo systemctl restart rathole-server"
  fi
fi

echo
log "nasb kamel shod!"

echo "gamhai badi:"
echo "  afzoodan node:   $(c_y 'sudo ratholectl add <name> <inbound_port> [--api-port <p>]')"
echo "  list nodeha:   $(c_y 'sudo ratholectl ls')"
echo "  mnvi kamel:    $(c_y 'sudo ratholectl menu')"
echo "  barresi slamt:  $(c_y 'sudo ratholectl doctor')"
