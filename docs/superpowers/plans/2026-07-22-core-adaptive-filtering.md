# Core Hardening and Adaptive Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enteshar-e `v1.5.0` ba core-e patch-shode, config reload-e read-safe, control path-e anti-probe va adaptive failover-e ghabele roshan/khamosh bein WS/TLS va KCP.

**Architecture:** Source-e rathole ba commit-e sabet clone va ba patch-haye repo build mishavad; binary-ha va checksum dakhel bundle gharar migirand va update snapshot anha ra ham rollback mikonad. Manager state-ra regenerate mikonad, config ra zir-e sidecar lock in-place commit mikonad, va node ba probe-e WebSocket `101` salamat-e har carrier ra misanjad. Adaptive controller faghat carrier-e main ra avaz mikonad, hysteresis/cooldown darad, va plain ra bedoon ejaze entekhab nemikonad.

**Tech Stack:** Bash 4+, Python 3 stdlib, Rust/Cargo, systemd, nginx, jq, OpenSSL, GitHub Actions.

## Global Constraints

- TLS faghat dar nginx terminate mishavad; rathole server TLS nadarad.
- Path/name/token/inbound-e service-haye karbar taghir nemikonad.
- Bash CLI-ha `set -uo pipefail` ra hefz mikonand; installer/workflow-ha mitavanand `set -euo pipefail` bemanand.
- Comment va log-e jadid Finglish ast.
- Config-e live in-place neveshte mishavad ta inode hefz shavad; reader/writer az `${config}.lock` estefade mikonand.
- Core build az commit-e pin-shode ast va binary-e release bayad SHA-256-e motabar dashte bashad.
- Adaptive pishfarz khamoosh ast; plain pishfarz candidate nist.
- Hich token, control path, Noise key ya KCP key dar hub/log-e sanitize-shode chap nemishavad.
- Hame-ye shell/Markdown file-ha LF mimanand.

## File Map

- `core/upstream.env`: repo, commit, version va target-haye build-e core.
- `core/patches/0001-websocket-retry-path.patch`: error propagation va WebSocket path.
- `core/patches/0002-config-lock-debounce.patch`: config lock/debounce/retry.
- `core/build.sh`: clone, verify commit, apply patch, test va build.
- `rathole-manager/core-install.sh`: verify checksum, entekhab architecture va install-e binary.
- `rathole-manager/core/`: binary-ha va `SHA256SUMS` ke workflow ghabl az package por mikonad.
- `rathole-manager/common.sh`: version/build-id va helper-e config commit-e lock-shode.
- `rathole-manager/ratholectl`: control path state, nginx anti-probe va config writer.
- `rathole-manager/ratholenode`: control path client, probe-ha va adaptive controller.
- `rathole-manager/install-panel.sh`, `install-node.sh`, `update.sh`: core install/snapshot/rollback.
- `rathole-manager/ratholehub/hub.py`: argv allow-list, adaptive status/API/UI.
- `tests/`: harness-haye shell/Python va release audit.
- `.github/workflows/ci.yml`, `release.yml`: test-e patch/core va build/upload-e do architecture.
- `CHANGELOG.md`, `README.md`, `docs/*.md`: version, operation va troubleshooting.

---

### Task 1: Test Harness and Current-Bug Reproduction

**Files:**
- Create: `tests/test_node_config.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `rathole-manager/ratholenode`
- Test: `tests/test_node_config.sh`

**Interfaces:**
- Produces: executable shell tests with `ok()`/`fail()` and stdlib `tomllib` validation for empty and populated generated configs.
- Produces: `RATHOLENODE_LIB_ONLY=1` contract so CLI functions can be sourced without dispatch.
- Consumes: current `ratholenode`, `ratholectl`, `hub.py`, `package.sh`.

- [ ] **Step 1: Write the failing config-regression test**

Create a sandbox, source a library-only copy of `ratholenode`, override `ENV_FILE`, `SVC_FILE`, `CLIENT_TOML`, and assert both an empty services file and one valid service generate parseable structure:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
export RATHOLENODE_LIB_ONLY=1
source "${REPO_ROOT:?}/rathole-manager/ratholenode"
ENV_FILE="$ROOT/node.env"; SVC_FILE="$ROOT/services.conf"; CLIENT_TOML="$ROOT/client.toml"
printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
: > "$SVC_FILE"
gen_client
grep -qx '\[client.services\]' "$CLIENT_TOML" || { echo 'missing empty services table'; exit 1; }
printf 'n1|token123|2087\n' > "$SVC_FILE"
gen_client
grep -qx '\[client.services.n1\]' "$CLIENT_TOML"
```

