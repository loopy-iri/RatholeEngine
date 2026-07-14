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
    "noise_on", "noise_off", "noise_node_on", "noise_node_off",

    "backup", "enable", "regen_full", "regen",
    # node
    "add_svc", "rm_svc", "kcp_on", "kcp_off", "apply", "restart",
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

def deploy_to_server(server):
    # askriptha ra ba scp be server mifrstd va update.sh ra ejra mikonad (apdit az rah dvr).
    if MOCK:
        return {"rc": 0, "out": "[mock deploy→%s] scp + update.sh" % server.get("name"), "err": ""}
    cfg = get_config()
    bundle = cfg.get("bundle_dir", "/opt/ratholehub/bundle")
    files = ["ratholectl", "ratholenode", "common.sh", "update.sh", "kcptest-iran.sh", "kcptest-node.sh"]
    srcs = [os.path.join(bundle, f) for f in files if os.path.exists(os.path.join(bundle, f))]
    if not srcs:
        return {"rc": 1, "out": "", "err": "bundle khali ast: %s" % bundle}
    user = server.get("ssh_user", "root"); host = server["host"]; port = str(server.get("ssh_port", 22))
    keyopt = (["-i", cfg["ssh_key_path"]] if cfg.get("ssh_key_path") else [])
    base = _ssh_base(cfg, server)
    try:
        r = subprocess.run(base + ["mkdir", "-p", "/root/rathole-manager"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"rc": r.returncode, "out": r.stdout, "err": "mkdir: " + r.stderr}
        scp = ["scp"] + list(cfg.get("ssh_opts", [])) + keyopt + ["-P", port] + srcs + \
              ["%s@%s:/root/rathole-manager/" % (user, host)]
        r = subprocess.run(scp, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return {"rc": r.returncode, "out": r.stdout, "err": "scp: " + r.stderr}
        r = subprocess.run(base + ["bash", "/root/rathole-manager/update.sh"],
                           capture_output=True, text=True, timeout=180)
        return {"rc": r.returncode, "out": _strip_ansi(r.stdout), "err": _strip_ansi(r.stderr)}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "SSH/scp timeout"}
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
    logs.append("== deploy (scp + update.sh) ==\n" + (dep.get("out", "") or "") +
                (("\n[stderr] " + dep.get("err", "")) if dep.get("err") else ""))
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
    if j == "ratholectl kcp status":
        return {"rc": 0, "out": "kcp: roshan  UDP :443 → 127.0.0.1:2333  (profile: balanced)\n"
                "  estetar: UDP/443 ~ QUIC/HTTP3\n  service: active\n  gvshdadn UDP:443: blh", "err": ""}
    if j == "ratholectl game ls":
        return {"rc": 0, "out": "NAME           SNI                    DATA     NODE-INBOUND\n"
                "------------------------------------------------------------\n"
                "gmtrk          gmtrk.l1t.ir           1007     8444", "err": ""}
    if j == "ratholectl doctor":
        return {"rc": 0, "out": "OK rathole-server faal ast\nOK nginx faal ast\nOK trk01 amade\n"
                "khlash: OK=6  FAIL=0", "err": ""}
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


def parse_doctor(text):
    m = re.search(r"OK=(\d+)\s+FAIL=(\d+)", text or "")
    if m:
        return {"ok": int(m.group(1)), "fail": int(m.group(2))}
    return {"ok": (text or "").count("OK "), "fail": (text or "").count("FAIL")}

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
            audit_log(self._user(), name, "deploy", "deploy (scp + update.sh)", res.get("rc"))
            return self._send(200, {"server": name, "cmd": "deploy (scp + update.sh)", **res})
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
            ov["game"] = parse_game_ls(R(["ratholectl", "game", "ls"]).get("out", ""))
            ov["health"] = parse_doctor(R(["ratholectl", "doctor"]).get("out", ""))
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
 :root{--bg:#0d141c;--panel:#151f2b;--panel2:#1b2735;--line:#263547;--tx:#e7eef6;--mut:#8ba0b6;--ac:#3b82f6;--gr:#22c55e;--rd:#ef4444;--yl:#eab308}
 *{box-sizing:border-box}
 body{font-family:system-ui,Segoe UI,Tahoma,sans-serif;margin:0;background:var(--bg);color:var(--tx)}
 header{position:sticky;top:0;z-index:5;background:#0f1822;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;padding:12px 20px}
 header .logo{font-weight:700;font-size:18px} header .logo span{color:var(--ac)}
 .wrap{max-width:1100px;margin:0 auto;padding:18px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;margin:14px 0;overflow:hidden}
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
 .b-role{background:rgba(234,179,8,.16);color:#fde047}
 table{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}
 th,td{text-align:right;padding:7px 9px;border-bottom:1px solid var(--line)}
 th{color:var(--mut);font-weight:600} tr:last-child td{border-bottom:0}
 .sec{margin-top:12px} .sec h4{margin:0 0 6px;font-size:13px;color:var(--mut);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .dot{width:9px;height:9px;border-radius:50%;display:inline-block} .d-ok{background:var(--gr)} .d-bad{background:var(--rd)} .d-un{background:var(--yl)}
 .up{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0}
 pre{background:#0a1017;padding:10px;border-radius:8px;overflow:auto;max-height:220px;white-space:pre-wrap;font-size:12px;margin:8px 0 0}
 .toast{position:fixed;bottom:18px;left:18px;max-width:520px;background:#0a1017;border:1px solid var(--line);border-radius:10px;padding:12px 14px;font-size:12px;white-space:pre-wrap;display:none;z-index:20;box-shadow:0 8px 30px rgba(0,0,0,.5)}
 .toast.show{display:block}
 .empty{color:var(--mut);font-size:13px;padding:6px 0}
 label.sw{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--mut);cursor:pointer}
 .addbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:50}.mbox{background:#0f1720;border:1px solid #2b3a4a;border-radius:12px;padding:18px;min-width:320px;max-width:90vw;max-height:85vh;overflow:auto}.mbox h3{margin:0 0 12px}.mbox .row{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}.mbox label{min-width:120px;color:#9fb3c8}.mbox input,.mbox select{background:#0b1219;border:1px solid #2b3a4a;color:#e6eef7;border-radius:8px;padding:6px 8px}.mbox table{width:100%;border-collapse:collapse;font-size:12px}.mbox td,.mbox th{border-bottom:1px solid #22303c;padding:4px 6px;text-align:right}</style></head><body>
<header><div class="logo">rathole<span>hub</span></div>
 <span class="sub" id="clock"></span><span style="flex:1"></span>
 <button class="gh" id="langbtn" onclick="toggleLang()">EN</button>
 <label class="sw"><input type="checkbox" id="auto" checked> <span id="lb_auto"></span></label>
 <button class="gh" id="refbtn" onclick="loadAll()"></button>
 <button class="gh" id="setbtn" onclick="openSettings()" style="display:none"></button>
 <button class="gh" id="auditbtn" onclick="openAudit()" style="display:none"></button>
 <button class="s" id="logbtn" onclick="logout()" style="display:none"></button>
</header>

<div class="wrap" id="app"></div>
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

  restart_rathole:'restart rathole',cf_restart:'restart rathole-server? hameye tunnelha lahzei ghat mishavand.',
  fakeweb:'web fake:',fw_start:'roshan/taghir port',fw_stop:'tavaghof',fw_rm:'khamoosh kamel',cf_fwrm:'hazf kamel web fake?',
  nodes_svcs:'nodeha / serviceha',add_node:'+ afzoodan node',no_nodes:'nodi tarif nashode.',
  c_name:'nam',c_dport:'port dade',c_inbound:'inbound',c_api:'API',c_ops:'amaliat',
  show_token:'nasb/token',edit:'virayesh',rename:'taghir nam',rotate:'chrkhesh token',cf_rotate:'chrkhesh token node',remove:'hazf',
  game_svcs:'servicehaye game (SNI/443)',add_game:'+ game',get_cert:'greftan gvahi',no_game:'service game nadari.',
  c_data:'dade',c_node_inb:'inbound node',
  main_tunnel:'tunnel asli →',restart_tunnel:'restart tunnel',migrate:'naghshe mohajerat',
  watchdog:'watchdog (restart khodkar):',wd_on:'roshan',wd_off:'khamoosh',wd_status:'vaziat',
  svc_tunnel:'servicehaye in tunnel',add_svc:'+ service',no_svc:'servisi nist.',c_svc:'service',
  upstreams:'serverhaye Iran-e digar (upstream)',add_up:'+ upstream',no_up:'upstream nadari (faghat yek Iran).',status:'status',del_up:'hazf upstream',cf_delup:'hazf upstream',cf_delupsvc:'hazf service az upstream',

  cancel:'enseraf',save:'zakhire',fill:'hameye field haye lazem ra por kon',saved:'zakhire shod ✓',
  cf_delsrv:'hazf server az panel?',cf_delnode:'hazf node',cf_delsvc:'hazf service',cf_deploy:'apdit scripthaye',
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
  dt_show:'namayesh feli',dt_hint:'khorooji dar toast',dt_domain:'damnh asli',dt_fc:'masir fullchain',dt_key:'masir privkey',
  dt_le:'greftan gvahi (domain/email)',dt_get:'begir',dt_apply:'emal (regen)',
  dt_list:'gvahihaye mojood rooye in server:',dt_active:'faal',dt_expiry:'enghza',dt_none:'gvahii peyda nashod.',
  dt_served:'damnhhaye faal rooye in server:',dt_kind:'nooe',dt_primary:'asli',dt_extra:'ezafi',dt_add:'afzoodan damnh',dt_add_btn:'+ damnh',dt_makeprimary:'asli kon',dt_mp_confirm:'damnh asli avaz shavad be',
  running:'ejra-ye',on:'rooye',ok_rc:'anjam shod',fail_rc:'nashod',
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

  restart_rathole:'restart rathole',cf_restart:'Restart rathole-server? All tunnels drop briefly.',
  fakeweb:'Fake web:',fw_start:'Start/Change port',fw_stop:'Stop',fw_rm:'Remove fully',cf_fwrm:'Remove fake web completely?',
  nodes_svcs:'Nodes / Services',add_node:'+ Add node',no_nodes:'No nodes defined.',
  c_name:'Name',c_dport:'Data port',c_inbound:'Inbound',c_api:'API',c_ops:'Actions',
  show_token:'Install/token',edit:'Edit',rename:'Rename',rotate:'Rotate token',cf_rotate:'Rotate token for node',remove:'Remove',
  game_svcs:'Game services (SNI/443)',add_game:'+ game',get_cert:'Get certificate',no_game:'No game services.',
  c_data:'Data',c_node_inb:'Node inbound',
  main_tunnel:'Main tunnel →',restart_tunnel:'restart tunnel',migrate:'Migration map',
  watchdog:'watchdog (auto restart):',wd_on:'On',wd_off:'Off',wd_status:'Status',
  svc_tunnel:'Services on this tunnel',add_svc:'+ service',no_svc:'No services.',c_svc:'Service',
  upstreams:'Other Iran servers (upstream)',add_up:'+ upstream',no_up:'No upstream (single Iran).',status:'status',del_up:'Remove upstream',cf_delup:'Remove upstream',cf_delupsvc:'Remove service from upstream',

  cancel:'Cancel',save:'Save',fill:'Fill all required fields',saved:'Saved ✓',
  cf_delsrv:'Remove server from panel?',cf_delnode:'Remove node',cf_delsvc:'Remove service',cf_deploy:'Update scripts of',
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
  dt_show:'Show current',dt_hint:'output in toast',dt_domain:'Main domain',dt_fc:'fullchain path',dt_key:'privkey path',
  dt_le:'Obtain cert (domain/email)',dt_get:'Get',dt_apply:'Apply (regen)',
  dt_list:'Certificates on this server:',dt_active:'active',dt_expiry:'expiry',dt_none:'No certificates found.',
  dt_served:'Active domains on this server:',dt_kind:'Type',dt_primary:'primary',dt_extra:'extra',dt_add:'Add domain',dt_add_btn:'+ domain',dt_makeprimary:'Make primary',dt_mp_confirm:'Switch primary domain to',
  running:'running',on:'on',ok_rc:'done',fail_rc:'failed',
 }
};
function t(k){return (DICT[LANG]&&DICT[LANG][k])||DICT.fa[k]||k;}
function applyStatic(){
 document.documentElement.lang=LANG; document.documentElement.dir=(LANG==='fa'?'rtl':'ltr');
 $('langbtn').textContent=(LANG==='fa'?'EN':'فا');
 $('lb_auto').textContent=t('auto'); $('refbtn').textContent=t('refresh');
 $('setbtn').textContent=t('settings'); $('auditbtn').textContent=t('audit'); $('logbtn').textContent=t('logout');
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
function setNav(d){['setbtn','auditbtn'].forEach(i=>{const e=$(i);if(e)e.style.display=d;});}
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

setInterval(()=>{$('clock').textContent=new Date().toLocaleTimeString(LANG==='fa'?'fa-IR':'en-US');},1000);

function shell(){
 applyStatic();
 if(!TOKEN){$('logbtn').style.display='none';setNav('none');
  $('app').innerHTML=`<div class="card"><div class="cbody"><h3>${t('login_title')}</h3>
   <div class="addbar"><input id="pw" type="password" placeholder="${t('pw_ph')}" style="min-width:220px">
   <button class="g" onclick="doLogin()">${t('login_btn')}</button></div><div id="msg" class="sub"></div></div></div>`;
  const p=$('pw'); if(p)p.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();}); return;}
 $('logbtn').style.display='';setNav('');
 $('app').innerHTML=`<div class="card"><div class="cbody">
   <div class="addbar"><b>${t('add_server')}:</b>
   <input id="n" placeholder="${t('f_name')}" size="10"><select id="rl"><option value="iran">iran</option><option value="node">node</option></select>
   <input id="hh" placeholder="${t('f_host')}" size="14"><input id="uu" value="root" size="6"><input id="pp" value="22" size="4">
   <input id="sw" type="password" placeholder="${t('prov_pw')}" size="14">
   <button class="g" onclick="provSrv()">${t('prov_btn')}</button>
   <button class="gh" onclick="addSrv()">${t('add_btn')}</button></div>
   <div class="sub" style="margin-top:6px">${t('prov_hint')}</div></div></div>
   <div id="servers"></div>`;
 loadAll();
}
async function doLogin(){const {status,j}=await api('POST','api/login',{password:$('pw').value});
 if(status===200){TOKEN=j.token;localStorage.setItem('rh_token',TOKEN);shell();}else{$('msg').textContent=t('pw_wrong');}}

async function loadAll(){ if(!TOKEN)return; const {j}=await api('GET','api/servers'); SERVERS=j||[];
 const c=$('servers'); if(!c)return;
 if(!SERVERS.length){c.innerHTML=`<div class="card"><div class="cbody empty">${t('no_servers')}</div></div>`;return;}
 c.innerHTML=SERVERS.map(s=>`<div class="card" id="srv_${h(s.name)}">
   <div class="chead"><span class="dot d-un" id="dot_${h(s.name)}"></span>
     <span class="name">${h(s.name)}</span><span class="badge b-role">${h(s.role)}</span>
     <span class="sub">${h(s.host)}:${s.ssh_port}</span><span id="hd_${h(s.name)}"></span>
     <span style="flex:1"></span>
     <div class="btns">
       <button class="gh" onclick="loadOv('${h(s.name)}')">↻</button>
       <button class="gh" onclick="showDetails('${h(s.name)}')">${t('details')}</button>
       <button class="s" onclick="doDeploy('${h(s.name)}')">${t('update')}</button>
       <button class="s" onclick="run('${h(s.name)}','tune')">tune</button>
       <button class="gh" onclick="editServer('${h(s.name)}')">${t('edit_server')}</button>
       <button class="r" onclick="delSrv('${h(s.name)}')">${t('del_server')}</button>
     </div></div>
   <div class="cbody" id="body_${h(s.name)}"><div class="empty">${t('loading')}</div></div></div>`).join('');
 SERVERS.forEach(s=>loadOv(s.name));
}
function fnd(n){return SERVERS.find(s=>s.name===n)||{};}
async function loadOv(n){const {j}=await api('GET','api/servers/'+n+'/overview'); renderOv(n,j||{});}
function setDot(n,cls){const d=$('dot_'+n); if(d)d.className='dot '+cls;}

function renderOv(n,ov){
 const body=$('body_'+n), hd=$('hd_'+n); if(!body)return; const role=fnd(n).role;
 if(ov.reachable===false){setDot(n,'d-bad');hd.innerHTML=`<span class="badge b-bad">${t('no_ssh')}</span>`;
   body.innerHTML=`<div class="empty">${t('ssh_help')}<br><code>ssh-copy-id -i /root/.ssh/id_ed25519.pub root@${h(fnd(n).host)}</code><br><br>${h(ov.error||'')}</div>`;return;}
 let hb='';
 if(role==='iran'){const ok=(ov.health||{}).fail===0; setDot(n,ok?'d-ok':'d-bad');
   hb=`<span class="badge ${ok?'b-ok':'b-bad'}">doctor ${(ov.health||{}).ok||0}/${((ov.health||{}).ok||0)+((ov.health||{}).fail||0)}</span>`;
   const k=ov.kcp||{}; hb+=k.enabled?` <span class="badge b-kcp">kcp ${h(k.profile||'')}${k.port?(' :'+h(k.port)):''}${k.stealth?' · QUIC':''}</span>`:' <span class="badge b-ws">ws/443</span>';
   const nz=ov.noise||{}; if(nz.enabled){hb+=` <span class="badge b-noise">noise${nz.port?(' :'+h(nz.port)):''}${nz.count?(' · '+h(nz.count)+' node'):''}</span>`;}
 } else { const m=ov.main_tunnel||(ov.kcp||{}).mode||'ws'; setDot(n,'d-ok');
   hb=m==='noise'?`<span class="badge b-noise">tunnel noise</span>`:(m==='kcp'?`<span class="badge b-kcp">tunnel kcp ${h((ov.kcp||{}).profile||'')}</span>`:'<span class="badge b-ws">tunnel ws/443</span>');
   if((ov.noise||{}).enabled && m!=='noise'){hb+=' <span class="badge b-noise">noise</span>';}
 }
 hd.innerHTML=hb;
 body.innerHTML = role==='iran'? renderIran(n,ov) : renderNode(n,ov);
}
function tbl(cols){return '<table><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr>';}
function esc(s){return h(s);}

function renderIran(n,ov){
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
   <div class="btns" style="margin-top:6px"><span class="sub">${t('fakeweb')}</span>

   <button class="g" onclick="fakewebStart('${n}')">${t('fw_start')}</button>
   <button class="s" onclick="run('${n}','fakeweb_stop')">${t('fw_stop')}</button>
   <button class="r" onclick="if(confirm(t('cf_fwrm')))run('${n}','fakeweb_rm')">${t('fw_rm')}</button></div></div>`;
 s+=`<div class="sec"><h4>${t('nodes_svcs')} <button class="g" onclick="addNode('${n}')">${t('add_node')}</button></h4>`;
 const nodes=ov.nodes||[];
 if(!nodes.length)s+=`<div class="empty">${t('no_nodes')}</div>`;
 else{ s+=tbl([t('c_name'),t('c_dport'),t('c_inbound'),t('c_api'),t('c_ops')]);
  const nnodes=(ov.noise||{}).nodes||[];
  nodes.forEach(d=>{ const isN=nnodes.indexOf(d.name)>=0;
   const nbadge=isN?` <span class="badge b-noise">noise</span>`:'';
   const ntog=isN?`<button class="s" onclick="run('${n}','noise_node_off',{name:'${esc(d.name)}'})">${t('noise_node_off')}</button>`
                 :`<button class="s" onclick="run('${n}','noise_node_on',{name:'${esc(d.name)}'})">${t('noise_node_on')}</button>`;
   s+=`<tr><td>${esc(d.name)}${nbadge}</td><td>${esc(d.port)}</td><td>${esc(d.inbound)}</td><td>${esc(d.api)}</td>
   <td class="btns"><button class="gh" onclick="run('${n}','show_node',{name:'${esc(d.name)}'})">${t('show_token')}</button>
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

function renderNode(n,ov){
 let s='<div id="det_'+n+'"></div>';
 s+=`<div class="sec"><h4>${t('main_tunnel')} ${esc(ov.main_server||'?')}</h4><div class="btns">
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
  sv.forEach(d=>{s+=`<tr><td>${esc(d.name)}</td><td>${esc(d.inbound)}</td>
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
  if((u.services||[]).length){s+=tbl([t('c_svc'),t('c_inbound'),t('c_ops')]);u.services.forEach(x=>{s+=`<tr><td>${esc(x.name)}</td><td>${esc(x.inbound)}</td>
   <td class="btns"><button class="r" onclick="upRmSvc('${n}','${esc(u.id)}','${esc(x.name)}')">${t('remove')}</button></td></tr>`;});s+='</table>';}
  s+='</div>';

 });
 s+='</div>';
 return s;
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
async function showDetails(n){toast(t('loading_det'));
 const {j}=await api('GET','api/servers/'+n+'/details');
 outModal('details · '+n, j.text||JSON.stringify(j));}
function copyText(id){const el=$(id);if(!el)return;const x=el.textContent;
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(x).then(()=>toast(t('copied')),()=>toast('copy?'));}
 else{const r=document.createRange();r.selectNode(el);getSelection().removeAllRanges();getSelection().addRange(r);try{document.execCommand('copy');toast(t('copied'));}catch(e){toast('copy?');}}}
async function addSrv(){const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value};
 const {status,j}=await api('POST','api/servers',b); if(status!==200){toast('error: '+(j.error||status));return;} $('n').value='';$('hh').value=''; loadAll();}
async function provSrv(){const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value,ssh_password:$('sw').value};
 if(!b.name||!b.host||!b.ssh_password){toast(t('fill'));return;}
 toast(t('provisioning'));
 const {status,j}=await api('POST','api/provision',b);
 const out=((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):'');
 outModal(t('prov_btn')+' · '+b.name, out.trim()||JSON.stringify(j));
 if(status===200){$('n').value='';$('hh').value='';$('sw').value='';loadAll();}}
