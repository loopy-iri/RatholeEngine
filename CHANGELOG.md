# Changelog

Hameye taghirat-e ghabel-e tavajoh-e in project inja sabt mishavad.
Format bar asas-e [Keep a Changelog](https://keepachangelog.com/) va versioning bar asas-e [SemVer](https://semver.org/).

Ghabl az har release: bakhsh-e **[Unreleased]** ra be `[X.Y.Z] - YYYY-MM-DD` taghir bede,
yek bakhsh-e Unreleased-e khali-ye jadid bala-ye an bezar, baad tag `vX.Y.Z` ra push kon —
release.yml hamin bakhsh ra be onvan-e title/body-e GitHub Release montasher mikonad.

## [Unreleased]

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

[Unreleased]: https://github.com/loopy-iri/RatholeEngine/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/loopy-iri/RatholeEngine/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/loopy-iri/RatholeEngine/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/loopy-iri/RatholeEngine/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/loopy-iri/RatholeEngine/releases/tag/v1.0.0