- [ ] **Step 2: Run it and verify RED**

Run: `wsl bash -lc 'cd /mnt/d/MohammadHosein/projectsupertunnel && REPO_ROOT=$PWD bash tests/test_node_config.sh'`

Expected: FAIL because `RATHOLENODE_LIB_ONLY` is ignored and/or empty `[client.services]` is not generated.

- [ ] **Step 3: Add the library dispatch seam, empty table fix and CI call**

Wrap the current bottom-level case in this exact interface, without changing command mapping:

```bash
main(){
  case "${1:-show}" in
    # existing cases, unchanged
  esac
}
if [ "${RATHOLENODE_LIB_ONLY:-0}" != 1 ]; then main "$@"; fi
```

Track the number of valid emitted services in `gen_client`; when it is zero, emit the required empty table:

```bash
echo "[client.services]"
```

Add CI commands:

```yaml
- name: manager regression tests
  run: |
    bash tests/test_node_config.sh
```

- [ ] **Step 4: Run the focused tests**

Run: `wsl bash -lc 'cd /mnt/d/MohammadHosein/projectsupertunnel && REPO_ROOT=$PWD bash tests/test_node_config.sh'`

Expected: PASS with the empty services table and one-service config both covered.

- [ ] **Step 5: Commit the harness seam**

```bash
git add tests .github/workflows/ci.yml rathole-manager/ratholenode
git commit -m "fix(node): generate valid empty client services"
```

---

### Task 2: Reproducible Patched Rathole Core

**Files:**
- Create: `core/upstream.env`
- Create: `core/build.sh`
- Create: `core/patches/0001-websocket-retry-path.patch`
- Create: `core/patches/0002-config-lock-debounce.patch`
- Create: `tests/test_core_patch.sh`
- Modify: `.github/workflows/ci.yml`
- Test: upstream Rust tests plus `tests/test_core_patch.sh`

**Interfaces:**
- Produces: `core/build.sh <target> <output-dir>`.
- Produces: binary reporting `rathole 0.5.1-ratholeengine.1`.
- Produces: TOML interface `[client.transport.websocket] path = "/_rh/..."` with `/` default.
- Produces: `${config}.lock` shared-read protocol in the core watcher.

- [ ] **Step 1: Write the failing patch-contract test**

```bash
#!/usr/bin/env bash
set -euo pipefail
source core/upstream.env
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
git clone -q "$RATHOLE_UPSTREAM_REPO" "$tmp/src"
git -C "$tmp/src" checkout -q "$RATHOLE_UPSTREAM_REV"
for p in core/patches/*.patch; do git -C "$tmp/src" apply --check "$OLDPWD/$p"; git -C "$tmp/src" apply "$OLDPWD/$p"; done
! rg -n 'expect\("failed to connect"\)' "$tmp/src/src/transport/websocket.rs"
rg -n 'pub path: String' "$tmp/src/src/config.rs"
rg -n 'config_lock_path|try_read_config' "$tmp/src/src/config_watcher.rs"
```

- [ ] **Step 2: Run it and verify RED**

Run: `wsl bash tests/test_core_patch.sh`

Expected: FAIL because `upstream.env` and patches do not exist.

- [ ] **Step 3: Implement the first core patch**

Pin immutable source metadata:

```bash
RATHOLE_UPSTREAM_REPO=https://github.com/rathole-org/rathole.git
RATHOLE_UPSTREAM_REV=b55f7e50fe1b9dfbd0f3208258897a4eb5bfabe3
RATHOLE_ENGINE_VERSION=0.5.1-ratholeengine.1
```

Patch `WebsocketConfig` to contain a serde-defaulted `path`, validate that it starts with `/` and has no ASCII control character, construct `ws://host${path}`, and replace:

```rust
.await.expect("failed to connect")
```

with:

```rust
.await.context("websocket handshake failed")?
```

Add Rust tests that use `catch_unwind`/a closed listener to prove connection failure returns `Err`, and TOML tests for default, custom and invalid paths.

