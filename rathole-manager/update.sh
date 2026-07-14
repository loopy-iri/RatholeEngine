#!/usr/bin/env bash
# update.sh — beroozresani-e amn ba snapshot + health-check + rollback (panel ya node ya hub)
# az dakhl-e pvshhi baste ejra kon:
#   panel:  sudo bash update.sh [--domain ... --fullchain ... --key ... --fake-port ...]
#   node:   sudo bash update.sh           (az node.env mojood estefade mikonad)
# ghabl az har taghir yek snapshot-e kamel (CLI + config + units) migirad; baad-e update
# health-check mizanad va agar kharab bood KHODKAR be snapshot barmigardad.
#
# rollback/backup dasti:
#   sudo bash update.sh --list-backups            # list-e snapshot-ha
#   sudo bash update.sh --rollback                # bazgasht be akharin snapshot
#   sudo bash update.sh --rollback <timestamp>    # bazgasht be snapshot-e moshakhas
#   sudo bash update.sh --no-rollback [...]       # update kon vali khodkar barnagardan (faghat snapshot begir)
#
# agar state/config mojood bashad fght regenerate miknd; agar init anjam nshdh, init ra ejra mikonad.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "$PWD")"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (sudo)."

# ---------- config ----------
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/rathole-manager}"
RETENTION="${RATHOLE_BACKUP_RETENTION:-7}"     # tedad snapshot-e negahdari-shode
AUTO_ROLLBACK=1                                 # ba --no-rollback khamoosh mishavad

# ---------- pars-e argvman (flag-haye ma jda az flag-haye init) ----------
DO_ROLLBACK=0; ROLLBACK_TS=""; DO_LIST=0
PASS_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --rollback)      DO_ROLLBACK=1; shift
                     # timestamp-e ekhtiari (agar badi ba -- shoroo nashavad)
                     if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then ROLLBACK_TS="$1"; shift; fi ;;
    --list-backups)  DO_LIST=1; shift ;;
    --no-rollback)   AUTO_ROLLBACK=0; shift ;;
    *)               PASS_ARGS+=("$1"); shift ;;
  esac
done
set -- "${PASS_ARGS[@]:-}"
# agar hich PASS_ARG naboode, "$@" yek reshte-ye khali darad; paksazi
[ "$#" -eq 1 ] && [ -z "${1:-}" ] && shift || true

# ---------- tashkhis-e naghsh(-ha) ----------
detect_roles(){
  PANEL=0; NODE=0; HUB=0
  { [ -d /etc/rathole-manager ] || [ -f /etc/systemd/system/rathole-server.service ]; } && PANEL=1
  { [ -f /etc/rathole/node.env ] || [ -f /etc/systemd/system/rathole-client.service ]; } && NODE=1
  { [ -f /opt/ratholehub/hub.py ] || [ -f /etc/systemd/system/ratholehub.service ]; } && HUB=1
  return 0   # MOHEM: bدون in، agar akharin test false bashad (mesl-e server-e bدون-hub) tabe ba rc=1
             # barmigardad va zir-e `set -e` kolle update.sh bی-seda exit mishavad.
}

# ---------- masir-haye har naghsh baraye snapshot (faghat mojood-ha chap mishavand) ----------
_units_glob(){ # $@ = pattern-ha; unit-haye mojood ra chap kon
  local p f
  for p in "$@"; do
    for f in /etc/systemd/system/$p; do [ -e "$f" ] && echo "$f"; done
  done
}

snapshot_paths(){ # naghsh-ha ra migirad, masir-haye mojood ra (yekta) chap mikonad
  local role
  {
    for role in "$@"; do
      case "$role" in
        panel)
          echo /usr/local/bin/ratholectl
          echo /usr/local/share/rathole/common.sh
          echo /etc/rathole-manager
          echo /etc/rathole
          # file-e nginx az state (agar jq bashad) + config-haye sabet
          if command -v jq >/dev/null 2>&1 && [ -f /etc/rathole-manager/state.json ]; then
            jq -r '.nginx_conf // "/etc/nginx/conf.d/rathole.conf"' /etc/rathole-manager/state.json 2>/dev/null
          fi
          echo /etc/nginx/conf.d/rathole.conf
          echo /etc/nginx/conf.d/rathole-upgrade-map.conf
          echo /etc/nginx/stream.d/rathole-stream.conf
          _units_glob 'rathole-server.service' 'rathole-noise.service' 'rathole-kcp-server.service' 'rathole-panel-fakeweb.service'
          ;;
        node)
          echo /usr/local/bin/ratholenode
          echo /usr/local/share/rathole/common.sh
          echo /etc/rathole
          _units_glob 'rathole-client.service' 'rathole-client@*.service' 'rathole-kcp-client.service' 'rathole-kcp-up-*.service'
          ;;
        hub)
          echo /opt/ratholehub
          echo /etc/ratholehub
          _units_glob 'ratholehub.service'
          ;;
      esac
    done
  } | while IFS= read -r p; do [ -n "$p" ] && [ -e "$p" ] && echo "$p"; done | sort -u
}

