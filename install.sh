#!/usr/bin/env bash
# install.sh — nasb-e tak-command az GitHub (curl | sudo bash)
#
# in file baraye ejra be sooratِ pipe tarahi shode:
#   curl -fsSL https://raw.githubusercontent.com/loopy-iri/RatholeEngine/main/install.sh | sudo bash -s -- --panel \
#        --domain panel.example.ir --fullchain /root/cert/.../fullchain.pem --key /root/cert/.../privkey.pem
#   curl -fsSL https://raw.githubusercontent.com/loopy-iri/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \
#        --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087
#   curl -fsSL https://raw.githubusercontent.com/loopy-iri/RatholeEngine/main/install.sh | sudo bash -s -- --update
#   curl -fsSL https://raw.githubusercontent.com/loopy-iri/RatholeEngine/main/install.sh | sudo bash -s -- --rollback
#
# repo slug pishfarz loopy-iri/RatholeEngine ast؛ baraye estefade az fork-e khodet ba mtghir-e mohiti
# override kon:   RATHOLE_GH="youruser/yourrepo" curl -fsSL .../install.sh | sudo bash -s -- ...
set -euo pipefail

# ---------- tanzimat ----------
GH="${RATHOLE_GH:-loopy-iri/RatholeEngine}"    # owner/repo — pishfarz، ba RATHOLE_GH override kon
REL="${RATHOLE_RELEASE:-latest}"               # latest ya yek tag mesl v1.0.0
BASE="https://github.com/${GH}/releases"
if [ "$REL" = "latest" ]; then DL="$BASE/latest/download"; else DL="$BASE/download/$REL"; fi

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (curl ... | sudo bash -s -- ...)."

# ---------- nasb-e pish-niaz-e hadaghali ----------
install_prereqs(){
  command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1 && return 0
  log "nasb pish-niazha (curl tar unzip ca-certificates)..."
  local pkgs="curl unzip tar ca-certificates"
  if command -v apt-get >/dev/null 2>&1; then export DEBIAN_FRONTEND=noninteractive; apt-get update -y && apt-get install -y $pkgs
  elif command -v dnf >/dev/null 2>&1; then dnf install -y $pkgs
  elif command -v yum >/dev/null 2>&1; then yum install -y $pkgs
  elif command -v pacman >/dev/null 2>&1; then pacman -Sy --noconfirm curl unzip tar ca-certificates
  elif command -v apk >/dev/null 2>&1; then apk add --no-cache curl unzip tar ca-certificates bash
  else warn "pkijmnijr shnakhth nshd; motmaen shv curl/unzip/tar nasb-and."; fi
}

fetch(){ # $1=url $2=out ; ba curl ya wget، ba fallback
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then curl -fSL --retry 3 --connect-timeout 20 "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then wget -q -O "$out" "$url"
  else return 1; fi
}

main(){
  install_prereqs
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  log "download az GitHub release: $(c_y "$GH ($REL)")"
  # 1) bootstrap.sh (mantegh-e amade-sazi va nasb)
  if ! fetch "$DL/bootstrap.sh" "$tmp/bootstrap.sh"; then
    err "download bootstrap.sh az release shekast khord: $DL/bootstrap.sh"
    err "elal-e ehtemali: release hanooz montasher nashode (tag v* push kon)، slug eshtebah، ya filtering."
    err "rah-e jaygozin: baste ra dasti begir va bootstrap.sh ra ba --local ejra kon (docs/README.fa.md)."
    exit 1
  fi
  # 2) baste-ye asli
  local bundle=""
  if fetch "$DL/rathole-manager.zip" "$tmp/rathole-manager.zip"; then
    bundle="$tmp/rathole-manager.zip"
  elif fetch "$DL/rathole-manager.tar.gz" "$tmp/rathole-manager.tar.gz"; then
    bundle="$tmp/rathole-manager.tar.gz"
  else
    die "download baste (rathole-manager.zip/.tar.gz) az release shekast khord: $DL"
  fi
  log "baste daryaft shod: $(basename "$bundle")  ($(du -h "$bundle" 2>/dev/null | cut -f1))"

  # 3) tahvil be bootstrap.sh (hameye argvman-haye passed be bootstrap miravand)
  log "ejra-ye bootstrap..."
  exec bash "$tmp/bootstrap.sh" --local "$bundle" "$@"
}

main "$@"
