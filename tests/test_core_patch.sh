#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../core/upstream.env
source "$ROOT/core/upstream.env"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone -q "$RATHOLE_UPSTREAM_REPO" "$tmp/src"
git -C "$tmp/src" checkout -q "$RATHOLE_UPSTREAM_REV"
for patch in "$ROOT"/core/patches/*.patch; do
  git -C "$tmp/src" apply --check "$patch"
  git -C "$tmp/src" apply "$patch"
done

! grep -nF '.expect("failed to connect")' "$tmp/src/src/transport/websocket.rs"
grep -nF 'pub path: String' "$tmp/src/src/config.rs"
grep -nE 'config_lock_path|try_read_config' "$tmp/src/src/config_watcher.rs"
grep -qF 'static ref VERSION' "$tmp/src/src/cli.rs"
grep -qF 'env!("CARGO_PKG_VERSION")' "$tmp/src/src/cli.rs"
grep -qF "version = \"$RATHOLE_ENGINE_VERSION\"" "$tmp/src/Cargo.toml"

grep -qF 'cargo test --locked' "$ROOT/core/build.sh"
grep -qF 'cargo build --release --locked --target "$target"' "$ROOT/core/build.sh"
grep -qF 'rev-parse HEAD' "$ROOT/core/build.sh"
grep -qF '"$binary" --version' "$ROOT/core/build.sh"
grep -qF 'version_first=' "$ROOT/core/build.sh"

echo 'ok - contract-e patch-haye core bargharar ast'
