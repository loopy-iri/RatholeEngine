#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=upstream.env
source "$ROOT/core/upstream.env"

[ "$#" -eq 2 ] || {
  echo "usage: $0 <target> <output-dir>" >&2
  exit 2
}

target="$1"
output_dir="$2"
case " $RATHOLE_CORE_TARGETS " in
  *" $target "*) ;;
  *) echo "target-e core mojaz nist: $target" >&2; exit 2 ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone -q "$RATHOLE_UPSTREAM_REPO" "$tmp/src"
git -C "$tmp/src" checkout -q "$RATHOLE_UPSTREAM_REV"
actual_rev="$(git -C "$tmp/src" rev-parse HEAD)"
[ "$actual_rev" = "$RATHOLE_UPSTREAM_REV" ] || {
  echo "commit-e upstream motabegh nist" >&2
  exit 1
}

for patch in "$ROOT"/core/patches/*.patch; do
  git -C "$tmp/src" apply --check "$patch"
  git -C "$tmp/src" apply "$patch"
done

# Integration-e TLS-e upstream certificate-e expire-shode darad; unit/bin gate
# hame test-haye core va regression-haye patch ra bedoon hang ejra mikonad.
cargo test --locked --lib --bins --manifest-path "$tmp/src/Cargo.toml"
cargo build --release --locked --target "$target" --manifest-path "$tmp/src/Cargo.toml"

binary="$tmp/src/target/$target/release/rathole"
[ -x "$binary" ] || {
  echo "binary-e core sakhte nashod: $binary" >&2
  exit 1
}
version_output="$("$binary" --version)"
version_first="${version_output%%$'\n'*}"
if [ "$version_first" != "rathole $RATHOLE_ENGINE_VERSION" ] \
  || ! grep -qF "Build Version:       $RATHOLE_ENGINE_VERSION" <<<"$version_output"; then
  echo "version-e core motabegh nist: $version_output" >&2
  exit 1
fi

mkdir -p "$output_dir"
install -m 0755 "$binary" "$output_dir/rathole"
echo "ok - core $RATHOLE_ENGINE_VERSION baraye $target sakhte shod"
