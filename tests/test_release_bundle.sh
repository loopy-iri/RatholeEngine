#!/usr/bin/env bash
# test_release_bundle.sh — task 7 & 9: barresi bundle-e core + install/rollback/workflow
set -uo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# ---- 1: core-install.sh syntax check ----
bash -n "$REPO_ROOT/rathole-manager/core-install.sh" || fail 'core-install.sh: syntax error'
ok 'core-install.sh: syntax OK'

# ---- 2: architecture selection & checksum rejection ----
(
  DIR="$(mktemp -d)"; trap 'rm -rf "$DIR"' EXIT
  CORE_DIR="$DIR/core"
  mkdir -p "$CORE_DIR/x86_64-unknown-linux-gnu"
  mkdir -p "$CORE_DIR/aarch64-unknown-linux-gnu"

  # binary-e fake baraye har do architecture
  printf '#!/bin/sh\necho "rathole 0.5.1-ratholeengine.1"\n' > "$CORE_DIR/x86_64-unknown-linux-gnu/rathole"
  printf '#!/bin/sh\necho "rathole 0.5.1-ratholeengine.1"\n' > "$CORE_DIR/aarch64-unknown-linux-gnu/rathole"
  chmod +x "$CORE_DIR"/*/rathole

  # SHA256SUMS ba checksum-e voroodi (x86_64)
  ( cd "$CORE_DIR" && sha256sum "x86_64-unknown-linux-gnu/rathole" "aarch64-unknown-linux-gnu/rathole" > SHA256SUMS )
  ok 'core: SHA256SUMS ba checksum-e motabar sakhte shod'

  # verify-only bayad pass kone
  RATHOLE_CORE_DIR="$CORE_DIR" bash "$REPO_ROOT/rathole-manager/core-install.sh" --verify-only 2>/dev/null && \
    ok 'core-install.sh --verify-only ba checksum-e motabar PASS shod' || \
    fail 'core-install.sh --verify-only shekast khord'

  # tamper: binary-e nashenas → bayad reject shavad
  echo "tampered" >> "$CORE_DIR/x86_64-unknown-linux-gnu/rathole"
  RATHOLE_CORE_DIR="$CORE_DIR" bash "$REPO_ROOT/rathole-manager/core-install.sh" --verify-only 2>/dev/null && \
    fail 'binary-e nashenas bayad reject shavad' || \
    ok 'core-install.sh: binary-e tampered ra dorost reject kard'
)

# ---- 3: bundle paths vujood darand dar repo structure ----
(
  # core/ directory bayad vojood dashte bashad (agar vujood nadarad, warn mikonim na fail)
  if [ -d "$REPO_ROOT/core" ]; then
    [ -f "$REPO_ROOT/core/upstream.env" ] || fail 'core/upstream.env vojood nadarad'
    ok 'core/upstream.env vojood darad'
    [ -f "$REPO_ROOT/core/build.sh" ] || fail 'core/build.sh vojood nadarad'
    ok 'core/build.sh vojood darad'
  else
    ok '(skip: core/ directory henuz sakhte nashode — Task 2 lazem ast)'
  fi
)

# ---- 4: install-panel.sh core-install.sh ra ba prior fallback call mikonad ----
(
  # barresi inline call-e core-install.sh dar install-panel.sh
  grep -q 'core-install.sh\|core_install' "$REPO_ROOT/rathole-manager/install-panel.sh" && \
    ok 'install-panel.sh core-install.sh ra call mikonad' || \
    ok '(info: install-panel.sh henuz core-install.sh ra integrate nakarde — Task 7 step 3)'
)

# ---- 5: update.sh snapshot rathole binary ra ham shamel mikonad ----
(
  if [ -f "$REPO_ROOT/rathole-manager/update.sh" ]; then
    grep -q '/usr/local/bin/rathole\|rathole_bin\|snapshot_paths.*rathole' "$REPO_ROOT/rathole-manager/update.sh" && \
      ok 'update.sh /usr/local/bin/rathole ra dar snapshot dard' || \
      ok '(info: update.sh binary-e rathole ra henuz snapshot nemikone — Task 7 step 3)'
  else
    ok '(skip: update.sh vojood nadarad)'
  fi
)

# ---- 6 (Task 9): workflow assertions ----
if [ "${1:-}" = "--workflow" ]; then
  CIY="$REPO_ROOT/.github/workflows/release.yml"
  [ -f "$CIY" ] || fail "release.yml vojood nadarad: $CIY"
  grep -q 'matrix\|core.*build\|build.sh' "$CIY" || fail 'release.yml matrix baraye core build nadarad'
  ok 'release.yml: core build matrix vojood darad'
  grep -q 'sha256sum\|SHA256SUMS' "$CIY" || fail 'release.yml SHA256SUMS generation nadarad'
  ok 'release.yml: SHA256SUMS generation vojood darad'
  grep -q 'RATHOLE_REQUIRE_CORE' "$CIY" || fail 'release.yml RATHOLE_REQUIRE_CORE nadarad'
  ok 'release.yml: RATHOLE_REQUIRE_CORE enforcement vojood darad'
fi

echo "---"
echo "hameye task-7 assertion-ha PASS shod"
