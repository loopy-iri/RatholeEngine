# Hub Update + Upstream Feature-Parity + Dual-Core (rathole ⊕ backhaul) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three independent improvements to rathole-manager: (A) make the hub *diagnose accurately* and stop hiding tunnel state, (B) give reverse-tunnel **upstreams** the same transport options the **main tunnel** already has, and (C) allow a node↔Iran pair to run **rathole and backhaul cores at the same time** — some paths over rathole, some over backhaul, on the single shared 443.

**Architecture:** All three keep the core invariant *state → regenerate → hot-reload*; nothing hand-edits generated configs. (A) is hub-only (Python + inline JS) plus one `ratholectl doctor` probe fix. (B) generalizes the per-upstream generator that already exists for `kcp` to also cover `plain`/`noise`. (C) turns `transport` from a **per-node** attribute into a **per-node-entry** one and runs *both* cores on the node simultaneously; the two cores already live on disjoint nginx paths (`/`+`/_rh/*` for rathole vs hardcoded `/channel`+`/tunnel` for backhaul), so 443 is not the blocker — the bind-collision on `127.0.0.1:<node.port>` is.

**Tech Stack:** bash (`ratholectl`, `ratholenode`, `common.sh`; `set -uo pipefail`, `jq`), Python 3 stdlib (`hub.py`, `hubcmds.py`), inline vanilla JS/CSS (`ui/app.js`, `ui/i18n.js`, `ui/app.css`), systemd units, nginx (L7 + stream/SNI), rathole v0.5.0 (unpatched), Backhaul v0.6.5.

## Global Constraints

- **Commit identity:** author `loopy-iri`, **no** Claude co-author trailer.
- **Secrets never committed:** `state.json`, `node.env`, `services.conf`, `inventory.json`, `config.json`, certs/keys are gitignored.
- **LF line endings**, scripts executable; no CRLF (jq on Windows emits `\r` — strip with `${v%$'\r'}` before writing TOML).
- **Bash:** keep `set -uo pipefail` (not `-e`); the `jq | while read` pattern returns nonzero by design. Temp files via `rth_mktemp`/`rth_mktempd`.
- **In-place config writes** (inode preserved via `rth_commit_config`) so rathole's `config_watcher` hot-reloads without dropping tunnels.
- **TLS terminates only at nginx.** rathole server transport is always `tls=false`; backhaul server is always the non-TLS variant (`ws`/`wsmux`), client always TLS (`wss`/`wssmux`).
- **Hub security:** never run raw strings on servers. Every new action goes in `build_iran_cmd`/`build_node_cmd` as an argv list, every arg validated by an `RE_*` regex, mutating actions added to `WRITE_ACTIONS`.
- **Version:** bump `MANAGER_VERSION` in `common.sh` per release; update `CHANGELOG.md` `[Unreleased]` → dated section.
- **rathole path is not configurable:** the client always uses `/` for control; `[client.transport.websocket]` accepts only `tls` (adding `path` crash-loops the client). Path routing is nginx's job.

---

# Part A — Hub update: accurate diagnosis + no hidden tunnel state

**Why:** This session's outage was prolonged because the hub actively *misled*: `doctor` reported WS→`200`/OK while every tunnel was down, there was no per-node "what carrier is this and is it up" view, upstreams had no logs/status button, and adding a game node silently flipped all of 443 to L4 with no warning. v1.6.1 already fixed the per-node **mode display**; Part A finishes the diagnosis story.

**Files:**
- Modify: `rathole-manager/ratholectl` — `cmd_doctor()` (~2440-2490): probe the real control path, not just `/`.
- Modify: `rathole-manager/ratholehub/hubcmds.py` — add `upstream_logs`, `upstream_status` node actions (read-only).
- Modify: `rathole-manager/ratholehub/hub.py` — parse doctor's control-path result; surface a per-node "diagnose" blob.
- Modify: `rathole-manager/ratholehub/ui/app.js` — upstream logs/status buttons; a "diagnose" affordance on the node row.
- Modify: `rathole-manager/ratholehub/ui/i18n.js` — fa/en keys.
- Modify: `tests/test_hub.py` — allow-list + parser tests.