async function delSrv(n){if(!confirm(t('cf_delsrv')+' ('+n+')'))return;await api('DELETE','api/servers/'+n);loadAll();}

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

async function openSettings(){const {j}=await api('GET','api/config');const c=j||{};const warn=c.insecure?`<div class="badge b-bad">${t('insecure')}</div>`:'';
 modal(`<h3>${t('t_settings')}</h3>${warn}<div class="row"><label>${t('l_apitoken')}</label><span class="sub">${h(c.api_token_hint||'')}</span></div><div class="row"><label>${t('l_listen')}</label><span class="sub">${h(c.listen_host||'')}:${h(c.listen_port||'')}</span></div><h3 style="margin-top:14px">${t('chpw')}</h3><div class="row"><label>${t('l_curpw')}</label><input id="cpw" type="password"></div><div class="row"><label>${t('l_newpw')}</label><input id="npw" type="password" placeholder="${t('pw_hint')}"></div><div class="row"><button class="g" onclick="savePw()">${t('save_pw')}</button></div><h3 style="margin-top:14px">${t('l_apitoken')}</h3><div class="row"><button class="s" onclick="rotTok()">${t('rot_tok')}</button></div><div class="row" style="margin-top:10px"><button class="gh" onclick="closeModal()">${t('close')}</button></div>`);}