# ---------- gereftan-e snapshot ghabl az update ----------
snapshot_now(){ # $@ = naghsh-ha ; khorooji: masir-e snapshot dir (rooye stdout khat-e akhar)
  local roles="$*" ts dir paths
  ts="$(date +%Y%m%d-%H%M%S)"
  dir="$BACKUP_ROOT/pre-update-$ts"
  mkdir -p "$dir"
  # list-e masir-haye mojood
  mapfile -t paths < <(snapshot_paths "$@")
  if [ "${#paths[@]}" -eq 0 ]; then
    warn "hich file-e ghabel-e backup peyda nashod (nasb-e naghes?)." >&2
    rmdir "$dir" 2>/dev/null || true
    echo ""; return 0
  fi
  # manifest
  {
    echo "timestamp=$ts"
    echo "roles=$roles"
    echo "rathole_version=$(rathole --version 2>/dev/null | head -n1 || echo '?')"
    [ -f /usr/local/bin/ratholectl ]  && echo "ratholectl_sha=$(sha256sum /usr/local/bin/ratholectl 2>/dev/null | cut -d' ' -f1)"
    [ -f /usr/local/bin/ratholenode ] && echo "ratholenode_sha=$(sha256sum /usr/local/bin/ratholenode 2>/dev/null | cut -d' ' -f1)"
    [ -f /opt/ratholehub/hub.py ]     && echo "hub_sha=$(sha256sum /opt/ratholehub/hub.py 2>/dev/null | cut -d' ' -f1)"
    echo "files:"
    printf '%s\n' "${paths[@]}"
  } > "$dir/manifest.txt"
  # tar ba masir-haye motlagh (strip-e / -e ebtedaii) — restore ba tar -xzf ... -C /
  local rels=(); local p
  for p in "${paths[@]}"; do rels+=("${p#/}"); done
  tar -czf "$dir/backup.tar.gz" -C / "${rels[@]}" 2>/dev/null || {
    warn "sakht-e tar-e backup ba khata (edame midahim vali rollback mumken ast naghes bashad)." >&2
  }
  log "snapshot gereftه shod: $dir  (${#paths[@]} file/pvshh)" >&2
  # retention: faghat akharin RETENTION ta ra negah dar
  prune_snapshots
  echo "$dir"
}

prune_snapshots(){
  [ -d "$BACKUP_ROOT" ] || return 0
  local olds
  mapfile -t olds < <(ls -1dt "$BACKUP_ROOT"/pre-update-* 2>/dev/null | tail -n +"$((RETENTION+1))")
  local d
  for d in "${olds[@]:-}"; do [ -n "$d" ] && [ -d "$d" ] && { rm -rf "$d"; log "snapshot-e ghadimi hazf shod: $(basename "$d")" >&2; }; done
}

latest_snapshot(){ ls -1dt "$BACKUP_ROOT"/pre-update-* 2>/dev/null | head -n1; }

# ---------- list-e backup-ha ----------
list_backups(){
  [ -d "$BACKUP_ROOT" ] || { echo "hich snapshot-i nist ($BACKUP_ROOT)."; return 0; }
  local d found=0 dirs
  printf '%-22s %-16s %s\n' "SNAPSHOT" "ROLES" "RATHOLE"
  printf '%s\n' "----------------------------------------------------------------"
  # nam-e pre-update-<YYYYmmdd-HHMMSS> lexically = chronological → glob + sort -r (newest aval)
  mapfile -t dirs < <(printf '%s\n' "$BACKUP_ROOT"/pre-update-* | sort -r)
  for d in "${dirs[@]}"; do
    [ -d "$d" ] || continue     # glob-e bedoon-e tatbigh ra rad kon
    found=1
    local ts roles rv
    ts="$(basename "$d" | sed 's/^pre-update-//')"
    roles="$(sed -n 's/^roles=//p' "$d/manifest.txt" 2>/dev/null)"
    rv="$(sed -n 's/^rathole_version=//p' "$d/manifest.txt" 2>/dev/null)"
    printf '%-22s %-16s %s\n' "$ts" "${roles:-?}" "${rv:-?}"
  done
  [ "$found" -eq 1 ] || echo "(khali)"
}

