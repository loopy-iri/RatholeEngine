#!/usr/bin/env bash
# bootstrap.sh — amade-sazi mhit, thih baste (mahalli ya download), baz kardan va ejra-ye nasab
#
# agar baste (rathole-manager.zip / .tar.gz) knar askript ya dar masir jari bashd, download nemishavad.
# agar etelaat kafi ndhi, bhsvrt taamoli miporsad.
#
# nemoonehaye gheyre-taamoli:
#   sudo bash bootstrap.sh --panel --domain panel.example.ir \
#        --fullchain /root/cert/panel.example.ir/fullchain.pem --key /root/cert/panel.example.ir/privkey.pem
#   sudo bash bootstrap.sh --node -- --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087
#   sudo bash bootstrap.sh --url https://host/rathole-manager.zip --panel ...
#   sudo bash bootstrap.sh --local ./rathole-manager.zip --no-run
#   sudo bash bootstrap.sh --local ./rathole-manager.zip --update   # update kamel (khodkar panel/node/hub)
#
# taamoli: fght `sudo bash bootstrap.sh` va baghie ra miporsad (menu shamel gozine update ham hast).

set -euo pipefail

BUNDLE_URL="${BUNDLE_URL:-}"
LOCAL=""
INSTALL_DIR="${INSTALL_DIR:-/opt/rathole-manager}"
MODE=""
RUN=1
ASSUME_YES=0
ROLLBACK_TS=""
PASS_ARGS=()

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "$PWD")"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }
ask_yn(){ [ "$ASSUME_YES" -eq 1 ] && return 0; local a; read -rp "$1 [Y/n]: " a; [[ -z "$a" || "$a" =~ ^[Yy]$ ]]; }
is_tty(){ [ -t 0 ]; }

# ---------- pars argvmanha ----------
while [ $# -gt 0 ]; do
  case "$1" in
    --url)     BUNDLE_URL="$2"; shift 2;;
    --local)   LOCAL="$2"; shift 2;;
    --dir)     INSTALL_DIR="$2"; shift 2;;
    --panel)   MODE="panel"; shift;;
    --node)    MODE="node"; shift;;
    --update)  MODE="update"; shift;;
    --rollback) MODE="rollback"; shift
                if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then ROLLBACK_TS="$1"; shift; fi ;;
    --list-backups) MODE="listbackups"; shift;;
    --no-run)  RUN=0; shift;;

    --yes|-y)  ASSUME_YES=1; shift;;
    --)        shift; PASS_ARGS+=("$@"); break;;
    *)         PASS_ARGS+=("$1"); shift;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (sudo)."

# ---------- nasb pishniazhai paih ----------
install_prereqs(){
  local pkgs="curl unzip tar ca-certificates"
  log "amade-sazi mohit va nasb pish-niazha ($pkgs)..."
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive; apt-get update -y && apt-get install -y $pkgs
  elif command -v dnf >/dev/null 2>&1; then dnf install -y $pkgs
  elif command -v yum >/dev/null 2>&1; then yum install -y $pkgs
  elif command -v pacman >/dev/null 2>&1; then pacman -Sy --noconfirm curl unzip tar ca-certificates
  elif command -v apk >/dev/null 2>&1; then apk add --no-cache curl unzip tar ca-certificates bash
  else warn "pkijmnijr shnakhth nshd; motmaen shv curl/unzip/tar nasb-and."; fi
}

# ---------- peyda kardan baste-ye mahalli ----------
find_local_bundle(){
  local d f
  for d in "$SCRIPT_DIR" "$PWD"; do
    for f in rathole-manager.zip rathole-manager.tar.gz rathole-manager.tgz; do
      [ -f "$d/$f" ] && { echo "$d/$f"; return 0; }
    done
  done
  return 1
}

# ---------- peyda kardan update.sh-e mahalli (baraye rollback/list-backups bedoon download) ----------
find_update_sh(){
  local c
  for c in "$INSTALL_DIR/update.sh" "$SCRIPT_DIR/rathole-manager/update.sh" "$SCRIPT_DIR/update.sh"; do
    [ -f "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

# ---------- ejra-ye rollback/list-backups az tarigh-e update.sh ----------
exec_update_action(){ # $1 = masir update.sh
  local u="$1"
  case "$MODE" in
    listbackups) exec bash "$u" --list-backups ;;
    rollback)    if [ -n "$ROLLBACK_TS" ]; then exec bash "$u" --rollback "$ROLLBACK_TS"; else exec bash "$u" --rollback; fi ;;
  esac
}