- [ ] **Step 4: Implement watcher lock/debounce**

Use a sidecar `${path}.lock`; read under shared lock and let a burst settle before parsing. The retry contract is bounded:

```rust
const CONFIG_READ_RETRIES: usize = 3;
const CONFIG_READ_RETRY_DELAY: Duration = Duration::from_millis(50);
```

The last invalid read is logged once and ignored. Add a Rust test with an exclusive writer lock that truncates, waits, writes valid TOML, and proves the reader never returns the empty snapshot.

- [ ] **Step 5: Implement the build script and run GREEN**

`core/build.sh` must clone into a temp directory, verify `HEAD == RATHOLE_UPSTREAM_REV`, apply all patches with `git apply --check`, run `cargo test --locked --lib --bins`, build `--release --locked --target "$target"`, verify `--version`, and copy only the binary to the output directory. The pinned upstream integration fixtures have expired TLS certificates and retry indefinitely after 2026, so they are excluded from the deterministic build gate; all upstream unit/bin tests and the added core regressions remain required.

Run: `wsl bash tests/test_core_patch.sh`

Expected: PASS.

Run: `wsl bash core/build.sh x86_64-unknown-linux-gnu /tmp/rathole-core-out`

Expected: Rust tests PASS and `/tmp/rathole-core-out/rathole` reports `0.5.1-ratholeengine.1`.

- [ ] **Step 6: Add CI patch verification and commit**

```yaml
- name: verify pinned core patches
  run: bash tests/test_core_patch.sh
```

```bash
git add core tests/test_core_patch.sh .github/workflows/ci.yml
git commit -m "fix(core): retry websocket failures without panic"
```

---

### Task 3: Read-Safe Config Generation

**Files:**
- Modify: `rathole-manager/common.sh`
- Modify: `rathole-manager/ratholectl`
- Modify: `rathole-manager/ratholenode`
- Modify: `tests/test_node_config.sh`
- Test: `tests/test_node_config.sh`, `rathole-manager/test-harness.sh`

**Interfaces:**
- Produces: `rth_commit_config <generated-file> <live-file>`.
- Consumes: core sidecar lock `${live-file}.lock`.

- [ ] **Step 1: Extend tests and verify RED**

Add assertions that `gen_client`, `gen_up_client`, `gen_server_toml`, and `gen_noise_server_toml` call the common writer; hold `${CLIENT_TOML}.lock` in another process and prove commit waits instead of exposing an empty file. Keep the Task 1 empty-services regression in the focused suite.

Run: `wsl bash tests/test_node_config.sh`

Expected: FAIL because direct `cat "$tmp" > "$live"` remains.

- [ ] **Step 2: Add the minimal writer**

```bash
rth_commit_config(){ # $1=generated $2=live
  local src="$1" dst="$2" lock="${2}.lock"
  [ -s "$src" ] || { err "config-e jadid khali ast: $src"; return 1; }
  mkdir -p "$(dirname "$dst")"
  (
    flock -x 9
    cat "$src" > "$dst"
  ) 9>"$lock" || return 1
  rm -f "$src"
}
```

Require `flock` through util-linux in installers. Replace all live TOML `cat` writes with this helper. Count valid services while generating client/upstream configs; emit the empty services table when count is zero.

- [ ] **Step 3: Run GREEN and existing panel harness**

Run: `wsl bash tests/test_node_config.sh`

Expected: PASS.

Run: `wsl bash rathole-manager/test-harness.sh`

Expected: PASS with no invalid empty-service config.

- [ ] **Step 4: Commit**

```bash
git add rathole-manager/common.sh rathole-manager/ratholectl rathole-manager/ratholenode tests/test_node_config.sh
git commit -m "fix(config): make hot reload reads consistent"
```

---

### Task 4: Secret WebSocket Control Path and Anti-Probe Routing

**Files:**
- Modify: `rathole-manager/ratholectl`
- Modify: `rathole-manager/ratholenode`
- Modify: `rathole-manager/install-node.sh`
- Modify: `rathole-manager/ratholehub/hub.py`
- Create: `tests/test_nginx_control_path.sh`
- Modify: `tests/test_node_config.sh`
- Test: nginx routing and client TOML tests

**Interfaces:**
- Produces: panel state `.control_path` and node env `WS_PATH`.
- Produces: `ratholectl control-path show|rotate`.
- Consumes: patched core `WebsocketConfig.path`.

