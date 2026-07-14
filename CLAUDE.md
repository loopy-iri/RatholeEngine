# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`rathole-manager` is a multi-location reverse-tunnel system built on **rathole + Nginx**. A single Iran server (behind one domain, one cert, one port 443) fronts many foreign "nodes" that connect back via reverse tunnel. User traffic is routed to nodes **by URL path** (`map $uri $backend_port` in nginx). The primary goal is censorship-resistant tunneling for Iran; almost all code comments and log strings are Persian transliterated into Latin ("Finglish", e.g. `tvlid khodkar` = auto-generate). Match that style when editing.

The repo root holds packaging/bootstrap scripts; the actual product lives in `rathole-manager/`.

## Three roles, three programs

The system has three distinct runtime roles. Read the file for the role you're touching:

- **Iran panel** → `rathole-manager/ratholectl` (bash). Runs the rathole **server** + nginx. Owns node inventory. Generates `/etc/rathole/server.toml` and `/etc/nginx/conf.d/rathole.conf`.
- **Foreign node** → `rathole-manager/ratholenode` (bash). Runs the rathole **client**. Generates `/etc/rathole/client.toml`.
- **Hub** → `rathole-manager/ratholehub/hub.py` (Python 3, **stdlib only, no pip**). Central web panel that drives many Iran servers + nodes over SSH. Listens on `127.0.0.1` (fronted by nginx under `/hub/`).

`rathole-manager/common.sh` is sourced by both bash tools (colors/logging, `kcp_profile`, `install_kcptun`, `apply_sysctl_tuning`, `fakeweb_service`).

## Central design principle: state → regenerate → hot-reload

Every mutation follows the same pattern — **never hand-edit the generated configs**; change state and regenerate:

- **ratholectl**: state is `/etc/rathole-manager/state.json` (jq-manipulated via `state_set`/`s_get`). Commands mutate state, then call `regenerate()` → `gen_server_toml()` + `gen_nginx_conf()` → `nginx -t` → reload. Configs are written **in place (preserving inode)** so rathole's `config_watcher` hot-reloads without dropping active tunnels. `regenerate` keeps a `.rathole-good.bak` and auto-reverts nginx if `nginx -t` fails.
- **ratholenode**: state is `/etc/rathole/node.env` (key=value, via `env_set`/`load_env`) + `/etc/rathole/services.conf` (`name|token|inbound` lines). `gen_client()` builds `client.toml`; `reload_svc` prefers hot-reload over restart (`restart_svc` only for transport changes like kcp on/off).

## Transport modes (the core complexity)

The same tunnel can carry traffic four ways; switching modes never changes user-facing services/tokens/paths — only the transport. Key invariant: **TLS is terminated only by nginx** — rathole server transport is always `tls = false`; the default client uses `tls = true` over websocket to nginx/443.