async function savePw(){const cur=$('cpw').value,nw=$('npw').value;if(!nw){toast(t('need_newpw'));return;}const {status,j}=await api('POST','api/config',{current_password:cur,new_password:nw});if(status!==200){toast('error: '+(j.error||status));return;}toast(t('pw_changed'));closeModal();}
async function rotTok(){if(!confirm(t('cf_rottok')))return;const {status,j}=await api('POST','api/config',{rotate_token:true});if(status!==200){toast('error: '+(j.error||status));return;}TOKEN=j.api_token;localStorage.setItem('rh_token',TOKEN);toast(t('tok_applied'));closeModal();}
async function openAudit(){const {j}=await api('GET','api/audit?limit=100');const rows=(j||[]);let x=`<h3>${t('t_audit')}</h3>`;if(!rows.length)x+=`<div class="empty">${t('no_audit')}</div>`;else{x+=`<table><tr><th>${t('c_time')}</th><th>${t('c_user')}</th><th>server</th><th>${t('c_action')}</th><th>rc</th></tr>`;rows.forEach(e=>{const d=new Date((e.ts||0)*1000).toLocaleString(LANG==='fa'?'fa-IR':'en-US');x+=`<tr><td>${h(d)}</td><td>${h(e.user)}</td><td>${h(e.server)}</td><td>${h(e.action)}</td><td>${h(e.rc)}</td></tr>`;});x+='</table>';}x+=`<div class="row" style="margin-top:10px"><button class="gh" onclick="closeModal()">${t('close')}</button></div>`;modal(x);}
setInterval(()=>{if($('auto')&&$('auto').checked&&TOKEN&&SERVERS.length)SERVERS.forEach(s=>loadOv(s.name));},20000);
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