- [ ] **Step 1: Write failing state/config/nginx tests**

Assert init/migration creates `/_rh/<32 lowercase hex>`, generated client TOML contains `path = "..."`, install commands carry `--ws-path`, and nginx sends only the exact secret Upgrade location to the control port. Assert `/`, an incorrect Upgrade path and `/<node>` retain fake/data behavior.

Run: `wsl bash tests/test_nginx_control_path.sh`

Expected: FAIL because all WebSocket Upgrade requests on `/` currently reach control.

- [ ] **Step 2: Implement state migration and client propagation**

Add:

```bash
ensure_control_path(){
  local p
  p="$(jq -r '.control_path // empty' "$STATE")"
  if [ -z "$p" ]; then
    p="/_rh/$(openssl rand -hex 16)"
    state_set '.control_path' "$p" str
  fi
  printf '%s\n' "$p"
}
```

Generate `path = "${WS_PATH:-/}"` for WS, plain and KCP client configs. Add validated `--ws-path` to fresh node installs and hub provisioning. `cmd_show` prints `WS_PATH=<masked>`.

- [ ] **Step 3: Implement exact nginx routing and rotation grace**

Generate dedicated locations for current and optional previous path:

```nginx
location = /_rh/<secret> {
    proxy_pass http://127.0.0.1:<control_port>;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
}
```

All other paths continue through the existing fake/data map. `control-path rotate` stores `.control_path_previous` plus expiry, regenerates both locations, and prints the node update command; a later regenerate removes the expired previous path.

- [ ] **Step 4: Run GREEN**

Run: `wsl bash tests/test_nginx_control_path.sh`

Expected: PASS.

Run: `wsl bash tests/test_node_config.sh`

Expected: PASS with custom path in TOML.

- [ ] **Step 5: Commit**

```bash
git add rathole-manager tests/test_nginx_control_path.sh tests/test_node_config.sh
git commit -m "feat(stealth): hide control websocket behind secret path"
```

---

### Task 5: Layered Filtering Detection

**Files:**
- Modify: `rathole-manager/ratholenode`
- Create: `tests/test_adaptive.sh`
- Test: `tests/test_adaptive.sh`

**Interfaces:**
- Produces: `adaptive_probe_dns`, `adaptive_probe_tcp`, `adaptive_probe_ws_tls`, `adaptive_probe_ws_plain`, `adaptive_probe_kcp`.
- Produces: `ratholenode adaptive test [--json]`.
- Produces: `/etc/rathole/adaptive-state.json` mode `0600` with sanitized fields.

- [ ] **Step 1: Write table-driven failing tests**

Stub `getent`, `timeout`, `openssl` and local sockets. Cover these exact classifications:

```text
dns_failed dns_mismatch tcp_timeout tls_failed ws_rejected ws_timeout kcp_unreachable healthy
```

Assert a valid raw WebSocket response beginning `HTTP/1.1 101` is healthy, while systemd `active` alone is not enough. Assert JSON contains `time`, `current`, `classification`, `latency_ms`, `consecutive_failures`, and never contains `WS_PATH`, token or key.

Run: `wsl bash tests/test_adaptive.sh`

Expected: FAIL because `adaptive` is not a command.

- [ ] **Step 2: Implement bounded probes**

Use a real RFC 6455 request:

