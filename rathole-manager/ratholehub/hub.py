#!/usr/bin/env python3
# ratholehub — panel mrkzi mdirit tunnel rathole/kcp (REST API + UI)
# - bedoon vabstgi pip (fght stdlib)
# - pshtshnh: ejra-ye ratholectl/ratholenode rooye serverha az trigh SSH (kelid)
# - rooye 127.0.0.1 mishnvd; nginx zir damnhi TLS srvsh midahad (yek port/yek damnh hefz mishavad)
#
# tanzimat:  /etc/ratholehub/config.json   , inventory: /etc/ratholehub/inventory.json
# mtghirhai mhiti baraye tst lvkal: RATHOLEHUB_CONF, RATHOLEHUB_INV, RATHOLEHUB_MOCK=1
import os, sys, json, hmac, hashlib, time, subprocess, re, secrets, threading, shlex, shutil


from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CONF_PATH = os.environ.get("RATHOLEHUB_CONF", "/etc/ratholehub/config.json")
INV_PATH  = os.environ.get("RATHOLEHUB_INV",  "/etc/ratholehub/inventory.json")
MOCK      = os.environ.get("RATHOLEHUB_MOCK") == "1"
AUDIT_PATH = os.environ.get("RATHOLEHUB_AUDIT", "/etc/ratholehub/audit.log")

# ---------- tanzimat va inventory ----------
# RLock (na Lock) ta helper-haye atomic betavanand read-modify-write ra yekja
# ghofl konand va daroon-esh save_config/set_inventory (ke khodeshan ghofl migirand) seda bezanand.
_lock = threading.RLock()

# mhdvdsazi nrkhe tlashe vrvd (zde brute-force). kelid = IP.
_LOGIN_FAILS = {}
_LOGIN_MAX = 5            # hdaksr tlashe namvfgh
_LOGIN_WINDOW = 300       # pnjrhi sanihai
_login_lock = threading.Lock()

def login_allowed(ip):
    now = time.time()
    with _login_lock:
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < _LOGIN_WINDOW]
        _LOGIN_FAILS[ip] = fails
        return len(fails) < _LOGIN_MAX

def login_record_fail(ip):
    now = time.time()
    with _login_lock:
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < _LOGIN_WINDOW]
        fails.append(now)
        _LOGIN_FAILS[ip] = fails

def login_reset(ip):
    with _login_lock:
        _LOGIN_FAILS.pop(ip, None)

# mghadir pishfrze naamn ke hrgz nbaid dar mohit vaghai estefade shavand.
_INSECURE_TOKEN = "changeme"
_INSECURE_PW_SHA = hashlib.sha256(b"admin").hexdigest()