# ---------- tashkhis mnba baste (mahalli ya download) ----------
SRC_FILE=""   # agar pr shvd, iani file mahalli darim va download lazem nist
resolve_source(){
  # 1) --local sarih
  if [ -n "$LOCAL" ]; then
    [ -f "$LOCAL" ] || die "file mahalli peyda nashod: $LOCAL"
    SRC_FILE="$LOCAL"; return
  fi
  # 2) --url ke dar vaghe masir/file mahalli ast
  if [ -n "$BUNDLE_URL" ]; then
    case "$BUNDLE_URL" in
      file://*) local f="${BUNDLE_URL#file://}"; [ -f "$f" ] && SRC_FILE="$f" ;;
      /*|./*|../*) [ -f "$BUNDLE_URL" ] && SRC_FILE="$BUNDLE_URL" ;;
    esac
    return   # agar SRC_FILE khali mand, iani URL rah dvr ast → download
  fi
  # 3) jostojoo-ye khodkar baste-ye mahalli
  local lb
  if lb="$(find_local_bundle)"; then
    log "baste-ye mahalli peyda shod: $(c_y "$lb")"
    if ask_yn "az hamin estefade shavad (bedoon download)?"; then SRC_FILE="$lb"; return; fi
  fi
  # 4) chizi nadarim → agar taamoli ast bprs, vagarna khata
  if is_tty; then
    local ans; read -rp "link baste (URL) ya masir file mahalli: " ans
    [ -n "$ans" ] || die "mnba baste dade nashod."
    if [ -f "$ans" ]; then SRC_FILE="$ans"; else BUNDLE_URL="$ans"; fi
  else
    die "baste-i peyda nashod va --url/--local ham dade nashode."
  fi
}

# ---------- download ----------
download(){
  local url="$1" out="$2"
  log "download baste az: $url"
  if command -v curl >/dev/null 2>&1; then curl -fSL --retry 3 --connect-timeout 20 "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then wget -O "$out" "$url"
  else return 1; fi
}

# ---------- baz kardan ----------
extract(){
  local file="$1" dest="$2"; mkdir -p "$dest"
  case "$file" in
    *.zip) command -v unzip >/dev/null 2>&1 || die "unzip nasb nist."; unzip -o "$file" -d "$dest" >/dev/null; fix_backslash_names "$dest" ;;
    *.tar.gz|*.tgz) tar -xzf "$file" -C "$dest" ;;
    *.tar) tar -xf "$file" -C "$dest" ;;
    *) if head -c 2 "$file" | grep -q "PK"; then unzip -o "$file" -d "$dest" >/dev/null; fix_backslash_names "$dest"
       else tar -xzf "$file" -C "$dest" 2>/dev/null || die "frmt file nashenakhte ast."; fi ;;
  esac
}

# aslah namhaii ke ba backslash zkhirh shdhand (zip sakhthshdh ba Windows Compress-Archive)
fix_backslash_names(){
  local dest="$1" f rel fixed
  while IFS= read -r -d '' f; do
    rel="${f#"$dest"/}"
    fixed="${rel//\\//}"
    [ "$rel" = "$fixed" ] && continue
    mkdir -p "$dest/$(dirname "$fixed")"
    mv -f "$f" "$dest/$fixed"
  done < <(find "$dest" -maxdepth 1 -type f -name '*\\*' -print0 2>/dev/null)
}

find_root(){
  local base="$1" f
  f="$(find "$base" -maxdepth 3 -name 'install-panel.sh' -print -quit 2>/dev/null)"
  [ -n "$f" ] && { dirname "$f"; return 0; }
  return 1
}

# ---------- entekhab halat va grftn etelaat (taamoli) ----------
choose_mode(){
  echo; echo "$(c_g 'halat nasb ra entekhab kon:')"
  echo "  1) panel (server Iran)"
  echo "  2) node (server kharej)"
  echo "  3) update (beroozresani kamel ba snapshot + rollback-e khodkar)"
  echo "  4) fght amade-sazi (bedoon ejra-ye nasab)"
  echo "  5) rollback (bazgasht be akharin snapshot-e ghabl az update)"
  echo "  6) list-e backup-ha (snapshot-haye mojood)"
  local m; read -rp "entekhab [1/2/3/4/5/6]: " m
  case "$m" in
    1) MODE="panel" ;;
    2) MODE="node" ;;
    3) MODE="update" ;;
    4) RUN=0 ;;
    5) MODE="rollback" ;;
    6) MODE="listbackups" ;;
    *) die "entekhab namotabar." ;;
  esac
}


prompt_node_args(){
  echo; log "etelaat node ra vared kon (az khorooji 'ratholectl add' rooye panel):"
  local server name token inbound atoken aib
  read -rp "adres server Iran (masalan panel.example.ir:443): " server
  read -rp "name node (masalan trk01): " name
  read -rp "token service: " token
  read -rp "port inbound Xray rooye node [2087]: " inbound; inbound="${inbound:-2087}"
  read -rp "token API (akhtiari, khali=rad): " atoken
  PASS_ARGS=(--server "$server" --name "$name" --token "$token" --inbound-port "$inbound")
  if [ -n "$atoken" ]; then
    read -rp "port inbound API node [62050]: " aib; aib="${aib:-62050}"
    PASS_ARGS+=(--api-token "$atoken" --api-inbound-port "$aib")
  fi
}

main(){
  # rollback/list-backups: agar update.sh-e mahalli hast, bedoon download ejra kon
  if [ "$MODE" = "rollback" ] || [ "$MODE" = "listbackups" ]; then
    local u; if u="$(find_update_sh)"; then exec_update_action "$u"; fi
    warn "update.sh-e mahalli peyda nashod؛ baste ra amade mikonam..."
  fi

  install_prereqs
  resolve_source

  local tmp; tmp="$(mktemp -d)"
  local bundle
  local pickname="${SRC_FILE:-$BUNDLE_URL}"
  case "$pickname" in
    *.tar.gz|*.tgz) bundle="$tmp/bundle.tar.gz" ;;
    *.tar)          bundle="$tmp/bundle.tar" ;;
    *)              bundle="$tmp/bundle.zip" ;;
  esac

  if [ -n "$SRC_FILE" ]; then
    log "estefade az baste-ye mahalli (bedoon download): $SRC_FILE"
    cp "$SRC_FILE" "$bundle"
  else
    download "$BUNDLE_URL" "$bundle" || die "download shekast khord (link/shbkh/filtr ra barresi kon)."
  fi
  log "hajm baste: $(du -h "$bundle" | cut -f1)"

  log "baz kardan baste..."
  extract "$bundle" "$tmp/x"
  local src; src="$(find_root "$tmp/x")" || die "askripthai nasb dar baste peyda nshdnd."
  log "mohtava-ye baste dar: $src"

  log "copy be $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"; cp -rf "$src/." "$INSTALL_DIR/"

  log "normal-sazi khate-payan va mojavez ejra..."
  local s
  for s in "$INSTALL_DIR"/*.sh "$INSTALL_DIR/ratholectl" "$INSTALL_DIR/ratholenode"; do
    [ -f "$s" ] || continue; sed -i 's/\r$//' "$s"; chmod +x "$s"
  done
  rm -rf "$tmp"
  log "baste amade shod dar: $INSTALL_DIR"

  # entekhab halat agar moshakhas nashode va taamoli hastim
  if [ -z "$MODE" ] && [ "$RUN" -eq 1 ]; then
    if is_tty; then choose_mode; else RUN=0; fi
  fi

  if [ "$RUN" -eq 0 ] || [ -z "$MODE" ]; then
    echo; log "amade-sazi kamel shod (bedoon ejra-ye nasab)."
    echo "  panel:  $(c_y "sudo bash $INSTALL_DIR/install-panel.sh --domain <d> --fullchain <fc> --key <key>")"
    echo "  node:  $(c_y "sudo bash $INSTALL_DIR/install-node.sh --server <d>:443 --name <n> --token <t> --inbound-port <p>")"
    exit 0
  fi

  case "$MODE" in
    rollback|listbackups)
      # baste amade shod (chون update.sh-e mahalli naboud); hala action ra ejra kon
      exec_update_action "$INSTALL_DIR/update.sh" ;;
    update)
      # update kamel: update.sh khodesh panel/node/hub ra tashkhis mide va hameye ejza ra berooz mikonad
      log "ejra-ye update kamel ba snapshot + rollback-e khodkar..."
      exec bash "$INSTALL_DIR/update.sh" "${PASS_ARGS[@]}" ;;
    panel)
      log "ejra-ye nasab panel (agar argument ndhi, khodesh bhsvrt taamoli miporsad)..."
      exec bash "$INSTALL_DIR/install-panel.sh" "${PASS_ARGS[@]}" ;;

    node)
      # agar argument node dade nashode va taamoli hstim, bprs
      if [ "${#PASS_ARGS[@]}" -eq 0 ] && is_tty; then prompt_node_args; fi
      [ "${#PASS_ARGS[@]}" -gt 0 ] || die "etelaat node lazem ast (--server --name --token --inbound-port)."
      log "ejra-ye nasab node..."
      exec bash "$INSTALL_DIR/install-node.sh" "${PASS_ARGS[@]}" ;;
  esac
}

main