### Task A1: doctor probes the real control path (fixes false 200/OK)

**Interfaces:**
- Produces: `ratholectl doctor` output line `control_path_ws=<101|status>` in addition to the existing `/` probe.

- [ ] **Step 1 — reproduce the bug in a note:** `cmd_doctor` (ratholectl:~2457) curls `https://$domain/` with `Upgrade: websocket` and expects `101`. But the node connects at `/`, which nginx `map $http_upgrade` splits: a probe negotiating HTTP/2 loses the `Upgrade` header → falls to the fake site → `200`, and the secret `control_path` (`/_rh/<hex>`) is never probed at all. Both make doctor lie.
- [ ] **Step 2 — read** `ensure_control_path()` (ratholectl:86) and the doctor block; confirm `control_path` is in `state.json`.
- [ ] **Step 3 — implement:** force `--http1.1` on the probe; probe **both** `/` and `$control_path`; report each. Treat `101` on the control path as healthy. Keep the `/` line for the fake-site check.

```bash
  # dakhel-e cmd_doctor, ba --http1.1 (vagarna h2 header-e Upgrade ra hazf mikonad → 200-e doroughi)
  local cp; cp="$(jq -r '.control_path // "/"' "$STATE" 2>/dev/null)"
  local h=(-H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13'
           -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==')
  local code_cp; code_cp="$(curl -sk --http1.1 -o /dev/null -w '%{http_code}' \
       "${h[@]}" --resolve "$domain:443:127.0.0.1" "https://$domain:443${cp}" 2>/dev/null)"
  [ "$code_cp" = 101 ] && ok "control-path WS: 101 (kontrol salem)" || warn "control-path WS: ${code_cp} (entezar 101)"
```

- [ ] **Step 4 — run** `bash -n rathole-manager/ratholectl`; expect OK.
- [ ] **Step 5 — commit:** `fix(doctor): probe secret control_path over http1.1 (stop false 200)`.

### Task A2: expose upstream logs + status in the hub (read-only)

**Interfaces:**
- Consumes: node already has `rathole-client@<id>` + `rathole-kcp-up-<id>` units.
- Produces: node actions `upstream_logs {id}` → `["ratholenode","upstream","logs",id]`, `upstream_status {id}` → `["ratholenode","upstream","status",id]`.

- [ ] **Step 1 — write failing test** in `tests/test_hub.py`:

```python
def test_upstream_logs_and_status_argv(self):
    self.assertEqual(build_node_cmd("upstream_logs", {"id": "iranviph"}),
                     ["ratholenode", "upstream", "logs", "iranviph"])
    self.assertEqual(build_node_cmd("upstream_status", {"id": "iranviph"}),
                     ["ratholenode", "upstream", "status", "iranviph"])
    self.assertIsNone(build_node_cmd("upstream_logs", {"id": "a; rm -rf /"}))
    self.assertNotIn("upstream_logs", WRITE_ACTIONS)   # read-only
```

- [ ] **Step 2 — run:** `python -m pytest tests/test_hub.py -k upstream_logs -q`; expect FAIL.
- [ ] **Step 3 — implement (node side first):** add `logs)` and `status)` to `cmd_upstream()` in `ratholenode` (mirror `up_kcp_status`; `logs` → `journalctl -u rathole-client@<id> -n 40 --no-pager` + the kcp-up unit if present). Then add both actions to `build_node_cmd` guarded by `RE_ID`, and *not* to `WRITE_ACTIONS`.
- [ ] **Step 4 — run** the test; expect PASS. Then `bash -n rathole-manager/ratholenode`.
- [ ] **Step 5 — UI:** in `renderNode` upstream row (app.js:~430) add `<button>` for `upstream_status`/`upstream_logs` beside the existing kcp buttons; add `up_logs`/`up_status` i18n keys (fa/en).
- [ ] **Step 6 — commit:** `feat(hub): upstream logs + status (read-only) so upstream tunnels are diagnosable`.