def load_json(path, default):
    """khvandn JSON. fght "nbvde file" bhsvrt default brmigrdd;
    faile khrab/ghirghablkhvandn khata midahad ta ba kanfige pishfrze naamn ejra nshvim."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        raise RuntimeError("khvandn %s shekast khord (file khrab ya bedoon dstrsi?): %s" % (path, e))


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
def _strip_ansi(s):
    return _ANSI.sub("", s or "")

def get_config():
    cfg = load_json(CONF_PATH, {
        "api_token": _INSECURE_TOKEN,
        "admin_password_sha256": _INSECURE_PW_SHA,
        "listen_host": "127.0.0.1", "listen_port": 8088,
        "ssh_key_path": "", "ssh_opts": ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                                          "-o", "StrictHostKeyChecking=accept-new"],
        "bundle_dir": "/opt/ratholehub/bundle",
    })
    cfg["_insecure"] = (cfg.get("api_token") == _INSECURE_TOKEN
                        or cfg.get("admin_password_sha256") == _INSECURE_PW_SHA)
    return cfg

def get_inventory():
    inv = load_json(INV_PATH, [])
    return inv if isinstance(inv, list) else []

def set_inventory(inv):
    with _lock:
        save_json(INV_PATH, inv)

def update_inventory(mutator):
    # read-modify-write-e atomic: kolle chrkhe zir-e _lock ta do darkhast-e hamzaman
    # (ThreadingHTTPServer) update-e hamdigar ra pak nakonand. mutator(inv) -> inv-e jadid.
    with _lock:
        inv = get_inventory()
        new_inv = mutator(inv)
        if new_inv is not None:
            save_json(INV_PATH, new_inv)
        return new_inv

def save_config(cfg):
    # fildhai dakhli (ba _ shrva) zkhirh nmishvnd.
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    with _lock:
        save_json(CONF_PATH, clean)
        try:
            os.chmod(CONF_PATH, 0o600)
        except Exception:
            pass

def update_config(mutator):
    # read-modify-write-e atomic baraye config (mesl update_inventory).
    with _lock:
        cfg = get_config()
        new_cfg = mutator(cfg)
        save_config(new_cfg if new_cfg is not None else cfg)
        return new_cfg if new_cfg is not None else cfg

def audit_log(user, server, action, cmd, rc):
    # sbte append-only az har amliate nvshtari baraye rdgiri.
    try:
        line = json.dumps({
            "ts": int(time.time()), "user": user, "server": server,
            "action": action, "cmd": cmd, "rc": rc,
        }, ensure_ascii=False)
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with _lock:
            with open(AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass  # log nbaid masir asli ra bshknd

def read_audit(limit=100):
    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        out.reverse()
        return out
    except FileNotFoundError:
        return []
    except Exception:
        return []

# ---------- vaziat-e khod-e server-e hub (uptime/load/mem/disk/serviceha) ----------
_HUB_START = time.time()

# noskhe-i ke hub «akharin» midanad: az MANAGER_VERSION-e common.sh (bundle ke deploy mishavad)
# khande mishavad ta ba noskhe-ye nasb-shode rooye har server moghayese shavad. fallback: rشته-ye sabet.
HUB_FALLBACK_VERSION = "1.4.7"
def hub_manager_version():
    cands = []
    try:
        cands.append(os.path.join(get_config().get("bundle_dir", ""), "rathole-manager", "common.sh"))
        cands.append(os.path.join(get_config().get("bundle_dir", ""), "common.sh"))
    except Exception:
        pass
    cands += ["/opt/ratholehub/bundle/rathole-manager/common.sh",
              "/usr/local/bin/common.sh", "/etc/rathole-manager/common.sh"]
    for p in cands:
        try:
            if p and os.path.isfile(p):
                with open(p, encoding="utf-8", errors="ignore") as f:
                    m = re.search(r'^\s*MANAGER_VERSION="?([^"\s]+)"?', f.read(), re.M)
                    if m:
                        return m.group(1)
        except Exception:
            continue
    return HUB_FALLBACK_VERSION

def hub_status():
    # hame-ye bakhsh-ha best-effort hastand; rooye system-haye bedoon /proc ya systemctl
    # (masalan test-e local rooye Windows/Mac) faghat field-haye mojood barmigardand.
    st = {"time": int(time.time()), "mock": MOCK,
          "hub_uptime": int(time.time() - _HUB_START),
          "python": "%d.%d.%d" % sys.version_info[:3]}
    try:
        with open("/proc/uptime") as f:
            st["uptime"] = int(float(f.read().split()[0]))
    except Exception:
        pass
    try:
        st["load"] = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        pass
    try:
        mi = {}
        with open("/proc/meminfo") as f:
            for ln in f:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    mi[k.strip()] = int(v.strip().split()[0])
        if mi.get("MemTotal"):
            st["mem_total_kb"] = mi["MemTotal"]
            st["mem_avail_kb"] = mi.get("MemAvailable", 0)
    except Exception:
        pass
    try:
        du = shutil.disk_usage("/")
        st["disk_total"] = du.total
        st["disk_free"] = du.free
    except Exception:
        pass
    svcs = {}
    if shutil.which("systemctl"):
        for u in ("ratholehub", "nginx"):
            try:
                r = subprocess.run(["systemctl", "is-active", u],
                                   capture_output=True, text=True, timeout=5)
                svcs[u] = (r.stdout or "").strip() or "unknown"
            except Exception:
                svcs[u] = "unknown"
    st["services"] = svcs
    st["latest_version"] = hub_manager_version()
    return st

# ---------- aatbarsnji vrvdi (zd tzrigh) ----------
# nokte: anchor ba \Z (na $) chvn dar Python `$` yek newline-e entehai ra ham
# ghabool mikonad (masalan "trk01\n") — ke mitavanad be command-e SSH/audit tzrigh shavad.
RE_NAME    = re.compile(r"^[A-Za-z0-9_-]{1,40}\Z")
RE_HOST    = re.compile(r"^[A-Za-z0-9_.-]{1,255}\Z")
RE_PORT    = re.compile(r"^[0-9]{1,5}\Z")
RE_PROFILE = re.compile(r"^(balanced|lossy|aggressive)\Z")
RE_IPPORT  = re.compile(r"^[A-Za-z0-9_.-]{1,255}:[0-9]{1,5}\Z")
RE_KEY     = re.compile(r"^[A-Fa-f0-9]{8,64}\Z")
RE_B64     = re.compile(r"^[A-Za-z0-9+/]{40,64}={0,2}\Z")   # kelid-e omomi-ye noise (base64)
RE_ID      = re.compile(r"^[A-Za-z0-9_-]{1,40}\Z")
RE_PW      = re.compile(r"^.{6,128}\Z")   # hdaghl 6 karaktr baraye ramz
RE_EMAIL   = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,20}\Z")
RE_PATH    = re.compile(r"^/[A-Za-z0-9_./-]{1,255}\Z")   # masir file gvahi (mtlgh)
RE_SLUG    = re.compile(r"^[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,64}\Z")   # owner/repo-ye GitHub
RE_HEADER  = re.compile(r"^[A-Za-z0-9-]{1,40}\Z")   # naam-e header-e masiryabi-ye direct

# ---------- whitelist dstvrha (bedoon shl dlkhvah) ----------
# har action → sazndhi argumenthaye amn. brmigrdand list arg baraye CLI.
def build_iran_cmd(action, a):
    if action == "ls":         return ["ratholectl", "ls"]
    if action == "doctor":     return ["ratholectl", "doctor"]
    if action == "kcp_status": return ["ratholectl", "kcp", "status"]
    if action == "kcp_off":    return ["ratholectl", "kcp", "off"]
    if action == "tune":       return ["ratholectl", "tune"]
    if action == "regen":      return ["ratholectl", "regen"]
    if action == "fakeweb_start":
        port = str(a.get("port", "") or "")
        cmd = ["ratholectl", "fakeweb", "start"]
        if port:
            if not RE_PORT.match(port): return None
            cmd.append(port)
        return cmd
    if action == "fakeweb_stop":   return ["ratholectl", "fakeweb", "stop"]
    if action == "fakeweb_rm":     return ["ratholectl", "fakeweb", "rm"]
    if action == "fakeweb_status": return ["ratholectl", "fakeweb", "status"]
    if action == "restart":        return ["ratholectl", "restart"]
    if action == "status":         return ["ratholectl", "status", "--json"]
    if action == "paths":          return ["ratholectl", "paths"]
    if action == "version":        return ["ratholectl", "version"]
    # ---- damnh / gvahi TLS ----
    if action == "tls_info":   return ["ratholectl", "info"]
    if action == "tls_certs":  return ["ratholectl", "certs"]
    if action == "domain_primary":
        d = str(a.get("domain","") or "")
        if not RE_HOST.match(d): return None
        cmd = ["ratholectl", "domain", "primary", d]
        if a.get("certbot"): cmd.append("--certbot")
        em = str(a.get("email","") or "")
        if em:
            if not RE_EMAIL.match(em): return None
            cmd += ["--email", em]
        fc = str(a.get("fullchain","") or "")
        if fc:
            if not RE_PATH.match(fc): return None
            cmd += ["--fullchain", fc]
        ky = str(a.get("key","") or "")
        if ky:
            if not RE_PATH.match(ky): return None
            cmd += ["--key", ky]
        return cmd
    if action == "domain_ls":  return ["ratholectl", "domain", "ls"]
    if action == "domain_rm":
        d = str(a.get("domain","") or "")
        if not RE_HOST.match(d): return None
        return ["ratholectl", "domain", "rm", d]
    if action == "domain_add":
        d = str(a.get("domain","") or "")
        if not RE_HOST.match(d): return None
        cmd = ["ratholectl", "domain", "add", d]
        if a.get("certbot"): cmd.append("--certbot")
        em = str(a.get("email","") or "")
        if em:
            if not RE_EMAIL.match(em): return None
            cmd += ["--email", em]
        fc = str(a.get("fullchain","") or "")
        if fc:
            if not RE_PATH.match(fc): return None
            cmd += ["--fullchain", fc]
        ky = str(a.get("key","") or "")
        if ky:
            if not RE_PATH.match(ky): return None
            cmd += ["--key", ky]
        return cmd
    if action == "tls_cert":
        domain = a.get("domain", ""); email = str(a.get("email", "") or "")
        if not RE_HOST.match(domain): return None
        cmd = ["ratholectl", "cert", domain]
        if email:
            if not RE_EMAIL.match(email): return None
            cmd.append(email)
        return cmd
    if action == "kcp_show":   return ["ratholectl", "kcp", "show"]
    if action == "kcp_on":
        port = a.get("port", "443"); profile = a.get("profile", "balanced")
        if not RE_PORT.match(str(port)) or not RE_PROFILE.match(str(profile)): return None
        return ["ratholectl", "kcp", "on", str(port), str(profile)]
    # ---- plain: tunnel-e websocket bedoon-e TLS (listener HTTP rooye port jda) ----
    if action == "plain_status": return ["ratholectl", "plain", "status"]
    if action == "plain_show":   return ["ratholectl", "plain", "show"]
    if action == "plain_off":    return ["ratholectl", "plain", "off"]
    if action == "plain_on":
        port = str(a.get("port", "8880") or "8880")
        if not RE_PORT.match(port): return None
        return ["ratholectl", "plain", "on", port]
    # ---- direct-IP: masiryabi ba header rooye port-e sade (bedoon TLS/auth) ----
    if action == "direct_status": return ["ratholectl", "direct", "status"]
    if action == "direct_show":   return ["ratholectl", "direct", "show"]
    if action == "direct_off":    return ["ratholectl", "direct", "off"]
    if action == "direct_on":
        port   = str(a.get("port", "8081") or "8081")
        header = str(a.get("header", "X-Cdn-Id") or "X-Cdn-Id")
        if not RE_PORT.match(port):     return None
        if not RE_HEADER.match(header): return None
        return ["ratholectl", "direct", "on", "--port", port, "--header", header]
    # ---- noise: tunnel-e ramznegari-shode (Noise) rooye instans-e dovom ----
    if action == "noise_status": return ["ratholectl", "noise", "status"]
    if action == "noise_show":   return ["ratholectl", "noise", "show"]
    if action == "noise_off":    return ["ratholectl", "noise", "off"]
    if action == "noise_on":
        port = str(a.get("port", "2334") or "2334")
        if not RE_PORT.match(port): return None
        return ["ratholectl", "noise", "on", port]
    if action in ("noise_node_on", "noise_node_off"):
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "noise", "node", name, ("on" if action == "noise_node_on" else "off")]
    # ---- service game (SNI rooye 443 + TLS rooye node) ----

    if action == "game_ls":   return ["ratholectl", "game", "ls"]
    if action == "game_show":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "game", "show", name]
    if action == "game_add":
        name = a.get("name", ""); inbound = str(a.get("inbound", "")); sni = a.get("sni", "")
        if not RE_NAME.match(name) or not RE_PORT.match(inbound) or not RE_HOST.match(sni): return None
        return ["ratholectl", "game", "add", name, inbound, sni]
    if action == "game_rm":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "game", "rm", name]
    if action == "game_cert":
        sni = a.get("sni", "")
        if not RE_HOST.match(sni): return None
        return ["ratholectl", "game", "cert", sni]
    # ---- mdirit node aadi ----
    if action == "add_node":
        name = a.get("name", ""); inbound = str(a.get("inbound", "")); api = str(a.get("api_port", "") or "")
        if not RE_NAME.match(name) or not RE_PORT.match(inbound): return None
        cmd = ["ratholectl", "add", name, inbound]
        if api:
            if not RE_PORT.match(api): return None
            cmd += ["--api-port", api]
        return cmd
    if action == "rm_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "rm", name]
    if action == "show_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "show", name]
    if action == "edit_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        cmd = ["ratholectl", "edit", name]
        inbound = str(a.get("inbound", "") or "")
        if inbound:
            if not RE_PORT.match(inbound): return None
            cmd += ["--inbound", inbound]
        api = str(a.get("api_port", "") or "")
        if api:
            if api != "off" and not RE_PORT.match(api): return None
            cmd += ["--api-port", api]
        if len(cmd) == 3: return None  # hich tghiiri dade nashode
        return cmd
    if action == "rename_node":
        old = a.get("old", ""); new = a.get("new", "")
        if not RE_NAME.match(old) or not RE_NAME.match(new): return None
        return ["ratholectl", "rename", old, new]
    if action == "rotate_node":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "rotate", name]
    if action == "set_config":
        key = a.get("key", ""); val = str(a.get("value", ""))
        if key not in ("domain", "fullchain", "key", "nginx-conf",
                       "fake-port", "sub-port", "control-port"): return None
        if key in ("fake-port", "sub-port", "control-port"):
            if not RE_PORT.match(val): return None
        elif key in ("domain",):
            if not RE_HOST.match(val): return None
        else:
            # fullchain/key/nginx-conf: masir-e file-e motlagh.
            # HATMAN ba RE_PATH etebar-sanji shavad — SSH argv ra be shl-e remote
            # micharband, pas har metachar-e shl (; | & $() `) inja RCE mishavad.
            if not RE_PATH.match(val): return None
        return ["ratholectl", "set", key, val]
    if action == "backup":
        return ["ratholectl", "backup"]
    if action == "enable":
        return ["ratholectl", "enable"]
    if action == "regen_full":
        return ["ratholectl", "regen"]
    if action == "hub_status":
        return ["ratholectl", "hub", "status"]
    return None

def build_node_cmd(action, a):
    if action == "show":        return ["ratholenode", "show"]
    if action == "ls":          return ["ratholenode", "ls"]
    if action == "upstream_ls": return ["ratholenode", "upstream", "ls"]
    if action == "kcp_status":  return ["ratholenode", "kcp", "status"]
    if action == "kcp_off":     return ["ratholenode", "kcp", "off"]
    if action == "plain_status": return ["ratholenode", "plain", "status"]
    if action == "plain_off":    return ["ratholenode", "plain", "off"]
    if action == "plain_on":
        remote = a.get("remote", "")
        if not RE_IPPORT.match(remote): return None
        return ["ratholenode", "plain", "on", remote]
    if action == "noise_status": return ["ratholenode", "noise", "status"]
    if action == "noise_off":    return ["ratholenode", "noise", "off"]
    if action == "noise_on":
        remote = a.get("remote", "")
        pubkey = a.get("pubkey", "")
        if not RE_IPPORT.match(remote): return None
        if not RE_B64.match(pubkey): return None
        cmd = ["ratholenode", "noise", "on", remote, pubkey]
        pattern = a.get("pattern", "")
        if pattern:
            if not RE_HOST.match(pattern): return None
            cmd.append(pattern)
        return cmd
    if action == "migrate":     return ["ratholenode", "migrate"]

    if action == "tune":        return ["ratholenode", "tune"]
    if action == "apply":       return ["ratholenode", "apply"]
    if action == "kcp_on":
        remote = a.get("remote", ""); key = a.get("key", ""); profile = a.get("profile", "balanced")
        if not RE_IPPORT.match(remote) or not RE_KEY.match(key) or not RE_PROFILE.match(profile): return None
        return ["ratholenode", "kcp", "on", remote, key, profile]
    if action == "upstream_kcp_on":
        uid = a.get("id", ""); remote = a.get("remote", ""); key = a.get("key", ""); profile = a.get("profile", "balanced")
        if not RE_ID.match(uid) or not RE_IPPORT.match(remote) or not RE_KEY.match(key) or not RE_PROFILE.match(profile): return None
        return ["ratholenode", "upstream", "kcp", uid, "on", remote, key, profile]
    if action == "upstream_kcp_off":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "kcp", uid, "off"]
    if action == "upstream_kcp_status":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "kcp", uid, "status"]
    if action == "upstream_apply":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "apply", uid]
    if action == "upstream_restart":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "restart", uid]
    if action == "restart":
        return ["ratholenode", "restart"]
    if action == "version":
        return ["ratholenode", "version"]
    if action == "set_server":
        # tunnel-e asli (main) ra be yek server Iran vasl mikonad: host ya host:port
        server = a.get("server", "")
        if not (RE_IPPORT.match(server) or RE_HOST.match(server)): return None
        return ["ratholenode", "set", "SERVER", server]
    if action == "watchdog_on":
        iv = str(a.get("interval", "60") or "60")
        if not RE_PORT.match(iv): return None
        return ["ratholenode", "watchdog", "on", iv]
    if action == "watchdog_off":    return ["ratholenode", "watchdog", "off"]
    if action == "watchdog_status": return ["ratholenode", "watchdog", "status"]
    if action == "logs":
        return ["ratholenode", "logs", "40"]
    # ---- mdirit service rooye node ----
    if action == "add_svc":
        name = a.get("name", ""); token = a.get("token", ""); inbound = str(a.get("inbound", ""))
        if not RE_NAME.match(name) or not RE_KEY.match(token) or not RE_PORT.match(inbound): return None
        return ["ratholenode", "add-svc", name, token, inbound]
    if action == "rm_svc":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholenode", "rm-svc", name]
    if action == "upstream_add":
        uid = a.get("id", ""); server = a.get("server", ""); host = a.get("host", "")
        if not RE_ID.match(uid) or not RE_IPPORT.match(server): return None
        cmd = ["ratholenode", "upstream", "add", uid, server]
        if host:
            if not RE_HOST.match(host): return None
            cmd.append(host)
        return cmd
    if action == "upstream_add_svc":
        uid = a.get("id", ""); name = a.get("name", ""); token = a.get("token", ""); inbound = str(a.get("inbound", ""))
        if not RE_ID.match(uid) or not RE_NAME.match(name) or not RE_KEY.match(token) or not RE_PORT.match(inbound): return None
        return ["ratholenode", "upstream", "add-svc", uid, name, token, inbound]
    if action == "upstream_rm_svc":
        uid = a.get("id", ""); name = a.get("name", "")
        if not RE_ID.match(uid) or not RE_NAME.match(name): return None
        return ["ratholenode", "upstream", "rm-svc", uid, name]
    if action == "upstream_rm":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "rm", uid]
    return None


WRITE_ACTIONS = {
    # iran
    "add_node", "rm_node", "edit_node", "rename_node", "rotate_node",
    "set_config", "kcp_on", "kcp_off", "game_add", "game_rm", "game_cert",
    "tls_cert", "domain_add", "domain_rm", "domain_primary",
    "fakeweb_start", "fakeweb_stop", "fakeweb_rm", "tune", "restart",
    "plain_on", "plain_off",
    "direct_on", "direct_off",
    "noise_on", "noise_off", "noise_node_on", "noise_node_off",

    "backup", "enable", "regen_full", "regen",
    # node
    "add_svc", "rm_svc", "kcp_on", "kcp_off", "apply", "restart", "set_server",
    "upstream_add", "upstream_add_svc", "upstream_rm", "upstream_rm_svc",
    "upstream_kcp_on", "upstream_kcp_off", "upstream_apply", "upstream_restart",

    "watchdog_on", "watchdog_off", "migrate", "deploy",

}

def build_cmd(role, action, args):
    return build_iran_cmd(action, args) if role == "iran" else build_node_cmd(action, args)

# ---------- ejra-ye az rah dvr (SSH) ----------
def run_on_server(server, cmd_args, timeout=120):
    if MOCK:
        return mock_run(server, cmd_args)
    cfg = get_config()
    ssh = _ssh_base(cfg, server) + cmd_args  # har arg jda; ssh ba space be shl rimvt midahad
    try:
        p = subprocess.run(ssh, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "out": _strip_ansi(p.stdout), "err": _strip_ansi(p.stderr)}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "SSH timeout"}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}

def _ssh_base(cfg, server):
    ssh = ["ssh"] + list(cfg.get("ssh_opts", []))
    if cfg.get("ssh_key_path"):
        ssh += ["-i", cfg["ssh_key_path"]]
    ssh += ["-p", str(server.get("ssh_port", 22)),
            "%s@%s" % (server.get("ssh_user", "root"), server["host"]), "--"]
    return ssh

def iran_main_server(s):
    # maghsad-e daghigh-e tunnel-e asli (SERVER=domain:443) ra az yek server-e Iran migirad.
    # dar halat-e pishfarz (ws+TLS) node bayad be DOMAIN vasl shavad (na host/IP-e SSH), chon
    # ratholenode az SERVER ham remote_addr va ham SNI ra misazad. domain ra az 'status --json'
    # migirim; agar darnayamad be host-e inventory fallback mikonim.
    # bazgasht: (server_str, domain)  — masalan ("rp01.l1t.ir:443", "rp01.l1t.ir")
    domain = ""
    try:
        st = run_on_server(s, ["ratholectl", "status", "--json"])
        d = json.loads(st.get("out", "") or "{}")
        domain = str(d.get("domain", "") or "").strip()
    except (ValueError, TypeError):
        domain = ""
    if domain and RE_HOST.match(domain):
        return "%s:443" % domain, domain
    host = str(s.get("host", ""))
    return ("%s:443" % host if host else ""), ""

def deploy_to_server(server):
    # apdit az GitHub: install.sh-e akharin Release ra rooye server migirad (ba mirror-haye
    # ghproxy baraye dor zadan-e filtering) va ba --update ejra mikonad. digar be bundle-e
    # mahalli-ye hub vabaste nist — server hamishe akharin noskhe-ye montasher-shode ra migirad.
    if MOCK:
        return {"rc": 0, "out": "[mock deploy→%s] github install.sh --update (akharin Release)" % server.get("name"), "err": ""}
    cfg = get_config()
    # slug az config (sabet، na vorodi-ye karbar) va ba regex etebarsanji mishavad.
    gh = str(cfg.get("gh_repo", "loopy-iri/RatholeEngine"))
    if not RE_SLUG.match(gh):
        return {"rc": 1, "out": "", "err": "gh_repo namotabar dar config: %r" % gh}
    base = _ssh_base(cfg, server)
    # yek script-e khoddATka ke rooye server ejra mishavad. tanha meghdar-e tazrigh-shode
    # slug-e etebarsanji-shode ast (RE_SLUG). mirror-ha hamsan-e install.sh/install-panel.sh.
    remote = r'''set -e
GH="%s"
URL="https://github.com/$GH/releases/latest/download/install.sh"
T="$(mktemp)"
trap 'rm -f "$T"' EXIT
ok=0
for M in "" "https://ghproxy.net/" "https://gh-proxy.com/" "https://mirror.ghproxy.com/"; do
  if curl -fsSL --connect-timeout 20 --retry 2 "${M}${URL}" -o "$T" 2>/dev/null; then ok=1; break; fi
done
[ "$ok" = 1 ] || { echo "download install.sh az hameye mirror-ha shekast khord (filtering?)" >&2; exit 1; }
RATHOLE_GH="$GH" bash "$T" --update
''' % gh
    try:
        r = subprocess.run(base + ["bash", "-c", remote],
                           capture_output=True, text=True, timeout=600)
        return {"rc": r.returncode, "out": _strip_ansi(r.stdout), "err": _strip_ansi(r.stderr)}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "SSH timeout (apdit-e GitHub bish az 600s tool keshid)"}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}

# ---------- provision khodkar (ba ramz SSH → nصب kelid + deploy + sabt) ----------
def ensure_hub_key():
    # motmaen mishavad hub yek jft-kelid SSH darad; agar nabashad misazad va masir ra dar config zakhire mikonad.
    cfg = get_config()
    kp = cfg.get("ssh_key_path") or "/etc/ratholehub/id_ed25519"
    pub = kp + ".pub"
    if not (os.path.exists(kp) and os.path.exists(pub)):
        os.makedirs(os.path.dirname(kp), exist_ok=True)
        # agar yeki az do file nesfe-nim bashad, pak kon ta ssh-keygen gير nakonad
        for f in (kp, pub):
            try: os.remove(f)
            except OSError: pass
        r = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "ratholehub", "-f", kp, "-q"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not os.path.exists(pub):
            raise RuntimeError("ssh-keygen shekast: " + (r.stderr or r.stdout or "?"))
        try: os.chmod(kp, 0o600)
        except OSError: pass
    if cfg.get("ssh_key_path") != kp:
        # atomic: faghat ssh_key_path ra rooye naskhe-ye taze bezan (na kolle cfg-e bayat)
        # ta ba _config_save-e hamzaman (masalan taghir-e ramz) race nakonad.
        def _set_kp(c):
            c["ssh_key_path"] = kp
            return c
        update_config(_set_kp)
    with open(pub, "r", encoding="utf-8") as f:
        return kp, f.read().strip()

def provision_server(d):
    # vorodi: name, role, host, ssh_user, ssh_port, ssh_password
    # marahel: 1) nصب kelid-e omoomi-ye hub rooye server ba ramz  2) deploy (scp + update.sh)  3) sabt dar inventory
    name = str(d.get("name", "")); role = str(d.get("role", ""))
    host = str(d.get("host", "")); user = str(d.get("ssh_user", "root"))
    port = str(d.get("ssh_port", "22")); pw = str(d.get("ssh_password", ""))
    if not RE_NAME.match(name) or role not in ("iran", "node") or not RE_HOST.match(host) \
       or not RE_NAME.match(user) or not RE_PORT.match(port):
        return {"rc": 1, "out": "", "err": "field-haye namotabar (name/role/host/user/port)"}
    if not pw:
        return {"rc": 1, "out": "", "err": "ramz SSH lazem ast"}
    if any(s.get("name") == name for s in get_inventory()):
        return {"rc": 1, "out": "", "err": "in nam az ghabl vojood darad"}
    server = {"name": name, "role": role, "host": host, "ssh_user": user, "ssh_port": int(port)}
    # baraye node: server-e Iran-e main ra moshakhas kon (vorodi iran_server ya, agar
    # faghat yek server Iran dar hub bashad, hamon). in tunnel-e asli (SERVER) ra baad az
    # deploy tanzim mikonad ta node digar «?» nashan nadahad.
    iran_host = ""; iran_srv = None
    if role == "node":
        want = str(d.get("iran_server", "")).strip()
        irs = [s for s in get_inventory() if s.get("role") == "iran"]
        if want:
            match = next((s for s in irs if s.get("name") == want or s.get("host") == want), None)
            if match:
                iran_host = str(match.get("host", "")); iran_srv = match
            elif RE_HOST.match(want):
                iran_host = want
        elif len(irs) == 1:
            iran_host = str(irs[0].get("host", "")); iran_srv = irs[0]
    if MOCK:
        update_inventory(lambda inv: inv + [server] if not any(s.get("name") == name for s in inv) else inv)
        return {"rc": 0, "out": "[mock provision→%s] kelid nصب shod + deploy + be hub ezafe shod" % name, "err": ""}
    if not shutil.which("sshpass"):
        return {"rc": 1, "out": "", "err": "sshpass rooye hub nصب nist. nصب kon: apt install -y sshpass"}
    try:
        kp, pubkey = ensure_hub_key()
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}
    logs = []
    opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=12", "-o", "NumberOfPasswordPrompts=1"]
    target = "%s@%s" % (user, host)
    # 1) nصب kelid-e omoomi dar authorized_keys (idempotent — dobare ezafe nemikonad)
    q = shlex.quote(pubkey)
    remote = ("set -e; umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
              "chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; "
              "grep -qF %s ~/.ssh/authorized_keys || printf '%%s\\n' %s >> ~/.ssh/authorized_keys" % (q, q))
    try:
        r = subprocess.run(["sshpass", "-p", pw, "ssh"] + opts + ["-p", port, target, remote],
                           capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "timeout dar atesal ba ramz (host/port/firewall?)"}
    except Exception as e:
        return {"rc": 1, "out": "", "err": str(e)}
    logs.append("== nصب kelid SSH ==\n" + (_strip_ansi(r.stdout) or "(ok)") +
                (("\n[stderr] " + _strip_ansi(r.stderr)) if r.stderr.strip() else ""))
    if r.returncode != 0:
        emsg = r.stderr.strip() or r.stdout.strip() or "khata"
        low = emsg.lower()
        if "permission denied" in low or "authentication" in low:
            emsg = "ramz/karbar eshtebah ast ya vorod ba ramz roo server baste ast (PasswordAuthentication)."
        return {"rc": r.returncode, "out": "\n\n".join(logs), "err": "nصب kelid shekast khord: " + emsg}
    # 2) deploy ba kelid (scp scripts + update.sh) — server hanoz dar inventory nist pas mostaghim server dict ra midahim
    dep = deploy_to_server(server)
    logs.append("== deploy (github-update) ==\n" + (dep.get("out", "") or "") +
                (("\n[stderr] " + dep.get("err", "")) if dep.get("err") else ""))
    # 2.5) baraye node: tunnel-e asli (SERVER) ra be server-e Iran vasl kon ta «?» nashan nadahad.
    # maghsad = DOMAIN-e omoomi-ye Iran (na host/IP-e SSH) ta SNI ba cert bekhanad va tunnel bala biad.
    if role == "node" and iran_host and dep.get("rc") == 0:
        main_srv = (iran_main_server(iran_srv)[0] if iran_srv else "") or (iran_host + ":443")
        sset = run_on_server(server, ["ratholenode", "set", "SERVER", main_srv])
        logs.append("== tunnel-e asli → %s ==\n" % main_srv + (sset.get("out", "") or "") +
                    (("\n[stderr] " + sset.get("err", "")) if sset.get("err") else ""))
    elif role == "node" and not iran_host:
        logs.append("== [هشدار] server Iran-e main tanzim nashod — dar safhe-ye node ba «tanzim tunnel asli» vaslesh kon. ==")
    # 3) sabt dar inventory (hata agar deploy naghes bood, kelid nصب shode va etesal ba kelid barقarار ast)
    # 3) sabt dar inventory (hata agar deploy naghes bood, kelid nصب shode va etesal ba kelid barقarار ast)
    update_inventory(lambda inv: inv + [server] if not any(s.get("name") == name for s in inv) else inv)
    logs.append("== be hub ezafe shod: %s (%s) — az in pas atesal ba kelid ast ==" % (name, role))
    note = "" if dep.get("rc") == 0 else "\n[هشدار] deploy kamel nashod (rc=%s)؛ mitavani baad dokme «apdit» ra bezani." % dep.get("rc")
    return {"rc": 0, "out": "\n\n".join(logs) + note, "err": ""}

def mock_run(server, cmd_args):
    j = " ".join(cmd_args)
    role = server.get("role")

    if j == "ratholectl ls":
        return {"rc": 0, "out": "NAME           PORT     INBOUND      API        USER PATH\n"
                "--------------------------------------------------------------\n"
                "trk01          1005     8444         -          https://d/trk01\n"
                "gamenodetrk    1007     2101         7001       https://d/gamenodetrk", "err": ""}
    if cmd_args[:2] == ["ratholectl", "show"] and len(cmd_args) >= 3:
        nm = cmd_args[2]
        return {"rc": 0, "out":
            "──────── dstvr nasb rooye node kharej (curl yek-khatti) ────────\n"
            "curl -fsSL https://raw.githubusercontent.com/loopy-iri/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \\\n"
            "  --server rp01.l1t.ir:443 --name %s --token a0370655deadbeefcafe1234 --inbound-port 8444\n"
            "────────────────────────────────────────" % nm, "err": ""}
    if j == "ratholectl version":
        return {"rc": 0, "out": "manager_version=1.4.7\nrole=panel\nrathole_version=0.5.0", "err": ""}
    if j == "ratholenode version":
        return {"rc": 0, "out": "manager_version=1.4.6\nrole=node\nrathole_version=0.5.0", "err": ""}
    if j == "ratholectl status --json":
        return {"rc": 0, "out": json.dumps({
            "domain": "rp01.l1t.ir", "public_ip": "5.202.4.40",
            "transport": "websocket+TLS (443)",
            "ports": {"control": 2333, "fake": 8080, "sub": 2096, "internal": 8443,
                      "plain": None, "direct": None, "hub": 8088, "noise": 2334},
            "direct_header": "X-Cdn-Id",
            "cert": {"fullchain": "/etc/letsencrypt/live/rp01.l1t.ir/fullchain.pem",
                     "key": "/etc/letsencrypt/live/rp01.l1t.ir/privkey.pem",
                     "exists": "yes", "expiry": "Oct 12 09:00:00 2026 GMT", "self_signed": "no"},
            "services": {"rathole_server": "yes", "nginx": "yes", "nginx_config_ok": "yes", "noise": "yes"},
            "sni_count": 1, "node_count": 2,
            "nodes": [{"name": "trk01", "port": 1005, "inbound_port": 8444, "api_local_port": None, "sni": None},
                      {"name": "gamenodetrk", "port": 1007, "inbound_port": 2101, "api_local_port": 7001, "sni": "gmtrk.l1t.ir"}]
        }), "err": ""}
    if j == "ratholectl paths":
        return {"rc": 0, "out": "──────── masir-e config-ha va file-ha ────────\n"
                "  ✓  state.json             /etc/rathole-manager/state.json\n"
                "  ✓  server.toml            /etc/rathole/server.toml\n"
                "  ✓  nginx rathole.conf     /etc/nginx/conf.d/rathole.conf\n"
                "  ✓  cert fullchain         /etc/letsencrypt/live/rp01.l1t.ir/fullchain.pem", "err": ""}
    if j == "ratholectl kcp status":
        return {"rc": 0, "out": "kcp: roshan  UDP :443 → 127.0.0.1:2333  (profile: balanced)\n"
                "  estetar: UDP/443 ~ QUIC/HTTP3\n  service: active\n  gvshdadn UDP:443: blh", "err": ""}
    if j == "ratholectl game ls":
        return {"rc": 0, "out": "NAME           SNI                    DATA     NODE-INBOUND\n"
                "------------------------------------------------------------\n"
                "gmtrk          gmtrk.l1t.ir           1007     8444", "err": ""}
    if j == "ratholectl doctor":
        return {"rc": 0, "out": "OK rathole-server faal ast\nOK nginx faal ast\n"
                "OK  node trk01 rooye port 1005 amade ast\n"
                "WARN node gamenodetrk rooye port 1007 gvsh nmidhd (klaint node vsl nist?)\n"
                "khlash: OK=3  FAIL=1", "err": ""}
    if j == "ratholenode ls":
        return {"rc": 0, "out": "tunnel be: rp01.l1t.ir:443  (hame serviceha rooye yek channel kontroli)\n"
                "SERVICE          INBOUND    TOKEN\n-------------------------------------------\n"
                "trk01            1101       a0370655…\ngamenodetrk      2101       32eb742b…", "err": ""}
    if j == "ratholenode kcp status":
        return {"rc": 0, "out": "halat tunnel: kcp\n  local: 127.0.0.1:29900   remote(UDP): 5.202.4.40:443   profile: balanced\n"
                "  estetar: UDP/443 ~ QUIC/HTTP3\n  kcp-client: active\n  rathole-client: active", "err": ""}
    if j == "ratholenode upstream ls":
        return {"rc": 0, "out": "tunnel asli (main): rp01.l1t.ir:443  [tunnel=kcp]\n"
                "upstream 'iran2nobody': rp02.btli.ir:443  [tunnel=ws]\n    trk01b|***|1102", "err": ""}
    if j == "ratholectl noise status":
        return {"rc": 0, "out": "noise (ramznegari-shode): roshan  rathole-noise rooye port-e omomi 2334  (node-haye noise: 1)\n"
                "  node-haye noise: gamenodetrk\n"
                "  gvshdadn TCP:2334: blh\n  rathole-noise: active", "err": ""}
    if j == "ratholectl noise show":
        return {"rc": 0, "out": "──────── faalsazi halat noise rooye node kharej ────────\n"
                "  ratholenode noise on 5.202.4.40:2334 Qm9ndXNMb2NrS2V5RXhhbXBsZUJhc2U2NFBhZGRpbmc= Noise_NK_25519_ChaChaPoly_BLAKE2s\n"
                "bazgsht: ratholenode noise off", "err": ""}
    if j == "ratholectl plain status":
        return {"rc": 0, "out": "plain (bedoon TLS): roshan  listener HTTP rooye port 8880\n"
                "  gvshdadn TCP:8880: blh", "err": ""}
    if j == "ratholectl direct status":
        return {"rc": 0, "out": "direct-IP (header-based): roshan   port 8081   header: X-Cdn-Id\n"
                "  gvshdadn TCP:8081: blh\n  node-ha:  trk01 -> \"X-Cdn-Id: trk01\"", "err": ""}
    if j.startswith("ratholenode set SERVER "):
        return {"rc": 0, "out": "tanzim shod: SERVER = %s\n[mock] tunnel-e asli be-ruz shod." % cmd_args[-1], "err": ""}
    return {"rc": 0, "out": "[mock] %s → %s" % (role, j), "err": ""}


# ---------- parser hai khorooji CLI → dadhi sakhtarmnd ----------
def parse_iran_ls(text):
    nodes = []
    for line in (text or "").splitlines():
        t = line.rstrip()
        s = t.strip()
        if not s or s.startswith("NAME") or set(s) <= set("-"):
            continue
        p = t.split()
        if len(p) >= 2 and p[1].isdigit():
            nodes.append({"name": p[0], "port": p[1], "inbound": p[2] if len(p) > 2 else "",
                          "api": p[3] if len(p) > 3 else "-", "path": p[4] if len(p) > 4 else ""})
    return nodes

def parse_kcp_status(text):
    text = text or ""
    enabled = ("roshan" in text) or (re.search(r"halat tunnel[:：]?\s*kcp", text) is not None)
    port = None; profile = None; mode = None
    m = re.search(r"UDP\s*:?(\d+)", text)
    if m: port = m.group(1)
    m = re.search(r"profile[:：]?\s*([A-Za-z]+)", text)
    if m: profile = m.group(1)
    m = re.search(r"halat tunnel[:：]?\s*(\w+)", text)
    if m: mode = m.group(1)
    stealth = "QUIC" in text
    return {"enabled": enabled, "port": port, "profile": profile, "mode": mode, "stealth": stealth}

def parse_kcp_connect(text):
    # az khorooji "ratholectl kcp show" khat "ratholenode kcp on <IP>:<port> <key> <profile>" ra darmiavarad.
    for line in (text or "").splitlines():
        m = re.search(r"ratholenode\s+kcp\s+on\s+(\S+:\d+)\s+([A-Fa-f0-9]{8,64})\s+(\w+)", line)
        if m:
            return {"remote": m.group(1), "key": m.group(2), "profile": m.group(3)}
    return None

def parse_kcp_key(text):
    # key ra mostaghel az tashkhis IP darmiavarad (rooye Iran curl baraye IP momken ast kar nakonad).
    m = re.search(r"ratholenode\s+kcp\s+on\s+\S+\s+([A-Fa-f0-9]{8,64})\s+\w+", text or "")
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Fa-f0-9]{24,64})\b", text or "")  # fallback: token hex
    return m.group(1) if m else None

def parse_noise_connect(text):
    # az khorooji "ratholectl noise show" khat "ratholenode noise on <IP>:<port> <pubkey> [pattern]" ra darmiavarad.
    for line in (text or "").splitlines():
        m = re.search(r"ratholenode\s+noise\s+on\s+\S+:(\d+)\s+([A-Za-z0-9+/]{40,64}={0,2})(?:\s+(\S+))?", line)
        if m:
            return {"port": m.group(1), "pubkey": m.group(2), "pattern": m.group(3) or ""}
    return None

def parse_version(text):
    # khorooji-ye "ratholectl/ratholenode version" (print_version) → manager/rathole version.
    t = text or ""
    out = {"manager": "", "rathole": ""}
    m = re.search(r"manager_version=(\S+)", t)
    if m: out["manager"] = m.group(1)
    m = re.search(r"rathole_version=(\S+)", t)
    if m: out["rathole"] = m.group(1)
    return out

def parse_node_connect(text):
    # az khorooji "ratholectl show <name>" (print_node_install) name/token/inbound-e vaghei
    # ra darmiavarad — token dar 'ls' mask ast, pas az inja migirim.
    t = text or ""
    out = {}
    m = re.search(r"--name\s+([A-Za-z0-9_-]{1,40})", t)
    if m: out["name"] = m.group(1)
    m = re.search(r"--token\s+([A-Za-z0-9._=+/-]{6,255})", t)
    if m: out["token"] = m.group(1)
    m = re.search(r"--inbound-port\s+(\d{1,5})", t)
    if m: out["inbound"] = m.group(1)
    m = re.search(r"--api-token\s+([A-Za-z0-9._=+/-]{6,255})", t)
    if m: out["api_token"] = m.group(1)
    m = re.search(r"--api-inbound-port\s+(\d{1,5})", t)
    if m: out["api_inbound"] = m.group(1)
    return out if (out.get("token") and out.get("inbound") and out.get("name")) else None

def parse_noise_status(text):
    # khorooji-ye "ratholectl/ratholenode noise status" ra parse mikonad → enabled/port/count/nodes/mode.
    text = text or ""
    enabled = ("roshan" in text) or (re.search(r"halat tunnel[:：]?\s*noise", text) is not None)
    port = None; count = None; nodes = []; mode = None
    m = re.search(r"port-e omomi\s*(\d+)", text)
    if m: port = m.group(1)
    if not port:
        m = re.search(r":(\d+)", text)   # fallback (samt-e node: remote IP:PORT)
        if m: port = m.group(1)
    m = re.search(r"node-haye noise[:：]?\s*(\d+)", text)
    if m: count = m.group(1)
    m = re.search(r"node-haye noise[:：]\s*([A-Za-z0-9_,\s-]+)$", text, re.M)
    if m:
        nodes = [x.strip() for x in m.group(1).split(",") if x.strip() and not x.strip().isdigit()]
    m = re.search(r"halat tunnel[:：]?\s*(\w+)", text)
    if m: mode = m.group(1)
    return {"enabled": enabled, "port": port, "count": count, "nodes": nodes, "mode": mode}

def parse_game_ls(text):
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("NAME") or set(s) <= set("-"):
            continue
        p = line.split()
        if len(p) >= 2:
            out.append({"name": p[0], "sni": p[1], "data": p[2] if len(p) > 2 else "",
                        "inbound": p[3] if len(p) > 3 else ""})
    return out


def parse_plain_status(text):
    # khorooji-ye "ratholectl plain status" → enabled/port. (ingress: masir-e ws bedoon TLS)
    text = text or ""
    enabled = "roshan" in text
    port = None
    m = re.search(r"port\s+(\d+)", text)
    if m: port = m.group(1)
    return {"enabled": enabled, "port": port}

def parse_direct_status(text):
    # khorooji-ye "ratholectl direct status" → enabled/port/header. (ingress: header-routing bedoon TLS)
    text = text or ""
    enabled = "roshan" in text
    port = None; header = None
    m = re.search(r"port\s+(\d+)", text)
    if m: port = m.group(1)
    m = re.search(r"header[:：]\s+([A-Za-z0-9-]+)", text)
    if m: header = m.group(1)
    return {"enabled": enabled, "port": port, "header": header or "X-Cdn-Id"}

def parse_doctor(text):
    # alave bar shomaresh OK/FAIL, vaziat har node ra ham darmiavarad
    # (khatt-haye "OK node X rooye port P amade ast" / "WARN node X ... gvsh nmidhd")
    # ta graph/panel betavanad har edge ra sabz/ghermez konad.
    text = re.sub(r"\x1b\[[0-9;]*m", "", text or "")  # hazf-e rang-haye ANSI (agar tty bood)
    nodes = {}
    for line in text.splitlines():
        m = re.match(r"\s*(OK|WARN|FAIL)\s+node\s+([A-Za-z0-9_-]+)\s+rooye\s+port", line)
        if m:
            nodes[m.group(2)] = "ok" if m.group(1) == "OK" else "warn"
    m = re.search(r"OK=(\d+)\s+FAIL=(\d+)", text)
    if m:
        return {"ok": int(m.group(1)), "fail": int(m.group(2)), "nodes": nodes}
    return {"ok": text.count("OK "), "fail": text.count("FAIL"), "nodes": nodes}

def parse_node_ls(text):
    svcs = []; server = None
    for line in (text or "").splitlines():
        t = line.strip()
        m = re.search(r"tunnel be[:：]\s*(\S+)", t)
        if m:
            server = m.group(1); continue
        if not t or t.startswith("SERVICE") or set(t) <= set("-"):
            continue
        p = t.split()
        if len(p) >= 2 and p[1].isdigit():
            svcs.append({"name": p[0], "inbound": p[1]})
    return {"server": server, "services": svcs}

def parse_upstream_ls(text):
    main = None; ups = []; cur = None
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        mt = re.search(r"\[tunnel=(\w+)\]", t)
        um = re.search(r"upstream '([^']+)'", t)
        if um and mt:
            srv = re.search(r"'[^']+'\s*[:：]?\s*(\S+)\s*\[tunnel=", t)
            cur = {"id": um.group(1), "server": (srv.group(1) if srv else ""), "tunnel": mt.group(1), "services": []}
            ups.append(cur); continue
        if ("main" in t) and mt:
            srv = re.search(r"[:：]\s*(\S+)\s*\[tunnel=", t)
            main = {"server": (srv.group(1) if srv else ""), "tunnel": mt.group(1)}; cur = None; continue
        if "|" in t and cur is not None:
            parts = t.split("|")
            if len(parts) >= 2:
                cur["services"].append({"name": parts[0].strip(), "inbound": parts[-1].strip()})
    return {"main": main, "upstreams": ups}

# ---------- token/nshst ----------
def make_session_token(cfg):
    # kvki nshst = hmac( api_token , expiry )
    exp = str(int(time.time()) + 86400)
    sig = hmac.new(cfg["api_token"].encode(), exp.encode(), hashlib.sha256).hexdigest()
    return "%s.%s" % (exp, sig)

def check_session(cfg, token):
    try:
        exp, sig = token.split(".", 1)
        if int(exp) < time.time(): return False
        good = hmac.new(cfg["api_token"].encode(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(good, sig)
    except Exception:
        return False

def authed(cfg, headers, cookies):
    # Bearer token (baraye API kharji) ya kvki nshst (baraye UI)
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return hmac.compare_digest(auth[7:].strip(), cfg["api_token"])
    tok = cookies.get("rhsession", "")
    return check_session(cfg, tok)

# ---------- HTTP handler ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "ratholehub/0.1"

    def _cookies(self):
        raw = self.headers.get("Cookie", "")
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1); out[k] = v
        return out

    def _send(self, code, body, ctype="application/json", extra_headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body_json(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            # saghf-e andaze-ye body (1 MiB) ta yek Content-Length-e bozorg rooye masir-e
            # ehraz-nashode (masalan /api/login) hafeze ra por nakonad.
            if n > 1048576:
                return {}
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def log_message(self, *a):
        pass  # sakt

    # ---- GET ----
    def do_GET(self):
        cfg = get_config()
        path = urlparse(self.path).path
        if path == "/" or path == "/hub/" or path == "/hub":
            return self._send(200, UI_HTML, "text/html")
        if path in ("/api/health", "/hub/api/health"):
            return self._send(200, {"ok": True, "mock": MOCK})
        p = path.replace("/hub", "", 1) if path.startswith("/hub/api") else path
        if not authed(cfg, self.headers, self._cookies()):
            return self._send(401, {"error": "unauthorized"})
        if p == "/api/servers":
            return self._send(200, get_inventory())
        if p == "/api/hubstatus":
            return self._send(200, hub_status())
        if p == "/api/config":
            return self._config_view()
        if p == "/api/audit":
            q = parse_qs(urlparse(self.path).query)
            try: lim = max(1, min(500, int(q.get("limit", ["100"])[0])))
            except Exception: lim = 100
            return self._send(200, read_audit(lim))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/status$", p)
        if m:
            return self._status(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/discover$", p)
        if m:
            return self._discover(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/overview$", p)
        if m:
            return self._overview(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/details$", p)
        if m:
            return self._details(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/kcpconnect$", p)
        if m:
            return self._kcpconnect(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/noiseconnect$", p)
        if m:
            return self._noiseconnect(m.group(1))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/nodeconnect/([A-Za-z0-9_-]+)$", p)
        if m:
            return self._nodeconnect(m.group(1), m.group(2))
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/mainconnect$", p)
        if m:
            return self._mainconnect(m.group(1))
        return self._send(404, {"error": "not found"})


    # ---- POST/DELETE ----
    def do_POST(self):
        cfg = get_config()
        path = urlparse(self.path).path
        p = path.replace("/hub", "", 1) if path.startswith("/hub/api") else path
        if p == "/api/login":
            # kelid-e rate-limit ba X-Real-IP (mesl _user); posht-e nginx TCP-peer
            # hamishe 127.0.0.1 ast pas yek bucket-e global mishavad va hame ra ghofl mikonad.
            ip = self.headers.get("X-Real-IP") or (self.client_address[0] if self.client_address else "?")
            if not login_allowed(ip):
                return self._send(429, {"error": "too many attempts; try later"})
            data = self._body_json()
            pw = str(data.get("password", "")).encode()
            if hmac.compare_digest(hashlib.sha256(pw).hexdigest(), cfg["admin_password_sha256"]):
                login_reset(ip)
                tok = make_session_token(cfg)
                return self._send(200, {"ok": True, "token": cfg["api_token"]},
                                  extra_headers={"Set-Cookie": "rhsession=%s; HttpOnly; SameSite=Strict; Path=/" % tok})
            login_record_fail(ip)
            return self._send(401, {"error": "bad password"})

        if not authed(cfg, self.headers, self._cookies()):
            return self._send(401, {"error": "unauthorized"})

        if p == "/api/servers":
            return self._add_server(self._body_json())
        if p == "/api/provision":
            return self._provision(self._body_json())
        if p == "/api/config":
            return self._config_save(self._body_json())

        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)/action$", p)
        if m:
            return self._action(m.group(1), self._body_json())
        return self._send(404, {"error": "not found"})

    def do_PUT(self):
        cfg = get_config()
        p = urlparse(self.path).path
        p = p.replace("/hub", "", 1) if p.startswith("/hub/api") else p
        if not authed(cfg, self.headers, self._cookies()):
            return self._send(401, {"error": "unauthorized"})
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)$", p)
        if m:
            return self._edit_server(m.group(1), self._body_json())
        return self._send(404, {"error": "not found"})

    def do_DELETE(self):
        cfg = get_config()
        p = urlparse(self.path).path
        p = p.replace("/hub", "", 1) if p.startswith("/hub/api") else p
        if not authed(cfg, self.headers, self._cookies()):
            return self._send(401, {"error": "unauthorized"})
        m = re.match(r"^/api/servers/([A-Za-z0-9_-]+)$", p)
        if m:
            name = m.group(1)
            update_inventory(lambda inv: [s for s in inv if s.get("name") != name])
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})

    # ---- helpers ----
    def _find(self, name):
        for s in get_inventory():
            if s.get("name") == name:
                return s
        return None

    def _user(self):
        # hvite tghribi baraye audit: IP klaint (psht nginx, X-Real-IP).
        return self.headers.get("X-Real-IP") or (self.client_address[0] if self.client_address else "?")

    def _add_server(self, d):
        name = str(d.get("name", "")); role = str(d.get("role", ""))
        host = str(d.get("host", "")); user = str(d.get("ssh_user", "root"))
        port = str(d.get("ssh_port", "22"))
        if not RE_NAME.match(name) or role not in ("iran", "node") or not RE_HOST.match(host) \
           or not RE_NAME.match(user) or not RE_PORT.match(port):
            return self._send(400, {"error": "invalid fields"})
        # check-and-append atomic zir-e yek ghofl ta do add-e hamzaman ham-digar ra pak nakonand.
        with _lock:
            inv = get_inventory()
            if any(s.get("name") == name for s in inv):
                return self._send(409, {"error": "name exists"})
            inv.append({"name": name, "role": role, "host": host,
                        "ssh_user": user, "ssh_port": int(port)})
            set_inventory(inv)
        return self._send(200, {"ok": True})

    def _provision(self, d):
        # nصب khodkar: ba ramz SSH vasl mishavad, kelid-e hub ra nصب mikonad,
        # scriptha ra deploy mikonad va server ra be hub ezafe mikonad.
        res = provision_server(d)
        audit_log(self._user(), str(d.get("name", "?")), "provision",
                  "provision role=%s host=%s" % (d.get("role", "?"), d.get("host", "?")), res.get("rc"))
        code = 200 if res.get("rc") == 0 else 400
        return self._send(code, res)

    def _config_view(self):

        # hrgz ramz/token ra brnmigrdanim; fght mtaditai bikhtr.
        cfg = get_config()
        tok = cfg.get("api_token", "")
        return self._send(200, {
            "listen_host": cfg.get("listen_host"),
            "listen_port": cfg.get("listen_port"),
            "ssh_key_path": cfg.get("ssh_key_path"),
            "ssh_opts": cfg.get("ssh_opts"),
            "insecure": cfg.get("_insecure", False),
            "api_token_hint": (tok[:4] + "…" + tok[-4:]) if len(tok) >= 8 else "(unset)",
            "mock": MOCK,
        })

    def _config_save(self, d):
        # tghiire ramz admin va/ya chrkhshe token API az dakhl panel.
        # kolle read-modify-write zir-e _lock ta ba ensure_hub_key/save-e digar race nakonad.
        with _lock:
            cfg = get_config()
            changed = []
            new_pw = d.get("new_password")
            if new_pw is not None:
                cur = str(d.get("current_password", "")).encode()
                if not hmac.compare_digest(hashlib.sha256(cur).hexdigest(), cfg.get("admin_password_sha256", "")):
                    return self._send(403, {"error": "current password incorrect"})
                if not RE_PW.match(str(new_pw)):
                    return self._send(400, {"error": "password must be 6-128 chars"})
                cfg["admin_password_sha256"] = hashlib.sha256(str(new_pw).encode()).hexdigest()
                changed.append("password")
            new_token = None
            if d.get("rotate_token"):
                new_token = secrets.token_hex(24)
                cfg["api_token"] = new_token
                changed.append("api_token")
            # ssh_key_path: masir-e file (reshte). ssh_opts: HATMAN list-e reshte
            # (chvn _ssh_base list(...)-esh mikonad; reshte be karaktr-ha shekaste mishavad).
            if "ssh_key_path" in d and isinstance(d["ssh_key_path"], str):
                cfg["ssh_key_path"] = d["ssh_key_path"]; changed.append("ssh_key_path")
            if "ssh_opts" in d:
                v = d["ssh_opts"]
                if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                    return self._send(400, {"error": "ssh_opts must be a list of strings"})
                cfg["ssh_opts"] = v; changed.append("ssh_opts")
            if not changed:
                return self._send(400, {"error": "nothing to change"})
            save_config(cfg)
        audit_log(self._user(), "-", "config_save", ",".join(changed), 0)
        out = {"ok": True, "changed": changed}
        if new_token:
            out["api_token"] = new_token  # tnha bar namayesh token jadid
        return self._send(200, out)

    def _edit_server(self, name, d):
        # viraishe mtaditai atsal (host/user/port) bedoon hazf/afzoodan dvbarh.
        # aval hame-ye field-ha ra etebar-sanji va jam mikonim, sps atomic emal mikonim.
        changes = {}
        if "host" in d:
            if not RE_HOST.match(str(d["host"])): return self._send(400, {"error": "bad host"})
            changes["host"] = str(d["host"])
        if "ssh_user" in d:
            if not RE_NAME.match(str(d["ssh_user"])): return self._send(400, {"error": "bad user"})
            changes["ssh_user"] = str(d["ssh_user"])
        if "ssh_port" in d:
            if not RE_PORT.match(str(d["ssh_port"])): return self._send(400, {"error": "bad port"})
            changes["ssh_port"] = int(d["ssh_port"])
        if "role" in d:
            if d["role"] not in ("iran", "node"): return self._send(400, {"error": "bad role"})
            changes["role"] = d["role"]
        found = {}
        with _lock:
            inv = get_inventory()
            target = None
            for srv in inv:
                if srv.get("name") == name:
                    target = srv; break
            if not target:
                return self._send(404, {"error": "server not found"})
            target.update(changes)
            found = dict(target)
            set_inventory(inv)
        audit_log(self._user(), name, "edit_server", "metadata", 0)
        return self._send(200, {"ok": True, "server": found})

    def _action(self, name, d):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        action = str(d.get("action", "")); args = d.get("args", {}) or {}
        if action == "deploy":
            res = deploy_to_server(s)
            audit_log(self._user(), name, "deploy", "github-update (install.sh --update)", res.get("rc"))
            return self._send(200, {"server": name, "cmd": "github-update (install.sh --update)", **res})
        cmd = build_cmd(s.get("role"), action, args)
        if not cmd:
            return self._send(400, {"error": "unknown or invalid action"})
        res = run_on_server(s, cmd)
        if action in WRITE_ACTIONS:
            audit_log(self._user(), name, action, " ".join(cmd), res.get("rc"))
        return self._send(200, {"server": name, "cmd": " ".join(cmd), **res})

    def _overview(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        role = s.get("role")
        ov = {"server": name, "role": role, "host": s.get("host"), "reachable": True}
        def R(args):
            return run_on_server(s, args)
        if role == "iran":
            r = R(["ratholectl", "ls"])
            # HAR rc-e gheyre-sefr (255=SSH fail, 124=timeout, 'Connection refused',
            # 'No route to host', 'Host key verification failed', ...) yani server dar dastras
            # nist ya command shekast khord — na faghat do zir-reshte-ye khass.
            if r.get("rc") not in (0, None):
                ov["reachable"] = False; ov["error"] = r.get("err", "") or ("rc=%s" % r.get("rc")); return self._send(200, ov)
            ov["nodes"] = parse_iran_ls(r.get("out", ""))
            ov["kcp"] = parse_kcp_status(R(["ratholectl", "kcp", "status"]).get("out", ""))
            ov["noise"] = parse_noise_status(R(["ratholectl", "noise", "status"]).get("out", ""))
            ov["plain"] = parse_plain_status(R(["ratholectl", "plain", "status"]).get("out", ""))
            ov["direct"] = parse_direct_status(R(["ratholectl", "direct", "status"]).get("out", ""))
            ov["game"] = parse_game_ls(R(["ratholectl", "game", "ls"]).get("out", ""))
            ov["health"] = parse_doctor(R(["ratholectl", "doctor"]).get("out", ""))
            ov["version"] = parse_version(R(["ratholectl", "version"]).get("out", ""))
        else:
            r = R(["ratholenode", "ls"])
            if r.get("rc") not in (0, None):
                ov["reachable"] = False; ov["error"] = r.get("err", "") or ("rc=%s" % r.get("rc")); return self._send(200, ov)
            nls = parse_node_ls(r.get("out", ""))
            ov["main_server"] = nls["server"]; ov["services"] = nls["services"]
            ov["kcp"] = parse_kcp_status(R(["ratholenode", "kcp", "status"]).get("out", ""))
            ov["noise"] = parse_noise_status(R(["ratholenode", "noise", "status"]).get("out", ""))
            ups = parse_upstream_ls(R(["ratholenode", "upstream", "ls"]).get("out", ""))
            ov["upstreams"] = ups["upstreams"]
            ov["main_tunnel"] = (ups.get("main") or {}).get("tunnel", ov["kcp"].get("mode", "ws"))
            ov["version"] = parse_version(R(["ratholenode", "version"]).get("out", ""))
        return self._send(200, ov)

    def _details(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        role = s.get("role")
        if role == "iran":
            cmds = [("ls", ["ratholectl", "ls"]), ("kcp status", ["ratholectl", "kcp", "status"]),
                    ("noise status", ["ratholectl", "noise", "status"]),
                    ("game ls", ["ratholectl", "game", "ls"]), ("doctor", ["ratholectl", "doctor"])]
        else:
            cmds = [("show", ["ratholenode", "show"]), ("kcp status", ["ratholenode", "kcp", "status"]),
                    ("noise status", ["ratholenode", "noise", "status"]),
                    ("upstream ls", ["ratholenode", "upstream", "ls"]), ("logs", ["ratholenode", "logs", "40"])]
        parts = []
        for label, c in cmds:
            r = run_on_server(s, c, timeout=30)
            body = (r.get("out", "") or "").rstrip()
            if r.get("err"):
                body += ("\n[stderr] " + r["err"].rstrip())
            parts.append("===== %s =====\n%s" % (label, body or "(khali)"))
        return self._send(200, {"server": name, "text": "\n\n".join(parts)})

    def _kcpconnect(self, name):
        # az server Iran khatte etesal KCP (remote/key/profile daghigh) ra migirad ta
        # form node bedoon typo por shavad (elate asli 'dasti kar mikard vali panel na').
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "kcpconnect fght baraye server iran ast"})
        # 1) az 'kcp show' faghat key ra migirim (tashkhis IP rooye Iran ba curl momken ast shekast bokhorad).
        show = run_on_server(s, ["ratholectl", "kcp", "show"])
        info = parse_kcp_connect(show.get("out", ""))
        key = (info or {}).get("key") or parse_kcp_key(show.get("out", ""))
        # 2) port/profile/enabled ra az 'kcp status' migirim (motmaen-tar).
        st = parse_kcp_status(run_on_server(s, ["ratholectl", "kcp", "status"]).get("out", ""))
        port = st.get("port") or (info or {}).get("remote", ":443").split(":")[-1] or "443"
        profile = st.get("profile") or (info or {}).get("profile") or "balanced"
        if not key:
            return self._send(200, {"ok": False, "error": "kcp roshan nist ya key peida nashod",
                                    "raw": show.get("out", "") + show.get("err", "")})
        # 3) remote = host-e inventory (haman IP-i ke hub baa an be Iran vasl mishavad) + port-e KCP.
        remote = "%s:%s" % (s.get("host"), port)
        return self._send(200, {"ok": True, "remote": remote, "key": key, "profile": profile})

    def _noiseconnect(self, name):
        # az server Iran khatte etesal noise (port + pubkey) ra migirad ta form node bedoon typo por shavad.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "noiseconnect fght baraye server iran ast"})
        show = run_on_server(s, ["ratholectl", "noise", "show"])
        info = parse_noise_connect(show.get("out", ""))
        if not info or not info.get("pubkey"):
            return self._send(200, {"ok": False, "error": "noise roshan nist ya pubkey peida nashod",
                                    "raw": show.get("out", "") + show.get("err", "")})
        # remote = host-e inventory + port-e noise (az khatte connect).
        remote = "%s:%s" % (s.get("host"), info.get("port", "2334"))
        return self._send(200, {"ok": True, "remote": remote, "pubkey": info["pubkey"],
                                "pattern": info.get("pattern", "")})

    def _nodeconnect(self, name, node):
        # az server Iran, meshkhassat-e yek node (name/token/inbound) ra migirad ta betavan
        # ba yek dokme rooye node-e kharej (ya upstream-esh) be-onvan service sim-keshi kard.
        # token dar 'ls' mask ast — pas az 'ratholectl show <node>' migirim.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "nodeconnect fght baraye server iran ast"})
        if not RE_NAME.match(node):
            return self._send(400, {"error": "name-e node namotabar"})
        show = run_on_server(s, ["ratholectl", "show", node])
        info = parse_node_connect(show.get("out", ""))
        if not info:
            return self._send(200, {"ok": False, "error": "node peida nashod ya token/inbound darnayamad",
                                    "raw": show.get("out", "") + show.get("err", "")})
        return self._send(200, {"ok": True, "name": info["name"], "token": info["token"],
                                "inbound": info["inbound"],
                                "api_token": info.get("api_token", ""),
                                "api_inbound": info.get("api_inbound", "")})

    def _mainconnect(self, name):
        # az server Iran, MAGHSAD-e daghigh-e tunnel-e asli (SERVER) ra migirad ta hangam-e
        # «tanzim tunnel asli» rooye node meghdar-e dorost set shavad. dar halat-e pishfarz
        # (ws+TLS) node bayad be DOMAIN-e omoomi vasl shavad (na host/IP-e SSH-e inventory),
        # chon ratholenode az SERVER ham remote_addr va ham hostname/SNI ra misazad — agar
        # SNI ba cert nakhanad, tunnel bala nemiayad. domain ra az 'status --json' migirim.
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "mainconnect fght baraye server iran ast"})
        server, domain = iran_main_server(s)
        return self._send(200, {"ok": bool(server), "server": server,
                                "domain": domain, "host": s.get("host", "")})

    def _discover(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        if s.get("role") != "iran":
            return self._send(400, {"error": "discover fght baraye server iran ast"})

        res = run_on_server(s, ["ratholectl", "ls"])
        nodes = []
        for line in (res.get("out", "") or "").splitlines():
            t = line.strip()
            if not t or t.startswith("NAME") or set(t) <= set("- "):
                continue
            parts = t.split()
            if parts and parts[0] not in nodes:
                nodes.append(parts[0])
        return self._send(200, {"server": name, "nodes": nodes, "raw": res.get("out", "")})

    def _status(self, name):
        s = self._find(name)
        if not s:
            return self._send(404, {"error": "server not found"})
        role = s.get("role")
        checks = (["doctor", "kcp_status", "noise_status"] if role == "iran" else ["kcp_status", "noise_status", "upstream_ls"])
        out = {}
        for act in checks:
            cmd = build_cmd(role, act, {})
            out[act] = run_on_server(s, cmd) if cmd else {"rc": 1, "err": "n/a"}
        return self._send(200, {"server": name, "role": role, "checks": out})


UI_HTML = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ratholehub</title>
<style>
 :root{--bg:#0a0f16;--panel:#111a25;--panel2:#17222f;--panel3:#1d2a3a;--line:#25364a;--tx:#e7eef6;--mut:#8ba0b6;--ac:#3b82f6;--gr:#22c55e;--rd:#ef4444;--yl:#eab308;
  --t-ws:#94a3b8;--t-kcp:#3b82f6;--t-noise:#a855f7;--t-plain:#f97316;
  --mono:Consolas,'Cascadia Mono',ui-monospace,Menlo,monospace;--sbw:210px;--rad:12px}
 *{box-sizing:border-box}
 body{font-family:system-ui,Segoe UI,Tahoma,sans-serif;margin:0;background:var(--bg);color:var(--tx)}
 .mono{font-family:var(--mono);font-size:12.5px}
 #app{display:flex;min-height:100vh;align-items:stretch}
 /* ---- sidebar ---- */
 #sb{width:var(--sbw);flex-shrink:0;position:sticky;top:0;height:100vh;background:var(--panel);border-inline-end:1px solid var(--line);display:flex;flex-direction:column;gap:2px;padding:14px 10px}
 #sb .logo{font-weight:700;font-size:18px;padding:4px 12px 14px}
 #sb .logo span{color:var(--ac)}
 .sitem{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:9px;color:var(--mut);cursor:pointer;font-size:14px;border-inline-start:3px solid transparent;user-select:none}
 .sitem:hover{background:var(--panel2);color:var(--tx)}
 .sitem.active{background:var(--panel3);color:var(--tx);border-inline-start-color:var(--ac)}
 .sitem .ic{width:18px;text-align:center;flex-shrink:0}
 .sfoot{margin-top:auto;display:flex;flex-direction:column;gap:8px;padding:10px 6px 2px;border-top:1px solid var(--line)}
 .sfoot .clock{color:var(--mut);font-size:12px;font-family:var(--mono);padding:0 6px}
 main#page{flex:1;min-width:0;padding:20px 22px;max-width:1220px;margin:0 auto}
 body.login #sb{display:none}
 body.login main#page{display:grid;place-items:center;max-width:none}
 /* ---- cards / panels ---- */
 .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);margin:14px 0;overflow:hidden}
 .chead{display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--panel2);border-bottom:1px solid var(--line);flex-wrap:wrap}
 .cbody{padding:14px 16px}
 .name{font-weight:700;font-size:16px}
 .sub{color:var(--mut);font-size:13px}
 button{background:var(--ac);color:#fff;border:0;border-radius:8px;padding:6px 11px;cursor:pointer;font-size:13px;transition:.15s}
 button:hover{filter:brightness(1.12)} button:active{transform:translateY(1px)}
 button.g{background:var(--gr)} button.r{background:var(--rd)} button.s{background:#475569} button.gh{background:transparent;border:1px solid var(--line);color:var(--tx)}
 .btns{display:flex;flex-wrap:wrap;gap:6px}
 input,select{background:var(--bg);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:7px 9px;font-size:13px}
 .badge{padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600}
 .b-ok{background:rgba(34,197,94,.16);color:#4ade80} .b-bad{background:rgba(239,68,68,.16);color:#f87171}
 .b-kcp{background:rgba(59,130,246,.18);color:#93c5fd} .b-ws{background:rgba(148,163,184,.16);color:#cbd5e1} .b-noise{background:rgba(147,51,234,.18);color:#c4b5fd}
 .b-plain{background:rgba(249,115,22,.16);color:#fdba74}
 .b-role{background:rgba(234,179,8,.16);color:#fde047}
 table{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}
 th,td{text-align:start;padding:7px 9px;border-bottom:1px solid var(--line)}
 th{color:var(--mut);font-weight:600} tr:last-child td{border-bottom:0}
 .sec{margin-top:12px} .sec h4{margin:0 0 6px;font-size:13px;color:var(--mut);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex-shrink:0} .d-ok{background:var(--gr)} .d-bad{background:var(--rd)} .d-un{background:var(--yl)}
 .up{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0}
 .pbar{flex:1;min-width:120px;height:10px;background:var(--bg);border:1px solid var(--line);border-radius:6px;overflow:hidden}
 .pfill{height:100%;background:var(--gr);transition:width .3s ease}
 .updrow{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px;border-top:1px solid var(--line)}
 .updrow .us{color:var(--mut)}
 pre{background:#070c12;padding:10px;border-radius:8px;overflow:auto;max-height:220px;white-space:pre-wrap;font-size:12px;margin:8px 0 0;font-family:var(--mono)}
 .toast{position:fixed;bottom:18px;left:18px;max-width:520px;background:#070c12;border:1px solid var(--line);border-radius:10px;padding:12px 14px;font-size:12px;white-space:pre-wrap;display:none;z-index:20;box-shadow:0 8px 30px rgba(0,0,0,.5)}
 .toast.show{display:block}
 .empty{color:var(--mut);font-size:13px;padding:6px 0}
 label.sw{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--mut);cursor:pointer}
 .addbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
 /* ---- dashboard grid / list ---- */
 .ptitle{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:2px 0 12px}
 .ptitle h2{margin:0;font-size:19px}
 .vswitch{display:flex;gap:2px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:2px}
 .vswitch button{background:transparent;color:var(--mut);padding:4px 10px;border-radius:6px}
 .vswitch button.on{background:var(--panel3);color:var(--tx)}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:12px;margin-top:12px}
 .scard{background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);padding:13px 15px;cursor:pointer;transition:border-color .15s,transform .15s;display:flex;flex-direction:column;gap:8px}
 .scard:hover{border-color:var(--ac);transform:translateY(-1px)}
 .scard .top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
 .scard .host{color:var(--mut)}
 .scard .bstrip{display:flex;gap:5px;flex-wrap:wrap;min-height:22px}
 .scard .meta{color:var(--mut);font-size:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
 .scard .meta .qr{margin-inline-start:auto}
 .grid.list{grid-template-columns:1fr;gap:8px}
 .grid.list .scard{flex-direction:row;align-items:center;padding:9px 15px;gap:12px}
 .grid.list .scard .top{flex:0 0 auto;min-width:210px}
 .grid.list .scard .bstrip{flex:1;min-height:0}
 .grid.list .scard .meta{flex:0 0 auto}
 /* ---- server page ---- */
 .spage-head{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--panel2);border:1px solid var(--line);border-radius:var(--rad);padding:12px 16px;margin-bottom:4px}
 .spage .sec{background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);padding:12px 14px;margin-top:12px}
 .back{background:transparent;border:1px solid var(--line);color:var(--tx);border-radius:8px;font-size:15px;padding:4px 12px}
 /* ---- routing graph ---- */
 .gwrap{direction:ltr;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);margin-top:12px}
 .gwrap svg{display:block;width:100%;min-width:780px;height:auto}
 .gbox{fill:var(--panel2);stroke:var(--line);cursor:pointer;transition:.15s}
 .gbox:hover{stroke:var(--ac)}
 .gbox-iran{stroke:#31527d}
 .gbox-ext{stroke-dasharray:5 4;opacity:.8;cursor:default}
 .gbox-off{opacity:.5}
 .gcolhead{fill:var(--mut);font-size:12px;font-weight:600}
 .gtxt{fill:var(--tx);font-size:13.5px;font-weight:700;cursor:pointer}
 .gsub{fill:var(--mut);font-size:11px;font-family:var(--mono)}
 .edge{fill:none;stroke-width:2;opacity:.9}
 .e-user{stroke:#3b4c61;stroke-width:1.5}
 .e-ws{stroke:var(--t-ws)} .e-kcp{stroke:var(--t-kcp);stroke-dasharray:9 5}
 .e-noise{stroke:var(--t-noise);stroke-dasharray:3 5} .e-plain{stroke:var(--t-plain);stroke-dasharray:12 4}
 .e-bad{stroke:var(--rd) !important;stroke-dasharray:3 4}
 .e-dim{opacity:.3}
 .flow{animation:dashflow 1.1s linear infinite}
 @keyframes dashflow{to{stroke-dashoffset:-28}}
 @media (prefers-reduced-motion:reduce){.flow{animation:none}}
 .elab rect{fill:#0b131d;stroke:var(--line);rx:9}
 .elab text{fill:var(--tx);font-size:11px;font-family:var(--mono);cursor:pointer}
 .legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--mut);margin:10px 2px;align-items:center;direction:ltr}
 .legend .li{display:flex;gap:7px;align-items:center}
 .legend .lw{width:28px;height:0;border-top:2.5px solid}
 .lw-ws{border-color:var(--t-ws)} .lw-kcp{border-color:var(--t-kcp);border-top-style:dashed}
 .lw-noise{border-color:var(--t-noise);border-top-style:dotted} .lw-plain{border-color:var(--t-plain);border-top-style:dashed}
 .lw-bad{border-color:var(--rd);border-top-style:dashed}
 /* ---- routing console (interactive: vorodi → router → khorooji) ---- */
 .rc{display:flex;flex-direction:column;gap:14px;margin-top:12px}
 .rcard{background:var(--panel);border:1px solid var(--line);border-radius:var(--rad);overflow:hidden}
 .rc-head{display:flex;align-items:center;gap:10px;padding:11px 15px;background:var(--panel2);border-bottom:1px solid var(--line);flex-wrap:wrap}
 .rc-head .nm{font-weight:700;font-size:15px} .rc-head .hst{color:var(--mut);font-size:12.5px;font-family:var(--mono)}
 .rc-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:0}
 .rc-col{padding:13px 15px;min-width:0} .rc-col+.rc-col{border-inline-start:1px solid var(--line)}
 .rc-col>h5{margin:0 0 4px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);display:flex;align-items:center;gap:7px}
 .rc-col>h5 .cnt{background:var(--panel3);border-radius:20px;padding:1px 8px;font-size:11px;letter-spacing:0;color:var(--tx)}
 .rc-sub{color:var(--mut);font-size:11.5px;margin:0 0 10px}
 /* lane = yek masir-e vorodi (chegoonegi-ye vorood-e karbar) */
 .lane{border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin-bottom:8px;background:var(--bg)}
 .lane.on{border-color:color-mix(in srgb,var(--lanec) 55%,var(--line));box-shadow:inset 3px 0 0 var(--lanec)}
 .lane .lh{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
 .lane .lh .lt{font-weight:600;font-size:13px} .lane .lh .lp{font-family:var(--mono);font-size:12px;color:var(--mut)}
 .lane .ld{color:var(--mut);font-size:11.5px;margin-top:3px;line-height:1.5}
 .lane .lact{margin-inline-start:auto;display:flex;gap:5px;flex-wrap:wrap}
 .ldot{width:8px;height:8px;border-radius:50%;background:var(--lanec);flex-shrink:0;box-shadow:0 0 0 3px color-mix(in srgb,var(--lanec) 22%,transparent)}
 .lane.off .ldot{background:var(--mut);box-shadow:none;opacity:.5}
 .lane-tls{--lanec:var(--gr)} .lane-plain{--lanec:var(--t-plain)} .lane-direct{--lanec:var(--yl)} .lane-sni{--lanec:var(--t-noise)}
 /* khorooji = node ba recipe-haye ettesal */
 .onode{border:1px solid var(--line);border-radius:10px;margin-bottom:9px;overflow:hidden}
 .onode.off{opacity:.55}
 .onode .oh{display:flex;align-items:center;gap:8px;padding:8px 11px;background:var(--panel2);flex-wrap:wrap}
 .onode .oh .onm{font-weight:600;font-size:13px} .onode .oh .otr{margin-inline-start:auto}
 .recipe{border-top:1px solid var(--line);padding:8px 11px;display:flex;flex-direction:column;gap:3px;font-family:var(--mono);font-size:12px}
 .recipe:first-of-type{border-top:0}
 .recipe .rl{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
 .recipe .rl .k{color:var(--mut);min-width:64px;font-size:11px} .recipe .rl .v{color:var(--tx);word-break:break-all}
 .recipe .rtag{font-size:10.5px;font-weight:700;padding:1px 8px;border-radius:20px;letter-spacing:.03em}
 .recipe .cpy{margin-inline-start:auto;background:transparent;border:1px solid var(--line);color:var(--mut);padding:3px 9px;font-size:11px;border-radius:7px}
 .recipe .cpy:hover{color:var(--tx);border-color:var(--ac)}
 .rc-empty{color:var(--mut);font-size:12.5px;padding:10px 2px}
 /* ---- modal ---- */
 .modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:50}.mbox{background:#0f1720;border:1px solid #2b3a4a;border-radius:12px;padding:18px;min-width:320px;max-width:90vw;max-height:85vh;overflow:auto}.mbox h3{margin:0 0 12px}.mbox .row{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}.mbox label{min-width:120px;color:#9fb3c8}.mbox input,.mbox select{background:#0b1219;border:1px solid #2b3a4a;color:#e6eef7;border-radius:8px;padding:6px 8px}.mbox table{width:100%;border-collapse:collapse;font-size:12px}.mbox td,.mbox th{border-bottom:1px solid #22303c;padding:4px 6px;text-align:start}
 /* ---- mobile ---- */
 @media (max-width:760px){
  #app{flex-direction:column}
  #sb{width:auto;height:auto;position:sticky;top:0;z-index:10;flex-direction:row;align-items:center;overflow-x:auto;padding:6px 8px;gap:4px;border-inline-end:0;border-bottom:1px solid var(--line)}
  #sb .logo{padding:2px 8px;font-size:15px;flex-shrink:0}
  .sitem{padding:7px 10px;border-inline-start:0;border-bottom:2px solid transparent;border-radius:7px;flex-shrink:0}
  .sitem.active{border-inline-start:0;border-bottom-color:var(--ac)}
  .sfoot{margin:0;margin-inline-start:auto;flex-direction:row;align-items:center;border-top:0;padding:0 4px;gap:6px;flex-shrink:0}
  .sfoot .clock{display:none}
  main#page{padding:12px}
  .rc-body{grid-template-columns:1fr}
  .rc-col+.rc-col{border-inline-start:0;border-top:1px solid var(--line)}
 }
</style></head><body>
<div id="app"></div>
<div class="toast" id="toast" onclick="this.classList.remove('show')"></div>
<script>
const $=id=>document.getElementById(id);
let TOKEN=localStorage.getItem('rh_token')||'';
let SERVERS=[];
let LANG=localStorage.getItem('rh_lang')||'fa';

// ---------- i18n (fa/en) — faghat baraye hub ----------
const DICT={
 fa:{
  auto:'refresh khodkar',refresh:'refresh',settings:'tanzimat',audit:'log faaliat',logout:'khorooj',
  login_title:'vorod be panel',pw_ph:'ramz modiriat',login_btn:'vorod',pw_wrong:'ramz eshtebah ast',
  add_server:'afzoodan server',f_name:'nam',f_host:'host/IP',f_user:'karbar SSH',f_port:'port SSH',add_btn:'+ afzoodan',
  prov_btn:'nasb khodkar',prov_pw:'ramz SSH (root)',provisioning:'dar hal etesal va nasb…',
  prov_hint:'ba ramz SSH vasl mishavad, kelid hub ra nasb mikonad, scriptha ra deploy va server ra be hub ezafe mikonad. (niazmand sshpass rooye hub)',

  role:'naghsh',details:'jozyiat',update:'apdit',edit_server:'virayesh server',del_server:'hazf server',
  loading:'dar hal daryaft vaziat…',no_servers:'hanoz serveri ezafe nashode. az bala ezafe kon.',
  no_ssh:'dastresi SSH nadarad',ssh_help:'atesal SSH barghrar nashod. kelid hub ra authorize kon:',
  kcp_backbone:'tunnel KCP (backbone be Iran)',kcp_on:'kcp on',kcp_off:'kcp off',show_key:'namayesh KEY node',
  plain_mode:'halat plain (bedoon TLS):',plain_on:'plain on',plain_off:'plain off',
  t_plain_iran:'roshan kardan plain (samt Iran)',l_plain_port:'port HTTP (masalan 8880)',
  t_plain_node:'roshan kardan plain (samt node)',l_plain_remote:'IP:PORT Iran (TCP HTTP)',
  noise_mode:'halat noise (ramznegari-shode, bedoon TLS/cert):',noise_on:'noise on',noise_off:'noise off',noise_node_on:'in node → noise',noise_node_off:'in node → ws',
  t_noise_iran:'roshan kardan noise (samt Iran)',l_noise_port:'port TCP omomi (masalan 2334)',
  t_noise_node:'roshan kardan noise (samt node)',l_noise_remote:'IP:PORT Iran (TCP noise)',l_noise_key:'pubkey server (az "namayesh")',l_noise_pattern:'pattern (pishfarz: Noise_NK...)',
  direct_mode:'halat direct-IP (masiryabi ba header, bedoon TLS):',direct_on:'direct on',direct_off:'direct off',
  t_direct_iran:'roshan kardan direct-IP (samt Iran)',l_direct_port:'port HTTP (masalan 8081)',l_direct_header:'naam header (masalan X-Cdn-Id)',

  restart_rathole:'restart rathole',cf_restart:'restart rathole-server? hameye tunnelha lahzei ghat mishavand.',
  fakeweb:'web fake:',fw_start:'roshan/taghir port',fw_stop:'tavaghof',fw_rm:'khamoosh kamel',cf_fwrm:'hazf kamel web fake?',
  nodes_svcs:'nodeha / serviceha',add_node:'+ afzoodan node',no_nodes:'nodi tarif nashode.',
  c_name:'nam',c_dport:'port dade',c_inbound:'inbound',c_api:'API',c_ops:'amaliat',
  show_token:'nasb/token',edit:'virayesh',rename:'taghir nam',rotate:'chrkhesh token',cf_rotate:'chrkhesh token node',remove:'hazf',
  game_svcs:'servicehaye game (SNI/443)',add_game:'+ game',get_cert:'greftan gvahi',no_game:'service game nadari.',
  c_data:'dade',c_node_inb:'inbound node',
  main_tunnel:'tunnel asli →',restart_tunnel:'restart tunnel',migrate:'naghshe mohajerat',
  set_main:'tanzim tunnel asli',l_iran_srv:'server Iran',no_iran:'hich server Iran dar hub sabt nashode — aval yeki ezafe kon.',
  wire_to_node:'afzoodan be node',wire_title:'sim-keshi node be maghsad',l_dst_node:'maghsad (node / upstream)',
  upd_all:'apdit-e hame',cf_upd_all:'hameye serverha yeki-yeki apdit shavand?',upd_wait:'dar saf',upd_running:'dar hal apdit…',
  upd_ok:'apdit shod',upd_fail:'shekast',upd_done:'apdit tamam shod',ver_ok:'noskhe be-ruz ast',ver_old:'noskhe ghadimi — apdit kon',
  no_node_dst:'hich node-e kharej dardastras nist (aval yek node ezafe/roshan kon).',wire_fail:'gereftan token-e node shekast khord.',
  watchdog:'watchdog (restart khodkar):',wd_on:'roshan',wd_off:'khamoosh',wd_status:'vaziat',
  svc_tunnel:'servicehaye in tunnel',add_svc:'+ service',no_svc:'servisi nist.',c_svc:'service',
  upstreams:'serverhaye Iran-e digar (upstream)',add_up:'+ upstream',no_up:'upstream nadari (faghat yek Iran).',status:'status',del_up:'hazf upstream',cf_delup:'hazf upstream',cf_delupsvc:'hazf service az upstream',

  cancel:'enseraf',save:'zakhire',fill:'hameye field haye lazem ra por kon',saved:'zakhire shod ✓',
  cf_delsrv:'hazf server az panel?',cf_delnode:'hazf node',cf_delsvc:'hazf service',cf_deploy:'apdit az GitHub (akharin Release) rooye',
  copy_out:'copy khorooji',close:'bastan',copied:'copy shod ✓',loading_det:'dar hal daryaft jozyiat…',
  // form titles/labels
  t_kcp_iran:'roshan kardan KCP (samt Iran)',l_udp:'port UDP (443 = estetar QUIC)',l_profile:'profile',
  t_kcp_node:'roshan kardan KCP (samt node)',l_remote:'IP:PORT Iran (UDP)',l_key:'KEY (az "namayesh KEY node")',
  t_kcp_up:'roshan kardan KCP (upstream)',
  l_autofill:'daryaft khodkar az server Iran',autofilling:'daryaft key/IP az Iran…',autofilled:'meghdar por shod ✓ (remote/key/profile motabegh Iran)',autofail:'daryaft nashod — motmaen sho rooye Iran "kcp on" zade shode',

  t_game_add:'afzoodan service game',l_inb_tls:'port inbound TLS rooye node',l_sni:'SNI (masalan gmtrk.l1t.ir)',
  t_game_cert:'greftan gvahi TLS',l_sni_cert:'SNI (DNS be in server, port 80 azad)',
  t_add_node:'afzoodan node',l_node_name:'nam node (path)',l_xray_inb:'port inbound Xray',l_api_opt:'port API (ekhtiari)',
  t_add_svc:'afzoodan service (hamnam ba Iran)',l_token:'token',l_inbound:'port inbound',
  t_up_add:'afzoodan upstream',l_up_id:'shenase upstream (masalan iran2)',l_up_srv:'server Iran-e dovom (host:port)',
  t_up_addsvc:'afzoodan service be upstream',
  t_fw:'roshan kardan web fake',l_fw_port:'port (khali = pishfarz fake_port)',
  t_wd:'roshan kardan watchdog',l_wd_iv:'baze check (sanie)',
  t_edit_node:'virayesh node',l_inb_new:'inbound jadid (khali = bedoon taghir)',l_api_new:'port API jadid (off=hazf, khali=bedoon taghir)',nochg:'chizi baraye taghir nist',
  t_rename:'taghir nam node',l_new_name:'nam jadid',
  t_edit_srv:'virayesh server',
  t_settings:'tanzimat panel',l_apitoken:'token API',l_listen:'listen', insecure:'hoshdar: ramz/token pishfarz naamn ast',
  chpw:'taghir ramz modiriat',l_curpw:'ramz feli',l_newpw:'ramz jadid',pw_hint:'hadaghal 6 karakter',save_pw:'zakhire ramz',
  rot_tok:'chrkhesh token API (niazmand vorod mojadad)',cf_rottok:'token API chrkhande shavad? bayad dobare vared shavi.',
  pw_changed:'ramz taghir kard ✓',tok_applied:'token jadid emal shod ✓',need_newpw:'ramz jadid ra vared kon',
  t_audit:'log faaliat (100 morede akhir)',no_audit:'chizi sabt nashode.',c_time:'zaman',c_user:'karbar',c_action:'amaliat',
  domain_tls:'damnh / TLS',manage:'modiriat',domain_hint:'taghir damnh, masir gvahi, ya greftan gvahi Let\'s Encrypt. baraye damnhi dovom az bakhsh game (SNI) estefade kon.',
  status_btn:'vaziat',status_err:'khorooji-ye status khande nashod.',
  st_domain:'damnh',st_ip:'IP omomi',st_transport:'transport-e faal',st_services:'service-ha',st_ports:'port-ha',
  st_ok:'salem',st_bad:'khata',st_cert:'gvahi (TLS)',st_cert_ok:'mojood',st_cert_missing:'peyda nashod',st_selfsigned:'self-signed!',
  st_nodes:'node-ha',st_no_nodes:'hich node-i ezafe nashode.',
  st_p_443:'vrvdi-ye asli (nginx TLS/SNI)',st_p_control:'kontrol-e rathole (lokal)',st_p_fake:'sait-e fik/panel (lokal)',
  st_p_sub:'sabaskripshn (lokal)',st_p_internal:'panel-e dakheli (posht-e SNI)',st_p_plain:'plain (ws bedoon TLS)',
  st_p_direct:'direct-IP (header)',st_p_hub:'hub (lokal, zir /hub/)',st_p_noise:'noise (ramznegari-shode)',
  dt_show:'namayesh feli',dt_hint:'khorooji dar toast',dt_domain:'damnh asli',dt_fc:'masir fullchain',dt_key:'masir privkey',
  dt_le:'greftan gvahi (domain/email)',dt_get:'begir',dt_apply:'emal (regen)',
  dt_list:'gvahihaye mojood rooye in server:',dt_active:'faal',dt_expiry:'enghza',dt_none:'gvahii peyda nashod.',
  dt_served:'damnhhaye faal rooye in server:',dt_kind:'nooe',dt_primary:'asli',dt_extra:'ezafi',dt_add:'afzoodan damnh',dt_add_btn:'+ damnh',dt_makeprimary:'asli kon',dt_mp_confirm:'damnh asli avaz shavad be',
  running:'ejra-ye',on:'rooye',ok_rc:'anjam shod',fail_rc:'nashod',
  nav_dash:'dashbord',nav_routing:'naghshe masirha',back:'bazgasht',
  view_grid:'kart',view_list:'list',
  n_nodes:'node',n_svcs:'service',n_ups:'upstream',n_game:'game',
  srv_notfound:'server peyda nashod',
  g_users:'karbaran',g_iran_col:'serverhaye Iran',g_node_col:'nodehaye kharej',
  g_legend:'rahnama',g_loading:'dar hal sakhtan naghshe…',g_empty:'serveri baraye namayesh nist.',
  g_external:'server-e kharej az panel',g_hint:'rooye har box ya label click kon ta safhe-ye server baz shavad.',
  g_drag:'boxha ra mitavani bala/paeen bekeshi — tartib zakhire mishavad.',g_reset:'reset chinesh',
  view_graph:'graph',view_table:'jadval',
  c_tunnel:'tunnel',c_status:'vaziat',c_upstream:'upstream',c_iran:'server Iran',c_node:'node',
  tun_up:'tunnel vasl',tun_down:'tunnel ghat',
  view_console:'konsol',rc_pick_iran:'aval yek server-e Iran ezafe kon.',rc_unreach:'server dar dastras nist (SSH).',
  rc_ingress:'vorodi-ha (karbar chegoone vasl mishavad)',rc_ingress_sub:'har masir yek ravesh-e vorood-e karbar ast — mostaghel az transport-e tunnel.',
  rc_outputs:'khorooji-ha (node-ha)',rc_outputs_sub:'har node backend ast; transport-e reverse-tunnel-esh joda az ravesh-e vorood-e karbar ast.',
  rc_no_nodes:'rooye in server node-i nist.',
  ing_tls_t:'masir + TLS (443)',ing_tls_p:'wss://<domain>:443/<node>',
  ing_tls_d:'pishfarz. karbar ba WebSocket+TLS rooye 443 vasl mishavad; node ba path route mishavad.',
  ing_plain_t:'plain (ws bedoon TLS)',ing_plain_p:'ws://<ip>:<port>/<node>',
  ing_plain_d:'listener-e HTTP-e sade rooye port-e joda. karbar bedoon TLS ba path route mishavad.',
  ing_direct_t:'direct — masiryabi ba header (bedoon TLS)',ing_direct_p:'ws://<ip>:<port>  +  <header>: <node>',
  ing_direct_d:'listener-e HTTP-e sade; node NA ba path balke ba header entekhab mishavad. daghighan halat-e "TCP bedoon PF/TLS + header".',
  ing_sni_t:'game / SNI (443 passthrough)',ing_sni_d:'agar node-i SNI dashte bashad, 443 be halat-e L4/SNI miravad va TLS rooye node terminate mishavad.',
  rc_on:'roshan',rc_off:'khamoosh',rc_enable:'roshan kon',rc_disable:'khamoosh',rc_edit:'virayesh',
  rc_recipe:'recipe-e ettesal-e karbar',rc_via:'az tarigh',rc_copy:'copy',rc_copied:'copy shod',
  rc_transport:'transport-e tunnel',rc_reach:'chegoone karbar be in node mireside',
  rc_addr:'address',rc_port:'port',rc_wspath:'ws path',rc_wshost:'ws Host',rc_header:'header',rc_tls:'TLS',
  rc_yes:'bale',rc_no:'kheyr',rc_hosthint:'har domain-e bikhatar (decoy)',
  rc_off_hint:'in vorodi khamoosh ast — baraye didane recipe roshan-esh kon.',
  rc_legend:'transport = tunnel-e node be Iran · ingress = vorood-e karbar',
  hub_box:'server-e hub',hs_up:'uptime',hs_load:'load',hs_mem:'RAM',hs_disk:'disk azad',
  nd_up:'faal',nd_down:'ghat',e_bad:'edge ghermez = node vasl nist (doctor)',
 },
 en:{
  auto:'Auto refresh',refresh:'Refresh',settings:'Settings',audit:'Activity log',logout:'Logout',
  login_title:'Panel login',pw_ph:'Admin password',login_btn:'Login',pw_wrong:'Wrong password',
  add_server:'Add server',f_name:'Name',f_host:'Host/IP',f_user:'SSH user',f_port:'SSH port',add_btn:'+ Add',
  prov_btn:'Auto install',prov_pw:'SSH password (root)',provisioning:'Connecting & installing…',
  prov_hint:'Connects via SSH password, installs the hub key, deploys the scripts and adds the server to the hub. (requires sshpass on the hub)',

  role:'Role',details:'Details',update:'Update',edit_server:'Edit server',del_server:'Remove server',
  loading:'Loading status…',no_servers:'No servers yet. Add one above.',
  no_ssh:'No SSH access',ssh_help:'SSH connection failed. Authorize the hub key:',
  kcp_backbone:'KCP tunnel (backbone to Iran)',kcp_on:'kcp on',kcp_off:'kcp off',show_key:'Show node KEY',
  plain_mode:'Plain mode (no TLS):',plain_on:'plain on',plain_off:'plain off',
  t_plain_iran:'Enable plain (Iran side)',l_plain_port:'HTTP port (e.g. 8880)',
  t_plain_node:'Enable plain (node side)',l_plain_remote:'IP:PORT Iran (TCP HTTP)',
  noise_mode:'Noise mode (encrypted, no TLS/cert):',noise_on:'noise on',noise_off:'noise off',noise_node_on:'this node → noise',noise_node_off:'this node → ws',
  t_noise_iran:'Enable noise (Iran side)',l_noise_port:'Public TCP port (e.g. 2334)',
  t_noise_node:'Enable noise (node side)',l_noise_remote:'IP:PORT Iran (TCP noise)',l_noise_key:'Server pubkey (from "Show")',l_noise_pattern:'Pattern (default: Noise_NK...)',
  direct_mode:'Direct-IP (header routing, no TLS):',direct_on:'direct on',direct_off:'direct off',
  t_direct_iran:'Enable direct-IP (Iran side)',l_direct_port:'HTTP port (e.g. 8081)',l_direct_header:'Header name (e.g. X-Cdn-Id)',

  restart_rathole:'restart rathole',cf_restart:'Restart rathole-server? All tunnels drop briefly.',
  fakeweb:'Fake web:',fw_start:'Start/Change port',fw_stop:'Stop',fw_rm:'Remove fully',cf_fwrm:'Remove fake web completely?',
  nodes_svcs:'Nodes / Services',add_node:'+ Add node',no_nodes:'No nodes defined.',
  c_name:'Name',c_dport:'Data port',c_inbound:'Inbound',c_api:'API',c_ops:'Actions',
  show_token:'Install/token',edit:'Edit',rename:'Rename',rotate:'Rotate token',cf_rotate:'Rotate token for node',remove:'Remove',
  game_svcs:'Game services (SNI/443)',add_game:'+ game',get_cert:'Get certificate',no_game:'No game services.',
  c_data:'Data',c_node_inb:'Node inbound',
  main_tunnel:'Main tunnel →',restart_tunnel:'restart tunnel',migrate:'Migration map',
  set_main:'Set main tunnel',l_iran_srv:'Iran server',no_iran:'No Iran server registered in the hub — add one first.',
  wire_to_node:'Add to node',wire_title:'Wire node to target',l_dst_node:'Target (node / upstream)',
  upd_all:'Update all',cf_upd_all:'Update all servers one by one?',upd_wait:'queued',upd_running:'updating…',
  upd_ok:'updated',upd_fail:'failed',upd_done:'update finished',ver_ok:'version up to date',ver_old:'outdated — please update',
  no_node_dst:'No foreign node reachable (add/start one first).',wire_fail:'Failed to fetch node token.',
  watchdog:'watchdog (auto restart):',wd_on:'On',wd_off:'Off',wd_status:'Status',
  svc_tunnel:'Services on this tunnel',add_svc:'+ service',no_svc:'No services.',c_svc:'Service',
  upstreams:'Other Iran servers (upstream)',add_up:'+ upstream',no_up:'No upstream (single Iran).',status:'status',del_up:'Remove upstream',cf_delup:'Remove upstream',cf_delupsvc:'Remove service from upstream',

  cancel:'Cancel',save:'Save',fill:'Fill all required fields',saved:'Saved ✓',
  cf_delsrv:'Remove server from panel?',cf_delnode:'Remove node',cf_delsvc:'Remove service',cf_deploy:'Update from GitHub (latest Release) on',
  copy_out:'Copy output',close:'Close',copied:'Copied ✓',loading_det:'Loading details…',
  t_kcp_iran:'Enable KCP (Iran side)',l_udp:'UDP port (443 = QUIC stealth)',l_profile:'Profile',
  t_kcp_node:'Enable KCP (node side)',l_remote:'IP:PORT Iran (UDP)',l_key:'KEY (from "Show node KEY")',
  t_kcp_up:'Enable KCP (upstream)',
  t_game_add:'Add game service',l_inb_tls:'TLS inbound port on node',l_sni:'SNI (e.g. gmtrk.l1t.ir)',
  t_game_cert:'Get TLS certificate',l_sni_cert:'SNI (DNS to this server, port 80 free)',
  t_add_node:'Add node',l_node_name:'Node name (path)',l_xray_inb:'Xray inbound port',l_api_opt:'API port (optional)',
  t_add_svc:'Add service (same name as Iran)',l_token:'Token',l_inbound:'Inbound port',
  t_up_add:'Add upstream',l_up_id:'Upstream id (e.g. iran2)',l_up_srv:'Second Iran server (host:port)',
  t_up_addsvc:'Add service to upstream',
  t_fw:'Start fake web',l_fw_port:'Port (empty = default fake_port)',
  t_wd:'Enable watchdog',l_wd_iv:'Check interval (sec)',
  t_edit_node:'Edit node',l_inb_new:'New inbound (empty = no change)',l_api_new:'New API port (off=remove, empty=no change)',nochg:'Nothing to change',
  t_rename:'Rename node',l_new_name:'New name',
  t_edit_srv:'Edit server',
  t_settings:'Panel settings',l_apitoken:'API token',l_listen:'listen',insecure:'Warning: default insecure password/token',
  chpw:'Change admin password',l_curpw:'Current password',l_newpw:'New password',pw_hint:'min 6 chars',save_pw:'Save password',
  rot_tok:'Rotate API token (requires re-login)',cf_rottok:'Rotate API token? You must log in again.',
  pw_changed:'Password changed ✓',tok_applied:'New token applied ✓',need_newpw:'Enter the new password',
  t_audit:'Activity log (last 100)',no_audit:'Nothing logged yet.',c_time:'Time',c_user:'User',c_action:'Action',
  domain_tls:'Domain / TLS',manage:'Manage',domain_hint:'Change domain, cert paths, or obtain a Let\'s Encrypt cert. For a second domain use the Game (SNI) section.',
  status_btn:'Status',status_err:'Could not read status output.',
  st_domain:'Domain',st_ip:'Public IP',st_transport:'Active transport',st_services:'Services',st_ports:'Ports',
  st_ok:'ok',st_bad:'error',st_cert:'Certificate (TLS)',st_cert_ok:'present',st_cert_missing:'not found',st_selfsigned:'self-signed!',
  st_nodes:'Nodes',st_no_nodes:'No nodes added.',
  st_p_443:'main ingress (nginx TLS/SNI)',st_p_control:'rathole control (local)',st_p_fake:'fake site/panel (local)',
  st_p_sub:'subscription (local)',st_p_internal:'internal panel (behind SNI)',st_p_plain:'plain (ws no TLS)',
  st_p_direct:'direct-IP (header)',st_p_hub:'hub (local, under /hub/)',st_p_noise:'noise (encrypted)',
  dt_show:'Show current',dt_hint:'output in toast',dt_domain:'Main domain',dt_fc:'fullchain path',dt_key:'privkey path',
  dt_le:'Obtain cert (domain/email)',dt_get:'Get',dt_apply:'Apply (regen)',
  dt_list:'Certificates on this server:',dt_active:'active',dt_expiry:'expiry',dt_none:'No certificates found.',
  dt_served:'Active domains on this server:',dt_kind:'Type',dt_primary:'primary',dt_extra:'extra',dt_add:'Add domain',dt_add_btn:'+ domain',dt_makeprimary:'Make primary',dt_mp_confirm:'Switch primary domain to',
  running:'running',on:'on',ok_rc:'done',fail_rc:'failed',
  nav_dash:'Dashboard',nav_routing:'Routing map',back:'Back',
  view_grid:'Grid',view_list:'List',
  n_nodes:'nodes',n_svcs:'services',n_ups:'upstreams',n_game:'game',
  srv_notfound:'Server not found',
  g_users:'Users',g_iran_col:'Iran servers',g_node_col:'Foreign nodes',
  g_legend:'Legend',g_loading:'Building map…',g_empty:'Nothing to draw yet.',
  g_external:'Server outside this panel',g_hint:'Click any box or label to open that server page.',
  g_drag:'Drag boxes up/down to reorder — order is saved.',g_reset:'Reset layout',
  view_graph:'Graph',view_table:'Table',
  c_tunnel:'Tunnel',c_status:'Status',c_upstream:'Upstream',c_iran:'Iran server',c_node:'Node',
  tun_up:'tunnel up',tun_down:'tunnel down',
  view_console:'Console',rc_pick_iran:'Add an Iran server first.',rc_unreach:'Server unreachable (SSH).',
  rc_ingress:'Ingress (how the user connects)',rc_ingress_sub:'Each lane is one way a user enters — independent of the tunnel transport.',
  rc_outputs:'Outputs (nodes)',rc_outputs_sub:'Each node is a backend; its reverse-tunnel transport is separate from how the user enters.',
  rc_no_nodes:'No nodes on this server.',
  ing_tls_t:'Path + TLS (443)',ing_tls_p:'wss://<domain>:443/<node>',
  ing_tls_d:'Default. User connects over WebSocket+TLS on 443; the node is chosen by path.',
  ing_plain_t:'Plain (ws, no TLS)',ing_plain_p:'ws://<ip>:<port>/<node>',
  ing_plain_d:'Bare HTTP listener on a separate port. User connects without TLS, routed by path.',
  ing_direct_t:'Direct — header routing (no TLS)',ing_direct_p:'ws://<ip>:<port>  +  <header>: <node>',
  ing_direct_d:'Bare HTTP listener; the node is picked by a header, not the path. Exactly the "TCP, no PF/TLS + header" case.',
  ing_sni_t:'Game / SNI (443 passthrough)',ing_sni_d:'If any node has an SNI, 443 switches to L4/SNI mode and TLS terminates on the node.',
  rc_on:'on',rc_off:'off',rc_enable:'Enable',rc_disable:'Disable',rc_edit:'Edit',
  rc_recipe:'User connection recipe',rc_via:'via',rc_copy:'copy',rc_copied:'copied',
  rc_transport:'Tunnel transport',rc_reach:'How a user reaches this node',
  rc_addr:'address',rc_port:'port',rc_wspath:'ws path',rc_wshost:'ws Host',rc_header:'header',rc_tls:'TLS',
  rc_yes:'yes',rc_no:'no',rc_hosthint:'any harmless domain (decoy)',
  rc_off_hint:'This ingress is off — enable it to see the recipe.',
  rc_legend:'transport = node→Iran tunnel · ingress = user entry',
  hub_box:'Hub server',hs_up:'uptime',hs_load:'load',hs_mem:'RAM',hs_disk:'disk free',
  nd_up:'up',nd_down:'down',e_bad:'red edge = node not connected (doctor)',
 }
};
function t(k){return (DICT[LANG]&&DICT[LANG][k])||DICT.fa[k]||k;}
function applyStatic(){
 document.documentElement.lang=LANG; document.documentElement.dir=(LANG==='fa'?'rtl':'ltr');
}
function toggleLang(){LANG=(LANG==='fa'?'en':'fa');localStorage.setItem('rh_lang',LANG);applyStatic();shell();}
function confirmT(k,extra){return confirm(t(k)+(extra?(' '+extra):'')+' ?');}

function h(t){return (''+(t==null?'':t)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function toast(t){const e=$('toast');e.textContent=t;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),5000);}
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
 if(TOKEN)o.headers['Authorization']='Bearer '+TOKEN; if(b)o.body=JSON.stringify(b);
 const r=await fetch(p,o); let j={};try{j=await r.json()}catch(e){}
 if(r.status===401){TOKEN='';localStorage.removeItem('rh_token');shell();} return {status:r.status,j};}
function logout(){TOKEN='';localStorage.removeItem('rh_token');shell();}
function modal(html){let m=$('modal');if(!m){m=document.createElement('div');m.id='modal';m.className='modal';m.onclick=e=>{if(e.target===m)closeModal();};document.body.appendChild(m);}m.innerHTML='<div class="mbox">'+html+'</div>';m.style.display='flex';}
function closeModal(){const m=$('modal');if(m)m.style.display='none';}

// ---------- form modal (jaigozin prompt zanjire-i) ----------
// fields: [{id,label,type,val,ph,opts:[{v,t}],req}]  onOk(values)
function formModal(title,fields,onOk){
 const rows=fields.map(f=>{
  let inp;
  if(f.type==='select'){inp=`<select id="f_${f.id}">`+f.opts.map(o=>`<option value="${h(o.v)}"${o.v==(f.val||'')?' selected':''}>${h(o.t)}</option>`).join('')+`</select>`;}
  else{inp=`<input id="f_${f.id}" type="${f.type||'text'}" value="${h(f.val==null?'':f.val)}" placeholder="${h(f.ph||'')}">`;}
  return `<div class="row"><label>${h(f.label)}</label>${inp}</div>`;
 }).join('');
 modal(`<h3>${h(title)}</h3>${rows}<div class="row" style="margin-top:12px;justify-content:flex-end">
  <button class="gh" onclick="closeModal()">${t('cancel')}</button>
  <button class="g" id="f_ok">${t('save')}</button></div>`);
 setTimeout(()=>{const first=fields[0]&&$('f_'+fields[0].id);if(first)first.focus();},30);
 $('f_ok').onclick=()=>{
  const v={};let ok=true;
  fields.forEach(f=>{v[f.id]=($('f_'+f.id).value||'').trim();if(f.req&&!v[f.id])ok=false;});
  if(!ok){toast(t('fill'));return;}
  onOk(v);
 };
}
const PROF=[{v:'balanced',t:'balanced'},{v:'lossy',t:'lossy'},{v:'aggressive',t:'aggressive'}];

setInterval(()=>{const c=$('clock');if(c)c.textContent=new Date().toLocaleTimeString(LANG==='fa'?'fa-IR':'en-US');},1000);

// ---------- router (hash-based ta posht-e /hub/ ham kar konad) ----------
let OVS={};                                            // cache: name -> akharin overview
let VIEW=localStorage.getItem('rh_view')||'grid';      // chinesh dashboard: grid|list
let ROUTE={page:'dashboard',param:null};
function parseHash(){const hh=location.hash||'#/dashboard';
 let m=hh.match(/^#\/server\/([A-Za-z0-9_-]+)$/); if(m)return{page:'server',param:m[1]};
 m=hh.match(/^#\/(dashboard|routing|audit|settings)$/); return m?{page:m[1],param:null}:{page:'dashboard',param:null};}
function nav(hh){if(location.hash===hh){router();}else{location.hash=hh;}}
window.addEventListener('hashchange',()=>{if(TOKEN)router();});
function markNav(){document.querySelectorAll('.sitem').forEach(e=>{
 e.classList.toggle('active',e.dataset.pg===ROUTE.page);});}
async function router(){
 if(!TOKEN)return; ROUTE=parseHash(); markNav();
 await ensureServers();
 if(ROUTE.page==='server')renderServerPage(ROUTE.param);
 else if(ROUTE.page==='routing')renderRouting();
 else if(ROUTE.page==='audit')renderAuditPage();
 else if(ROUTE.page==='settings')renderSettingsPage();
 else renderDashboard();
}
async function ensureServers(){if(SERVERS.length)return;const {j}=await api('GET','api/servers');SERVERS=j||[];}
// sazegari ba code-haye ghadimi: refresh-e inventory + safhe-ye faal
async function loadAll(){SERVERS=[];await ensureServers();router();}
// vaghti overview miresad, faghat safhe-ye faal ra be-rooz kon
function onOv(n){
 if(ROUTE.page==='dashboard'){updateCard(n);
  // doctor-e iran vaziat-e tunnel-e node-ha ra moshakhas mikonad → kart-e node-ha ham berooz shavand
  if(fnd(n).role==='iran')SERVERS.filter(s=>s.role==='node').forEach(s=>updateCard(s.name));
  updateHubStrip();}
 else if(ROUTE.page==='server'&&ROUTE.param===n)renderServerPage(n);
 else if(ROUTE.page==='server'&&fnd(n).role==='iran'&&fnd(ROUTE.param).role==='node')renderServerPage(ROUTE.param);
 else if(ROUTE.page==='routing')scheduleGraph();
}
async function loadOv(n){const {j}=await api('GET','api/servers/'+n+'/overview');OVS[n]=j||{};onOv(n);}

function shell(){
 applyStatic();
 if(!TOKEN){document.body.classList.add('login');
  $('app').innerHTML=`<main id="page"><div class="card" style="min-width:300px"><div class="cbody"><h3>${t('login_title')}</h3>
   <div class="addbar"><input id="pw" type="password" placeholder="${t('pw_ph')}" style="min-width:220px">
   <button class="g" onclick="doLogin()">${t('login_btn')}</button></div><div id="msg" class="sub"></div></div></div></main>`;
  const p=$('pw'); if(p)p.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();}); return;}
 document.body.classList.remove('login');
 $('app').innerHTML=`<nav id="sb">
   <div class="logo">rathole<span>hub</span></div>
   <div class="sitem" data-pg="dashboard" onclick="nav('#/dashboard')"><span class="ic">▦</span><span>${t('nav_dash')}</span></div>
   <div class="sitem" data-pg="routing" onclick="nav('#/routing')"><span class="ic">◈</span><span>${t('nav_routing')}</span></div>
   <div class="sitem" data-pg="audit" onclick="nav('#/audit')"><span class="ic">≡</span><span>${t('audit')}</span></div>
   <div class="sitem" data-pg="settings" onclick="nav('#/settings')"><span class="ic">⚙</span><span>${t('settings')}</span></div>
   <div class="sfoot">
    <span class="clock" id="clock"></span>
    <label class="sw"><input type="checkbox" id="auto" checked> <span>${t('auto')}</span></label>
    <div class="btns"><button class="gh" onclick="toggleLang()">${LANG==='fa'?'EN':'فا'}</button>
    <button class="gh" onclick="refreshPage()">${t('refresh')}</button>
    <button class="s" onclick="logout()">${t('logout')}</button></div>
   </div></nav><main id="page"></main>`;
 router();
}
function refreshPage(){SERVERS=[];ensureServers().then(()=>{router();pollByPage();});}
// polling-e hoshmand: faghat overview-haye lazem baraye safhe-ye faal
function pollByPage(){
 if(!TOKEN)return;
 if(ROUTE.page==='server'&&ROUTE.param){loadOv(ROUTE.param);
  // vaziat-e tunnel-e node az doctor-e Iran miayad → overview-e Iran-ha ham lazem ast
  if(fnd(ROUTE.param).role==='node')SERVERS.filter(s=>s.role==='iran').forEach(s=>loadOv(s.name));}
 else if(ROUTE.page==='dashboard'||ROUTE.page==='routing'){SERVERS.forEach(s=>loadOv(s.name));}
 if(ROUTE.page==='dashboard')loadHubStatus();
}
async function doLogin(){const {status,j}=await api('POST','api/login',{password:$('pw').value});
 if(status===200){TOKEN=j.token;localStorage.setItem('rh_token',TOKEN);if(!location.hash)location.hash='#/dashboard';shell();}else{$('msg').textContent=t('pw_wrong');}}
function fnd(n){return SERVERS.find(s=>s.name===n)||{};}
function setDot(n,cls){const d=$('dot_'+n); if(d)d.className='dot '+cls;}

// ---------- vaziat-e vasl boodan-e tunnel-e node (az doctor-e serverhaye Iran) ----------
// doctor rooye Iran har node ra ok/warn mikonad; inja natije baraye yek server-e node
// jam mishavad: 'ok' (hameye service-ha vasl), 'warn' (hadaghal yeki ghat), ya null (namalum).
function nodeTunnelStatus(n){
 const ov=OVS[n]; if(!ov||ov.reachable===false)return null;
 const keys=[n].concat((ov.services||[]).map(x=>x.name));
 (ov.upstreams||[]).forEach(u=>(u.services||[]).forEach(x=>keys.push(x.name)));
 let seen=false,bad=false;
 SERVERS.filter(s=>s.role==='iran').forEach(s=>{
  const hn=(((OVS[s.name]||{}).health)||{}).nodes||{};
  keys.forEach(k=>{if(k in hn){seen=true;if(hn[k]==='warn')bad=true;}});
 });
 return seen?(bad?'warn':'ok'):null;
}
// ---------- badge-haye khoolase (moshtarak beyne kart va safhe-ye server) ----------
function headBadges(n,ov){
 const role=fnd(n).role;
 if(!ov||ov.reachable===false)return `<span class="badge b-bad">${t('no_ssh')}</span>`;
 let hb='';
 if(role==='iran'){const ok=(ov.health||{}).fail===0;
  hb=`<span class="badge ${ok?'b-ok':'b-bad'}">doctor ${(ov.health||{}).ok||0}/${((ov.health||{}).ok||0)+((ov.health||{}).fail||0)}</span>`;
  const k=ov.kcp||{}; hb+=k.enabled?` <span class="badge b-kcp">kcp ${h(k.profile||'')}${k.port?(' :'+h(k.port)):''}${k.stealth?' · QUIC':''}</span>`:' <span class="badge b-ws">ws/443</span>';
  const nz=ov.noise||{}; if(nz.enabled){hb+=` <span class="badge b-noise">noise${nz.port?(' :'+h(nz.port)):''}${nz.count?(' · '+h(nz.count)+' node'):''}</span>`;}
 }else{const m=ov.main_tunnel||(ov.kcp||{}).mode||'ws';
  hb=m==='noise'?`<span class="badge b-noise">tunnel noise</span>`:(m==='kcp'?`<span class="badge b-kcp">tunnel kcp ${h((ov.kcp||{}).profile||'')}</span>`:(m==='plain'?`<span class="badge b-plain">tunnel plain</span>`:'<span class="badge b-ws">tunnel ws/443</span>'));
  if((ov.noise||{}).enabled&&m!=='noise'){hb+=' <span class="badge b-noise">noise</span>';}
  const ts=nodeTunnelStatus(n);
  if(ts)hb+=` <span class="badge ${ts==='ok'?'b-ok':'b-bad'}">${ts==='ok'?t('tun_up'):t('tun_down')}</span>`;
 }
 hb+=verBadge(ov);
 return hb;
}
// badge-e noskhe: sabz=hamsan ba akharin (latest_version-e hub), zard=ghadimi-tar (niaz be apdit).
function latestVer(){return (HUBST&&HUBST.latest_version)||'';}
function verBadge(ov){
 const mv=((ov||{}).version||{}).manager||''; if(!mv)return '';
 const lv=latestVer(); const old=lv&&mv!==lv;
 return ` <span class="badge ${old?'b-bad':'b-ok'}" title="${old?t('ver_old'):t('ver_ok')}">v${h(mv)}${old?' → v'+h(lv):''}</span>`;
}
function ovDotCls(n,ov){
 if(!ov)return 'd-un';
 if(ov.reachable===false)return 'd-bad';
 if(fnd(n).role==='iran')return ((ov.health||{}).fail===0)?'d-ok':'d-bad';
 const ts=nodeTunnelStatus(n);
 return ts==='warn'?'d-bad':'d-ok';
}

// ---------- vaziat-e khod-e server-e hub (strip-e bala-ye dashboard) ----------
let HUBST=null;
function fmtDur(s){if(s==null)return '?';const d=Math.floor(s/86400),hh=Math.floor(s%86400/3600),mm=Math.floor(s%3600/60);
 return (d?d+'d ':'')+(hh?hh+'h ':'')+mm+'m';}
function fmtGB(b){return (b/1073741824).toFixed(1)+'G';}
async function loadHubStatus(){const {j}=await api('GET','api/hubstatus');HUBST=j||null;updateHubStrip();}
function updateHubStrip(){
 const box=$('hubstrip'); if(!box)return;
 const st=HUBST;
 if(!st){box.innerHTML=`<span class="sub">${t('loading')}</span>`;return;}
 let x=`<span class="badge b-role">${t('hub_box')}</span>`;
 const sv=st.services||{};
 Object.keys(sv).forEach(u=>{const ok=sv[u]==='active';
  x+=` <span class="badge ${ok?'b-ok':'b-bad'}">${h(u)} ${ok?'✓':'✗'}</span>`;});
 if(st.uptime!=null)x+=` <span class="sub mono">${t('hs_up')}: ${fmtDur(st.uptime)}</span>`;
 else x+=` <span class="sub mono">${t('hs_up')}(hub): ${fmtDur(st.hub_uptime)}</span>`;
 if(st.load)x+=` <span class="sub mono">${t('hs_load')}: ${st.load.join(' ')}</span>`;
 if(st.mem_total_kb){const used=st.mem_total_kb-(st.mem_avail_kb||0);
  x+=` <span class="sub mono">${t('hs_mem')}: ${(used/1048576).toFixed(1)}/${(st.mem_total_kb/1048576).toFixed(1)}G</span>`;}
 if(st.disk_total)x+=` <span class="sub mono">${t('hs_disk')}: ${fmtGB(st.disk_free)}/${fmtGB(st.disk_total)}</span>`;
 // khoolase-ye inventory: chand server up/down (az overview-haye cache-shode)
 let up=0,down=0,unk=0;
 SERVERS.forEach(s=>{const ov=OVS[s.name];
  if(!ov)unk++;else if(ov.reachable===false)down++;else up++;});
 x+=` <span class="badge ${down?'b-bad':'b-ok'}">${up}/${SERVERS.length} SSH</span>`;
 box.innerHTML=x;
}

// ---------- safhe: dashboard (grid/list kart-haye khoolase) ----------
function renderDashboard(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('nav_dash')}</h2><span style="flex:1"></span>
   <button class="g" id="updall" onclick="updateAll()">${t('upd_all')}</button>
   <div class="vswitch"><button id="vg" class="${VIEW==='grid'?'on':''}" onclick="setView('grid')">▦ ${t('view_grid')}</button>
   <button id="vl" class="${VIEW==='list'?'on':''}" onclick="setView('list')">☰ ${t('view_list')}</button></div></div>
  <div id="updpanel"></div>
  <div class="card" style="margin-top:0"><div class="cbody" id="hubstrip" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 16px"></div></div>
  <div class="card"><div class="cbody">
   <div class="addbar"><b>${t('add_server')}:</b>
   <input id="n" placeholder="${t('f_name')}" size="10"><select id="rl"><option value="iran">iran</option><option value="node">node</option></select>
   <input id="hh" placeholder="${t('f_host')}" size="14"><input id="uu" value="root" size="6"><input id="pp" value="22" size="4">
   <input id="sw" type="password" placeholder="${t('prov_pw')}" size="14">
   <select id="isv" title="${t('l_iran_srv')}"><option value="">${t('l_iran_srv')}?</option>${iranSrvOptions()}</select>
   <button class="g" onclick="provSrv()">${t('prov_btn')}</button>
   <button class="gh" onclick="addSrv()">${t('add_btn')}</button></div>
   <div class="sub" style="margin-top:6px">${t('prov_hint')}</div></div></div>
  <div id="servers" class="grid ${VIEW==='list'?'list':''}"></div>`;
 drawCards();
 updateHubStrip(); loadHubStatus();
 SERVERS.forEach(s=>{if(OVS[s.name])updateCard(s.name);loadOv(s.name);});
}
function setView(v){VIEW=v;localStorage.setItem('rh_view',v);
 const c=$('servers');if(c)c.classList.toggle('list',v==='list');
 const vg=$('vg'),vl=$('vl');if(vg)vg.classList.toggle('on',v==='grid');if(vl)vl.classList.toggle('on',v==='list');}
function drawCards(){
 const c=$('servers'); if(!c)return;
 if(!SERVERS.length){c.innerHTML=`<div class="card" style="margin:0"><div class="cbody empty">${t('no_servers')}</div></div>`;return;}
 c.innerHTML=SERVERS.map(s=>`<div class="scard" id="srv_${h(s.name)}" onclick="nav('#/server/${h(s.name)}')">
   <div class="top"><span class="dot d-un" id="dot_${h(s.name)}"></span>
    <span class="name">${h(s.name)}</span><span class="badge b-role">${h(s.role)}</span></div>
   <div class="host mono">${h(s.host)}:${s.ssh_port}</div>
   <div class="bstrip" id="hd_${h(s.name)}"><span class="sub">${t('loading')}</span></div>
   <div class="meta" id="mt_${h(s.name)}"><span class="qr"><button class="gh" onclick="event.stopPropagation();loadOv('${h(s.name)}')">↻</button></span></div>
  </div>`).join('');
}
function updateCard(n){
 const ov=OVS[n]; if(!ov)return;
 setDot(n,ovDotCls(n,ov));
 const hd=$('hd_'+n); if(hd)hd.innerHTML=headBadges(n,ov);
 const mt=$('mt_'+n); if(!mt)return;
 let meta='';
 if(ov.reachable===false){meta=`<span>${h((ov.error||'').split(String.fromCharCode(10))[0].slice(0,60))}</span>`;}
 else if(fnd(n).role==='iran'){meta=`<span>${(ov.nodes||[]).length} ${t('n_nodes')}</span>`;
  if((ov.game||[]).length)meta+=`<span>${ov.game.length} ${t('n_game')}</span>`;}
 else{meta=`<span>${(ov.services||[]).length} ${t('n_svcs')}</span>`;
  if((ov.upstreams||[]).length)meta+=`<span>${ov.upstreams.length} ${t('n_ups')}</span>`;
  if(ov.main_server)meta+=`<span class="mono">→ ${h(ov.main_server)}</span>`;}
 mt.innerHTML=meta+`<span class="qr"><button class="gh" onclick="event.stopPropagation();loadOv('${h(n)}')">↻</button></span>`;
}

// ---------- safhe: server (hameye amaliat-e ghadimi inja) ----------
function renderServerPage(n){
 const pg=$('page'); if(!pg)return; const s=fnd(n);
 if(!s.name){pg.innerHTML=`<div class="ptitle"><button class="back" onclick="nav('#/dashboard')">${LANG==='fa'?'→':'←'} ${t('back')}</button><h2>${t('srv_notfound')}</h2></div>`;return;}
 const ov=OVS[n];
 let head=`<div class="spage-head"><button class="back" onclick="nav('#/dashboard')">${LANG==='fa'?'→':'←'} ${t('back')}</button>
   <span class="dot ${ovDotCls(n,ov)}" id="dot_${h(n)}"></span>
   <span class="name" style="font-size:18px">${h(n)}</span><span class="badge b-role">${h(s.role)}</span>
   <span class="sub mono">${h(s.host)}:${s.ssh_port}</span><span id="hd_${h(n)}">${ov?headBadges(n,ov):''}</span>
   <span style="flex:1"></span>
   <div class="btns">
     <button class="gh" onclick="loadOv('${h(n)}')">↻</button>
     <button class="gh" onclick="showDetails('${h(n)}')">${t('details')}</button>
     ${s.role==='iran'?`<button class="g" onclick="statusModal('${h(n)}')">${t('status_btn')}</button>`:''}
     <button class="s" onclick="doDeploy('${h(n)}')">${t('update')}</button>
     <button class="s" onclick="run('${h(n)}','tune')">tune</button>
     <button class="gh" onclick="editServer('${h(n)}')">${t('edit_server')}</button>
     <button class="r" onclick="delSrvPage('${h(n)}')">${t('del_server')}</button>
   </div></div>`;
 let body;
 if(!ov){body=`<div class="empty">${t('loading')}</div>`;loadOv(n);}
 else if(ov.reachable===false){body=`<div class="sec"><div class="empty">${t('ssh_help')}<br><code>ssh-copy-id -i /root/.ssh/id_ed25519.pub root@${h(s.host)}</code><br><br>${h(ov.error||'')}</div></div>`;}
 else{body=(s.role==='iran'?renderIran(n,ov):renderNode(n,ov));}
 // baraye node: dot-haye vaziat az doctor-e Iran miayand — agar overview-e Iran-i nadarim, biar
 if(s.role==='node')SERVERS.filter(x=>x.role==='iran'&&!OVS[x.name]).forEach(x=>loadOv(x.name));
 pg.innerHTML=`<div class="spage">${head}<div id="body_${h(n)}">${body}</div></div>`;
}
async function delSrvPage(n){if(!confirm(t('cf_delsrv')+' ('+n+')'))return;await api('DELETE','api/servers/'+n);SERVERS=[];delete OVS[n];nav('#/dashboard');}
function tbl(cols){return '<table><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr>';}
function esc(s){return h(s);}

function renderIran(n,ov){
 // baraye dokme-ye «afzoodan be node»: overview-e node-haye kharej ra pishaz-dast biar
 // ta list-e maghsad (node/upstream) khali nabashad.
 SERVERS.filter(x=>x.role==='node'&&!OVS[x.name]).forEach(x=>loadOv(x.name));
 let s='<div id="det_'+n+'"></div>';
 s+=`<div class="sec"><h4>${t('domain_tls')} <button class="g" onclick="domainTls('${n}')">${t('manage')}</button></h4>
   <div class="empty">${t('domain_hint')}</div></div>`;
 s+=`<div class="sec"><h4>${t('kcp_backbone')}</h4><div class="btns">
   <button class="g" onclick="kcpOnIran('${n}')">${t('kcp_on')}</button>
   <button class="r" onclick="run('${n}','kcp_off')">${t('kcp_off')}</button>
   <button class="gh" onclick="run('${n}','kcp_show')">${t('show_key')}</button>
   <button class="s" onclick="if(confirm(t('cf_restart')))run('${n}','restart')">${t('restart_rathole')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('plain_mode')}</span>
   <button class="g" onclick="plainOnIran('${n}')">${t('plain_on')}</button>
   <button class="r" onclick="run('${n}','plain_off')">${t('plain_off')}</button>
   <button class="gh" onclick="run('${n}','plain_show')">${t('show_key')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('noise_mode')}</span>
   <button class="g" onclick="noiseOnIran('${n}')">${t('noise_on')}</button>
   <button class="r" onclick="run('${n}','noise_off')">${t('noise_off')}</button>
   <button class="gh" onclick="run('${n}','noise_show')">${t('show_key')}</button>
   <button class="s" onclick="noiseNode('${n}','on')">${t('noise_node_on')}</button>
   <button class="s" onclick="noiseNode('${n}','off')">${t('noise_node_off')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('direct_mode')}</span>
   <button class="g" onclick="directOnIran('${n}')">${t('direct_on')}</button>
   <button class="r" onclick="run('${n}','direct_off')">${t('direct_off')}</button>
   <button class="gh" onclick="run('${n}','direct_show')">${t('show_key')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('fakeweb')}</span>

   <button class="g" onclick="fakewebStart('${n}')">${t('fw_start')}</button>
   <button class="s" onclick="run('${n}','fakeweb_stop')">${t('fw_stop')}</button>
   <button class="r" onclick="if(confirm(t('cf_fwrm')))run('${n}','fakeweb_rm')">${t('fw_rm')}</button></div></div>`;
 s+=`<div class="sec"><h4>${t('nodes_svcs')} <button class="g" onclick="addNode('${n}')">${t('add_node')}</button></h4>`;
 const nodes=ov.nodes||[];
 if(!nodes.length)s+=`<div class="empty">${t('no_nodes')}</div>`;
 else{ s+=tbl([t('c_name'),t('c_dport'),t('c_inbound'),t('c_api'),t('c_ops')]);
  const nnodes=(ov.noise||{}).nodes||[]; const hn=(ov.health||{}).nodes||{};
  nodes.forEach(d=>{ const isN=nnodes.indexOf(d.name)>=0;
   const st=hn[d.name]; const hdot=st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}" title="${st==='ok'?t('nd_up'):t('nd_down')}" style="margin-inline-end:6px"></span>`:'';
   const nbadge=isN?` <span class="badge b-noise">noise</span>`:'';
   const ntog=isN?`<button class="s" onclick="run('${n}','noise_node_off',{name:'${esc(d.name)}'})">${t('noise_node_off')}</button>`
                 :`<button class="s" onclick="run('${n}','noise_node_on',{name:'${esc(d.name)}'})">${t('noise_node_on')}</button>`;
   s+=`<tr><td>${hdot}${esc(d.name)}${nbadge}</td><td class="mono">${esc(d.port)}</td><td class="mono">${esc(d.inbound)}</td><td class="mono">${esc(d.api)}</td>
   <td class="btns"><button class="gh" onclick="run('${n}','show_node',{name:'${esc(d.name)}'})">${t('show_token')}</button>
   <button class="g" onclick="wireNode('${n}','${esc(d.name)}')">${t('wire_to_node')}</button>
   <button class="gh" onclick="editNode('${n}','${esc(d.name)}')">${t('edit')}</button>
   <button class="gh" onclick="renameNode('${n}','${esc(d.name)}')">${t('rename')}</button>
   <button class="gh" onclick="if(confirmT('cf_rotate','${esc(d.name)}'))run('${n}','rotate_node',{name:'${esc(d.name)}'})">${t('rotate')}</button>
   ${ntog}
   <button class="r" onclick="rmNode('${n}','${esc(d.name)}')">${t('remove')}</button></td></tr>`;});
  s+='</table>';}
 s+='</div>';
 s+=`<div class="sec"><h4>${t('game_svcs')} <button class="g" onclick="gameAdd('${n}')">${t('add_game')}</button> <button class="gh" onclick="gameCert('${n}')">${t('get_cert')}</button></h4>`;
 const g=ov.game||[];
 if(!g.length)s+=`<div class="empty">${t('no_game')}</div>`;
 else{ s+=tbl([t('c_name'),'SNI',t('c_data'),t('c_node_inb'),t('c_ops')]);
  g.forEach(d=>{s+=`<tr><td>${esc(d.name)}</td><td>${esc(d.sni)}</td><td>${esc(d.data)}</td><td>${esc(d.inbound)}</td>
   <td class="btns"><button class="r" onclick="run('${n}','game_rm',{name:'${esc(d.name)}'})">${t('remove')}</button></td></tr>`;});
  s+='</table>';}
 s+='</div>';
 return s;
}

// vaziat-e yek service-e node az doctor-e hameye Iran-ha ('ok'/'warn'/null)
function svcStatus(name){
 let st=null;
 SERVERS.filter(s=>s.role==='iran').forEach(s=>{
  const hn=(((OVS[s.name]||{}).health)||{}).nodes||{};
  if(name in hn){if(hn[name]==='warn')st='warn';else if(st===null)st='ok';}
 });
 return st;
}
function svcDot(name){
 const st=svcStatus(name);
 return st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}" title="${st==='ok'?t('nd_up'):t('nd_down')}" style="margin-inline-end:6px"></span>`:'';
}

function renderNode(n,ov){
 let s='<div id="det_'+n+'"></div>';
 s+=`<div class="sec"><h4>${t('main_tunnel')} ${esc(ov.main_server||'?')} <button class="g" onclick="setMainSrv('${n}')">${t('set_main')}</button></h4><div class="btns">
   <button class="g" onclick="kcpOnNode('${n}')">${t('kcp_on')}</button>
   <button class="r" onclick="run('${n}','kcp_off')">${t('kcp_off')}</button>
   <button class="s" onclick="run('${n}','restart')">${t('restart_tunnel')}</button>
   <button class="gh" onclick="run('${n}','migrate')">${t('migrate')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('plain_mode')}</span>
   <button class="g" onclick="plainOnNode('${n}')">${t('plain_on')}</button>
   <button class="r" onclick="run('${n}','plain_off')">${t('plain_off')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('noise_mode')}</span>
   <button class="g" onclick="noiseOnNode('${n}')">${t('noise_on')}</button>
   <button class="r" onclick="run('${n}','noise_off')">${t('noise_off')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('watchdog')}</span>

   <button class="g" onclick="wdOn('${n}')">${t('wd_on')}</button>
   <button class="r" onclick="run('${n}','watchdog_off')">${t('wd_off')}</button>
   <button class="gh" onclick="run('${n}','watchdog_status')">${t('wd_status')}</button></div></div>`;
 s+=`<div class="sec"><h4>${t('svc_tunnel')} <button class="g" onclick="addSvc('${n}')">${t('add_svc')}</button></h4>`;
 const sv=ov.services||[];
 if(!sv.length)s+=`<div class="empty">${t('no_svc')}</div>`;
 else{s+=tbl([t('c_svc'),t('c_inbound'),t('c_ops')]);
  sv.forEach(d=>{s+=`<tr><td>${svcDot(d.name)}${esc(d.name)}</td><td>${esc(d.inbound)}</td>
   <td class="btns"><button class="r" onclick="rmSvc('${n}','${esc(d.name)}')">${t('remove')}</button></td></tr>`;});
  s+='</table>';}
 s+='</div>';
 s+=`<div class="sec"><h4>${t('upstreams')} <button class="g" onclick="upAdd('${n}')">${t('add_up')}</button></h4>`;
 const ups=ov.upstreams||[];
 if(!ups.length)s+=`<div class="empty">${t('no_up')}</div>`;
 ups.forEach(u=>{
  const kb=u.tunnel==='kcp'?'<span class="badge b-kcp">kcp</span>':'<span class="badge b-ws">ws</span>';
  s+=`<div class="up"><div class="btns" style="align-items:center">
   <b>${esc(u.id)}</b> ${kb} <span class="sub">→ ${esc(u.server)}</span><span style="flex:1"></span>
   <button class="g" onclick="upKcpOn('${n}','${esc(u.id)}')">${t('kcp_on')}</button>
   <button class="r" onclick="run('${n}','upstream_kcp_off',{id:'${esc(u.id)}'})">${t('kcp_off')}</button>
   <button class="s" onclick="run('${n}','upstream_restart',{id:'${esc(u.id)}'})">restart</button>
   <button class="gh" onclick="run('${n}','upstream_kcp_status',{id:'${esc(u.id)}'})">${t('status')}</button>
   <button class="g" onclick="upAddSvc('${n}','${esc(u.id)}')">${t('add_svc')}</button>
   <button class="r" onclick="upRm('${n}','${esc(u.id)}')">${t('del_up')}</button></div>`;
  if((u.services||[]).length){s+=tbl([t('c_svc'),t('c_inbound'),t('c_ops')]);u.services.forEach(x=>{s+=`<tr><td>${svcDot(x.name)}${esc(x.name)}</td><td>${esc(x.inbound)}</td>
   <td class="btns"><button class="r" onclick="upRmSvc('${n}','${esc(u.id)}','${esc(x.name)}')">${t('remove')}</button></td></tr>`;});s+='</table>';}
  s+='</div>';
 });
 s+='</div>';
 return s;
}

// ---------- safhe: routing (graph-e topology, SVG dasti bedoon lib) ----------
let _gTimer=null,_gDragging=false;
let GVIEW=localStorage.getItem('rh_gview')||'graph';     // namaye routing: graph|table
function scheduleGraph(){clearTimeout(_gTimer);_gTimer=setTimeout(()=>{if(ROUTE.page==='routing'&&!_gDragging){if(GVIEW==='console')drawConsole();else drawGraph();}},150);}
function setGView(v){GVIEW=v;localStorage.setItem('rh_gview',v);renderRouting();}
// tartib-e dasti-e box-ha (drag): dar localStorage mimanad
function gOrder(col){try{return JSON.parse(localStorage.getItem('rh_gorder_'+col)||'[]');}catch(e){return[];}}
function gResetOrder(){localStorage.removeItem('rh_gorder_iran');localStorage.removeItem('rh_gorder_node');drawGraph();toast(t('saved'));}
function gApplyOrder(names,col){ // sort-e stable: avval tartib-e save-shode, baghye ba tartib-e ghabli
 const ord=gOrder(col),idx={};ord.forEach((n,i)=>idx[n]=i);
 return names.map((n,i)=>({n,i})).sort((a,b)=>{
  const ia=(a.n in idx)?idx[a.n]:1e9+a.i, ib=(b.n in idx)?idx[b.n]:1e9+b.i; return ia-ib;
 }).map(x=>x.n);
}
function renderRouting(){
 const pg=$('page'); if(!pg)return;
 const isC=GVIEW==='console';
 pg.innerHTML=`<div class="ptitle"><h2>${t('nav_routing')}</h2><span style="flex:1"></span>
   <div class="vswitch"><button class="${GVIEW==='console'?'on':''}" onclick="setGView('console')">⚡ ${t('view_console')}</button>
   <button class="${GVIEW==='graph'?'on':''}" onclick="setGView('graph')">◈ ${t('view_graph')}</button>
   <button class="${GVIEW==='table'?'on':''}" onclick="setGView('table')">☰ ${t('view_table')}</button></div>
   ${GVIEW==='graph'?`<button class="gh" onclick="gResetOrder()">${t('g_reset')}</button>`:''}
   <button class="gh" onclick="pollByPage()">${t('refresh')}</button></div>
  ${GVIEW==='graph'?`<div class="legend"><b style="color:var(--tx)">${t('g_legend')}:</b>
   <span class="li"><span class="lw lw-ws"></span> ws/443</span>
   <span class="li"><span class="lw lw-kcp"></span> kcp</span>
   <span class="li"><span class="lw lw-noise"></span> noise</span>
   <span class="li"><span class="lw lw-plain"></span> plain</span>
   <span class="li"><span class="lw lw-bad"></span> ${t('e_bad')}</span></div>`:''}
  ${isC?`<div class="rc" id="rcwrap"></div>`:`<div class="gwrap" id="gwrap"></div>
  <div class="sub" style="margin-top:8px">${GVIEW==='graph'?(t('g_hint')+' '+t('g_drag')):t('g_hint')}</div>`}`;
 if(isC)drawConsole(); else drawGraph();
 SERVERS.forEach(s=>{if(!OVS[s.name])loadOv(s.name);});
}
// ---------- namaye console: vorodi (ingress) → router → khorooji (node) ----------
// ravesh-haye vorood-e karbar (ingress) mostaghel az transport-e reverse-tunnel-e node.
function ingressLanes(ov){
 const p=ov.plain||{},d=ov.direct||{},g=(ov.game||[]);
 return [
  {key:'tls',cls:'lane-tls',on:true,edit:null,title:t('ing_tls_t'),patt:t('ing_tls_p'),desc:t('ing_tls_d'),port:'443'},
  {key:'direct',cls:'lane-direct',on:!!d.enabled,editFn:'directOnIran',offAct:'direct_off',
   title:t('ing_direct_t'),patt:t('ing_direct_p'),desc:t('ing_direct_d'),port:d.port,header:d.header||'X-Cdn-Id'},
  {key:'plain',cls:'lane-plain',on:!!p.enabled,editFn:'plainOnIran',offAct:'plain_off',
   title:t('ing_plain_t'),patt:t('ing_plain_p'),desc:t('ing_plain_d'),port:p.port},
  {key:'sni',cls:'lane-sni',on:g.length>0,edit:null,title:t('ing_sni_t'),patt:'',desc:t('ing_sni_d'),count:g.length}
 ];
}
function laneHtml(n,ln){
 const st=ln.on?`<span class="badge b-ok">${t('rc_on')}</span>`:`<span class="badge b-bad">${t('rc_off')}</span>`;
 let act='';
 if(ln.editFn){
  act=`<button class="gh" onclick="${ln.editFn}('${h(n)}')">${ln.on?t('rc_edit'):t('rc_enable')}</button>`;
  if(ln.on&&ln.offAct)act+=`<button class="r" onclick="run('${h(n)}','${ln.offAct}')">${t('rc_disable')}</button>`;
 }
 const meta=(ln.port?` <span class="lp">:${h(ln.port)}</span>`:'')+(ln.header?` <span class="lp">${h(ln.header)}</span>`:'')
   +(ln.count!=null&&ln.key==='sni'?` <span class="lp">${ln.count} SNI</span>`:'');
 return `<div class="lane ${ln.cls} ${ln.on?'on':'off'}">
   <div class="lh"><span class="ldot"></span><span class="lt">${h(ln.title)}</span>${meta}${st}
    <span class="lact">${act}</span></div>
   ${ln.patt?`<div class="lh" style="margin-top:5px"><span class="lp">${h(ln.patt)}</span></div>`:''}
   <div class="ld">${h(ln.desc)}</div></div>`;
}
// recipe-ha: baraye har node, chegoone karbar (Xray/V2Ray) be an vasl mishavad — bar asas-e ingress-e roshan.
function iranDomain(iran,ov){
 const nn=(ov.nodes||[]);
 for(const d of nn){const m=/^https?:\/\/([^\/]+)/.exec(d.path||'');if(m)return m[1].replace(/:\d+$/,'');}
 return (fnd(iran).host)||'<domain>';
}
function nodeRecipes(iran,ov,node){
 const host=(fnd(iran).host)||'<IRAN_IP>',dom=iranDomain(iran,ov);
 const p=ov.plain||{},d=ov.direct||{};
 const out=[];
 out.push({tag:'ws/443',cls:'b-ws',lines:[[t('rc_addr'),dom],[t('rc_port'),'443'],[t('rc_wspath'),'/'+node.name],[t('rc_tls'),t('rc_yes')]]});
 if(d.enabled){out.push({tag:'direct',cls:'b-plain',lines:[[t('rc_addr'),host],[t('rc_port'),d.port||'8081'],
   [t('rc_wshost'),'myket.ir  ('+t('rc_hosthint')+')'],[t('rc_header'),(d.header||'X-Cdn-Id')+': '+node.name],[t('rc_tls'),t('rc_no')]]});}
 if(p.enabled){out.push({tag:'plain',cls:'b-plain',lines:[[t('rc_addr'),host],[t('rc_port'),p.port||'8880'],
   [t('rc_wspath'),'/'+node.name],[t('rc_tls'),t('rc_no')]]});}
 return out;
}
function recipeCopyText(node,r){return node+' · '+r.tag+'\\n'+r.lines.map(l=>l[0]+': '+l[1]).join('\\n');}
function drawConsole(){
 const w=$('rcwrap'); if(!w)return;
 const irans=SERVERS.filter(s=>s.role==='iran');
 if(!irans.length){w.innerHTML=`<div class="rc-empty">${t('rc_pick_iran')}</div>`;return;}
 let x='';
 irans.forEach(s=>{
  const ov=OVS[s.name];
  x+=`<div class="rcard"><div class="rc-head">
    <span class="dot ${ov?ovDotCls(s.name,ov):'d-un'}"></span>
    <span class="nm">${h(s.name)}</span><span class="hst">${h(s.host)}</span>
    <span style="flex:1"></span><span class="sub" style="font-size:11px">${t('rc_legend')}</span>
    <button class="gh" onclick="nav('#/server/${h(s.name)}')">${t('details')}</button></div>`;
  if(!ov){x+=`<div class="rc-empty" style="padding:14px">${t('loading')}</div></div>`;return;}
  if(ov.reachable===false){x+=`<div class="rc-empty" style="padding:14px"><span class="badge b-bad">${t('rc_unreach')}</span></div></div>`;return;}
  const lanes=ingressLanes(ov),nodes=ov.nodes||[];
  x+=`<div class="rc-body">
    <div class="rc-col"><h5>${t('rc_ingress')} <span class="cnt">${lanes.filter(l=>l.on).length}/${lanes.length}</span></h5>
      <p class="rc-sub">${t('rc_ingress_sub')}</p>${lanes.map(l=>laneHtml(s.name,l)).join('')}</div>
    <div class="rc-col"><h5>${t('rc_outputs')} <span class="cnt">${nodes.length}</span></h5>
      <p class="rc-sub">${t('rc_outputs_sub')}</p>`;
  if(!nodes.length)x+=`<div class="rc-empty">${t('rc_no_nodes')}</div>`;
  else{
   const nn=(ov.noise||{}).nodes||[],hn=(ov.health||{}).nodes||{};
   nodes.forEach(d=>{
    const isN=nn.indexOf(d.name)>=0,tr=isN?'noise':((ov.kcp||{}).enabled?'kcp':'ws');
    const trb=tr==='noise'?'b-noise':(tr==='kcp'?'b-kcp':'b-ws');
    const st=hn[d.name],dot=st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}"></span>`:'<span class="dot d-un"></span>';
    const recs=nodeRecipes(s.name,ov,d);
    x+=`<div class="onode ${st==='warn'?'off':''}"><div class="oh">${dot}<span class="onm">${h(d.name)}</span>
      <span class="sub" style="font-size:11px">${t('rc_transport')}:</span><span class="badge ${trb}">${tr}</span>
      <span class="otr sub" style="font-size:11px">→ :${h(d.port)}</span></div>`;
    recs.forEach((r,i)=>{
     const rid='rec_'+h(s.name)+'_'+h(d.name)+'_'+i;
     x+=`<div class="recipe"><div class="rl"><span class="rtag badge ${r.cls}">${t('rc_via')} ${h(r.tag)}</span>
       <button class="cpy" onclick="copyRecipe('${rid}')">⧉ ${t('rc_copy')}</button></div>
       <div id="${rid}" data-cp="${h(recipeCopyText(d.name,r))}">`;
     r.lines.forEach(l=>{x+=`<div class="rl"><span class="k">${h(l[0])}</span><span class="v">${h(l[1])}</span></div>`;});
     x+=`</div></div>`;
    });
    x+=`</div>`;
   });
  }
  x+=`</div></div></div>`;
 });
 w.innerHTML=x;
}
function copyRecipe(id){const el=$(id);if(!el)return;const txt=(el.getAttribute('data-cp')||'').replace(/\\n/g,'\n');
 navigator.clipboard&&navigator.clipboard.writeText(txt);toast(t('rc_copied'));}

// ---------- namaye jadval: har edge yek radif ----------
function drawRouteTable(){
 const w=$('gwrap'); if(!w)return;
 const M=buildGraphModel();
 if(!M.edges.length){w.innerHTML=`<div class="empty" style="padding:20px">${t('g_empty')}</div>`;return;}
 const rows=M.edges.slice().sort((a,b)=>(a.tgt.name+a.node).localeCompare(b.tgt.name+b.node));
 let x=`<div style="direction:${LANG==='fa'?'rtl':'ltr'};padding:4px 10px">`;
 x+=tbl([t('c_node'),t('c_upstream'),t('c_iran'),t('c_tunnel'),t('n_svcs'),t('c_status')]);
 rows.forEach(e=>{
  const tb=e.tunnel==='kcp'?'b-kcp':(e.tunnel==='noise'?'b-noise':(e.tunnel==='plain'?'b-plain':'b-ws'));
  const st=e.status==='warn'?`<span class="dot d-bad"></span> ${t('tun_down')}`
          :(e.status==='ok'?`<span class="dot d-ok"></span> ${t('tun_up')}`:`<span class="dot d-un"></span>`);
  const tgt=e.tgt.kind==='iran'
    ?`<a style="color:var(--ac);cursor:pointer" onclick="nav('#/server/${h(e.tgt.name)}')">${h(e.tgt.name)}</a>`
    :`${h(e.tgt.name)} <span class="sub">(${t('g_external')})</span>`;
  x+=`<tr><td><a style="color:var(--ac);cursor:pointer" onclick="nav('#/server/${h(e.node)}')">${h(e.node)}</a></td>
   <td class="mono">${h(e.label||'main')}</td><td>${tgt}</td>
   <td><span class="badge ${tb}">${h(e.tunnel)}</span></td>
   <td class="mono">${h(e.svcs.join(', ')||'-')}</td><td>${st}</td></tr>`;});
 x+='</table></div>';
 w.innerHTML=x;
}
// host-e yek "host:port" ra be name-e server-e iran dar inventory map mikonad
function matchIran(hostport,idmap){
 if(!hostport)return null;
 const hst=hostport.replace(/:\d+$/,'').toLowerCase();
 return idmap[hst]||null;
}
function buildGraphModel(){
 const irans=SERVERS.filter(s=>s.role==='iran'), nds=SERVERS.filter(s=>s.role==='node');
 // idmap: host/domain → name-e iran (domain az path-e nodes-e overview darmiayad)
 const idmap={};
 irans.forEach(s=>{idmap[(s.host||'').toLowerCase()]=s.name;
  const ov=OVS[s.name];
  ((ov&&ov.nodes)||[]).forEach(d=>{const m=/^https?:\/\/([^\/]+)/.exec(d.path||'');
   if(m)idmap[m[1].replace(/:\d+$/,'').toLowerCase()]=s.name;});});
 const edges=[],externals={};
 // fallback: agar host match nashod (masalan inventory IP darad vali node ba domain vasl ast),
 // az rooye esm-e service-haye moshtarak irane motenazer ra peyda kon.
 function svcFallback(svcNames){
  const hits=irans.filter(s=>{const ovn=((OVS[s.name]||{}).nodes||[]).map(x=>x.name);
   return svcNames.some(nm=>ovn.indexOf(nm)>=0);});
  return hits.length===1?hits[0].name:null;
 }
 function target(hostport,svcNames){
  const nm=matchIran(hostport,idmap); if(nm)return{kind:'iran',name:nm};
  const fb=svcFallback(svcNames||[]); if(fb)return{kind:'iran',name:fb};
  const hst=(hostport||'?').replace(/:\d+$/,'');
  externals[hst]=externals[hst]||{name:hst}; return{kind:'ext',name:hst};
 }
 nds.forEach(d=>{
  const ov=OVS[d.name]; if(!ov||ov.reachable===false)return;
  if(ov.main_server){edges.push({tgt:target(ov.main_server,(ov.services||[]).map(x=>x.name)),node:d.name,tunnel:ov.main_tunnel||'ws',
   svcs:(ov.services||[]).map(x=>x.name),label:''});}
  (ov.upstreams||[]).forEach(u=>{edges.push({tgt:target(u.server,(u.services||[]).map(x=>x.name)),node:d.name,tunnel:u.tunnel||'ws',
   svcs:(u.services||[]).map(x=>x.name),label:u.id});});
 });
 // vaziat-e har edge az doctor-e iran: agar HAR yeki az service-haye in edge kharab bashad → warn
 edges.forEach(e=>{
  e.svc=e.svcs.length;
  if(e.tgt.kind!=='iran')return;
  const hov=OVS[e.tgt.name]; const hn=((hov||{}).health||{}).nodes||{};
  const keys=e.svcs.concat([e.node]);
  if(keys.some(k=>hn[k]==='warn'))e.status='warn';
  else if(keys.some(k=>hn[k]==='ok'))e.status='ok';
 });
 return {irans,nds,edges,externals:Object.keys(externals)};
}
function drawGraph(){
 const w=$('gwrap'); if(!w)return;
 if(GVIEW==='table'){drawRouteTable();return;}
 const M=buildGraphModel();
 if(!M.irans.length&&!M.nds.length){w.innerHTML=`<div class="empty" style="padding:20px">${t('g_empty')}</div>`;return;}
 const anyOv=SERVERS.some(s=>OVS[s.name]);
 const BW=195,BH=60,GY=26,X=[26,300,606],WID=830;
 // sotoon-e node-ha ra bar asas-e iran-e mabda sort kon ta edge-ha kamtar ghat shavand
 const firstIran={};
 M.edges.forEach(e=>{if(!(e.node in firstIran))firstIran[e.node]=(e.tgt.kind==='iran'?e.tgt.name:'zz_'+e.tgt.name);});
 let nodeNames=M.nds.slice().sort((a,b)=>((firstIran[a.name]||'~')+a.name).localeCompare((firstIran[b.name]||'~')+b.name)).map(s=>s.name);
 nodeNames=gApplyOrder(nodeNames,'node');                      // tartib-e dasti (drag) oloviat darad
 const nodeCol=nodeNames.map(nm=>M.nds.find(s=>s.name===nm)).filter(Boolean);
 const iranNames=gApplyOrder(M.irans.map(s=>s.name),'iran');
 const iranCol=iranNames.map(nm=>{const s=M.irans.find(x=>x.name===nm);return{name:s.name,host:s.host,ext:false};})
   .concat(M.externals.map(hst=>({name:hst,host:'',ext:true})));
 // mokhtasat-e amoodi
 function place(list,x,hh){let y=46;const pos={};list.forEach(it=>{pos[it.name?it.name:it]={x,y,h:hh};y+=hh+GY;});return{pos,bot:y};}
 const pi=place(iranCol,X[1],BH+8), pn=place(nodeCol,X[2],BH);
 const H=Math.max(pi.bot,pn.bot,190)+14;
 // markaz-e amoodi baraye sotoon-e kootah-tar
 function recenter(p,bot){const off=(H-14-bot)/2;if(off>4)Object.values(p).forEach(o=>o.y+=off);}
 recenter(pi.pos,pi.bot);recenter(pn.pos,pn.bot);
 const uy=H/2-35;
 let sv=`<svg viewBox="0 0 ${WID} ${H}" xmlns="http://www.w3.org/2000/svg">`;
 sv+=`<text x="${X[0]+60}" y="24" text-anchor="middle" class="gcolhead">${t('g_users')}</text>`;
 sv+=`<text x="${X[1]+BW/2}" y="24" text-anchor="middle" class="gcolhead">${t('g_iran_col')}</text>`;
 sv+=`<text x="${X[2]+BW/2}" y="24" text-anchor="middle" class="gcolhead">${t('g_node_col')}</text>`;
 // --- edges: user → iran (dade-ye vorodi) ---
 const ucx=X[0]+120;
 iranCol.forEach(it=>{if(it.ext)return;const p=pi.pos[it.name];const y2=p.y+ (BH+8)/2;
  sv+=`<path class="edge e-user" d="M ${ucx} ${uy+35} C ${(ucx+X[1])/2} ${uy+35} ${(ucx+X[1])/2} ${y2} ${X[1]} ${y2}" marker-end="url(#arr)"/>`;});
 // --- edges: iran ← node (tunnel-haye barghashti) ---
 // taghsim-e noghat-e etesal rooye labe-ye har box baraye jelogiri az ham-poshani
 const outCnt={},inCnt={};
 M.edges.forEach(e=>{const k=e.tgt.name;outCnt[k]=(outCnt[k]||0)+1;inCnt[e.node]=(inCnt[e.node]||0)+1;});
 const outIdx={},inIdx={};
 let edgeSvg='',labSvg='';
 M.edges.forEach(e=>{
  const P1=pi.pos[e.tgt.name],P2=pn.pos[e.node]; if(!P1||!P2)return;
  outIdx[e.tgt.name]=(outIdx[e.tgt.name]||0)+1; inIdx[e.node]=(inIdx[e.node]||0)+1;
  const y1=P1.y+P1.h*outIdx[e.tgt.name]/(outCnt[e.tgt.name]+1);
  const y2=P2.y+P2.h*inIdx[e.node]/(inCnt[e.node]+1);
  const x1=X[1]+BW,x2=X[2],mx=(x1+x2)/2;
  const cls=e.status==='warn'?'e-bad':('e-'+(['ws','kcp','noise','plain'].indexOf(e.tunnel)>=0?e.tunnel:'ws'));
  const anim=(e.tunnel!=='ws'||e.status==='warn')?' flow':'';
  const dim=e.status==='warn'?'':''; // edge-e kharab ghermez mishavad, dim nemikonim
  edgeSvg+=`<path class="edge ${cls}${anim}${dim}" d="M ${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2} ${y2}"/>`;
  // label-e vasat-e edge: [upstream-id ·] tunnel · svc
  const txt=(e.label?e.label+' · ':'')+e.tunnel+(e.svc?(' · '+e.svc):'');
  const tw=txt.length*6.6+14, lx=mx-tw/2, ly=(y1+y2)/2-9;
  labSvg+=`<g class="elab" onclick="nav('#/server/${h(e.node)}')"><rect x="${lx}" y="${ly}" width="${tw}" height="18" rx="9"/>`+
   `<text x="${mx}" y="${ly+13}" text-anchor="middle">${h(txt)}</text></g>`;
 });
 sv+=edgeSvg;
 // --- box: users ---
 sv+=`<g><rect class="gbox gbox-ext" x="${X[0]}" y="${uy}" width="120" height="70" rx="12"/>`;
 [[36,uy+26],[60,uy+20],[84,uy+26]].forEach(c=>{sv+=`<circle cx="${c[0]}" cy="${c[1]}" r="6" fill="#3b4c61"/><path d="M ${c[0]-9} ${c[1]+18} a 9 9 0 0 1 18 0" fill="#3b4c61"/>`;});
 sv+=`<text x="${X[0]+60}" y="${uy+60}" text-anchor="middle" class="gsub">${t('g_users')}</text></g>`;
 // --- box-haye iran ---
 iranCol.forEach(it=>{
  const p=pi.pos[it.name],hh=P=>p.y+P;
  const ov=OVS[it.name],off=!it.ext&&ov&&ov.reachable===false;
  const click=it.ext?'':` onclick="nav('#/server/${h(it.name)}')"`;
  const drag=it.ext?'':` data-gcol="iran" data-gname="${h(it.name)}"`;
  sv+=`<g${click}${drag}><rect class="gbox gbox-iran${it.ext?' gbox-ext':''}${off?' gbox-off':''}" x="${p.x}" y="${p.y}" width="${BW}" height="${p.h}" rx="10"><title>${h(it.ext?t('g_external'):it.name)}</title></rect>`;
  const dcls=it.ext?'#8ba0b6':(off?'var(--rd)':(ov?(((ov.health||{}).fail===0)?'var(--gr)':'var(--rd)'):'var(--yl)'));
  sv+=`<circle cx="${p.x+16}" cy="${hh(20)}" r="4.5" fill="${dcls}"/>`;
  sv+=`<text x="${p.x+28}" y="${hh(24)}" class="gtxt">${h(it.name.length>20?it.name.slice(0,19)+'…':it.name)}</text>`;
  if(it.ext){sv+=`<text x="${p.x+14}" y="${hh(44)}" class="gsub">${t('g_external')}</text>`;}
  else{sv+=`<text x="${p.x+14}" y="${hh(42)}" class="gsub">${h((it.host||'').slice(0,26))}</text>`;
   let inf=':443';
   if(ov){const k=ov.kcp||{},nz=ov.noise||{};inf=':443'+(k.enabled?(' · kcp'+(k.port?(' udp:'+k.port):'')):'')+(nz.enabled?(' · noise:'+(nz.port||'')):'');
    inf+=' · '+((ov.nodes||[]).length)+' '+t('n_nodes');}
   sv+=`<text x="${p.x+14}" y="${hh(58)}" class="gsub">${h(inf.slice(0,30))}</text>`;}
  sv+='</g>';});
 // --- box-haye node ---
 nodeCol.forEach(d=>{
  const p=pn.pos[d.name];const ov=OVS[d.name];const off=ov&&ov.reachable===false;
  const bad=M.edges.some(e=>e.node===d.name&&e.status==='warn');
  const dcls=off||bad?'var(--rd)':(ov?'var(--gr)':'var(--yl)');
  sv+=`<g onclick="nav('#/server/${h(d.name)}')" data-gcol="node" data-gname="${h(d.name)}"><rect class="gbox${off?' gbox-off':''}" x="${p.x}" y="${p.y}" width="${BW}" height="${p.h}" rx="10"><title>${h(d.name)}</title></rect>`;
  sv+=`<circle cx="${p.x+16}" cy="${p.y+20}" r="4.5" fill="${dcls}"/>`;
  sv+=`<text x="${p.x+28}" y="${p.y+24}" class="gtxt">${h(d.name.length>20?d.name.slice(0,19)+'…':d.name)}</text>`;
  const sub=(d.host||'')+(ov&&ov.services?(' · '+ov.services.length+' '+t('n_svcs')):'');
  sv+=`<text x="${p.x+14}" y="${p.y+44}" class="gsub">${h(sub.slice(0,30))}</text></g>`;});
 sv+=labSvg;
 sv+=`<defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#3b4c61"/></marker></defs>`;
 sv+='</svg>';
 if(!anyOv)sv=`<div class="empty" style="padding:12px 16px 0">${t('g_loading')}</div>`+sv;
 w.innerHTML=sv;
 bindGraphDrag(w);
}
// ---------- drag-e amoodi-e box-ha (tartib dar localStorage) ----------
function bindGraphDrag(w){
 const svg=w.querySelector('svg'); if(!svg)return;
 svg.querySelectorAll('g[data-gname]').forEach(g=>{
  g.style.cursor='grab';
  g.addEventListener('pointerdown',ev=>{
   const col=g.dataset.gcol,name=g.dataset.gname;
   const vb=svg.viewBox.baseVal,scale=vb.height/svg.getBoundingClientRect().height;
   let moved=false;const y0=ev.clientY;
   const mv=e=>{const dy=(e.clientY-y0)*scale;
    if(!moved&&Math.abs(dy)>6){moved=true;_gDragging=true;g.style.cursor='grabbing';svg.style.userSelect='none';}
    if(moved)g.setAttribute('transform','translate(0,'+dy+')');};
   const up=e=>{
    document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);
    svg.style.userSelect='';_gDragging=false;
    if(!moved)return;                      // click-e sade → navigation-e aadi
    // click-e badi (ke browser bad az pointerup mifrestad) navigation nakonad
    g.addEventListener('click',ce=>{ce.stopPropagation();ce.preventDefault();},{capture:true,once:true});
    // tartib-e jadid: markaz-e box-e keshide-shode ra beyn-e baghye peyda kon
    const others=[...svg.querySelectorAll('g[data-gcol="'+col+'"]')].filter(x=>x!==g);
    const cy=el=>{const r=el.querySelector('rect');return parseFloat(r.getAttribute('y'))+parseFloat(r.getAttribute('height'))/2;};
    const myY=cy(g)+(e.clientY-y0)*scale;
    const order=others.map(x=>({n:x.dataset.gname,y:cy(x)}));
    order.push({n:name,y:myY});
    order.sort((a,b)=>a.y-b.y);
    localStorage.setItem('rh_gorder_'+col,JSON.stringify(order.map(x=>x.n)));
    drawGraph();
   };
   document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up);
  });
 });
}

// ---------- safhe: audit / settings (ghablan modal boodand) ----------
async function renderAuditPage(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('audit')}</h2></div><div class="card" style="margin-top:0"><div class="cbody" id="auditbody"><div class="empty">${t('loading')}</div></div></div>`;
 const {j}=await api('GET','api/audit?limit=100');
 const box=$('auditbody'); if(!box)return;
 const rows=(j||[]);
 if(!rows.length){box.innerHTML=`<div class="empty">${t('no_audit')}</div>`;return;}
 let x=`<table><tr><th>${t('c_time')}</th><th>${t('c_user')}</th><th>server</th><th>${t('c_action')}</th><th>rc</th></tr>`;
 rows.forEach(e=>{const d=new Date((e.ts||0)*1000).toLocaleString(LANG==='fa'?'fa-IR':'en-US');
  x+=`<tr><td>${h(d)}</td><td class="mono">${h(e.user)}</td><td>${h(e.server)}</td><td class="mono">${h(e.action)}</td><td>${h(e.rc)}</td></tr>`;});
 box.innerHTML=x+'</table>';
}
async function renderSettingsPage(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('settings')}</h2></div><div class="card" style="margin-top:0"><div class="cbody" id="setbody"><div class="empty">${t('loading')}</div></div></div>`;
 const {j}=await api('GET','api/config');const c=j||{};
 const warn=c.insecure?`<div class="badge b-bad" style="margin-bottom:10px">${t('insecure')}</div>`:'';
 const box=$('setbody'); if(!box)return;
 box.innerHTML=`${warn}
  <div class="mbox" style="background:transparent;border:0;padding:0;min-width:0">
  <div class="row"><label>${t('l_apitoken')}</label><span class="sub mono">${h(c.api_token_hint||'')}</span></div>
  <div class="row"><label>${t('l_listen')}</label><span class="sub mono">${h(c.listen_host||'')}:${h(c.listen_port||'')}</span></div>
  <h3 style="margin-top:14px">${t('chpw')}</h3>
  <div class="row"><label>${t('l_curpw')}</label><input id="cpw" type="password"></div>
  <div class="row"><label>${t('l_newpw')}</label><input id="npw" type="password" placeholder="${t('pw_hint')}"></div>
  <div class="row"><button class="g" onclick="savePw()">${t('save_pw')}</button></div>
  <h3 style="margin-top:14px">${t('l_apitoken')}</h3>
  <div class="row"><button class="s" onclick="rotTok()">${t('rot_tok')}</button></div></div>`;
}

function outModal(title,text){var id='om_'+Math.random().toString(36).slice(2);modal('<h3>'+h(title)+'</h3><pre id="'+id+'" style="max-height:52vh;overflow:auto;white-space:pre-wrap;user-select:text;-webkit-user-select:text">'+h(text)+'</pre><div class="row" style="margin-top:10px"><button class="g" onclick="copyText(\''+id+'\')">'+t('copy_out')+'</button> <button class="gh" onclick="closeModal()">'+t('close')+'</button></div>');}
async function run(n,a,args){toast(t('running')+' '+a+' '+t('on')+' '+n+' …');
 const {j}=await api('POST','api/servers/'+n+'/action',{action:a,args:args||{}});
 const rc=(j&&typeof j.rc==='number')?j.rc:null;
 const ok=(rc===0), bad=(rc!==null&&rc!==0);
 const verdict=ok?('✓ '+t('ok_rc')):(bad?('✗ '+t('fail_rc')+' (rc='+rc+')'):'');
 const body=((j.cmd?('$ '+j.cmd+'\n'):'')+((j.out||'')+(j.err?('\n'+j.err):''))).trim();
 const full=((verdict?verdict+(body?'\n\n':''):'')+body)||JSON.stringify(j);
 if(bad){outModal(a+' ✗',full);}                                    // shekast: hamishe modal, ta gom nashavad
 else if(body&&(body.length>140||body.indexOf(String.fromCharCode(10))>=0)){outModal(a+' ✓',full);}
 else{toast(verdict+(body?(' — '+body):''));}
 loadOv(n);}
async function doDeploy(n){if(!confirm(t('cf_deploy')+' '+n+' ?'))return; run(n,'deploy');}
// apdit-e hamegani: hameye serverha ra YEKI-YEKI (tartibi) apdit mikonad va progress bar +
// vaziat-e har server ra live neshan midahad. deploy = install.sh --update (snapshot+rollback-e khodkar).
let UPD_BUSY=false;
async function updateAll(){
 if(UPD_BUSY)return;
 const list=SERVERS.slice();
 if(!list.length){toast(t('no_servers'));return;}
 if(!confirm(t('cf_upd_all')+' ('+list.length+')'))return;
 UPD_BUSY=true; const btn=$('updall'); if(btn){btn.disabled=true;}
 const panel=$('updpanel'); const total=list.length; let done=0, okc=0, failc=0;
 const rows=list.map(s=>`<div class="updrow" id="ur_${h(s.name)}"><span class="dot d-un"></span><b>${h(s.name)}</b> <span class="badge b-role">${h(s.role)}</span><span class="us" id="us_${h(s.name)}">${t('upd_wait')}</span></div>`).join('');
 if(panel)panel.innerHTML=`<div class="card"><div class="cbody">
   <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><b>${t('upd_all')}</b>
     <div class="pbar"><div class="pfill" id="pfill" style="width:0%"></div></div>
     <span id="pcnt" class="mono">0/${total}</span>
     <button class="gh" onclick="closeUpdPanel()" id="updclose" disabled>${t('close')}</button></div>
   ${rows}</div></div>`;
 for(const s of list){
  const us=$('us_'+s.name), dot=document.querySelector('#ur_'+CSS.escape(s.name)+' .dot');
  if(us)us.textContent=' — '+t('upd_running'); if(dot)dot.className='dot d-un';
  try{
   const {j}=await api('POST','api/servers/'+s.name+'/action',{action:'deploy',args:{}});
   const rc=(j&&typeof j.rc==='number')?j.rc:1;
   if(rc===0){okc++; if(dot)dot.className='dot d-ok';
     // baad az apdit noskhe-ye jadid ra bekhan
     await loadOv(s.name); const nv=((OVS[s.name]||{}).version||{}).manager||'?';
     if(us)us.textContent=' — ✓ '+t('upd_ok')+' (v'+nv+')';
   }else{failc++; if(dot)dot.className='dot d-bad';
     if(us)us.textContent=' — ✗ '+t('upd_fail')+' (rc='+rc+')';}
  }catch(e){failc++; if(dot)dot.className='dot d-bad'; if(us)us.textContent=' — ✗ '+t('upd_fail');}
  done++; const pct=Math.round(done*100/total);
  const pf=$('pfill'); if(pf)pf.style.width=pct+'%'; const pc=$('pcnt'); if(pc)pc.textContent=done+'/'+total;
 }
 UPD_BUSY=false; if(btn)btn.disabled=false;
 const cb=$('updclose'); if(cb)cb.disabled=false;
 toast(t('upd_done')+': ✓'+okc+' ✗'+failc);
 loadHubStatus();
}
function closeUpdPanel(){const p=$('updpanel'); if(p&&!UPD_BUSY)p.innerHTML='';}
async function showDetails(n){toast(t('loading_det'));
 const {j}=await api('GET','api/servers/'+n+'/details');
 outModal('details · '+n, j.text||JSON.stringify(j));}
// ---------- dashboard-e vaziat (mesl-e panel-e VPN): status --json ra ziba render mikonad ----------
function stDot(v){return '<span class="dot '+(v==='yes'?'d-ok':'d-bad')+'"></span>';}
async function statusModal(n){toast(t('loading'));
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'status',args:{}});
 let d=null; try{d=JSON.parse(j&&j.out||'');}catch(e){}
 if(!d){outModal('status · '+n,((j&&j.cmd?'$ '+j.cmd+'\\n':'')+((j&&j.out)||'')+((j&&j.err)?'\\n'+j.err:'')).trim()||t('status_err'));return;}
 const P=d.ports||{}, C=d.cert||{}, S=d.services||{};
 const portRow=(port,lbl)=>port?`<tr><td class="mono">${h(String(port))}</td><td>${h(lbl)}</td></tr>`:'';
 const certLine=C.exists==='yes'
   ?`${stDot('yes')} ${t('st_cert_ok')} — ${h(C.expiry||'?')}`+(C.self_signed==='yes'?` <span class="badge" style="background:#7f1d1d">${t('st_selfsigned')}</span>`:'')
   :`${stDot('no')} <span style="color:#f87171">${t('st_cert_missing')}: ${h(C.fullchain||'')}</span>`;
 let nodes='';
 (d.nodes||[]).forEach(x=>{const sni=(x.sni&&x.sni!=='-');
   const url=sni?('SNI: '+h(x.sni)):('https://'+h(d.domain||'')+'/'+h(x.name));
   nodes+=`<tr><td class="mono">${h(x.name)}</td><td class="mono">${h(String(x.port))}</td><td class="mono">${h(String(x.inbound_port))}</td><td class="mono" style="font-size:12px">${url}</td></tr>`;});
 if(!nodes)nodes=`<tr><td colspan="4" class="sub">${t('st_no_nodes')}</td></tr>`;
 modal(`<h3>${t('status_btn')} · ${h(n)}</h3>
  <div class="row"><label>${t('st_domain')}</label><span class="mono">${h(d.domain||'—')}</span></div>
  <div class="row"><label>${t('st_ip')}</label><span class="mono">${h(d.public_ip||'?')}</span></div>
  <div class="row"><label>${t('st_transport')}</label><span class="mono">${h(d.transport||'')}</span></div>
  <h4 style="margin:12px 0 4px">${t('st_services')}</h4>
  <div class="mono">${stDot(S.rathole_server)} rathole-server &nbsp; ${stDot(S.nginx)} nginx (${S.nginx_config_ok==='yes'?t('st_ok'):'<span style=color:#f87171>'+t('st_bad')+'</span>'})${S.noise&&S.noise!=='off'?' &nbsp; '+stDot(S.noise)+' noise':''}</div>
  <h4 style="margin:12px 0 4px">${t('st_ports')}</h4>
  <table><tr><th>PORT</th><th></th></tr>
   ${portRow(443,'443 — '+t('st_p_443'))}
   ${portRow(P.control,t('st_p_control'))}
   ${portRow(P.fake,t('st_p_fake'))}
   ${portRow(P.sub,t('st_p_sub'))}
   ${d.sni_count>0?portRow(P.internal,t('st_p_internal')):''}
   ${portRow(P.plain,t('st_p_plain'))}
   ${portRow(P.direct,t('st_p_direct')+' ('+h(d.direct_header||'')+')')}
   ${portRow(P.hub,t('st_p_hub'))}
   ${portRow(P.noise,t('st_p_noise'))}
  </table>
  <h4 style="margin:12px 0 4px">${t('st_cert')}</h4>
  <div class="mono" style="font-size:13px">${certLine}</div>
  <h4 style="margin:12px 0 4px">${t('st_nodes')} (${(d.nodes||[]).length})</h4>
  <table><tr><th>NAME</th><th>PORT</th><th>INBOUND</th><th>USER URL</th></tr>${nodes}</table>
  <div class="row" style="margin-top:12px"><button class="gh" onclick="closeModal()">${t('close')}</button></div>`);}
function copyText(id){const el=$(id);if(!el)return;const x=el.textContent;
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(x).then(()=>toast(t('copied')),()=>toast('copy?'));}
 else{const r=document.createRange();r.selectNode(el);getSelection().removeAllRanges();getSelection().addRange(r);try{document.execCommand('copy');toast(t('copied'));}catch(e){toast('copy?');}}}
async function addSrv(){const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value};
 const {status,j}=await api('POST','api/servers',b); if(status!==200){toast('error: '+(j.error||status));return;} $('n').value='';$('hh').value=''; loadAll();}
async function provSrv(){const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value,ssh_password:$('sw').value,iran_server:($('isv')?$('isv').value:'')};
 if(!b.name||!b.host||!b.ssh_password){toast(t('fill'));return;}
 toast(t('provisioning'));
 const {status,j}=await api('POST','api/provision',b);
 const out=((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):'');
 outModal(t('prov_btn')+' · '+b.name, out.trim()||JSON.stringify(j));
 if(status===200){$('n').value='';$('hh').value='';$('sw').value='';loadAll();}}

// ---------- form-based actions (bedoon prompt zanjire-i) ----------
function gameAdd(n){formModal(t('t_game_add'),[
  {id:'name',label:t('f_name'),ph:'gmtrk',req:1},
  {id:'inbound',label:t('l_inb_tls'),val:'8444',req:1},
  {id:'sni',label:t('l_sni'),ph:'gmtrk.l1t.ir',req:1}],
  v=>{closeModal();run(n,'game_add',v);});}
function gameCert(n){formModal(t('t_game_cert'),[
  {id:'sni',label:t('l_sni_cert'),req:1}],
  v=>{closeModal();run(n,'game_cert',v);});}

function domainTls(n){
 modal(`<h3>${t('domain_tls')} (${n})</h3>
 <div id="dt_list"><div class="empty">${t('loading')}</div></div>
 <div id="dt_domains"></div>
 <div class="row"><label>${t('dt_add')}</label><input id="dt_nd" placeholder="dom2.example.ir" style="min-width:140px"><input id="dt_nfc" placeholder="fullchain (optional)"><input id="dt_nkey" placeholder="privkey (optional)"><button class="g" onclick="dtAddDomain('${n}')">${t('dt_add_btn')}</button></div>
 <div class="row"><button class="s" onclick="run('${n}','tls_info');closeModal();">${t('dt_show')}</button>
   <span class="sub">${t('dt_hint')}</span></div>
 <div class="row"><label>${t('dt_domain')}</label><input id="dt_dom" placeholder="btli.ir">
   <button class="g" onclick="dtSet('${n}','domain','dt_dom')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_fc')}</label><input id="dt_fc" placeholder="/root/cert/x/fullchain.pem">
   <button class="g" onclick="dtSet('${n}','fullchain','dt_fc')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_key')}</label><input id="dt_key" placeholder="/root/cert/x/privkey.pem">
   <button class="g" onclick="dtSet('${n}','key','dt_key')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_le')}</label><input id="dt_ledom" placeholder="dom.example.ir">
   <input id="dt_leem" placeholder="email (optional)">
   <button class="g" onclick="dtCert('${n}')">${t('dt_get')}</button></div>
 <div class="row" style="justify-content:flex-end;margin-top:10px">
   <button class="s" onclick="run('${n}','regen_full');closeModal();">${t('dt_apply')}</button>
   <button class="gh" onclick="closeModal()">${t('close')}</button></div>`);dtRefresh(n);}

async function dtLoadList(n){
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'tls_certs',args:{}});
 const box=$('dt_list'); if(!box)return;
 const txt=(j&&j.out)||''; const rows=parseTable(txt,'DOMAIN|EXPIRY|ACTIVE|SNI');
 if(!rows.length){box.innerHTML=`<div class="empty">${t('dt_none')}</div>`;return;}
 let h2=`<div class="sub" style="margin:4px 0">${t('dt_list')}</div>`;
 h2+=`<table><tr><th>${t('dt_domain')}</th><th>${t('dt_expiry')}</th><th>${t('dt_active')}</th><th>SNI</th></tr>`;
 rows.forEach(p=>{const dom=h(p[0]||''),exp=h(p[1]||''),act=(p[2]||'')==='yes',sni=(p[3]||'')==='yes';
  h2+=`<tr><td>${dom}</td><td>${exp}</td><td>${act?('<span class="badge b-ok">'+t('dt_active')+'</span>'):''}</td><td>${sni?'SNI':''}</td></tr>`;});
 h2+='</table>';
 box.innerHTML=h2;
}
function parseTable(txt,header){const cols=header.split('|').length;const lines=(txt||'').split('\n').map(x=>x.trim());let hi=-1;for(let i=0;i<lines.length;i++){if(lines[i].toUpperCase().indexOf(header.toUpperCase())===0){hi=i;break;}}const start=hi>=0?hi+1:0;const dom=/^[A-Za-z0-9_*-]+(\.[A-Za-z0-9_*-]+)+$/;const out=[];for(let i=start;i<lines.length;i++){const l=lines[i];if(l.indexOf('|')<0)continue;const p=l.split('|');if(p.length<cols)continue;if(!dom.test((p[0]||'').trim()))continue;out.push(p);}return out;}
function dtRefresh(n){dtLoadDomains(n);dtLoadList(n);}
async function dtApi(n,action,args){const {j}=await api('POST','api/servers/'+n+'/action',{action,args:args||{}});
 const out=((j&&j.cmd?('$ '+j.cmd+'\n'):'')+(((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):''))).trim();if(out)toast(out);loadOv(n);return j;}
async function dtLoadDomains(n){
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'domain_ls',args:{}});
 const box=$('dt_domains'); if(!box)return;
 const txt=(j&&j.out)||''; const rows=parseTable(txt,'DOMAIN|FULLCHAIN|KEY|PRIMARY');
 if(!rows.length){box.innerHTML='';return;}
 let x=`<div class="sub" style="margin:4px 0">${t('dt_served')}</div><table><tr><th>${t('dt_domain')}</th><th>${t('dt_kind')}</th><th></th></tr>`;
 rows.forEach(p=>{const dom=h(p[0]||'');const prim=(p[3]||'')==='yes';
  x+=`<tr><td>${dom}</td><td>${prim?('<span class="badge b-role">'+t('dt_primary')+'</span>'):('<span class="badge b-kcp">'+t('dt_extra')+'</span>')}</td><td>${prim?'':('<button class="g" onclick="dtMakePrimary(\''+n+'\',\''+dom+'\')">'+t('dt_makeprimary')+'</button> '+'<button class="r" onclick="dtRmDomain(\''+n+'\',\''+dom+'\')">'+t('remove')+'</button>')}</td></tr>`;});
 x+='</table>'; box.innerHTML=x;
}
async function dtAddDomain(n){const d=($('dt_nd').value||'').trim();if(!d){toast(t('fill'));return;}
 const fc=($('dt_nfc').value||'').trim(),key=($('dt_nkey').value||'').trim();
 const a={domain:d}; if(fc&&key){a.fullchain=fc;a.key=key;}else{a.certbot=1;}
 await dtApi(n,'domain_add',a); domainTls(n);}
async function dtRmDomain(n,d){if(!confirm(t('remove')+' '+d+' ?'))return; await dtApi(n,'domain_rm',{domain:d}); domainTls(n);}
async function dtMakePrimary(n,d){if(!confirm(t('dt_mp_confirm')+' '+d+' ?'))return; await dtApi(n,'domain_primary',{domain:d}); domainTls(n);}

function dtSet(n,key,id){const v=($(id).value||'').trim();if(!v){toast(t('fill'));return;}closeModal();run(n,'set_config',{key,value:v});}
function dtCert(n){const d=($('dt_ledom').value||'').trim();if(!d){toast(t('fill'));return;}
 const e=($('dt_leem').value||'').trim();const a={domain:d};if(e)a.email=e;closeModal();run(n,'tls_cert',a);}

function addNode(n){formModal(t('t_add_node'),[
  {id:'name',label:t('l_node_name'),req:1},
  {id:'inbound',label:t('l_xray_inb'),req:1},
  {id:'api_port',label:t('l_api_opt')}],
  v=>{closeModal();const a={name:v.name,inbound:v.inbound};if(v.api_port)a.api_port=v.api_port;run(n,'add_node',a);});}
function rmNode(n,name){if(confirm(t('cf_delnode')+' ('+name+')'))run(n,'rm_node',{name});}
function addSvc(n){formModal(t('t_add_svc'),[
  {id:'name',label:t('f_name'),req:1},
  {id:'token',label:t('l_token'),req:1},
  {id:'inbound',label:t('l_inbound'),req:1}],
  v=>{closeModal();run(n,'add_svc',v);});}
function rmSvc(n,name){if(confirm(t('cf_delsvc')+' ('+name+')'))run(n,'rm_svc',{name});}
function upAdd(n){formModal(t('t_up_add'),[
  {id:'id',label:t('l_up_id'),ph:'iran2',req:1},
  {id:'server',label:t('l_up_srv'),ph:'rp02.example.ir:443',req:1}],
  v=>{closeModal();run(n,'upstream_add',v);});}
function upAddSvc(n,id){formModal(t('t_up_addsvc')+' ('+id+')',[
  {id:'name',label:t('f_name'),req:1},
  {id:'token',label:t('l_token'),req:1},
  {id:'inbound',label:t('l_inbound'),req:1}],
  v=>{closeModal();run(n,'upstream_add_svc',{id,name:v.name,token:v.token,inbound:v.inbound});});}
function upRm(n,id){if(confirm(t('cf_delup')+' ('+id+') ?'))run(n,'upstream_rm',{id});}
function upRmSvc(n,id,name){if(confirm(t('cf_delupsvc')+' ('+id+'/'+name+') ?'))run(n,'upstream_rm_svc',{id,name});}
function fakewebStart(n){formModal(t('t_fw'),[

  {id:'port',label:t('l_fw_port')}],
  v=>{closeModal();run(n,'fakeweb_start',v.port?{port:v.port}:{});});}
function wdOn(n){formModal(t('t_wd'),[
  {id:'interval',label:t('l_wd_iv'),val:'60',req:1}],
  v=>{closeModal();run(n,'watchdog_on',{interval:v.interval||'60'});});}
function kcpOnIran(n){formModal(t('t_kcp_iran'),[
  {id:'port',label:t('l_udp'),val:'443',req:1},
  {id:'profile',label:t('l_profile'),type:'select',val:'balanced',opts:PROF}],
  v=>{closeModal();run(n,'kcp_on',{port:v.port,profile:v.profile||'balanced'});});}
function plainOnIran(n){formModal(t('t_plain_iran'),[
  {id:'port',label:t('l_plain_port'),val:'8880',req:1}],
  v=>{closeModal();run(n,'plain_on',{port:v.port});});}
function directOnIran(n){formModal(t('t_direct_iran'),[
  {id:'port',label:t('l_direct_port'),val:'8081',req:1},
  {id:'header',label:t('l_direct_header'),val:'X-Cdn-Id',req:1}],
  v=>{closeModal();run(n,'direct_on',{port:v.port,header:v.header});});}
function plainOnNode(n){formModal(t('t_plain_node'),[
  {id:'remote',label:t('l_plain_remote'),ph:'5.202.4.40:8880',req:1}],
  v=>{closeModal();run(n,'plain_on',{remote:v.remote});});}
function noiseOnIran(n){formModal(t('t_noise_iran'),[
  {id:'port',label:t('l_noise_port'),val:'2334',req:1}],
  v=>{closeModal();run(n,'noise_on',{port:v.port});});}
function noiseNode(n,act){formModal(t(act==='on'?'noise_node_on':'noise_node_off'),[
  {id:'name',label:t('c_name'),req:1}],
  v=>{closeModal();run(n,act==='on'?'noise_node_on':'noise_node_off',{name:v.name});});}
// autofill-e noise: az server Iran remote+pubkey ra migirad
async function noiseAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/noiseconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_remote'))$('f_remote').value=j.remote||'';
 if($('f_pubkey'))$('f_pubkey').value=j.pubkey||'';
 if($('f_pattern')&&j.pattern)$('f_pattern').value=j.pattern;
 toast(t('autofilled'));
}
function noiseNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'remote',label:t('l_noise_remote'),ph:'5.202.4.40:2334',req:1});
 f.push({id:'pubkey',label:t('l_noise_key'),req:1});
 f.push({id:'pattern',label:t('l_noise_pattern'),val:'Noise_NK_25519_ChaChaPoly_BLAKE2s'});
 return f;
}
function noiseOnNode(n){formModal(t('t_noise_node'),noiseNodeFields(),
  v=>{closeModal();run(n,'noise_on',{remote:v.remote,pubkey:v.pubkey,pattern:v.pattern||''});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>noiseAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();noiseAutofill(sel.value);};box.appendChild(b);}
   noiseAutofill(sel.value);
 }}

// list-e serverhaye Iran (baraye autofill-e KCP)
function iranServers(){return SERVERS.filter(s=>s.role==='iran');}
// gozine-haye <option> baraye entekhab-e server Iran (host be onvan value)
function iranSrvOptions(){return iranServers().map(s=>`<option value="${h(s.host)}">${h(s.name)} (${h(s.host)})</option>`).join('');}
// tunnel-e asli (main) ye node ra be yek server Iran vasl kon (SERVER=domain:443)
// mohem: dar halat-e pishfarz (ws+TLS) node bayad be DOMAIN-e omoomi vasl shavad, na host/IP-e
// SSH-e inventory — chon ratholenode az SERVER ham remote_addr va ham SNI ra misazad. pas
// entekhab az roo-ye NAM-e server Iran ast va maghsad-e daghigh (domain) ra az server migirim.
function setMainSrv(n){
 const irs=iranServers();
 if(!irs.length){toast(t('no_iran'));return;}
 const f=[{id:'iran',label:t('l_iran_srv'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))}];
 formModal(t('set_main'),f,async v=>{
  const iran=(v.iran||'').trim(); if(!iran){toast(t('fill'));return;}
  closeModal();
  toast(t('autofilling'));
  // domain-e vaghei (ba cert-e mokhtabetesh) ra az server Iran begir, na host-e inventory
  const {j}=await api('GET','api/servers/'+iran+'/mainconnect');
  if(!j||!j.ok||!j.server){toast(t('autofail'));return;}
  run(n,'set_server',{server:j.server});
 });
}
// sim-keshi: yek node-e Iran (name/token/inbound) ra rooye yek node-e kharej (ya upstream-esh)
// be-onvan service ezafe kon. maghsadha: hameye node-ha + upstream-hayeshan; anha ke tunnel-eshan
// be hamin Iran vasl ast ba ✓ neshan dade va default entekhab mishavand.
function wireTargets(iranHost){
 const opts=[]; let def='';
 SERVERS.filter(s=>s.role==='node').forEach(s=>{
  const ov=OVS[s.name]; if(!ov||ov.reachable===false)return;
  const ms=String(ov.main_server||'');
  const hit=iranHost && (ms===iranHost || ms.split(':')[0]===iranHost);
  opts.push({v:s.name+'|', t:(hit?'✓ ':'')+s.name+' — main ('+(ms||'?')+')'});
  if(hit && !def)def=s.name+'|';
  (ov.upstreams||[]).forEach(u=>{
   const us=String(u.server||''); const uh=us && (us===iranHost || us.split(':')[0]===iranHost);
   opts.push({v:s.name+'|'+u.id, t:(uh?'✓ ':'')+s.name+' ▸ upstream '+u.id+' ('+(us||'?')+')'});
   if(uh && !def)def=s.name+'|'+u.id;
  });
 });
 return {opts, def:def||(opts[0]&&opts[0].v)||''};
}
async function wireNode(iranName,nodeName){
 const s=SERVERS.find(x=>x.name===iranName)||{}; const iranHost=s.host||'';
 const {opts,def}=wireTargets(iranHost);
 if(!opts.length){toast(t('no_node_dst'));return;}
 formModal(t('wire_title')+' · '+nodeName,
   [{id:'dst',label:t('l_dst_node'),type:'select',val:def,opts}],
   async v=>{
    const parts=(v.dst||'').split('|'); const dst=parts[0], up=parts[1]||'';
    if(!dst){toast(t('fill'));return;}
    closeModal();
    toast(t('autofilling'));
    // 1) token/inbound-e vaghei-ye node-e Iran ra begir (token dar 'ls' mask ast)
    const {j}=await api('GET','api/servers/'+iranName+'/nodeconnect/'+nodeName);
    if(!j||!j.ok){toast(t('wire_fail'));outModal(t('wire_title'),(j&&(j.error||j.raw))||'?');return;}
    // 2) rooye node-e kharej (ya upstream-esh) be-onvan service ezafe kon
    if(up)run(dst,'upstream_add_svc',{id:up,name:j.name,token:j.token,inbound:j.inbound});
    else  run(dst,'add_svc',{name:j.name,token:j.token,inbound:j.inbound});
   });
}
// autofill: az server Iran-e entekhab-shode remote/key/profile-e daghigh ra migirad
async function kcpAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/kcpconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_remote'))$('f_remote').value=j.remote||'';
 if($('f_key'))$('f_key').value=j.key||'';
 if($('f_profile')&&j.profile)$('f_profile').value=j.profile;
 toast(t('autofilled'));
}
function kcpNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'remote',label:t('l_remote'),ph:'5.202.4.40:443',req:1});
 f.push({id:'key',label:t('l_key'),req:1});
 f.push({id:'profile',label:t('l_profile'),type:'select',val:'balanced',opts:PROF});
 return f;
}
function kcpOnNode(n){formModal(t('t_kcp_node'),kcpNodeFields(),
  v=>{closeModal();run(n,'kcp_on',{remote:v.remote,key:v.key,profile:v.profile||'balanced'});});
 // dokme-ye autofill + trigger ba taghir-e select
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>kcpAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();kcpAutofill(sel.value);};box.appendChild(b);}
   kcpAutofill(sel.value); // avvalin bar khodkar por kon
 }}
function upKcpOn(n,id){formModal(t('t_kcp_up')+' ('+id+')',kcpNodeFields(),
  v=>{closeModal();run(n,'upstream_kcp_on',{id,remote:v.remote,key:v.key,profile:v.profile||'balanced'});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>kcpAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.onclick=e=>{e.preventDefault();kcpAutofill(sel.value);};box.appendChild(b);}
   kcpAutofill(sel.value);
 }}


function editNode(n,name){formModal(t('t_edit_node')+' ('+name+')',[
  {id:'inbound',label:t('l_inb_new')},
  {id:'api_port',label:t('l_api_new')}],
  v=>{const a={name};if(v.inbound)a.inbound=v.inbound;if(v.api_port)a.api_port=v.api_port;
   if(!a.inbound&&!a.api_port){toast(t('nochg'));return;}closeModal();run(n,'edit_node',a);});}
function renameNode(n,name){formModal(t('t_rename'),[
  {id:'new',label:t('l_new_name'),val:name,req:1}],
  v=>{if(v.new===name){closeModal();return;}closeModal();run(n,'rename_node',{old:name,new:v.new});});}
function editServer(n){const s=fnd(n);formModal(t('t_edit_srv')+' ('+n+')',[
  {id:'host',label:t('f_host'),val:s.host,req:1},
  {id:'ssh_user',label:t('f_user'),val:s.ssh_user||'root',req:1},
  {id:'ssh_port',label:t('f_port'),val:s.ssh_port||'22',req:1}],
  async v=>{const {status,j}=await api('PUT','api/servers/'+n,{host:v.host,ssh_user:v.ssh_user,ssh_port:v.ssh_port});
   if(status!==200){toast('error: '+(j.error||status));return;}closeModal();toast(t('saved'));loadAll();});}

async function savePw(){const cur=$('cpw').value,nw=$('npw').value;if(!nw){toast(t('need_newpw'));return;}const {status,j}=await api('POST','api/config',{current_password:cur,new_password:nw});if(status!==200){toast('error: '+(j.error||status));return;}toast(t('pw_changed'));$('cpw').value='';$('npw').value='';}
async function rotTok(){if(!confirm(t('cf_rottok')))return;const {status,j}=await api('POST','api/config',{rotate_token:true});if(status!==200){toast('error: '+(j.error||status));return;}TOKEN=j.api_token;localStorage.setItem('rh_token',TOKEN);toast(t('tok_applied'));renderSettingsPage();}
// refresh-e khodkar: faghat overview-haye safhe-ye faal (server SSH kamtar mikhorad)
setInterval(()=>{if($('auto')&&$('auto').checked&&TOKEN)pollByPage();},20000);
shell();

</script></body></html>"""


def main():
    cfg = get_config()
    host = os.environ.get("RATHOLEHUB_HOST", cfg.get("listen_host", "127.0.0.1"))
    port = int(os.environ.get("RATHOLEHUB_PORT", cfg.get("listen_port", 8088)))
    if cfg.get("_insecure"):
        sys.stderr.write(
            "\n[!!] hoshdar amniati: token/rmze pishfrze naamn faal ast.\n"
            "     ghabl az gharar dadn panel psht nginx, config.json ra ba mghadir ghvi bsaz:\n"
            "       api_token, admin_password_sha256\n\n")
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("ratholehub rooye http://%s:%d (mock=%s)" % (host, port, MOCK))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
