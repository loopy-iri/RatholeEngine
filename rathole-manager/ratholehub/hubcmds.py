# hubcmds.py — HASSAS-TARIN BAKHSH-E HUB: naghshe-ye action → argv-list.
#
# CHERA joda: hub HARGEZ reshte-ye kham rooye server ejra nemikonad. har action be yek
# LIST-e argv naghshe mishavad va har arg ba yek regex etebarsanji mishavad; SSH har arg
# ra jodagane pass midahad. in file amdan kuchak negah dashte mishavad ta ghabel-e
# morur bashad — moghe-e ezafe kardan-e action-e jadid:
#   1) an ra be build_iran_cmd YA build_node_cmd ezafe kon,
#   2) HAR argument ra ba RE_* etebarsanji kon (hich interpolation-e shl),
#   3) agar minevisad (na faghat mikhanad) be WRITE_ACTIONS ham ezafe kon.
#
# in module be hich chiz-e digar-e hub vabaste nist (faghat re/json) ta betavan
# mostaghel test-esh kard.

import json
import re

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
RE_CHAN    = re.compile(r"^(stable|beta)\Z")                                # kanal-e apdit-e hub
RE_HEADER  = re.compile(r"^[A-Za-z0-9-]{1,40}\Z")   # naam-e header-e masiryabi-ye direct
RE_BH_SRV  = re.compile(r"^(ws|wsmux)\Z")           # transport-e backhaul samt-e Iran (bedoon TLS)
RE_BH_CLI  = re.compile(r"^(wss|wssmux)\Z")         # transport-e backhaul samt-e node (TLS be nginx:443)
RE_BH_TOK  = re.compile(r"^[A-Fa-f0-9]{16,64}\Z")   # token-e moshtarak-e backhaul (openssl rand -hex)
# upstream-e reverse-proxy: DAGHIGHAN scheme://host:port — bedoon masir/query/metachar.
# in meghdar mostaghim be conf-e nginx miravad، pas har chiz-e digar rad mishavad.
RE_UPSTREAM = re.compile(r"^https?://[A-Za-z0-9._-]{1,255}:[0-9]{1,5}\Z")

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
    # ---- backhaul: core-e SMUX-e joda posht-e nginx/443 (tak-port hefz mishavad) ----
    if action == "backhaul_status": return ["ratholectl", "backhaul", "status"]
    if action == "backhaul_logs":   return ["ratholectl", "backhaul", "logs"]
    if action == "backhaul_show":   return ["ratholectl", "backhaul", "show"]
    if action == "backhaul_off":    return ["ratholectl", "backhaul", "off"]
    if action == "backhaul_on":
        port      = str(a.get("port", "3080") or "3080")
        transport = a.get("transport", "wsmux") or "wsmux"
        profile   = a.get("profile", "balanced") or "balanced"
        # transport-e server HATMAN bedoon-e TLS ast — TLS faghat rooye nginx terminate mishavad.
        if not RE_PORT.match(port):        return None
        if not RE_BH_SRV.match(transport): return None
        if not RE_PROFILE.match(profile):  return None
        return ["ratholectl", "backhaul", "on", port, transport, profile]
    if action in ("backhaul_node_on", "backhaul_node_off"):
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "backhaul", "node", name, ("on" if action == "backhaul_node_on" else "off")]
    # ---- reverse-proxy-e gheyre-tunnel: /<name>/ -> upstream-e delkhah ----
    if action == "proxy_ls":  return ["ratholectl", "proxy", "ls"]
    if action == "proxy_rm":
        name = a.get("name", "")
        if not RE_NAME.match(name): return None
        return ["ratholectl", "proxy", "rm", name]
    if action == "proxy_add":
        name = a.get("name", ""); up = a.get("upstream", "")
        # upstream mostaghim be conf-e nginx miravad — pas SAKHT-GIRANE mahdud mishavad:
        # faghat scheme://host:port. hich masir/query/metachar.
        if not RE_NAME.match(name): return None
        if not RE_UPSTREAM.match(up): return None
        return ["ratholectl", "proxy", "add", name, up]
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
                       "fake-port", "sub-port", "control-port",
                       "sub-path", "hub-path"): return None
        if key in ("fake-port", "sub-port", "control-port"):
            if not RE_PORT.match(val): return None
        elif key in ("sub-path", "hub-path"):
            # faghat yek segment-e sade (mesl 'subs' ya '/subs'); slash-haye atraf
            # ghabl az ersal bardashte mishavand. segment-e rezerv niz dar ratholectl
            # (is_reserved_name / normalize_path_seg) rad mishavad.
            seg = val.strip("/")
            if not RE_NAME.match(seg): return None
            val = seg
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
    # ---- backhaul: client-e SMUX ke be domain/443 (nginx → backhaul-server) vasl mishavad ----
    if action == "backhaul_status": return ["ratholenode", "backhaul", "status"]
    if action == "backhaul_logs":   return ["ratholenode", "backhaul", "logs"]
    if action == "backhaul_off":    return ["ratholenode", "backhaul", "off"]
    if action == "backhaul_on":
        domain    = a.get("domain", "")
        token     = a.get("token", "")
        transport = a.get("transport", "wssmux") or "wssmux"
        profile   = a.get("profile", "balanced") or "balanced"
        # transport-e client HATMAN TLS-dar ast (be nginx:443 mizanad).
        if not RE_HOST.match(domain):      return None
        if not RE_BH_TOK.match(token):     return None
        if not RE_BH_CLI.match(transport): return None
        if not RE_PROFILE.match(profile):  return None
        return ["ratholenode", "backhaul", "on", domain, token, transport, profile]
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
    # read-only: ayb-yabi-ye upstream (NA dar WRITE_ACTIONS)
    if action == "upstream_logs":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "logs", uid]
    if action == "upstream_status":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "status", uid]
    # ---- hamel-e per-upstream: hamsan-e tunnel-e asli vali baraye har upstream joda ----
    if action == "upstream_plain_on":
        uid = a.get("id", ""); remote = a.get("remote", "")
        if not RE_ID.match(uid) or not RE_IPPORT.match(remote): return None
        return ["ratholenode", "upstream", "plain", uid, "on", remote]
    if action == "upstream_plain_off":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "plain", uid, "off"]
    if action == "upstream_noise_on":
        uid = a.get("id", ""); remote = a.get("remote", ""); pubkey = a.get("pubkey", "")
        if not RE_ID.match(uid) or not RE_IPPORT.match(remote): return None
        if not RE_B64.match(pubkey): return None
        cmd = ["ratholenode", "upstream", "noise", uid, "on", remote, pubkey]
        pattern = a.get("pattern", "")
        if pattern:
            if not RE_HOST.match(pattern): return None
            cmd.append(pattern)
        return cmd
    if action == "upstream_noise_off":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "noise", uid, "off"]
    if action == "upstream_ws":
        uid = a.get("id", "")
        if not RE_ID.match(uid): return None
        return ["ratholenode", "upstream", "ws", uid]
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
    # ---- adaptive filtering (Task 8) ----
    if action == "adaptive_off":    return ["ratholenode", "adaptive", "off"]
    if action == "adaptive_status": return ["ratholenode", "adaptive", "status"]
    if action == "adaptive_test":   return ["ratholenode", "adaptive", "test", "--json"]
    if action == "adaptive_run":    return ["ratholenode", "adaptive", "run"]
    if action == "adaptive_on":
        iv = str(a.get("interval", "30") or "30")
        fa = str(a.get("failures",  "3")  or "3")
        re = str(a.get("recoveries","5")  or "5")
        if not RE_PORT.match(iv) or not RE_PORT.match(fa) or not RE_PORT.match(re): return None
        return ["ratholenode", "adaptive", "on", "--interval", iv, "--failures", fa, "--recoveries", re]
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
    "backhaul_on", "backhaul_off", "backhaul_node_on", "backhaul_node_off",
    "proxy_add", "proxy_rm",

    "backup", "enable", "regen_full", "regen",
    # node
    "add_svc", "rm_svc", "kcp_on", "kcp_off", "apply", "restart", "set_server",
    "upstream_add", "upstream_add_svc", "upstream_rm", "upstream_rm_svc",
    "upstream_kcp_on", "upstream_kcp_off", "upstream_apply", "upstream_restart",
    "upstream_plain_on", "upstream_plain_off",
    "upstream_noise_on", "upstream_noise_off", "upstream_ws",

    "watchdog_on", "watchdog_off", "migrate", "deploy",
    "adaptive_on", "adaptive_off", "adaptive_run",

}

def build_cmd(role, action, args):
    return build_iran_cmd(action, args) if role == "iran" else build_node_cmd(action, args)