# ---------- health-check baraye har naghsh ----------
health_check(){ # $@ = naghsh-ha ; return 0 = salem, 1 = kharab
  local role bad=0
  for role in "$@"; do
    case "$role" in
      panel)
        systemctl is-active --quiet rathole-server || { err "health: rathole-server faal nist."; bad=1; }
        if command -v nginx >/dev/null 2>&1; then
          nginx -t >/dev/null 2>&1 || { err "health: nginx -t khata dad."; bad=1; }
          systemctl is-active --quiet nginx || { err "health: nginx faal nist."; bad=1; }
        fi ;;
      node)
        systemctl is-active --quiet rathole-client || { err "health: rathole-client faal nist."; bad=1; } ;;
      hub)
        systemctl is-active --quiet ratholehub || { err "health: ratholehub faal nist."; bad=1; } ;;
    esac
  done
  return "$bad"
}

# ---------- restart-e service-haye har naghsh (baad az rollback) ----------
restart_services(){
  local role
  for role in "$@"; do
    case "$role" in
      panel) systemctl restart rathole-server 2>/dev/null || true
             systemctl list-unit-files 2>/dev/null | grep -q '^rathole-noise\.service' && systemctl restart rathole-noise 2>/dev/null || true
             command -v nginx >/dev/null 2>&1 && { nginx -t >/dev/null 2>&1 && { systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true; }; } ;;
      node) systemctl restart rathole-client 2>/dev/null || true ;;
      hub)  systemctl restart ratholehub 2>/dev/null || true ;;
    esac
  done
}

# ---------- rollback be yek snapshot ----------
rollback_to(){ # $1 = masir-e snapshot dir
  local dir="$1"
  [ -n "$dir" ] && [ -d "$dir" ] || die "snapshot peyda nashod: $dir"
  [ -f "$dir/backup.tar.gz" ] || die "file-e backup.tar.gz dar snapshot nist: $dir"
  local roles; roles="$(sed -n 's/^roles=//p' "$dir/manifest.txt" 2>/dev/null)"
  warn "rollback be snapshot: $(basename "$dir")  (roles: ${roles:-?})"
  tar -xzf "$dir/backup.tar.gz" -C / || die "estekhraj-e backup shekast khord."
  systemctl daemon-reload 2>/dev/null || true
  # shellcheck disable=SC2086
  restart_services ${roles:-}
  sleep 1
  # shellcheck disable=SC2086
  if health_check ${roles:-}; then
    log "rollback movafagh bood; system be halat-e ghabli bargasht."
    return 0
  else
    err "rollback anjam shod vali health hanooz kharab ast; dasti barresi kon: journalctl -u rathole-server|rathole-client|ratholehub -n 30"
    return 1
  fi
}

# ---------- 2) mantegh-e update (mesl-e ghabl, dakhl-e tabe) ----------
apply_update(){
  # beroozresani abzarhaye CLI
  local t
  for t in ratholectl ratholenode; do
    if [ -f "$SCRIPT_DIR/$t" ]; then
      sed -i 's/\r$//' "$SCRIPT_DIR/$t"
      install -m 755 "$SCRIPT_DIR/$t" "/usr/local/bin/$t"
      log "beroozresani shod: /usr/local/bin/$t"
    fi
  done
  # common.sh (agar dar baste bashad)
  if [ -f "$SCRIPT_DIR/common.sh" ]; then
    mkdir -p /usr/local/share/rathole
    sed -i 's/\r$//' "$SCRIPT_DIR/common.sh"
    install -m 644 "$SCRIPT_DIR/common.sh" /usr/local/share/rathole/common.sh
  fi

  # --- samt panel ---
  if [ "$PANEL" -eq 1 ]; then
    log "context: panel (server Iran)"
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

    if [ ! -f /etc/nginx/conf.d/rathole-upgrade-map.conf ] && [ -d /etc/nginx/conf.d ]; then
      cat > /etc/nginx/conf.d/rathole-upgrade-map.conf <<'MAP'
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAP
      log "map erteghaye websocket nasb shod."
    fi

    mkdir -p /etc/rathole /etc/rathole-manager
    if [ -f /etc/rathole-manager/state.json ]; then
      log "state mojood ast → baztolid configha (regen)..."
      ratholectl regen
    else
      warn "nasb naghes bood (state sakhte nashode) → ejra-ye init..."
      ratholectl init "$@"
    fi
    systemctl enable --now rathole-server 2>/dev/null && log "rathole-server faal shod." || \
      warn "rathole-server start nshd; journalctl -u rathole-server ra bebin."
  fi

  # --- samt node ---
  if [ "$NODE" -eq 1 ]; then
    log "context: node (server kharej)"
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
    if [ -f /etc/rathole/node.env ]; then
      log "baztolid client.toml va restart (ratholenode apply)..."
      systemctl enable rathole-client >/dev/null 2>&1 || true
      ratholenode apply || warn "apply ba hoshdar hamrah bood."
    fi
  fi

  # --- samt hub ---
  if [ "$HUB" -eq 1 ]; then
    log "context: ratholehub (web panel)"
    local HUB_SRC="" c
    for c in "$SCRIPT_DIR/ratholehub/hub.py" "$SCRIPT_DIR/hub.py"; do
      [ -f "$c" ] && { HUB_SRC="$c"; break; }
    done
    if [ -n "$HUB_SRC" ]; then
      sed -i 's/\r$//' "$HUB_SRC"
      install -m 755 "$HUB_SRC" /opt/ratholehub/hub.py
      log "beroozresani shod: /opt/ratholehub/hub.py"
      mkdir -p /opt/ratholehub/bundle
      local f
      for f in ratholectl ratholenode common.sh update.sh kcptest-iran.sh kcptest-node.sh; do
        [ -f "$SCRIPT_DIR/$f" ] && install -m 755 "$SCRIPT_DIR/$f" "/opt/ratholehub/bundle/$f"
      done
      systemctl daemon-reload 2>/dev/null || true
      systemctl restart ratholehub 2>/dev/null && log "ratholehub restart shod." || \
        warn "restart ratholehub nshd; journalctl -u ratholehub ra bebin."
    else
      warn "hub.py dar baste peyda nashod (ratholehub/hub.py); update hub rad shod."
    fi
  fi
}

