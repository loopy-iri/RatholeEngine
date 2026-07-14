#!/usr/bin/env bash
# package.sh — sakht baste-ye rathole-manager.zip bhsvrt dorost (forward-slash, LF)
# rooye linvks/mk ejra kon:  bash package.sh
# nokte: zip sakhthshdh ba Windows Compress-Archive az backslash estefade mikonad ke unzip
#       linvks drbarhash hoshdar midhd; in askript ba abzar zip dorost misazad.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]:-$0}")"

SRC="rathole-manager"
OUT="rathole-manager.zip"
[ -d "$SRC" ] || { echo "pvshh $SRC peyda nashod."; exit 1; }

# pvshh-ye mstndat (docs/) ham dar baste gonjande mishavad agar vojood dashte bashad.
DOCS="docs"
PACK=("$SRC")
[ -d "$DOCS" ] && PACK+=("$DOCS")

echo "[+] normal-sazi khate-payan (LF) rooye askriptha va mstndat..."
find "${PACK[@]}" -type f \( -name '*.sh' -o -name '*.md' -o -name 'common.sh' -o -name 'ratholectl' -o -name 'ratholenode' \) \
  -exec sed -i 's/\r$//' {} +
# ghabele-ejra kardan askriptha
for s in "$SRC"/*.sh "$SRC/ratholectl" "$SRC/ratholenode"; do [ -f "$s" ] && chmod +x "$s"; done

rm -f "$OUT"
if command -v zip >/dev/null 2>&1; then
  echo "[+] sakht $OUT ba zip (forward-slash)..."
  zip -r -q "$OUT" "${PACK[@]}"
else
  echo "[*] zip nasb nist; bhjai an tar.gz misazam (bootstrap har do ra mipzird)..."
  tar -czf "rathole-manager.tar.gz" "${PACK[@]}"
  echo "[+] sakhte shod: rathole-manager.tar.gz"
  exit 0
fi

# aatbarsnji: nbaid hich backslash dar namha bashad
if command -v unzip >/dev/null 2>&1; then
  if unzip -l "$OUT" | grep -q '\\'; then
    echo "[!] hoshdar: backslash dar namha peyda shod!"; exit 1
  fi
fi
echo "[+] sakhte shod: $OUT"
ls -lh "$OUT"