### Task A3: warn before a game node flips all of 443 to L4

**Interfaces:** UI-only guard; no new server action (uses existing `game_add`).

- [ ] **Step 1 — read** `gen_nginx_conf` branch on `sni_count` (ratholectl:539) and `cmd_game_add` warning (ratholectl:~1220) to quote the exact effect.
- [ ] **Step 2 — implement:** in `gameAdd(...)` (app.js) prepend a confirm: adding the **first** SNI/game node switches 443 to nginx stream/L4 passthrough and moves the L7 vhost (fake site + rathole control + backhaul) to the internal port — all plain ws/kcp/backhaul nodes keep working only because nginx stream re-fronts them, so mis-set SNI drops everyone. Show the count of currently-normal nodes affected.
- [ ] **Step 3 — i18n:** `cf_game_l4` (fa/en) with the warning copy.
- [ ] **Step 4 — commit:** `feat(hub): warn that adding a game/SNI node flips 443 to L4`.

---

# Part B — Upstream feature-parity (plain + noise per upstream)

**Why:** A node can attach to several Iran servers as **upstreams** (`ratholenode upstream ...`). Today an upstream only supports the default `ws/443` or `kcp` — the transport surface the *main* tunnel gained (`plain`, `noise`) never reached upstreams. During this incident the backup Iran (`iranviph`) upstream had no way to move off ws to a censorship-resistant carrier independently of the main tunnel. This part gives each upstream the same `plain` and `noise` options `kcp` already has.

**Current surface (verified):**
- Main tunnel: `kcp | plain | noise | backhaul | watchdog | adaptive`.
- Upstream: `add | add-svc | rm-svc | rm | apply | kcp | ls | restart` — i.e. **only kcp** among transports. (watchdog already covers each upstream via `wd_check_one "rathole-client@<id>"` at ratholenode:1041.)

**Files:**
- Modify: `rathole-manager/ratholenode` — `gen_up_client()` (~680-739), `up_toml`/`up_env` helpers, `cmd_upstream()` case (~846-916).
- Modify: `rathole-manager/ratholehub/hubcmds.py` — `upstream_plain_on/off`, `upstream_noise_on/off` actions.
- Modify: `rathole-manager/ratholehub/ui/app.js` — per-upstream carrier `<select>` (mirror the main-tunnel `carrierSelect`, scoped to an id).
- Modify: `ui/i18n.js`, `tests/test_hub.py`.

**Design:** an upstream's transport is stored in its own `up_env` (e.g. `UP_TUNNEL=<ws|kcp|plain|noise>`), exactly as the main tunnel keeps `TUNNEL` in `node.env`. `gen_up_client()` branches on `UP_TUNNEL` the same way `gen_client()` branches on `TUNNEL` (remote/tls/hostline/transport block). No change to Iran — an upstream connects to a *remote* Iran that already runs the matching listener (plain HTTP port, or noise instance); the node side just needs to speak it.

### Task B1: per-upstream transport state + generator

**Interfaces:**
- Produces: `UP_TUNNEL` key in each upstream env; `gen_up_client <id>` honors it. Node commands `ratholenode upstream plain <id> on <remote> | off` and `ratholenode upstream noise <id> on <remote> <pubkey> [pattern] | off`.

