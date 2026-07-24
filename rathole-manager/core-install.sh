#!/usr/bin/env bash
# core-install.sh — verify checksum va nasb-e binary-e rathole core (v1.5.0-ratholeengine.1)
# estefade: sudo bash core-install.sh [--verify-only]
# RATHOLE_CORE_DIR: masir-e core/ (default: kenar-e file)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RATHOLE_CORE_DIR="${RATHOLE_CORE_DIR:-$SCRIPT_DIR/core}"
REQUIRED_VERSION="${RATHOLE_ENGINE_VERSION:-0.5.1-ratholeengine.1}"
VERIFY_ONLY=0

log(){ printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }
die(){ err "$*"; exit 1; }

for a in "$@"; do
  case "$a" in
    --verify-only) VERIFY_ONLY=1;;
    --core-dir=*) RATHOLE_CORE_DIR="${a#*=}";;
    --version=*) REQUIRED_VERSION="${a#*=}";;
  esac
done

# architecture: x86_64 → x86_64-unknown-linux-gnu, aarch64 → aarch64-unknown-linux-gnu
case "$(uname -m)" in
  x86_64)  TARGET="x86_64-unknown-linux-gnu" ;;
  aarch64) TARGET="aarch64-unknown-linux-gnu" ;;
  *) die "memari poshtibani-nashode: $(uname -m)" ;;
esac

CORE_BIN="$RATHOLE_CORE_DIR/$TARGET/rathole"
SHA256_FILE="$RATHOLE_CORE_DIR/SHA256SUMS"

# ---- barresi vojood binary ----
[ -f "$CORE_BIN" ] || die "binary-e core peyda nashod: $CORE_BIN (avval core/build.sh ra ejra kon ya az release download kon)"
[ -f "$SHA256_FILE" ] || die "SHA256SUMS peyda nashod: $SHA256_FILE"

# ---- verify checksum ----
log "barresi checksum baraye $TARGET..."
( cd "$RATHOLE_CORE_DIR" && sha256sum -c SHA256SUMS --ignore-missing --quiet ) || \
  die "checksum-e binary motabar nist! binary-e dastkar-shode ya nashenas."

if [ "$VERIFY_ONLY" -eq 1 ]; then
  log "verify OK (--verify-only flag: nasb naShod)."
  exit 0
fi

# ---- ejra va barresi version ----
[ "$(id -u)" -eq 0 ] || die "nasb niyaz be root darad (sudo bash core-install.sh)."
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cp "$CORE_BIN" "$tmp"
chmod +x "$tmp"
actual_ver="$("$tmp" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+-[a-z0-9]+\.[0-9]+' | head -1 || echo '')"
if [ "$actual_ver" != "$REQUIRED_VERSION" ]; then
  die "version-e binary namotabar: got='$actual_ver', expected='$REQUIRED_VERSION' (binary eshari? rebuild lazem?)"
fi

# ---- nasb binary ----
install -m 0755 "$tmp" /usr/local/bin/rathole
log "rathole core nasb shod: $REQUIRED_VERSION → /usr/local/bin/rathole"
