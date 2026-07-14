# Direct-IP Header Routing — Design Spec

**Date:** 2026-07-14
**Status:** Approved for planning
**Scope:** `rathole-manager/ratholectl`, `rathole-manager/ratholehub/hub.py`, docs

---

## 1. Goal

Add a new ingress mode where the **end user connects directly to the Iran server's IP**
(not the server's domain, no nginx TLS) over a dedicated plain HTTP port, carrying:

- a **decoy `Host` header** (e.g. `myket.ir`) — camouflage only, ignored for routing;
- a **camouflaged routing header** whose value equals a **node name** (e.g. `X-Cdn-Id: trk01`).

nginx maps that header value to the matching node's local rathole port → rathole tunnel →
node inbound abroad → egress. A request **without** a recognized header value falls back to
the **fake site only** (no path routing on this port).

This is purely **additive**. It does not touch port 443 / nginx TLS, the SNI/game stream mode,
the plain **transport** mode (`plain_port`), or the noise transport. It coexists with normal
path-based routing (`map $uri $backend_port`), which stays exactly as-is on 443.

### Why (over the existing path mode)

With path routing, the URL path leaks which node is in use (`/trk01/...`). With header routing
the visible path can be anything innocuous and the node selection is hidden in a header — better
camouflage for direct-IP / domain-fronting-style access where the user points a benign `Host`
at the raw IP.

### Non-goals / explicit boundaries

- **No authentication and no TLS on this listener.** Anyone who sends a valid header value +
  node name reaches that node. This is intentional: real auth/encryption lives in the proxy
  layer *inside* the tunnel (VLESS/VMess UUID, etc.). The header is routing + camouflage, not a
  secret. This must be stated in `direct status` output and in the docs.
- Does not generate any Xray/proxy config on the node — same as every other transport mode, the
  node inbound is whatever the operator already configured.
- SNI nodes are **excluded** from the header map (they are L4 passthrough on 443; there is no
  local L7 port to send plain HTTP to).

---

## 2. State (`/etc/rathole-manager/state.json`)

Two new top-level keys, siblings of the existing `plain_port` / `hub_port`. Absent = feature off.

| Key             | Type   | Default    | Meaning                                            |
|-----------------|--------|------------|----------------------------------------------------|
| `direct_port`   | number | `8081`     | Public plain-HTTP listen port for direct-IP mode.  |
| `direct_header` | string | `X-Cdn-Id` | Routing header name (value = node name).           |

Both are cleared by `direct off`. When both absent, `gen_nginx_conf` emits nothing new.

**Port reservation:** `direct_port` participates in the same reserved-port set as the others
(the jq expression at `ratholectl:218` that collects `control_port, fake_port, sub_port,
internal_port, plain_port, hub_port, noise_port`). Add `direct_port` there so node-port
auto-allocation never collides with it.

---

## 3. nginx generation (`gen_nginx_conf`, ratholectl:380)

### 3.1 The header→backend maps (two maps, no `if`)

Emitted only when `direct_port` is set. **Map 1** turns the routing header into a node port,
built from the same `jq .nodes[]` loop used for the path map, **skipping SNI nodes**
(`select(.sni == null)`), so every non-SNI node is automatically routable with no per-node config:

```nginx
# map 1: meghdar-e header-e masiryabi (= naam-e node) -> port lvkal rathole
# header nbud ya nashnas -> "" (khali)
map $http_x_cdn_id $direct_node {
    default        "";
    "trk01"        2001;
    "trk02"        2002;
}
```

**Map 2** resolves the empty case to the fallback backend. Its `""` branch differs by mode, which
is the *only* difference between the standalone and merged forms — so both are handled with plain
maps and a single `proxy_pass`, never an `if`:

```nginx
# map 2: agar header khali bud -> fallback; vagarna -> port-e node
map $direct_node $direct_backend {
    default    $direct_node;   # header matched a node -> its port
    ""         8080;           # standalone: fallback = fake_port
    #  (merged form uses:  ""  $backend_port;  -> fall through to path map)
}
```

- The nginx variable name in map 1 is derived from `direct_header` by nginx's own rule: lowercase,
  `-` → `_`, prefixed `$http_`. E.g. `X-Cdn-Id` → `$http_x_cdn_id`. The generator computes this
  transform (`tr 'A-Z-' 'a-z_'`) so a custom header name produces the correct variable.
- Node names are already validated `^[A-Za-z0-9_-]{1,40}$`, so they are safe as literal map keys
  (exact-match strings, not regex — no metacharacter risk).

### 3.2 The listener server block

Emitted right after the existing `plain_port` block, guarded by `direct_port` being set. Because
map 2 guarantees `$direct_backend` is always a valid port, `location /` is a single clean
`proxy_pass` — no `if`, avoiding nginx's well-known "if is evil" pitfalls:

```nginx
server {
    listen 8081;
    listen [::]:8081;
    server_name _;

    # header matched -> port-e node; vagarna -> sait-e fik (az tarigh-e map 2)
    location / {
        proxy_pass http://127.0.0.1:$direct_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_request_buffering off;
        tcp_nodelay on;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

- **Bind:** IPv4 + IPv6 public (`listen <port>;` + `listen [::]:<port>;`) — matches the plain
  block's convention (ratholectl:494-495).
- **Fallback = fake site only.** No `map $uri` on this port; unknown/absent header → `fake_port`
  via map 2's `""` branch.
- Timeouts/keepalive mirror the existing plain/data blocks so WebSocket-based proxies work.

### 3.3 Coexistence with `plain_port`

If the operator sets `direct_port == plain_port`, do **not** emit two conflicting `server` blocks
on the same port. Instead the generator emits **one** block on that port and only changes map 2's
`""` branch from `fake_port` to `$backend_port` — so an absent/unknown header falls through to the
existing path-based `$backend_port` map instead of the fake site, while a matched header still wins.
`location /` stays a single `proxy_pass http://127.0.0.1:$direct_backend;` in both modes; only the
one map line differs. When the ports differ, emit two independent blocks (direct block uses the
`fake_port` fallback). This equality/merge branch is the one subtle piece and must be unit-visible
in the test harness.

### 3.4 `connection_upgrade` map

The `$connection_upgrade` map already exists in the generated conf (used by 443/plain blocks); the
new block reuses it. No new global map needed beyond `$direct_backend`.

---

## 4. CLI command: `ratholectl direct`

New subcommand dispatched in `main()` (ratholectl:1800, next to `plain)` / `noise)`), backed by a
`cmd_direct()` following the exact shape of `cmd_noise` (ratholectl:1522).

```
ratholectl direct on  [--port N] [--header NAME]
ratholectl direct off
ratholectl direct status
ratholectl direct show [name]      # print client-config example (see §5)
```

### `on`
1. `need_root; need_bin jq; ensure_state`.
2. Parse optional `--port` (default `8081`) and `--header` (default `X-Cdn-Id`).
3. Validate:
   - port: `^[0-9]+$`; reject `443`; reject collision with `internal_port` (reuse the guard at
     ratholectl:1530-1531) and with other reserved ports.
   - header: `^[A-Za-z0-9-]+$` (letters/digits/hyphen only — prevents injection into the nginx
     `map` directive and guarantees a clean `$http_*` transform).
4. `state_set '.direct_port' "$port" num`; `state_set '.direct_header' "$header"` (string).
5. `warn` + best-effort `ufw allow $port/tcp` (mirror noise `on`, ratholectl:1538-1539).
6. `regenerate` (→ `gen_nginx_conf` → `nginx -t` → reload; auto-revert on failure is inherited).
7. `print_direct_connect` (§5).

### `off`
`jq 'del(.direct_port, .direct_header)'` → write state → `regenerate`. Best-effort note that the
firewall port can be closed. (No systemd unit to remove — this is nginx-only.)

### `status`
Show roshan/khamoosh, port, header name, listen-check via `ss -ltnH "sport = :$port"`, and a
per-node line listing each routable node with its exact header value, e.g.:

```
direct-IP (header-based): roshan   port 8081   header: X-Cdn-Id
  gvshdadn TCP:8081: blh
  node-ha:  trk01 -> "X-Cdn-Id: trk01",  trk02 -> "X-Cdn-Id: trk02"
  hoshdar: in listener bedoon TLS/auth ast; ehrazhoviat dar laye-ye proxy-e daroon-e tunnel ast.
```

This per-node, hub-parseable format mirrors the noise `status` block (ratholectl:1580-1585).

### `show [name]`
Calls `print_direct_connect` for the client example (§5).

All user-facing strings in Finglish, matching surrounding code.

---

## 5. Client-config guide (`print_direct_connect`)

Printed after `direct on` and by `direct show`. Prints a ready example for an Xray/V2Ray client
using **WebSocket transport without TLS**:

- address = `<IRAN_IP>:<direct_port>` (IP fetched like ratholectl:1601: `api.ipify.org` →
  `hostname -I` fallback);
- WS `Host` header = a benign decoy domain (placeholder `myket.ir`, note it's freely changeable);
- extra header `<direct_header>: <node_name>`;
- WS path = the node's normal path (same as the path-mode inbound expects).

If a `name` arg is given, print the concrete values for that node; otherwise print a template with
`<node_name>`. Include the no-TLS/no-auth security note.

---

## 6. Hub button (`ratholehub/hub.py`)

Add actions to the Iran allow-list in `build_iran_cmd` (hub.py:174), argv form, each arg regex-
validated — same pattern as `plain_*` (hub.py:250-256):

```python
if action == "direct_status": return ["ratholectl", "direct", "status"]
if action == "direct_show":   return ["ratholectl", "direct", "show"]
if action == "direct_off":    return ["ratholectl", "direct", "off"]
if action == "direct_on":
    port   = str(a.get("port", "8081"))
    header = str(a.get("header", "X-Cdn-Id"))
    if not RE_PORT.match(port):  return None
    if not RE_HEADER.match(header): return None   # new: ^[A-Za-z0-9-]{1,40}$
    return ["ratholectl", "direct", "on", "--port", port, "--header", header]
```

- Add `RE_HEADER = re.compile(r"^[A-Za-z0-9-]{1,40}\Z")` next to the other `RE_*` (hub.py:159).
- UI: a per-Iran-server toggle + status line under the existing transport controls (near the
  plain/noise toggles), with an optional port/header field. i18n strings added to both fa/en dicts.
- No change to `run_on_server`/`_ssh_base` — reuses the existing argv-over-SSH path.

---

## 7. Testing

- **test-harness.sh** (sandboxed, no root/nginx/systemd): add cases asserting that after
  `direct on`, the generated nginx conf contains the `$direct_backend` map with a line per non-SNI
  node, the `listen <port>` block, and the correct `$http_*` variable for a custom `--header`;
  and that `direct off` removes them. Add a case for `direct_port == plain_port` producing a
  single merged block (no duplicate-listen). Assert SNI nodes are absent from the map.
- **nginx -t** is exercised by `regenerate` on a real box; the harness stubs it, so also add a
  focused check that the emitted block is well-formed (balanced braces, single `proxy_pass` per
  location).
- **hub:** with `RATHOLEHUB_MOCK=1`, assert `direct_on` with a bad header/port returns None
  (rejected) and a good one yields the exact argv.
- Run `shellcheck` + `bash -n` on ratholectl and `py_compile` on hub.py (CI parity).

---

## 8. Security summary (must surface to the operator)

- The direct listener is **plaintext, unauthenticated, public**. Confidentiality and auth come
  from the proxy protocol inside the tunnel, never from this layer.
- The routing header is **camouflage + routing only** — not a credential. Knowing a node name is
  enough to reach that node's inbound (which then enforces its own auth).
- Header name and node names are strictly validated before ever reaching the nginx `map`, so no
  operator input is interpolated unescaped into config.
- Opening `direct_port` on the public interface is a firewall change the operator is told about
  explicitly (warn + best-effort `ufw allow`).

---

## 9. Files touched

- `rathole-manager/ratholectl` — `cmd_direct`, `print_direct_connect`, `gen_nginx_conf` additions,
  reserved-port jq (`:218`), `main()` dispatch (`:1800`).
- `rathole-manager/ratholehub/hub.py` — `RE_HEADER`, `build_iran_cmd` actions, UI toggle, i18n.
- `rathole-manager/test-harness.sh` — new assertions.
- Docs: `docs/transport-modes.md` (+ `.fa`), `docs/README.fa.md`, hub docs — describe the mode and
  its security boundary.