- [ ] **Step 1 — read** `gen_client()` (ratholenode:1-64) and `gen_up_client()` (~680) side by side; note where `gen_client` emits `remote_addr`/`tls`/`[client.transport.*]` from `TUNNEL`, and replicate that switch in `gen_up_client` keyed on `UP_TUNNEL` (default `ws`).
- [ ] **Step 2 — write a bash assertion test** (extend `test-harness.sh` or a new `tests/test_upstream_gen.sh`): set `UP_TUNNEL=plain` for a fake upstream, run `gen_up_client`, assert the toml has `tls = false` and points at the plain remote; set `UP_TUNNEL=noise`, assert `[client.transport.noise]` + `remote_public_key`.
- [ ] **Step 3 — implement** the `UP_TUNNEL` branch in `gen_up_client()` (kcp branch already exists — generalize it; keep the per-upstream local kcp port scheme intact for `kcp`).
- [ ] **Step 4 — implement** `cmd_upstream` cases `plain)` / `noise)` calling `up_env_set UP_TUNNEL ...` + `gen_up_client "$id"` + `up_reload "$id"` (hot-reload, restart only for kcp on/off which changes the unit).
- [ ] **Step 5 — run** the bash test + `bash -n`; expect PASS/OK.
- [ ] **Step 6 — commit:** `feat(node): per-upstream plain/noise transport (parity with main tunnel)`.

### Task B2: hub actions + per-upstream carrier select

**Interfaces:**
- Consumes: B1's node commands.
- Produces: node actions `upstream_plain_on {id,remote}`, `upstream_plain_off {id}`, `upstream_noise_on {id,remote,pubkey,pattern?}`, `upstream_noise_off {id}` (all in `WRITE_ACTIONS`), validated by `RE_ID`/`RE_IPPORT`/`RE_B64`/`RE_HOST`.

- [ ] **Step 1 — write failing tests** in `tests/test_hub.py`:

```python
def test_upstream_plain_noise_argv(self):
    self.assertEqual(build_node_cmd("upstream_plain_on", {"id": "u1", "remote": "1.2.3.4:8880"}),
                     ["ratholenode", "upstream", "plain", "u1", "on", "1.2.3.4:8880"])
    self.assertIsNone(build_node_cmd("upstream_noise_on", {"id": "u1", "remote": "1.2.3.4:2334", "pubkey": "x"}))  # bad b64
    for a in ("upstream_plain_on","upstream_plain_off","upstream_noise_on","upstream_noise_off"):
        self.assertIn(a, WRITE_ACTIONS)
```

- [ ] **Step 2 — run:** expect FAIL.
- [ ] **Step 3 — implement** the four actions in `build_node_cmd` (mirror `upstream_kcp_on`), add to `WRITE_ACTIONS`.
- [ ] **Step 4 — run** tests; expect PASS.
- [ ] **Step 5 — UI:** replace the per-upstream kcp on/off buttons (app.js:~408-416) with a scoped carrier `<select id="upcar_<n>__<id>">` (values `ws|kcp|plain|noise`) → `setUpstreamCarrier(n,id,next,cur)`; reuse the `iranSrvOptions`/autofill modals used by the main carrier for kcp/noise params. Add `carrier_up_hint` i18n.
- [ ] **Step 6 — commit:** `feat(hub): per-upstream carrier select (ws/kcp/plain/noise)`.

> **Deferred:** per-upstream **backhaul** and per-upstream **adaptive** are intentionally out of scope for Part B — backhaul-per-upstream needs a second backhaul core keyed by upstream (heavy; overlaps Part C), and adaptive-per-upstream multiplies probe timers. Revisit after Part C lands.

---

# Part C — Dual-core: rathole ⊕ backhaul on the same node↔Iran pair