```text
GET <WS_PATH> HTTP/1.1
Host: <SERVER_HOST>
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

For TLS use `openssl s_client -verify_return_error -verify_hostname "$host" -servername "$host"`; for KCP send the plain WS request to `KCP_LOCAL`. Each probe has a hard timeout and returns a reason code plus latency. DNS mismatch is informational until a carrier probe also fails.

- [ ] **Step 3: Implement sanitized state and CLI output**

Write JSON through a temp file with jq, chmod `0600`, then rename the state file because no live watcher consumes it. Human output is Finglish; `--json` emits the file verbatim.

- [ ] **Step 4: Run GREEN and commit**

Run: `wsl bash tests/test_adaptive.sh`

Expected: all classification cases PASS.

```bash
git add rathole-manager/ratholenode tests/test_adaptive.sh
git commit -m "feat(node): diagnose filtered tunnel carriers"
```

---

### Task 6: Toggleable Adaptive Failover Controller

**Files:**
- Modify: `rathole-manager/ratholenode`
- Modify: `rathole-manager/install-node.sh`
- Modify: `rathole-manager/update.sh`
- Modify: `tests/test_adaptive.sh`
- Test: `tests/test_adaptive.sh`

**Interfaces:**
- Produces: `ratholenode adaptive on|off|status|test|run`.
- Produces: `/etc/rathole/adaptive.env`, `rathole-adaptive.service`, `rathole-adaptive.timer`.
- Consumes: probe results from Task 5 and existing `gen_client`/`restart_svc`.

- [ ] **Step 1: Write RED tests for state transitions**

Test three failures cause `ws → kcp`, one/two failures do not switch, five healthy WS probes plus a completed 300-second cooldown cause `kcp → ws`, and failed post-switch verification restores the previous config/mode. Assert `off` disables timer and preserves current mode. Assert plain is absent unless `ALLOW_INSECURE=1`.

Run: `wsl bash tests/test_adaptive.sh`

Expected: transition assertions FAIL.

- [ ] **Step 2: Implement configuration and timer**

Persist validated values:

```text
ADAPTIVE_ENABLED=1
ADAPTIVE_INTERVAL=30
ADAPTIVE_FAILURES=3
ADAPTIVE_RECOVERIES=5
ADAPTIVE_COOLDOWN=300
ALLOW_INSECURE=0
```

The oneshot unit runs `/usr/local/bin/ratholenode adaptive run`; the timer uses `OnBootSec=45s`, `OnUnitActiveSec=<interval>` and `RandomizedDelaySec=5s`. Controller execution uses `flock -n /run/rathole-adaptive.lock`.

- [ ] **Step 3: Implement selection, switch and rollback**

Priority is `ws,kcp` and optionally `plain`. Before switching, save `node.env` and `client.toml`, update `TUNNEL`, regenerate/restart, and run the target probe. On failure restore both files under their locks and restart. Record `last_switch`, `previous`, `reason`, counters and `cooldown_until`.

- [ ] **Step 4: Run GREEN and commit**

Run: `wsl bash tests/test_adaptive.sh`

Expected: all threshold/cooldown/rollback/off tests PASS.

```bash
git add rathole-manager/ratholenode rathole-manager/install-node.sh rathole-manager/update.sh tests/test_adaptive.sh
git commit -m "feat(node): add toggleable adaptive carrier failover"
```

---

### Task 7: Core Packaging, Upgrade and Rollback

**Files:**
- Create: `rathole-manager/core-install.sh`
- Create: `tests/test_release_bundle.sh`
- Modify: `rathole-manager/install-panel.sh`
- Modify: `rathole-manager/install-node.sh`
- Modify: `rathole-manager/update.sh`
- Modify: `package.sh`
- Modify: `tests/test_release_bundle.sh`
- Test: `tests/test_release_bundle.sh`

**Interfaces:**
- Produces: `core-install.sh [--verify-only]` using `RATHOLE_CORE_DIR` defaulting to sibling `core/`.
- Produces: bundle paths `core/<target>/rathole` and `core/SHA256SUMS`.
- Consumes: Task 2 binary and version.

- [ ] **Step 1: Write failing bundle/install/rollback tests**

Create fake binaries for both target directories, a valid/invalid checksum manifest and a fake `/usr/local/bin/rathole`. Assert architecture selection, checksum rejection, executable mode, version verification, snapshot inclusion of `/usr/local/bin/rathole`, and rollback restoration.

Run: `wsl bash tests/test_release_bundle.sh`

Expected: FAIL because core installer and bundled layout do not exist.

- [ ] **Step 2: Implement verified core installation**

Map `x86_64 → x86_64-unknown-linux-gnu` and `aarch64 → aarch64-unknown-linux-musl`. Verify with:

```bash
(cd "$core_dir" && sha256sum -c SHA256SUMS --ignore-missing)
```

Copy candidate to a temp path, execute `--version`, require `0.5.1-ratholeengine.1`, then `install -m 0755` to `/usr/local/bin/rathole`. `RATHOLE_VERSION=v0.5.0` remains an explicit upstream fallback; bundled core is default.

- [ ] **Step 3: Include the core in snapshots and health checks**

Add `/usr/local/bin/rathole` once to `snapshot_paths`, record `rathole_sha`, install core during `apply_update` before regeneration, and require matching manager/core build on panel/node health. Rollback naturally restores the archived binary before services restart.

- [ ] **Step 4: Enforce release bundle contents**

When `RATHOLE_REQUIRE_CORE=1`, `package.sh` must fail unless both binaries and `SHA256SUMS` exist. Normal developer packaging warns but remains available.

Run: `wsl bash tests/test_release_bundle.sh`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rathole-manager/core-install.sh rathole-manager/install-panel.sh rathole-manager/install-node.sh rathole-manager/update.sh package.sh tests/test_release_bundle.sh
git commit -m "feat(update): ship and roll back the patched core"
```

