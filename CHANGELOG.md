# Changelog

Hameye taghirat-e ghabel-e tavajoh-e in project inja sabt mishavad.
Format bar asas-e [Keep a Changelog](https://keepachangelog.com/) va versioning bar asas-e [SemVer](https://semver.org/).

Ghabl az har release: bakhsh-e **[Unreleased]** ra be `[X.Y.Z] - YYYY-MM-DD` taghir bede,
yek bakhsh-e Unreleased-e khali-ye jadid bala-ye an bezar, baad tag `vX.Y.Z` ra push kon —
release.yml hamin bakhsh ra be onvan-e title/body-e GitHub Release montasher mikonad.

## [Unreleased]

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
