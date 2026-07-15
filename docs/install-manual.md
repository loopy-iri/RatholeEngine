<div align="center">

<img src="assets/logo.svg" alt="RatholeEngine" width="110" height="110" />

# Full Manual Install — RatholeEngine

**Iran panel + Pasargad config + foreign nodes + central hub**

_Step by step, no automated script — exactly what the installers do._

[**Persian version**](install-manual.fa.md) · [**README**](../README.md) · [One-command install](../README.md#quick-start)

</div>

> **Who is this for?** When you want to install **manually**, fully aware of every layer (instead of the one-command `install.sh`), or when an automated install got stuck at some step and you want to carry that step forward by hand. Every command here is taken verbatim from the real scripts (`install-panel.sh`, `install-node.sh`, `install-hub.sh`, `ratholectl init`).
>
> If the automated install is enough for you, go to the [one-command install](../README.md#quick-start). For the conceptual design and deeper pessimism, read the [Pasargad design doc](../rathole-multilocation-pasargad.md) (Persian).

## Contents

- [0. Prerequisites & sanity checks](#0-prerequisites--sanity-checks)
- [1. Install the rathole binary (both roles)](#1-install-the-rathole-binary-both-roles)
- [2. Iran server (panel) — manual install](#2-iran-server-panel--manual-install)
- [3. Pasargad config (Xray inbound + user)](#3-pasargad-config-xray-inbound--user)
- [4. Foreign node — manual install](#4-foreign-node--manual-install)
- [5. Full central hub install](#5-full-central-hub-install)
- [6. Verification & troubleshooting](#6-verification--troubleshooting)
- [7. Final checklist](#7-final-checklist)

---

## 0. Prerequisites & sanity checks

| Item | Assumed value (change it) |
|------|---------------------------|
| Domain | `panel.example.ir` (points to the Iran server's IP) |
| Iran server | Public IP, Ubuntu 22.04+ |
| Foreign nodes | e.g. `trk01`, `nld01` … |
| rathole control port (local) | `127.0.0.1:2333` |
| Data port start (local, on Iran) | from `1001` |
| Management/API port start (local, on Iran) | from `7001` |
| Xray ws inbound on each node (local) | `127.0.0.1:<inbound>` (no TLS) |

**Before anything, check these on the Iran server:**

```bash
dig panel.example.ir +short         # must return the Iran server IP
sudo ss -ltnp | grep ':443'         # must be empty; only nginx should own 443
timedatectl                         # clock in sync; clock skew = TLS failure
sudo timedatectl set-ntp true       # if needed
```

> **Pessimism:**
> - Cloud firewall / security group: ports **443 and 80** must be open (80 for certbot).
> - If the domain is behind Cloudflare, start with **DNS-only** (grey cloud); Cloudflare's extra TLS layer is a source of weird trouble.
> - The rathole version **must be identical on the Iran server and all nodes** (`v0.5.0`).

---

## 1. Install the rathole binary (both roles)

Check the architecture with `uname -m`, then install the binary. **This step is identical on the Iran server and all nodes.**

```bash
cd /tmp
VER="v0.5.0"
# x86_64:
ARCH="x86_64-unknown-linux-gnu"
# aarch64 (ARM):  ARCH="aarch64-unknown-linux-musl"

curl -fsSL "https://github.com/rapiz1/rathole/releases/download/${VER}/rathole-${ARCH}.zip" -o rathole.zip
unzip -o rathole.zip
sudo install -m 755 rathole /usr/local/bin/rathole
rathole --version
```

> **GitHub blocked from inside Iran?** Two options:
> 1. Fetch the binary on a **foreign node** and `scp` it to the Iran server, then `install -m 755`.
> 2. Use mirrors (the same ones `install-panel.sh` tries as fallback):
>    `https://ghproxy.net/https://github.com/…` · `https://gh-proxy.com/https://github.com/…` · `https://mirror.ghproxy.com/https://github.com/…`
>
> Old glibc? Grab the `musl` build.

---

## 2. Iran server (panel) — manual install

These are the same steps as `install-panel.sh`, one at a time.

### 2.1 Prerequisites

```bash
sudo apt-get update -y
export DEBIAN_FRONTEND=noninteractive
# sshpass is needed for automated node provisioning from the panel/hub
sudo apt-get install -y nginx jq curl unzip openssl ca-certificates \
     certbot python3-certbot-nginx sshpass
```

### 2.2 Install `ratholectl`

From the `rathole-manager/` directory of the bundle:

```bash
sudo mkdir -p /etc/rathole /etc/rathole-manager /usr/local/share/rathole
sudo install -m 755 ratholectl        /usr/local/bin/ratholectl
sudo install -m 644 common.sh         /usr/local/share/rathole/common.sh
```

### 2.3 systemd unit for the server

```bash
sudo tee /etc/systemd/system/rathole-server.service >/dev/null <<'UNIT'
[Unit]
Description=rathole server (Iran panel)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/rathole /etc/rathole/server.toml
Restart=always
RestartSec=2
Environment=RUST_LOG=info
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
```

### 2.4 WebSocket upgrade map (once)

```bash
sudo tee /etc/nginx/conf.d/rathole-upgrade-map.conf >/dev/null <<'MAP'
# needed for WebSocket / HTTP Upgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAP
```

> **Pessimism:** this `map` must be defined **only once** in the http context; if it appears twice, `nginx -t` fails with `duplicate map`.

### 2.5 Resolve 443 conflicts

Any config already listening on 443 (e.g. an old panel) must move aside:

```bash
grep -rlE 'listen[[:space:]]+(\[::\]:)?443' /etc/nginx/sites-enabled /etc/nginx/conf.d
# Move the offending files into a backup dir (don't delete):
sudo mkdir -p /etc/nginx/rathole-backup-$(date +%Y%m%d-%H%M%S)
# Disable the nginx default site if it has default_server:
sudo rm -f /etc/nginx/sites-enabled/default
```

### 2.6 init — generate state and configs

The core principle: **change state → regenerate config → `nginx -t` → hot-reload.** Never hand-edit `server.toml` or `rathole.conf`; work only through `ratholectl`.

```bash
sudo ratholectl init \
  --domain     panel.example.ir \
  --fullchain  /root/cert/panel.example.ir/fullchain.pem \
  --key        /root/cert/panel.example.ir/privkey.pem
```

Optional `init` flags (the defaults are usually right):

| Flag | Default | Purpose |
|------|---------|---------|
| `--control-port` | `2333` | rathole local control port |
| `--fake-port` | `8080` | fake site / panel on root |
| `--sub-port` | `2096` | subscription |
| `--data-start` | `1001` | start of data port numbering |
| `--api-start` | `7001` | start of management port numbering |
| `--nginx-conf` | `/etc/nginx/conf.d/rathole.conf` | generated nginx config file |
| `--certbot` | — | obtain a cert via certbot if you have none |

> **Certificate:** if a cert already exists at the `--fullchain/--key` paths, it is used. Otherwise, if you pass `--certbot` (or confirm in interactive mode), `certbot` obtains a Let's Encrypt cert (requires DNS pointing here + port 80 free).

### 2.7 Test and bring up the service

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now rathole-server
sudo ratholectl doctor        # health check
```

> **Later updates:** `sudo ratholectl update` pulls the latest GitHub Release and
> runs the full snapshot + health-check + auto-rollback update. Same for
> `sudo ratholenode update` on a node. Both fall back through ghproxy mirrors, so
> they work from inside Iran. The hub's **Update** button does the same over SSH.

### 2.8 Add a node

Every time you add a node, `ratholectl` mutates state and regenerates + hot-reloads the configs (without dropping active tunnels):

```bash
# Data-only node:
sudo ratholectl add trk01 2087

# Node with a panel↔node management channel (a <name>_api service on 127.0.0.1):
sudo ratholectl add trk01 2087 --api-port 62050

sudo ratholectl ls                 # list nodes + user paths
sudo ratholectl show trk01         # prints the exact install command for that node
```

The output of `show` is exactly what you run on the foreign node — go to section [4](#4-foreign-node--manual-install).

> **Key reminder:** the node name (`trk01`) is simultaneously the **URL path**, the **nginx map entry**, and the **Xray inbound path on the node**. These three must stay identical, character for character.

---

## 3. Pasargad config (Xray inbound + user)

### The golden rule of path alignment

The path must be **identical in three places**, otherwise the user "connects but has no internet":

```
user VLESS config   =   nginx location   =   Xray node ws inbound path
      /trk01                /trk01                    /trk01
```

### Inbound on each node (in the Pasargad panel)

For node `trk01`:

- Protocol: **VLESS**
- Network: **ws**
- Path: **`/trk01`**  (the node name)
- Listen: **`127.0.0.1`**
- Port: the same `inbound` you gave to `ratholectl add` (here `2087`)
- TLS: **off** — nginx terminates TLS on the Iran server; turning it on here means double-TLS and breakage.

### User-side config (one domain, one port, one cert)

```
Address : panel.example.ir
Port    : 443
Network : ws
Path    : /trk01          ← to connect through node trk01
Host/SNI: panel.example.ir
TLS     : tls (on — because nginx has the Let's Encrypt cert)
```

To use another node, the user only changes `Path` (`/nld01`, etc.). **Everything else stays the same.**

### Panel↔node management channel (`_api`)

If you created the node with `--api-port`, a `<name>_api` service appears on `127.0.0.1:<api_local_port>` of the Iran server (`ratholectl show` tells you this port). In the Pasargad panel when adding the node:

- Set the node address to **`127.0.0.1`** (not the node's public IP)
- Set the API port to that `api_local_port` (e.g. `7001`)

because the node's API surfaced on the Iran server's localhost through the tunnel.

> **Hard pessimism (from the Pasargad doc):**
> - **Reality does not work behind nginx** — you must use **VLESS/VMess + WS**.
> - Bind the inbound to `127.0.0.1`, not `0.0.0.0`; otherwise the node port leaks directly and the "one port" logic breaks.
> - The Pasargad-node internal cert (panel↔node authentication) is separate from Let's Encrypt and is still required.
>
> Full details and three-layer troubleshooting in the [Pasargad doc](../rathole-multilocation-pasargad.md) (Persian).

---

## 4. Foreign node — manual install

### The easy way: with the installer

`ratholectl show <name>` on the Iran server gives you exactly this. From the `rathole-manager/` directory on the node:

```bash
sudo bash install-node.sh --server panel.example.ir:443 --name trk01 \
     --token <TOKEN> --inbound-port 2087 \
     [--api-token <API_TOKEN> --api-inbound-port 62050]
```

The installer: installs rathole, copies `ratholenode` and `common.sh`, creates the `rathole-client` unit, writes `node.env` and `services.conf`, and starts the client.

### The fully manual way (no installer)

If you want to build each file yourself:

```bash
# 1) rathole installed per section 1
sudo mkdir -p /etc/rathole /usr/local/share/rathole
sudo install -m 755 ratholenode /usr/local/bin/ratholenode
sudo install -m 644 common.sh   /usr/local/share/rathole/common.sh

# 2) client systemd unit
sudo tee /etc/systemd/system/rathole-client.service >/dev/null <<'UNIT'
[Unit]
Description=rathole client (foreign node)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/rathole /etc/rathole/client.toml
Restart=always
RestartSec=2
Environment=RUST_LOG=info
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
```

Then `client.toml` (exactly what `install-node.sh` generates):

```toml
# /etc/rathole/client.toml — on the foreign node
[client]
remote_addr = "panel.example.ir:443"
retry_interval = 1
heartbeat_timeout = 40

[client.transport]
type = "websocket"
[client.transport.websocket]
tls = true
[client.transport.tls]
hostname = "panel.example.ir"

# data service: publishes this node's Xray ws inbound
[client.services.trk01]
token = "<TOKEN>"
local_addr = "127.0.0.1:2087"
type = "tcp"

# (optional) management channel — only if you passed --api-port
[client.services.trk01_api]
token = "<API_TOKEN>"
local_addr = "127.0.0.1:62050"
type = "tcp"
```

```bash
sudo systemctl enable --now rathole-client
journalctl -u rathole-client -f      # should print "control channel established"
```

> **Pessimism:**
> - `remote_addr` is the same for all nodes: `panel.example.ir:443`. Nodes differ only in **service name and token**.
> - The client's `heartbeat_timeout` (`40`) **must** be greater than the server's `heartbeat_interval` (`30`), otherwise the tunnel keeps flapping.
> - `hostname` must match the cert domain exactly, otherwise `certificate verify failed`.
> - Compare tokens against `ratholectl show` output **character by character**.

### More services / upstreams on the same node

```bash
# Another service (IP/inbound) over the same tunnel:
sudo ratholenode add-svc <name> <token> <inbound>

# Attach this node to a second Iran server (multi-location):
sudo ratholenode upstream add <id> <server:443>
sudo ratholenode upstream add-svc <id> <name> <token> <inbound>

sudo ratholenode backup              # back up node state
sudo ratholenode update              # full update from GitHub (latest Release; snapshot + auto-rollback)
```

---

## 5. Full central hub install

The hub (`ratholehub`) is a single-file web panel (Python stdlib) installed on **one management server** (usually the Iran panel itself) that runs `ratholectl`/`ratholenode` on the other servers over **SSH with a key**, using a **validated argv** — never a raw shell string. It listens on `127.0.0.1`.

### 5.1 Install

```bash
cd rathole-manager/ratholehub
sudo bash install-hub.sh          # asks for an admin password, generates an API TOKEN
```

The installer does:

- `hub.py` → `/opt/ratholehub/hub.py`
- copies `ratholectl`/`ratholenode`/`update.sh`/… into `/opt/ratholehub/bundle/` (for remote deploy)
- generates `/etc/ratholehub/config.json` (containing `api_token`, admin password hash, SSH key path) and an empty `inventory.json`
- a `ratholehub.service` unit on `127.0.0.1:8088` (`HUB_PORT` env overrides)
- creates the hub SSH key: `/root/.ssh/id_ed25519`

> `config.json` contains the token and password hash; it is `chmod 600` and **must never** be committed or leaked.

### 5.2 Authorize the SSH key on each server

The hub connects only with the SSH key (no password). Put the hub's public key on every server you want to manage:

```bash
# on the hub server:
ssh-copy-id -i /root/.ssh/id_ed25519.pub -p 22 root@<server_ip>
# test:
ssh -i /root/.ssh/id_ed25519 root@<server_ip> 'ratholenode show || ratholectl ls'
```

### 5.3 Access the panel

**The secure way (opening no port)** — SSH local-forward from your own machine:

```bash
ssh -L 8088:127.0.0.1:8088 root@<hub_ip>
# browser:  http://localhost:8088
```

**Or behind nginx under the same domain** — if the hub is on the same Iran panel server, `install-hub.sh` does this automatically; otherwise, manually:

```bash
sudo ratholectl hub on 8088          # persistent location /hub/ behind nginx
# first run: auto-installs the hub too (install-hub.sh, asks for the admin password)
# later runs: changes the hub's real listen_port + restarts ratholehub + updates nginx
# access:  https://panel.example.ir/hub/
sudo ratholectl hub status           # also shows ratholehub service state and port-mismatch warnings
sudo ratholectl hub off              # remove from nginx (the service keeps running on 127.0.0.1)
```

> Since `hub on` makes the panel public, make sure you set a **strong password**.

### 5.4 REST API (example)

Every route uses the `Authorization: Bearer <API_TOKEN>` header (or the UI session cookie):

```bash
TOKEN=... ; B=http://localhost:8088
curl -s -H "Authorization: Bearer $TOKEN" $B/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST $B/api/servers/rp01/action \
  -d '{"action":"kcp_on","args":{"port":"443","profile":"balanced"}}'
```

Full allow-listed actions and security model: [`docs/hub.md`](hub.md) (Persian).

---

## 6. Verification & troubleshooting

### Golden debug commands

```bash
# On the Iran server: are the local ports open?
sudo ss -ltnp | grep -E '2333|1001|7001'
# nginx on 443?
sudo ss -ltnp | grep ':443'
# On the node: does the Xray inbound actually respond?
curl -v http://127.0.0.1:2087
# Logs on both ends simultaneously:
journalctl -u rathole-server -f   # Iran
journalctl -u rathole-client -f   # node
```

### Troubleshooting table

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Node keeps "retrying" | wrong domain/port, nginx down, firewall | `curl -v https://panel.example.ir` and `ss -ltnp` |
| Drops immediately after connecting | token mismatch | compare against `ratholectl show` |
| User connects but has no internet | **three-way path mismatch** | user path = nginx = Xray |
| Node offline in the panel | `_api` channel not set / wrong port | check the `_api` service and `api_local_port` |
| `certificate verify failed` | hostname doesn't match the cert | `hostname` = real domain |
| WebSocket `400/502` | nginx not passing the Upgrade header | the `map` and `proxy_set_header`s |
| Tunnel drops every 60s | low nginx timeout | don't touch the generated config; `ratholectl regen` |
| `duplicate default server` | old server block on 443 | section [2.5](#25-resolve-443-conflicts) |
| `ratholehub` won't come up | config/python error | `journalctl -u ratholehub -n 30` |

> **Golden method:** start from the lowest layer — 1) does the Xray inbound respond locally on the node? → 2) are the rathole services (`_data`/`_api`) established? → 3) is nginx proxying the path correctly? → 4) is TLS/DNS healthy from the outside?

---

## 7. Final checklist

- [ ] `rathole` at the **same version** (`v0.5.0`) on Iran and all nodes.
- [ ] Domain DNS points to the Iran server IP; ports 443 and 80 open on the firewall.
- [ ] Only nginx sits on 443 (not Xray directly, not an old panel).
- [ ] Cert obtained and `nginx -t` clean; `map $http_upgrade` defined only once.
- [ ] `rathole-server` on Iran and `rathole-client` on each node **active and enabled**.
- [ ] For nodes needing management, `--api-port` was given (the `_api` service).
- [ ] Tokens match `ratholectl show` exactly; all `bind_addr`/`local_addr` on `127.0.0.1`.
- [ ] Client `heartbeat_timeout` (40) > server `heartbeat_interval` (30).
- [ ] **Path identical in three places:** user config = nginx = Xray inbound.
- [ ] Xray inbound on the node is **TLS-off** and on `127.0.0.1`; protocol **VLESS+WS** (not Reality).
- [ ] In the panel, node address is `127.0.0.1` and the API port is `70xx`.
- [ ] All servers' clocks in sync; both ends log "control channel established".
- [ ] (Hub) the hub SSH key is authorized on every server in the inventory.
- [ ] End-to-end connection tested from a real user client.

---

**Full CLI reference & automated install:** [`README.fa.md`](README.fa.md) (Persian) · **Design & deep pessimism:** [Pasargad doc](../rathole-multilocation-pasargad.md) (Persian) · **Hub:** [`hub.md`](hub.md)