---

### Task 8: Hub API and Adaptive UI

**Files:**
- Modify: `rathole-manager/ratholehub/hub.py`
- Create: `tests/test_hub.py`
- Test: `tests/test_hub.py`

**Interfaces:**
- Produces: `build_node_cmd` actions `adaptive_on`, `adaptive_off`, `adaptive_status`, `adaptive_test`.
- Produces: node overview field `adaptive` parsed from sanitized JSON.
- Consumes: Task 6 CLI.

- [ ] **Step 1: Write failing allow-list and parser tests**

```python
self.assertEqual(build_node_cmd("adaptive_off", {}), ["ratholenode", "adaptive", "off"])
self.assertEqual(build_node_cmd("adaptive_test", {}), ["ratholenode", "adaptive", "test", "--json"])
self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "30;id"}))
self.assertEqual(
    build_node_cmd("adaptive_on", {"interval": "30", "failures": "3", "recoveries": "5"}),
    ["ratholenode", "adaptive", "on", "--interval", "30", "--failures", "3", "--recoveries", "5"],
)
```

Also test malformed JSON returns a safe unknown state and no secret field is forwarded.

Run: `python -m unittest -v tests/test_hub.py`

Expected: FAIL because actions/parser are absent.

- [ ] **Step 2: Implement argv-only actions and overview collection**

Validate each number with the existing numeric regex and explicit ranges. Add write actions only for on/off; status/test remain read actions. Execute `adaptive status --json` with the existing argv path and parse only known keys.

- [ ] **Step 3: Add UI controls**

Node cards show on/off, current carrier, classification, latency, counters, last switch and readiness badges. Buttons call the existing API wrapper with structured args; no command string is constructed in JavaScript.

- [ ] **Step 4: Run GREEN and commit**

Run: `python -m unittest -v tests/test_hub.py`

Expected: PASS.

Run: `python -m py_compile rathole-manager/ratholehub/hub.py`

Expected: exit 0.

```bash
git add rathole-manager/ratholehub/hub.py tests/test_hub.py
git commit -m "feat(hub): control and display adaptive filtering"
```

---