**Goal (user's words):** "between the node and Iran, one port is backhaul and one is rathole" — run **both cores at once**, each carrying a disjoint set of paths, over the single shared domain/443.

### Why it's blocked today (root cause, verified)

- On Iran, `transport` is **already per-node-entry** in `state.json`. `gen_server_toml` emits only rathole entries (skips `noise|backhaul`); `gen_backhaul_server_toml` emits only `transport=="backhaul"` entries. They would collide **only if they bound the same `127.0.0.1:<node.port>`** — and two *different* node entries have different ports. So Iran can already host rathole entries and backhaul entries at the same time.
- At nginx/443 the two cores are on **disjoint paths**: rathole control = `/` + secret `/_rh/<hex>`; backhaul = hardcoded `/channel` + `/tunnel`; user data = `/<node>` by `map $uri`. No path conflict.
- **The real blocker is the node side.** `ratholenode backhaul on` (ratholenode:517) sets a single global `TUNNEL=backhaul` and **`systemctl disable --now rathole-client`** (line 547) — because it assumes backhaul *replaces* the whole tunnel. So a node can run exactly one core.

### The design: two lanes on one node

A single foreign machine registers on Iran as **two (or more) node entries** — e.g. `trkfast` (rathole, low-latency ws/kcp) and `trkbulk` (backhaul, SMUX for bulk/lossy) — each its own name = path = port = inbound. On the node, run **both** `rathole-client` (serving the rathole entries' inbounds) **and** `backhaul-client` (serving the backhaul entries' inbounds) concurrently. Because the two lanes own disjoint inbound ports, there is no bind collision and no crash-loop. This reuses the existing per-node-entry `transport` model end-to-end; the only thing that must change is the node's **"backhaul replaces everything"** assumption.

> ### ✅ DECIDED (2026-07-30): Option 1 — per-lane / per-node-entry
> Core is chosen per Iran node-entry (path). The node keeps two service registries: existing `services.conf` (rathole) + new `bh-services.conf` (backhaul), and runs both cores concurrently. Matches the existing "path == node == port == transport" model; each path is unambiguously one core. C1–C3 below implement this. (Option 2 — per-service flag — rejected: breaks the one-path-one-core model and complicates `map $uri`.)

**Files (Option 1):**
- Modify: `rathole-manager/ratholenode` — remove the forced `rathole-client` disable in `cmd_backhaul on`; make backhaul a **coexisting** lane; add `bh-services.conf` + `gen_backhaul_client_toml` fed by it; keep `TUNNEL` describing only the *rathole* lane.
- Modify: `rathole-manager/ratholectl` — no schema change (transport already per node), but add a `ratholectl backhaul node <name> on` guard that verifies the node's rathole entry (if any) uses a *different* port, and a `doctor` line per core.
- Modify: `rathole-manager/ratholehub/hub.py` + `hubcmds.py` + `ui/app.js` — surface "core" alongside the existing per-node mode select; show both cores' health.
- Modify: `docs/transport-modes.md` + `docs/assets/transport-modes.svg` — document the dual-core topology.
- Modify: `tests/test_hub.py` + harness.

### Task C1: node runs both cores concurrently (remove mutual exclusion)

**Interfaces:**
- Produces: `bh-services.conf` (`name|token|inbound` lines, like `services.conf`); `gen_backhaul_client_toml` reads it; `rathole-client` and `backhaul-client` both stay enabled when each lane is non-empty.

- [ ] **Step 1 — read** `cmd_backhaul` (ratholenode:517-571), `gen_backhaul_client_toml`, `services.conf` handling, and `restart_svc`/`reload_svc`. Confirm the only reason rathole-client is disabled is the assumption that Iran removed *all* of this node's services.
- [ ] **Step 2 — write a harness assertion:** with a rathole service `s1|tok|1101` in `services.conf` **and** a backhaul service `s2|tok2|1201` in `bh-services.conf`, generating both tomls yields `client.toml` binding `127.0.0.1:1101` (rathole) and `backhaul` client mapping `1201` — no shared port; assert both units would be enabled.
- [ ] **Step 3 — implement:** in `cmd_backhaul on`, stop `systemctl disable rathole-client`; instead keep it running iff `services.conf` is non-empty. Feed backhaul from `bh-services.conf` (new `add-bh-svc`/`rm-bh-svc` node commands) rather than `TUNNEL=backhaul`. `TUNNEL` now names only the rathole lane's carrier (`ws|kcp|plain|noise`).
- [ ] **Step 4 — run** the harness + `bash -n`; expect both lanes present, no port overlap.
- [ ] **Step 5 — commit:** `feat(node): run rathole + backhaul cores side by side (dual-core lanes)`.

### Task C2: Iran-side guard + doctor per core

**Interfaces:**
- Produces: `ratholectl backhaul node <name> on` refuses if `<name>`'s rathole entry shares a port with a backhaul entry; `doctor` prints a health line per core.

- [ ] **Step 1 — read** `gen_server_toml` skip logic (ratholectl:391-402) + `gen_backhaul_server_toml` (484-528) and confirm disjoint-port requirement.
- [ ] **Step 2 — write test:** two entries same machine, distinct ports, one rathole one backhaul → both configs valid, `nginx -t` passes (harness-stubbed).
- [ ] **Step 3 — implement** the port-overlap guard + `doctor` per-core probe (rathole control-path from Task A1 **and** a `/channel` probe for backhaul).
- [ ] **Step 4 — run** harness; expect PASS.
- [ ] **Step 5 — commit:** `feat(iran): dual-core port-overlap guard + per-core doctor`.

### Task C3: hub UI — assign a path to a core, show both cores

**Interfaces:**
- Consumes: existing `iranNodeMode` (v1.6.1) already returns `backhaul`; extend the per-node select to treat rathole-carriers and backhaul as coexisting lanes rather than mutually exclusive.
- Produces: node actions `add_bh_svc`/`rm_bh_svc` (node), health strip showing `rathole: ok / backhaul: ok` per machine.

- [ ] **Step 1 — write allow-list tests** for `add_bh_svc {id,name,token,inbound}` / `rm_bh_svc {id,name}` (RE-validated, in `WRITE_ACTIONS`).
- [ ] **Step 2 — run:** expect FAIL.
- [ ] **Step 3 — implement** the actions + node commands; UI: on a node with both lanes, render two mini-tables ("rathole services" / "backhaul services") and a per-lane health dot.
- [ ] **Step 4 — run** tests + `node --check`; expect PASS.
- [ ] **Step 5 — commit:** `feat(hub): dual-core UI — per-lane services + health`.

### Task C4: docs + version + changelog

- [ ] **Step 1** — update `docs/transport-modes.md` with the dual-core section; extend `transport-modes.svg` (same visual style: white bg, dark banner, pastel zones, `#334155` data arrows / `#9333ea` dashed reverse-tunnel arrows, Segoe UI).
- [ ] **Step 2** — bump `MANAGER_VERSION`; move `CHANGELOG.md` `[Unreleased]` → dated `[1.7.0]` (dual-core is a feature ⇒ minor bump).
- [ ] **Step 3 — commit:** `docs(dual-core): topology + changelog + v1.7.0`.

---

## Self-Review

- **Spec coverage:** (A) hub update = doctor fix A1 + upstream diagnosability A2 + game warning A3; (B) upstream parity = plain/noise B1–B2; (C) dual-core = C1–C4. All three user asks mapped.
- **Ordering / independence:** A, B, C are independent and each ends shippable. Recommended order **A → B → C** (A is smallest and fixes the live diagnosis gap; C is largest and gated on the decision above). A1 (doctor control-path probe) is a dependency of C2's per-core doctor — do A1 first.
- **Open decision:** the 🔶 block in Part C (per-lane vs per-service). C1–C3 assume per-lane; confirm before starting C1.
- **Type consistency:** node actions use `RE_ID`/`RE_IPPORT`/`RE_B64`/`RE_HOST`/`RE_KEY`/`RE_PORT` already in `hubcmds.py`; `bh-services.conf` mirrors `services.conf`'s `name|token|inbound` format.