- **websocket + TLS** (default): client connects `wss://domain:443`, nginx splits root `/` between the fake site and the rathole control channel using `$http_upgrade` (rathole always uses `/` for control; path isn't configurable in rathole).
- **kcp** (`cmd_kcp` both sides): parallel UDP+FEC path via kcptun for lossy links (TCP-over-TCP mitigation). Additive — doesn't touch server/nginx/443. Profiles (`balanced`/`lossy`/`aggressive`) must match on both ends; defined in `common.sh:kcp_profile`. Multi-Iran nodes run independent kcp per upstream (`rathole-kcp-up-<id>`, local ports from 29901).
- **plain** (`cmd_plain` both sides): no-TLS websocket to a separate HTTP listener port (default 8880). Lighter, unencrypted tunnel path.
- **game / SNI** (`ratholectl game`, `gen_stream_conf`): when any node has an `sni`, port 443 switches to nginx **stream/SNI** mode (L4 passthrough) and the L7 path/WS vhost moves to an internal port (`internal_port`, default 8443). TLS for game traffic terminates on the **node** (real cert, VLESS+TLS+Vision). This is why `gen_nginx_conf` branches on `sni_count`.

## Path == node name == nginx map == Xray inbound

A node's `name` is simultaneously its URL path, its nginx `map` entry, and the Xray inbound path on the node. These three must stay identical. Each node has a data service; adding `--api-port` also creates a `<name>_api` service (bound to `127.0.0.1`) for panel↔node management over the tunnel.

## Hub (hub.py) specifics

- Single-file stdlib HTTP server; all UI (HTML/JS/CSS) and i18n (fa/en dicts) are inline. `Handler` is the router; `main()` serves `ThreadingHTTPServer`.
- **Security-critical:** it never runs raw strings on servers. `build_iran_cmd` / `build_node_cmd` map an `action` + validated args (via the `RE_*` regexes) to an **argv list**, executed over SSH with each arg passed separately (`run_on_server` → `_ssh_base`). When adding a server action, add it to the right `build_*_cmd` **and** the allow-list of actions, and validate every arg with a regex — do not interpolate user input into a shell string.
- `deploy_to_server` scp's the CLI tools + `update.sh` to a server and runs `update.sh` (remote upgrade). `provision_server` bootstraps SSH key auth.

## Commands

There is no build step (bash + stdlib Python). Common tasks:

```bash
# Test ratholectl end-to-end WITHOUT root/systemd/nginx (sandboxed; stubs need_root/nginx/systemctl):
bash rathole-manager/test-harness.sh
#   NOTE: it hardcodes BASE=/mnt/d/... (WSL path) and needs a `jq-linux` binary beside the scripts.

# Run the hub locally with mocked SSH (no real servers touched):
RATHOLEHUB_MOCK=1 RATHOLEHUB_CONF=/tmp/hub-conf.json RATHOLEHUB_INV=/tmp/hub-inv.json \
  python3 rathole-manager/ratholehub/hub.py        # then open http://127.0.0.1:8088
#   Env overrides: RATHOLEHUB_HOST, RATHOLEHUB_PORT, RATHOLEHUB_CONF, RATHOLEHUB_INV, RATHOLEHUB_MOCK.

# Build the distributable zip (LF endings, forward-slash paths — do NOT use Windows Compress-Archive):
bash package.sh                                     # → rathole-manager.zip (bundles rathole-manager/ + docs/; falls back to tar.gz)

# One-command install from GitHub (fetches the latest Release bundle, then runs bootstrap):
curl -fsSL https://raw.githubusercontent.com/loopy-iri/RatholeEngine/main/install.sh | sudo bash -s -- --panel --domain ... --fullchain ... --key ...
#   install.sh: defaults to loopy-iri/RatholeEngine; RATHOLE_GH="owner/repo" overrides the repo slug; RATHOLE_RELEASE="vX" pins a version.

# Local install on a fresh server (no download; bundle already present):
sudo bash bootstrap.sh                              # interactive; asks panel/node/update/rollback
sudo bash bootstrap.sh --local ./rathole-manager.zip --panel --domain ... --fullchain ... --key ...
```

## Update, backup & rollback

`update.sh` is the safe upgrade path (auto-detects panel/node/hub). Before touching anything it takes a **full snapshot** (CLI + configs + systemd units, per role) into `/var/backups/rathole-manager/pre-update-<ts>/` (`manifest.txt` + `backup.tar.gz`), applies the update, runs a per-role **health check** (`rathole-server`/`rathole-client`/`ratholehub` active + `nginx -t`), and **auto-rolls-back** to the snapshot on failure. Retention = last 7 (env `RATHOLE_BACKUP_RETENTION`).

- Manual: `update.sh --list-backups`, `update.sh --rollback [<ts>]`, `update.sh --no-rollback`. `bootstrap.sh` forwards `--rollback`/`--list-backups` (and menu entries 5/6) to `update.sh`, using a local `update.sh` without re-downloading when possible.
- This complements the narrower `.rathole-good.bak` (nginx rollback inside `regenerate`) and `ratholectl backup`/`ratholenode backup` (state-only tarballs). The rathole binary is not changed by `update.sh`, so it is intentionally excluded from snapshots.

Installers/lifecycle (run on the target server, all need root): `rathole-manager/install-panel.sh`, `install-node.sh`, `ratholehub/install-hub.sh`, `update.sh` (snapshot + upgrade + health-check + rollback; also finishes partial installs), `uninstall-panel.sh`, `uninstall-node.sh`. One-command entry from GitHub: root `install.sh` (curl-piped) → downloads the Release bundle → `bootstrap.sh`.

CI/release: `.github/workflows/ci.yml` (shellcheck + `bash -n` + `py_compile` on push/PR) and `.github/workflows/release.yml` (on tag `v*`: runs `package.sh`, uploads `rathole-manager.zip` + `bootstrap.sh` + `install.sh` as Release assets — the exact assets `install.sh` fetches from `releases/latest/download`).

## Editing conventions

- **Bash:** these scripts intentionally use `set -uo pipefail` (not `-e`) — the `jq | while read` pattern returns nonzero and would abort under `-e`; errors are handled explicitly via `die`. Keep that. Preserve in-place config writes (inode preservation) so hot-reload keeps working. Temp files go through `rth_mktemp`/`rth_mktempd` (auto-cleaned via trap).
- **Windows/line-endings:** this repo lives on a Windows drive. Scripts must ship with **LF** endings and be executable; `package.sh`/`update.sh`/`bootstrap.sh` all run `sed -i 's/\r$//'` defensively. Don't introduce CRLF.
- **Secrets:** certs/keys, `state.json`, `inventory.json`, `node.env`, `services.conf`, and `config.json` are gitignored and must never be committed. (Note: `fullchain.pem` currently sits at repo root and is gitignored — leave it out of any bundle.)

## Reference docs

Documentation lives in `docs/` (Persian, except the root README). Diagrams (SVG/PNG) are in `docs/assets/`.

- `README.md` (repo root) — GitHub landing page, **bilingual** (English + Persian summary). Embeds `docs/assets/architecture.svg` and `transport-modes.svg`.
- `docs/README.fa.md` — full CLI reference and install flows (Persian; was `rathole-manager/README.md`).
- `docs/install-manual.fa.md` — full **manual** install walkthrough (Persian): Iran panel + Pasargad Xray/user config + foreign nodes + hub, step by step, mirroring exactly what `install-panel.sh`/`install-node.sh`/`install-hub.sh`/`ratholectl init` do.
- `docs/architecture.md` — three roles + the state→regenerate→reload principle (embeds `architecture.svg`, `state-regenerate-reload.svg`).
- `docs/transport-modes.md` — the four transport carriers + game/SNI (embeds `transport-modes.svg`).
- `docs/traffic-flow.md` — packet path layer-by-layer (Mermaid + `assets/*.svg`; was `TRAFFIC-FLOW.md`).
- `docs/hub.md` — hub web panel / REST API + security model (embeds `hub-architecture.svg`; mirrors `rathole-manager/ratholehub/README.md`).
- `docs/performance.md` — tuning beyond the tunnel (BBR, kcp, non-tunnel bottlenecks; was `PERFORMANCE-GUIDE.md`).
- `docs/amneziawg-reverse.md` — a separate AmneziaWG reverse-tunnel design (not part of the rathole flow; was `AMNEZIAWG-REVERSE.md`).
- `rathole-multilocation-pasargad.md` (repo root) — original detailed design/troubleshooting doc.

Three hand-authored diagrams are new: `docs/assets/transport-modes.svg`, `hub-architecture.svg`, `state-regenerate-reload.svg`. All diagrams share one visual style (white bg, dark title banner, per-zone pastel boxes, `#334155` data-path arrows / `#9333ea` dashed reverse-tunnel arrows, Segoe UI font). Match it when adding diagrams. `package.sh` bundles `docs/` alongside `rathole-manager/`.