# ==================== jarian-e asli ====================

# --list-backups: faghat list bede va khárej shv
if [ "$DO_LIST" -eq 1 ]; then
  list_backups
  exit 0
fi

# --rollback: bazgasht-e dasti
if [ "$DO_ROLLBACK" -eq 1 ]; then
  detect_roles
  local_dir=""
  if [ -n "$ROLLBACK_TS" ]; then
    local_dir="$BACKUP_ROOT/pre-update-$ROLLBACK_TS"
    [ -d "$local_dir" ] || die "snapshot ba in timestamp nist: $ROLLBACK_TS  (list: sudo bash update.sh --list-backups)"
  else
    local_dir="$(latest_snapshot)"
    [ -n "$local_dir" ] || die "hich snapshot-i baraye rollback nist ($BACKUP_ROOT)."
  fi
  rollback_to "$local_dir"
  exit $?
fi

# ---- update-e adi ba snapshot + health + auto-rollback ----
detect_roles
ROLES=()
[ "$PANEL" -eq 1 ] && ROLES+=("panel")
[ "$NODE" -eq 1 ]  && ROLES+=("node")
[ "$HUB" -eq 1 ]   && ROLES+=("hub")

if [ "${#ROLES[@]}" -eq 0 ]; then
  warn "nh panel, nh node va nh hub tashkhis dade nashod. agar nasb avlih ast az install-panel.sh / install-node.sh / ratholehub/install-hub.sh estefade kon."
  # ham-chenan CLI ra beroozresani mikonim (bدون snapshot chون chizi nist)
  apply_update "$@"
  exit 0
fi

log "naghsh-haye tashkhis-dade-shode: ${ROLES[*]}"
SNAP_DIR="$(snapshot_now "${ROLES[@]}")"
[ -n "$SNAP_DIR" ] || warn "snapshot gerefte nashod؛ update bدون emkan-e rollback edame miyabad."

# اعمال آپدیت
apply_update "$@"

# health-check
echo
if health_check "${ROLES[@]}"; then
  log "health-check pas shod؛ update salem ast."
else
  err "health-check baad az update SHEKAST khord."
  if [ "$AUTO_ROLLBACK" -eq 1 ] && [ -n "$SNAP_DIR" ]; then
    warn "rollback-e khodkar be snapshot-e ghabl az update..."
    if rollback_to "$SNAP_DIR"; then
      die "update kharab bood va be halat-e ghabli bargardande shod. log-ha ra barresi kon va نسخه-ye baste ra check kon."
    else
      die "update kharab bود va rollback-e khodkar ham natoanest salem konad. dasti: sudo bash update.sh --rollback $(basename "$SNAP_DIR" | sed 's/^pre-update-//')"
    fi
  else
    warn "rollback-e khodkar khamoosh ast (ya snapshot naboud). baraye bazgasht: sudo bash update.sh --rollback"
  fi
fi

echo
log "beroozresani/takmil kamel shod."
[ "$PANEL" -eq 1 ] && echo "  barresi panel: $(c_y 'sudo ratholectl doctor')   va   $(c_y 'sudo ratholectl ls')"
[ "$NODE" -eq 1 ]  && echo "  barresi node:  $(c_y 'ratholenode ls')   va   $(c_y 'journalctl -u rathole-client -n 10 --no-pager')"
[ "$HUB" -eq 1 ]   && echo "  barresi hub:   $(c_y 'systemctl status ratholehub --no-pager')"
echo "  list-e backup-ha: $(c_y 'sudo bash update.sh --list-backups')   |   rollback: $(c_y 'sudo bash update.sh --rollback')"