### Task 9: Multi-Architecture Release Workflow

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_release_bundle.sh`
- Test: workflow syntax and local release audit

**Interfaces:**
- Produces: artifacts for both Linux targets, embedded bundle binaries and `SHA256SUMS`.
- Consumes: `core/build.sh`, `package.sh` and Git tag `v1.5.0`.

- [ ] **Step 1: Write RED assertions for workflow structure**

Assert release YAML contains a two-entry core matrix, artifact upload/download, checksum generation before `package.sh`, and `RATHOLE_REQUIRE_CORE=1`.

Run: `wsl bash tests/test_release_bundle.sh --workflow`

Expected: FAIL.

- [ ] **Step 2: Add core build matrix**

Use `ubuntu-latest` for x86_64 and an ARM64 Linux runner for aarch64; install Rust targets and required native packages, run `core/build.sh`, and upload each binary as an artifact. The release job downloads artifacts into exact `rathole-manager/core/<target>/rathole` paths, runs `sha256sum` with relative paths, then packages.

- [ ] **Step 3: Publish auditable assets**

Keep existing manager zip/bootstrap/install assets and additionally upload `SHA256SUMS` plus per-target compressed core binaries. Release notes come from `[1.5.0]` in `CHANGELOG.md`.

- [ ] **Step 4: Run GREEN and commit**

Run: `wsl bash tests/test_release_bundle.sh --workflow`

Expected: PASS.

```bash
git add .github/workflows tests/test_release_bundle.sh
git commit -m "ci: build patched rathole core for release"
```

---

### Task 10: Documentation, Versioning and Full Verification

**Files:**
- Modify: `rathole-manager/common.sh`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `docs/README.fa.md`
- Modify: `docs/install-manual.md`
- Modify: `docs/install-manual.fa.md`
- Modify: `docs/transport-modes.md`
- Modify: `docs/hub.md`
- Modify: `rathole-manager/ratholehub/README.md`
- Test: complete local verification suite

**Interfaces:**
- Produces: `MANAGER_VERSION="1.5.0"` and documented operational commands.

- [ ] **Step 1: Write version/doc audit assertions and verify RED**

Extend release audit to require manager `1.5.0`, changelog section `[1.5.0]`, `adaptive on|off|status|test`, core version, plain warning, reason-code table and rollback behavior in docs.

Run: `wsl bash tests/test_release_bundle.sh --docs`

Expected: FAIL on old version/docs.

- [ ] **Step 2: Update version, changelog and docs**

Document exact defaults: interval 30s, failures 3, recoveries 5, cooldown 300s, priority WS→KCP, plain opt-in, Noise manual. Explain control-path propagation, core checksum/build-id, diagnosis codes, update rollback and commands for emergency disable.

- [ ] **Step 3: Run the complete fresh verification**

```bash
wsl bash -lc 'cd /mnt/d/MohammadHosein/projectsupertunnel && \
  bash -n bootstrap.sh install.sh package.sh rathole-manager/*.sh rathole-manager/ratholectl rathole-manager/ratholenode && \
  bash tests/test_node_config.sh && \
  bash tests/test_nginx_control_path.sh && \
  bash tests/test_adaptive.sh && \
  bash tests/test_core_patch.sh && \
  bash tests/test_release_bundle.sh --source-only --workflow --docs && \
  python3 -m unittest -v tests/test_hub.py && \
  python3 -m py_compile rathole-manager/ratholehub/hub.py && \
  git diff --check'
```

Expected: all commands exit 0.

Run shellcheck at error severity on all shell files and inspect warnings separately.

- [ ] **Step 4: Build and audit the local x86 core/bundle**

Run `core/build.sh x86_64-unknown-linux-gnu <temp-output>`, place the verified binary in the bundle layout, create checksums, run `RATHOLE_REQUIRE_CORE=1 bash package.sh`, list zip entries and scan for ignored secrets (`state.json`, `node.env`, `services.conf`, cert/key files).

Expected: correct core path/checksum, no secret, LF scripts, forward-slash entries.

- [ ] **Step 5: Commit release content**

```bash
git add rathole-manager/common.sh CHANGELOG.md README.md docs rathole-manager/ratholehub/README.md tests/test_release_bundle.sh
git commit -m "release: prepare v1.5.0 adaptive filtering"
```

---

### Task 11: Publish and Verify GitHub Release

**Files:**
- No source changes expected after the release commit.
- Verify: Git branch, tag, CI/release runs and GitHub assets.

**Interfaces:**
- Produces: pushed `main`, annotated tag `v1.5.0`, GitHub Release and installable assets.

- [ ] **Step 1: Verify clean release state**

Run the complete verification command from Task 10 again, then:

```bash
git status --short --branch
git log --oneline origin/main..HEAD
git tag --list v1.5.0
```

Expected: only the user-owned untracked `AGENTS.md` may remain; no tracked changes; tag absent before creation.

- [ ] **Step 2: Push source and create the annotated tag**

```bash
git push origin main
git tag -a v1.5.0 -m "RatholeEngine v1.5.0"
git push origin v1.5.0
```

- [ ] **Step 3: Monitor CI and release workflow**

Poll GitHub Actions through the authenticated Git remote/API until both the main CI run and tag release run complete. If either fails, inspect logs, fix through a new commit, delete/recreate only the unpublished failed tag if necessary, and rerun full local verification before pushing.

- [ ] **Step 4: Audit published release**

Fetch GitHub Release metadata and verify:

- tag/name `v1.5.0`;
- manager zip, bootstrap and install assets;
- both core architecture assets and checksum manifest;
- nonzero sizes and matching downloaded SHA-256;
- release notes include panic fix, adaptive toggle, anti-probe path and rollback.

Finally perform a download-only bootstrap extraction smoke test against `releases/download/v1.5.0` and verify the embedded core reports the expected version on x86_64.
