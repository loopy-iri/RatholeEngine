# Changelog

Hameye taghirat-e ghabel-e tavajoh-e in project inja sabt mishavad.
Format bar asas-e [Keep a Changelog](https://keepachangelog.com/) va versioning bar asas-e [SemVer](https://semver.org/).

Ghabl az har release: bakhsh-e **[Unreleased]** ra be `[X.Y.Z] - YYYY-MM-DD` taghir bede,
yek bakhsh-e Unreleased-e khali-ye jadid bala-ye an bezar, baad tag `vX.Y.Z` ra push kon —
release.yml hamin bakhsh ra be onvan-e title/body-e GitHub Release montasher mikonad.

## [Unreleased]

## [1.6.2] - 2026-07-30

upstream-ha hala shahrvand-e daraje-yek hastand (hamel + log + status mesl-e tunnel-e asli)،
va rishe-ye timeout-e gRPC rooye backhaul-e chand-mashini basteh shod.

### Added
- **hamel-e per-upstream (parity ba tunnel-e asli):** har upstream hala `ws|kcp|plain|noise`-e
  khodash ra darad — `ratholenode upstream <plain|noise|ws> <id> ...` + select dar hub (mesl-e
  select-e tunnel-e asli). `gen_up_client` az ghabl in halat-ha ra mishenakht؛ dastur/UI-yash nabood.
- **didan-e log/status-e upstream:** `ratholenode upstream logs <id> [n]` (ham `rathole-client@<id>`
  ham `rathole-kcp-up-<id>`) va `ratholenode upstream status <id>` + dokme dar hub.
- **log-e backhaul:** `ratholectl backhaul logs` (Iran) va `ratholenode backhaul logs` (node)
  + dokme-haye status/log dar hub baraye har do taraf.

- **namayesh-e mahdudiat-e backhaul dar hub:** bakhsh-e «hamel-haye dar dastras» hala node-haye
  rooye backhaul ra list mikonad va agar inbound-e tekrari bashad hoshdar-e ghermez midahad.
- **hoshdar ghabl az afzoodan-e avalin node-e SNI/game:** afzoodan-e an port 443 ra be stream/L4
  switch mikonad va vhost-e L7 be port-e dakheli miravad — hala tedad-e node-haye aadi-ye
  tahtetasir ra neshan midahad va taeed migirad.

### Fixed
- **gard-e backhaul-e chand-mashini (rishe-ye timeout-e gRPC):** backhaul 1:1 ast — YEK server،
  YEK token-e sarasari va YEK majmoue-ye `ports`. gozashtan-e DO mashin-e kharej rooye backhaul
  anha ra dar yek namespace jam mikonad: har do ba haman token vasl mishavand، sar-e channel-e
  kontrol daava mikonand va **HAR DO** ghat mishavand (na faghat dovomi). neshane-ash
  `inbound_port`-e tekrari beyn-e node-haye backhaul ast (masalan se node rooye 62050 = se
  mashin ke har kodam Pasargad ra anja darand)، va gRPC avvalin ghorbani ast chon
  handshake/cert-esh ba peer-e eshtebah jour darnemiayad.
  hala `backhaul node <name> on` GHABL az taghir-e state jelo-ye tadakhol ra migirad (die)،
  `doctor` vaziat-e mojood ra gozaresh mikonad va hub an ra neshan midahad.
- `doctor` masir-e VAGHEI-ye control (`control_path`-e makhfi) ra ba `--http1.1` probe mikonad؛
  ghablan faghat `/` ra mizad va zir-e HTTP/2 header-e Upgrade hazf mishod → **200-e doroughi**
  dar hali ke tunnel salem/kharab bood.

## [1.6.1] - 2026-07-30

behbood-e panel-e hub: namayesh-e DAGHIGH-e mode-e har node + kontrol-e per-node samt-e Iran.
in release reftar-e tunnel ra avaz nemikonad — faghat namayesh va rahati-ye modiriat ra dorost mikonad
(dar edame-ye fix-e backhaul-e 1.6.0).

### Added
- **select-e per-node-e hamel rooye safhe-ye Iran:** kenar-e har node dar jadval yek `<select>`
  (ws/noise/backhaul) ezafe shod — daghighan mesl-e select-e safhe-ye node. ta hala samt-e Iran
  faghat dokme-haye on/off-e SARASARI dasht va mode-e har node ja-be-ja (badge-e noise, dokme-ye
  backhaul-e sarasari) bood. hala har node az yek ja qabel-e switch ast (`noise_node_*`/`backhaul_node_*`).
- **badge-e mode-e vahed (`iranNodeMode`)**: yek manba-e vahed-e haghighat mode-e har node ra ba
  olaviat-e qati mohasebe mikonad — `game (SNI) > backhaul > noise > ws` — va hameye namayesh-ha
  (jadval + badge) az hamin mikhanand، pas digar «nAmnazm» be nazar nemirasad.
- **dokme-ye «tanzim-e mojadad (regen)»** dar bakhsh-e hamel-haye Iran: baad az taghir-e mode-e
  node-ha config az state bazsazi va hot-reload mishavad (bedoon-e oftadan-e tunnel-haye faal).
- sotoon-haye `TRANSPORT` va `SNI` be khorooji-ye `ratholectl ls` ezafe shod ta hub betavanad
  mode-e daghigh-e har node ra bekhanad (badge-e `b-backhaul`/`b-game` + kelid-haye i18n).

### Changed
- `MANAGER_VERSION` az `1.6.0` be `1.6.1`.

### Fixed
- `parse_iran_ls` (hub) sotoon-haye jadid-e transport/sni ra migirad va ba khorooji-ye
  `ratholectl ls`-e ghadimi (bedoon-e in do sotoon) ham sazgar mimanad — test-e vahed baraye har do format.

## [1.6.0] - 2026-07-30

release-e paydar (stable). channel-e beta (v1.6.0-beta.1..7) be onvan-e 1.6.0 promote shod.
in release DGHIGHAN moshkeli ra mibandad ke server-haye beta ra downgrade mikard va backhaul ra kharab.

### Fixed
- **downgrade-e mokharreb az dokme-ye «apdit»-e hub:** `deploy_to_server` (hub.py) koorkoorane `releases/latest/download/install.sh` ra migereft va hich `RATHOLE_RELEASE` pass nemidad. chon hameye `v1.6.0-beta.*` dar GitHub **prerelease** hastand، `releases/latest` be **v1.5.1** (ghabl az backhaul) resolve mishod — pas har server-e beta ba yek click be v1.5.1 downgrade mishod، `ratholectl`-e ghadimi state-e node-haye `.transport=backhaul` ra namishenakht va `gen_server_toml` port-e anha ra dobare bind mikard → **tunnel-e backhaul az beyn miraft**. hala `deploy_to_server` channel-agah ast: `update_channel` (stable|beta، pishfarz stable) ra az config mikhanad va baraye beta tag-e prerelease ra rooye khode server az `releases.atom` (mirror-agah، hamsan-e resolve_beta_tag) peyda karde va `RATHOLE_RELEASE` pass midahad.
- **gard-e zed-e downgrade dar `update.sh`:** ghabl az har taghir، `MANAGER_VERSION`-e baste-ye jadid ba noskhe-ye nasb-shode moghayese mishavad (semver-agah: `1.6.0 > 1.6.0-beta.7 > 1.5.1`). agar baste ghadimi-tar bashad، update **rad mishavad** va hich taghiri anjam nemidahad — magar `--allow-downgrade` (ya `RATHOLE_ALLOW_DOWNGRADE=1`). in class-e khata ra az HAR masir (hub/CLI/curl) baraye hamishe mibandad.

### Changed
- `MANAGER_VERSION` az `1.6.0-beta.7` be `1.6.0` (stable).
- config-e hub yek kelid-e jadid-e `update_channel` (stable|beta) darad؛ `RE_CHAN` an ra etebarsanji mikonad.
- UI-e hub: bakhsh-e «masir-ha (path)» — kelid-haye i18n-e fa/en baraye masir-e subscription va masir-e panel-e hub.

## [1.6.0-beta.5] - 2026-07-27

## [1.6.0-beta.1] - 2026-07-26

### Added
- **core-e backhaul (SMUX) — carrier-e panjom:** `ratholectl backhaul <on [port] [transport] [profile]|off|node <name> on|off|status|show>` va `ratholenode backhaul <on <domain> <token> [transport] [profile]|off|status>`. yek core-e joda-ye Go (`Musixal/Backhaul`) kenar-e rathole ke chand connection-e karbar ra ba SMUX rooye yek stream mux mikonad — baraye link-haye sholoogh/lossy ke rathole mux nadarad. `backhaul-server` rooye `127.0.0.1:<backhaul_port>` (pishfarz 3080) gush midahad va nginx masirhaye **hardcode-shode** `/channel` (control) va `/tunnel` (data) ra rooye haman 443 be an proxy mikonad — pas **tak-port/tak-domain hefz mishavad**.
- **`common.sh`:** `install_backhaul` (download ba halqe-ye mirror-e ghproxy), `backhaul_mux_profile` (balanced/lossy/aggressive), `backhaul_client_transport` (naghshe-ye server→client).
- **kanal-e beta dar updater:** `ratholectl update beta` / `ratholenode update beta` va `RATHOLE_RELEASE=beta` dar `install.sh`. chon masir-e `releases/latest/download` pre-release ha ra NADIDE migirad, `resolve_beta_tag()` akharin tag-e beta ra az `releases.atom` (az tarigh-e mirror-haye ghproxy، bedoon niaz be jq) peyda mikonad.
- **hub (hub.py):** action-haye `backhaul_on/off/node_on/node_off/status/show` ba argv-list va etebarsanji-ye regex (`RE_BH_SRV`, `RE_BH_CLI`, `RE_BH_TOK`), endpoint-e `GET /api/servers/<name>/backhaulconnect` baraye autofill-e domain+token, i18n-e fa/en va dokme-haye UI.
- **`ratholectl status`:** port va service-e backhaul dar khoruji-ye adami va `--json`; sotun-e `TRANSPORT` dar jadval-e node-ha.
- **adaptive (ratholenode):** case-e `backhaul` dar `adaptive_run_probe` — probe be `/channel` ba header-e `Authorization: Bearer <token>` (bedoon token backhaul ba 401 rad mikonad va failover-e eshtebah rokh midahad). `adaptive_probe_ws_tls` yek parameter-e ekhtiari-ye header gereft (sazgar ba ghabl).
- **release.yml:** tag-haye `-beta`/`-rc`/`-alpha` khodkar be onvan-e **prerelease** montasher mishavand ta `releases/latest/download` hamchenan be noskhe-ye stable eshare konad.

### Fixed
- **tadakhol-e bind:** node-e backhaul hamzaman dar `server.toml` va `ports`-e backhaul mimand va `rathole-server` va `backhaul-server` har do `127.0.0.1:<node.port>` ra bind mikardand (dovomi bala nemiamad). `backhaul` hala yek meghdar-e `.transport` ast (mesl-e `noise`) va `gen_server_toml` node-haye `noise|backhaul` ra rad mikonad. samt-e node ham `rathole-client` motevaghef va disable mishavad.
- **`ports` ba format-e ghalat:** `"127.0.0.1:<port>"` be `"127.0.0.1:<iran_port>=<node_inbound_port>"` eslah shod (service-e `_api` ham pushesh dade shod) — vagarna be port-e eshtebah rooye node forward mishod.
- **transport-e do taraf:** server hala faghat variant-e bedoon-e TLS (`ws`/`wsmux`) va client faghat variant-e TLS-dar (`wss`/`wssmux`) ra mipazirad — haman invariant-e rathole (TLS faghat rooye nginx). ghablan yek transport be har do taraf dade mishod ke dar har entekhabi yek taraf ra mishekast.
- **unit-e systemd:** `ExecStart` config ra be sooratِ positional pass midad vali backhaul `-c <path>` mikhahad — service ba `FATAL: Usage: ... -c` mimord. (dar tst ba binary-e vagheai peyda shod.)
- **`ratholenode backhaul` ghabl-e seda zadan nabud:** be `main()` va `usage()` vasl shod؛ `systemctl enable` masir-e file ra be jaye naam-e service pass midad.
- **`BH_PROFILE`** rooye node zakhire nemishod (hamishe `balanced` migereft) — hala `env_set` mishavad va argument migirad.
- **`noise off`** ba `del(.nodes[].transport)` transport-e node-haye backhaul ra ham pak mikard؛ hala entekhabi ast. gard-haye motaghabel bein `noise node on` va `backhaul node on` ezafe shod.
- **CRLF dar `ports`:** jq-e vindozi CRLF midahad va `\r` daakhel-e array-e `ports` TOML ra namotabar mikard.

## [1.5.0] - 2026-07-24

### Added
- **adaptive filtering (ratholenode):** `ratholenode adaptive on|off|status|test|run` — controller-e failover-e khodkar bein carrier-haye WS/KCP. probe-haye bounded `adaptive_probe_tcp`, `adaptive_probe_ws_tls`, `adaptive_probe_ws_plain`, `adaptive_probe_kcp` ba classification-e `dns_failed / tcp_timeout / tls_failed / ws_rejected / healthy` va khoruji JSON sanitize-shode (`/etc/rathole/adaptive-state.json`, mode 0600). threshold/hysteresis/cooldown ba `ADAPTIVE_FAILURES`, `ADAPTIVE_RECOVERIES`, `ADAPTIVE_COOLDOWN`. plain faghat ba `ALLOW_INSECURE=1` candidate mishavad. systemd timer/oneshot (`rathole-adaptive.service`, `rathole-adaptive.timer`).
- **secret WebSocket control path (ratholectl/ratholenode):** masir-e control-e WebSocket az `/` be `/_rh/<32 hex>` montaqel shod. `ratholectl control-path show|rotate` + `ensure_control_path()`. nginx location-e dedicate baraye masir-e maghfi; masirha-ye namotabar fake/data behaviour ra hefz mikonand. `WS_PATH` dar `node.env` va `client.toml` (`path = "..."` bar asas-e patch-e core) zakhire mishavad.
- **core-install.sh:** nasb-e binary-e patched ba verify-e SHA256SUMS + ejra-ye `--version` (barresi `0.5.1-ratholeengine.1`). `install-panel.sh` va `install-node.sh` avval core-install ra talash mikonand; fallback be download-e upstream.
- **hub API (hub.py):** `build_node_cmd` action-haye `adaptive_on|off|status|test|run` ba ARGV-only (bedoon interpolation). `parse_adaptive_state()` JSON-e khoruji ra sanitize mikonad — tanha field-haye shenakhte-shode, hich secret leak nemikonad. `adaptive_on`/`adaptive_off`/`adaptive_run` be `WRITE_ACTIONS` ezafe shod.
- **release workflow (release.yml):** do-stage build — `build-core` matrix (x86_64 + aarch64, `core/build.sh`) + artifact upload/download + `sha256sum` generation + `RATHOLE_REQUIRE_CORE=1` enforcement dar `package.sh` + publish.
- **package.sh:** `RATHOLE_REQUIRE_CORE=1` hengami ke core binary-ha vojood nadarand fail mikonad; dar halat-e ensha-garan (developer) faqat warn mikonad.
- **install-node.sh:** `--ws-path` argument; `WS_PATH` dar `node.env` zakhire mishavad.

### Fixed
- **rth_commit_config (common.sh):** hameye write-haye live config az طریق `flock -x` goozar mikonand ta reader ha file-e khali nabinad (inode hefz mishavad, hot-reload kamel ast).
- **ratholenode gen_client:** agar services.conf khali bashad `[client.services]` table-e khali chap mishavad (config-e valid baraye rathole).

### Tests
- `tests/test_node_config.sh`: regression baraye config-e khali + `rth_commit_config` lock
- `tests/test_nginx_control_path.sh`: barresi nginx routing baraye masir-e maghfi
- `tests/test_adaptive.sh`: probe + controller threshold/cooldown/plain-guard
- `tests/test_hub.py`: allow-list + injection prevention + `parse_adaptive_state`
- `tests/test_release_bundle.sh`: core-install checksum, tamper rejection, workflow structure

## [1.4.8] - 2026-07-19

### Fixed
- **hub/ratholenode — «tanzim tunnel asli» ba etela'at-e ghalat + khata-ye node.env:** do bug-e be-ham-marbut dar masir-e vasl-e node be server-e Iran raf shod. (1) **domain be jaye host/IP:** dar halat-e pishfarz (ws+TLS) `ratholenode` az `SERVER` ham `remote_addr` va ham `hostname`/SNI ra misazad — pas ferestadan-e `host:443` az inventory (ke momken ast IP ya adres-e SSH bashad) baaes mishod SNI ba gvahi nakhand va tunnel bala nayad. hala hub domain-e vaghei ra az `ratholectl status --json` migirad (endpoint-e jadid `GET /api/servers/<iran>/mainconnect` + tabe-e moshtarak `iran_main_server()`)؛ ham dokme-ye «tanzim tunnel asli» va ham vasl-e khodkar hengam-e provision az domain estefade mikonand (ba fallback be host). (2) **node.env peyda nashod:** `ratholenode set SERVER …` rooye node-e taze-provision-shode (ke hanoz nasb-e kamel-e `--node` nashode) ba «node.env peyda nshd» die mikard؛ hala `cmd_set` fayl ra khodesh bootstrap mikonad (`env_set` ba `touch`+`chmod 600`) va faghat vaghti hadaghal yek service tarif shode `cmd_apply` ra seda mizanad (vagarna `SERVER` zakhire mishavad va baad az avalin `add-svc` tunnel sakhte mishavad)

## [1.4.7] - 2026-07-16

### Added
- **hub — dokme-ye «apdit-e hame» + progress bar + namayesh-e noskhe rooye har server:** dar dashboard dokme-ye **«apdit-e hame»** ezafe shod ke hameye serverha (Iran + node) ra **yeki-yeki (tartibi)** az tarigh-e `deploy` (=`install.sh --update` ba snapshot+rollback-e khodkar) apdit mikonad va yek **progress bar** + vaziat-e live-e har server (dar saf / dar hal apdit / ✓ / ✗ + noskhe-ye jadid) neshan midahad. hamchenin: mafhoom-e **noskhe** be system ezafe shod — `MANAGER_VERSION` dar `common.sh` + dstvr-e `version` (ratholectl/ratholenode) ke `manager_version=`/`rathole_version=` chap mikonad؛ hub in ra dar overview-e har server migirad va ba `latest_version` (az `MANAGER_VERSION`-e bundle) moghayese mikonad → badge-e **sabz** (be-ruz) ya **zard** (`vX → vY`, niaz be apdit) rooye kart/safhe-ye har server.

## [1.4.6] - 2026-07-16

### Added
- **hub — sim-keshi-ye node-e Iran be node/upstream ba yek dokme:** dar jadval-e node-haye har server-e Iran, dokme-ye jadid **«afzoodan be node»** ezafe shod. ba click yek modal baz mishavad ke list-e **hameye** node-haye kharej + upstream-hayeshan ra neshan midahad (anhayi ke tunnel-eshan be hamin server-e Iran vasl ast ba `✓` alamat-gozari va default entekhab mishavand). baad az entekhab-e maghsad, token/inbound-e vaghei-ye node-e Iran (ke dar `ls` mask ast) az `ratholectl show <node>` gerefte mishavad (endpoint-e jadid `GET /api/servers/<iran>/nodeconnect/<node>`) va rooye node-e maghsad be onvan service sabt mishavad (`add_svc` ya `upstream_add_svc`). hame ba regex etebarsanji va argv (bedoon interpolation).
- **ratholectl — dstvr-e nasb-e node be shekl-e curl yek-khatti:** baad az `ratholectl add <name> <inbound>` (va `ratholectl token <name>`) alaan **avval** dstvr-e amade-ye `curl -fsSL …/install.sh | sudo bash -s -- --node -- --server <panel>:443 --name … --token … --inbound-port …` chap mishavad (ba field-haye por-shode az state)، sps shekl-e mahalli-ye `install-node.sh`. agar domain khali bashad (halat IP-tunnel)، `--server` ba IP-e omomi (`detect_ip`) por mishavad. slug/ref az `RATHOLE_GH`/`RATHOLE_REF` (pishfarz `loopy-iri/RatholeEngine` + `main`). dar hub ham chon in khorooji chand-khatti-ye `add_node` dar `outModal` (ba dokme-ye copy) neshan dade mishavad، mostaghim ghabel-e kopy ast

### Fixed
- **hub — node bedoon tunnel-e asli (`?`):** vaghti node az tarigh-e hub nasb/provision mishod, server-e Iran be onvan tunnel-e **main** set nemishod va dar safhe-ye node khali/`?` mimond. hala: (1) form-e «nasb khodkar» yek select-e «server Iran» darad ke baad az deploy khodkar `ratholenode set SERVER <iran>:443` ra ejra mikonad (agar faghat yek server Iran bashad، hamon entekhab mishavad)؛ (2) dar safhe-ye har node dokme-ye jadid **«tanzim tunnel asli»** ejaze midahad node-haye mojood ra be yek server Iran vasl koni. amal-e `set_server` dar hub ba regex etebarsanji va be sorat-e argv ejra mishavad (bedoon interpolation)

## [1.4.5] - 2026-07-16

### Added
- **ratholectl `status [--json]`:** dashboard-e kamel-e vaziat (mesl-e panel-e sabaskripshn-e VPN) — domain, IP-e omomi, transport-e faal، vaziat-e service-ha (rathole-server/nginx/noise + salamat-e config-e nginx)، hameye port-ha ba tozih (443/kontrol/fake/sub/internal/plain/direct/hub/noise)، vaziat va enghza-ye gvahi (+ hoshdar-e self-signed)، va jadval-e node-ha ba URL-e karbar. `--json` khorooji-ye machine-readable baraye hub
- **ratholectl `paths`:** namayesh-e masir-e hameye config-ha va file-ha (state.json، server.toml، nginx conf، cert، systemd unit، binary، common.sh) ba alamat-e ✓/✗ vojood
- **hub — dokme-ye «vaziat» (Status):** dar safhe-ye har server-e Iran، dokme-ye Status ke `ratholectl status --json` ra migirad va be sorat-e dashboard-e ziba (port-ha/service-ha/gvahi/node-ha) render mikonad (fa/en)

### Changed
- **ratholectl `hub on [port]`:** dige faghat nginx ra tanzim nemikonad — bar-e **aval** hub ra khodkar **nasb** mikonad (`install-hub.sh` ba `HUB_PORT` dorost؛ ghablan `hub on 2053` faghat nginx ra be 127.0.0.1:2053 point mikard dar hali ke hich servisi roo an port nabood → curl `Connection refused`). dafe-haye **baad** port-dadan yani taghyir-e vaghei-e port: `listen_port` dar `/etc/ratholehub/config.json` avaz + `systemctl restart ratholehub` + nginx hamgam. `hub on` bedoon port، port-e feli-ye config ra hefz mikonad
- **ratholectl `hub status`:** vaziat-e service `ratholehub` (faal/khamoosh/nasb-nashode) + listen_port ra ham neshan midahad va agar port-e nginx ba listen_port-e hub yeki nabashad hoshdar + dastoor-e dorost midahad
- **ratholectl `hub off`:** agar service ratholehub roshan bashad yadavari mikonad ke faghat az nginx hazf shode (service ra khamoosh nemikonad)

### Fixed
- **install-hub.sh:** prompt-e ramz-e panel az stdin mikhand → zir-e `curl|bash` ya ejra az `ratholectl hub on` shekast mikhord؛ hala tty-safe ast (`/dev/tty` fallback، hamsan-e `rth_read`). va vaghti az `ratholectl hub on` seda shavad (`RATHOLECTL_HUB_FROM_CTL=1`) dige khodesh `ratholectl hub on` ra dobare seda nemizanad (jelogiri az halghe/dobare-kari)

## [1.4.4] - 2026-07-15

### Fixed
- **ratholectl `gen_server_toml` / `gen_noise_server_toml`:** rathole v0.5.0 field-e `services` ra baraye `[server]` **ALZAMI** midanad. vaghti hich node-i ezafe nashode bood، `server.toml` hich `[server.services.*]`-i nadasht → rathole ba `missing field \`services\` for key \`server\`` crash mikard va `rathole-server` start nemishod (status=1/FAILURE، `nginx` rooye 443 salem bood vali tunnel bala nemiamad). hala vaghti service-i nist yek jadval-e khali-ye `[server.services]` neveshte mishavad (baraye har do transport-e websocket va noise) → server.toml-e khali ham motabar ast va rathole-server balafasele bala miayad
- **install-panel.sh — tashkhis-e tadakhol-e 443:** eskan-e `grep -rlE` file-haye backup mesl-e `rathole.conf.rathole-good.bak` ra ham migereft va hoshdar-e ghalat-e tadakhol midad، dar hali ke nginx faghat `conf.d/*.conf` va `sites-enabled/*` ra include mikonad (file-haye `.bak/.orig/.save/.disabled/~` load NEMISHAVAND). hala eskan mahdood be haman file-haye vaghean-include-shode ast va pasvand-haye backup rad mishavand
- **install-panel.sh — tashkhis-e start-e rathole:** ezafe shodan-e barresi-ye ejrapazir-boodan-e binary، tashkhis-e khorooji-ye khali، `pkill` khodkar vaghti port eshghal ast، va namayesh-e `systemctl status` + `journalctl`-e vaghei dar talash-e dovom

## [1.4.3] - 2026-07-15

### Fixed
- **ratholectl `obtain_cert` / game cert:** prompt-e aimil-e Let's Encrypt ham az stdin mikhand → zir-e `curl|bash`/bootstrap khali migereft va `aimil lazem ast` → certbot ejra nemishod → gvahi sakhte nemishod → `nginx -t` shekast (cert file nabood). hala az `rth_read` (tty) mikhanad va agar aimil khali bashad ba `--register-unsafely-without-email` edame midahad (be jaye die)
- **install-panel.sh:** vaghti `rathole-server` start nemishod، `journalctl` (dar halat-e auto-restart) khali bood va payam-e tashkhis mobham. hala binary mostaghim ba `timeout` ejra mishavad ta khata-ye vaghei (port eshghal / nasazgari-ye binary / server.toml) neshan dade shavad + rahnama-ye daghigh (`ss -ltnp`، `pkill`، `--version`) + yek talash-e dobare

## [1.4.2] - 2026-07-15

### Fixed
- **ratholectl init:** prompt-haye taamoli (`read`) az stdin mikhandand؛ zir-e `curl|bash` ya `exec` az bootstrap ke stdin pipe ast، `read` foran EOF migereft → `damnh alzami ast` va `init shekast khord`. hala helper-e `rth_read` az `/dev/tty` mikhanad (agar stdin terminal nabashad)؛ va agar hich tty nabashad payam-e vazeh mide ke ba `--domain ...` ejra kon

### Added
- **bootstrap.sh:** gozine-ye **hazf kamel (uninstall)** — menu (gozine 7) + flag-haye `--uninstall`/`--remove`/`--purge`. naghsh-haye nasb-shode (panel/node/hub) ra tashkhis mide va uninstaller-e har kodam ra ejra mikonad (hub mostaghim، chون uninstaller-e joda nadarad)؛ `--purge` binary-e rathole + config-e hub ra ham hazf mikonad
- **uninstall-panel.sh / uninstall-node.sh:** hazf-e `common.sh` (agar naghsh-e digari rooye hamin server nabashad) + config-e stream/SNI

## [1.4.1] - 2026-07-15

### Fixed
- **install-panel.sh:** dayrektori-ye `/usr/local/share/rathole` ghabl az kopi-ye `common.sh` sakhte nemishod → khata-ye `install: cannot create regular file '/usr/local/share/rathole/common.sh': No such file or directory` dar nasb-e panel-e Iran. hala `mkdir -p` ezafe shod (hamsan-e install-node.sh)

### Added
- **install-panel.sh:** tashkhis-e nasb-e ghabli/naghes + entekhab-e halat — **TAKMIL** (resume: ajza-ye gomshode kamel mishavand، vaziat hefz) ya **AZ-NO** (fresh: pak-sazi-ye config/state ba backup dar `/var/backups/rathole-manager/fresh-reset-*` va nasb-e kamel). flag-haye `--fresh`/`--repair`؛ zir-e `curl|bash` (bedoon terminal) pishfarz TAKMIL-e amn ast. gozaresh-e ✓/✗-e har joz (binary/ratholectl/common.sh/unit/state/server.toml/nginx) namayesh dade mishavad

## [1.4.0] - 2026-07-15

### Added
- **Hub:** namaye **konsol** dar safhe-ye masirha — vorodi-ha (ingress: TLS/443, direct-IP, plain, game/SNI) mostaghel az khorooji-ha (node-ha) namayesh dade mishavand; har node recipe-haye ettesal-e karbar (ws/443، direct، plain) ba dokme-ye copy darad
- **Hub:** parse-e `ratholectl plain status` / `direct status` dar overview (vaziat-e roshan/khamoosh + port + header)

### Changed
- **ratholectl:** helper-e `detect_ip` ba `--connect-timeout`/`--max-time`-e kootah baraye `api.ipify` (rooye Iran aksaran filter → curl hang mishod va SSH-e hub timeout midad)؛ fallback be `hostname -I` va override ba `RATHOLE_PUBLIC_IP`

## [1.3.0] - 2026-07-15

### Added
- **Hub:** namayesh-e vaziat-e vasl boodan-e node-ha (mesl `doctor`) rooye kart-haye dashboard va safhe-ye node
- **Hub:** panel-e vaziat-e khod-e server-e hub (uptime / load / RAM / disk / service-ha) rooye dashboard
- **Hub:** namaye jadval (table view) baraye naghshe-ye masirha + jabejaii-e dasti-e box-ha (drag)
- `CHANGELOG.md` + release note-haye khodkar az rooye an dar `release.yml`

### Changed
- `curl .../install.sh | sudo bash` **bedoon argument** rooye server-e nasb-shode hala be jaye nasb-e mojadad, khodkar **update** mikonad (tashkhis-e panel/node/hub)
- prompt-haye taamoli-e `bootstrap.sh` zir-e `curl | bash` ham kar mikonand (khandan az `/dev/tty`)

## [1.2.0] - 2026-07-15

### Changed
- **Hub:** bazsazi-e kamel-e UI — sidebar navigation, safhe-bandi (dashboard / server / routing / audit / settings), hash-router

### Added
- **Hub:** safhe-ye **naghshe-ye masirha** (routing graph SVG): user → Iran → node ba rang/style-e har transport (ws/kcp/noise/plain) va edge-e ghermez baraye node-e ghat

## [1.1.0] - 2026-07-15

### Added
- **Direct-IP header routing:** halat-e jadid `ratholectl direct` — masiryabi ba header (masalan `X-Cdn-Id`) rooye port-e sade bedoon TLS; nginx map + listener-e mostaghel; adgham ba block-e plain vaghti port yeki bashad
- **Hub:** toggle-e direct-IP dar kart-e server-e Iran + allow-list-e `direct_on/off/status/show` ba validation-e port/header
- Docs: mostanadat-e halat-e direct-IP + marz-e amniati (en/fa)

## [1.0.2] - 2026-07-14

### Fixed
- `update.sh`: `detect_roles` bayad rc=0 bargardanad — rooye server-haye bedoon-hub zir-e `set -e` bi-seda exit mishod

## [1.0.1] - 2026-07-14

### Added
- **Update az GitHub:** subcommand-e `update` baraye `ratholectl`/`ratholenode` + dokme-ye update-e hub — hamegi akharin Release ra (az tarigh-e mirror-haye ghproxy baraye dakhel-e Iran) migirand va ba snapshot + rollback-e khodkar emal mikonand

### Fixed
- **Hub:** namayesh-e ✓/✗ + rc baraye hameye action-ha؛ `common.sh` dar deploy hamrah mishavad

### Docs
- rahnamaye nasb-e dasti-e kamel (en + fa)، polish-e README (badge/TOC/RTL)

## [1.0.0] - 2026-07-14

### Added
- Import-e avalie-ye **RatholeEngine**: system-e reverse-tunnel-e chand-location ba rathole + nginx
  - `ratholectl` (panel-e Iran)، `ratholenode` (node-e khareji)، `ratholehub` (panel-e web-e markazi)
  - transport-ha: websocket+TLS / kcp / plain / noise / game-SNI
  - install/update/rollback: `install.sh`، `bootstrap.sh`، `update.sh` ba snapshot + health-check

[Unreleased]: https://github.com/loopy-iri/RatholeEngine/compare/v1.4.4...HEAD
[1.4.4]: https://github.com/loopy-iri/RatholeEngine/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/loopy-iri/RatholeEngine/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/loopy-iri/RatholeEngine/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/loopy-iri/RatholeEngine/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/loopy-iri/RatholeEngine/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/loopy-iri/RatholeEngine/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/loopy-iri/RatholeEngine/releases/tag/v1.0.0
