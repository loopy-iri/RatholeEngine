# RatholeEngine Core Hardening and Adaptive Filtering Design

**Tarikh:** 2026-07-22
**Release-e hadaf:** `v1.5.0`
**Vaziat:** tarh-e taeed-shode baraye bazbini-ye nahayi

## Hadaf

In taghirat do moshkel-e sabt-shode dar log-e node ra hal mikonad va yek laye-ye ekhtiari baraye tashkhis va jabeja-yi-ye khodkar bein masirhaye tunnel ezafe mikonad:

1. rathole dar timeout-e handshake-e WebSocket panic/abort nakonad va be halghe-ye retry bargardad.
2. watcher hich-gah `client.toml`/`server.toml`-e nime-neveshte ya khali ra parse nakonad.
3. node betavanad filter/shaping-e DNS, TCP, TLS, WebSocket va KCP ra tashkhis dahad.
4. adaptive mode ba dastoor-e sarikh roshan/khamosh shavad va bein masirhaye amn failover konad.
5. control channel dar barabar active probe ba yek masir-e makhfi va fake-site-e fali poshide bemanad.

Taghir-e path/token/service-e karbaran dar in release mamnoo ast. TLS hamchenan faghat dar nginx terminate mishavad.

## Rishe-ye moshkel-e fali

### Panic-e WebSocket

Dar `rathole v0.5.0` va `main`-e fali-ye upstream, natije-ye `client_async_with_config(...)` ba `expect("failed to connect")` baz mishavad. Timeout ya reset-e handshake panic misazad, process ba `SIGABRT` khateme miyabad va systemd dobare an ra start mikonad. In raftaar baraye yek link-e filter/shaping-shode ghalat ast; khata-ye network bayad yek `Result::Err`-e adi bashad ta retry-e client edame peyda konad.

### Config-e nime-neveshte

Manager temp file ra kamel misazad, ama ba `cat temp > live` file-e live ra aval truncate va baad por mikonad. Watcher parent directory ra mibinad va momken ast bein truncate va write file ra bekhanad. Log-e peyvast daghighan `Neither of [server] or [client] is defined` ra dar hamin panjere neshan midahad.

Rename-e sade in panjere ra mibandad ama inode ra avaz mikonad. Baraye hefz-e invariant-e hot-reload, core va manager az yek sidecar lock-e moshtarak estefade mikonand: writer hengam-e truncate/write exclusive lock migirad va watcher ghabl az read shared lock migirad. Watcher ham event-ha ra debounce mikonad va parse-e namovafagh-e movaghat ra ba taakhir-e mahdood retry mikonad. Dar natije inode hefz va read az did-e core atomic mishavad.

## Gozine-haye barresi-shode

### 1. Faghat tashkhis va hoshdar

Kamtarin taghir ra darad, ama dar qati-e vaghei recovery khodkar nadarad. Ba darkhast-e failover-e khodkar sazgar nist.

### 2. Adaptive-e amn rooye server-e asli — entekhab-shode

`WS/TLS`، `KCP` va dar sorat-e ejaze-ye sarikh `plain` hame be haman rathole server va haman service/token vasl mishavand. Node mitavanad bedoon taghir-e state-e panel carrier ra avaz konad. `Noise` dar instance/config-e joda ast; dar in release monitor va manual-emergency mimanad ta failover-e khodkar be migration-e do-tarafe va bind-port-e movazi niyaz nadashte bashad.

### 3. Chand instance-ye garm baraye hame-ye carrier-ha

Failover-e Noise ra ham khodkar mikonad, ama baraye har node port/service-e movazi, selector-e nginx va hamahang-sazi-ye state-e do-tarafe lazem darad. Risk va complexity-e an baraye release-e raf-e bug monaseb nist.

## Patch va sakht-e core

Core az yek commit-e sabt-shode va pin-shode-ye `rathole-org/rathole` sakhte mishavad; build hich-gah az branch/tag-e motaghayyer source nemigirad. Patch-ha dar repo negahdari mishavand va shamel in mavared hastand:

- tabdil `expect("failed to connect")` be propagation-e khata ba context, ta client retry konad;
- afzoodan `path`-e optional be `WebsocketConfig` ba default `/` baraye backward compatibility;
- validate kardan path (`/`-prefixed, bedoon newline/control character) va estefade az an dar URL-e handshake-e client;
- lock/debounce/retry-e watcher baraye khanesh-e config-e live;
- test-e Rust baraye handshake failure (bedoon panic), default/custom path, path-e namotabar va config read hamzaman ba writer.

Version-e binary `0.5.1-ratholeengine.1` khahad bood ta az upstream `0.5.0` ghabele tashkhis bashad. Workflow-e release do target ra misazad:

- `x86_64-unknown-linux-gnu`
- `aarch64-unknown-linux-musl`

Har asset SHA-256 darad. Release workflow source commit, patch, Cargo lockfile va checksum-e output ra sabt mikonad. Installer faghat binary-i ra mipazirad ke checksum-e an ba manifest-e dakhel bundle yeksan bashad.

## Tozi va rollback-e core

Binary-ha ghabl az `package.sh` dar bundle gharar migirand. `install-panel.sh` va `install-node.sh` bar asas `uname -m` binary-e sahih ra entekhab mikonand. `update.sh` digar core ra az snapshot hazf nemikonad:

1. binary-e fali, version va checksum dar snapshot zakhire mishavad;
2. binary-e jadid dar path-e temp verify mishavad;
3. replace ba mode `0755` anjam mishavad;
4. `rathole --version` va parse-e config ghabl az restart check mishavad;
5. health-check-e role anjam mishavad؛ dar shekast, binary va config-ha ba ham rollback mishavand.

Override-e `RATHOLE_VERSION=v0.5.0` baraye nasb-e upstream-e rasmi hefz mishavad, ama default-e release core-e patch-shode-ye bundle ast. Panel va node bayad haman build-id/checksum ra dashte bashand; mismatch dar `version` va hub ba badge-e khata namayesh dade mishavad.

## Control path-e makhfi va anti-probe

Panel dar init yek `control_path`-e random ba entropy-ye kafi misazad (mesal: `/_rh/<hex-32>`). In meghdar state ast va az haman masir-e state → regenerate → hot-reload modiriyat mishavad.

- Nginx faghat `Upgrade: websocket` rooye `control_path` ra be control port mifrestad.
- `/` va har path-e nashenas, hatta ba Upgrade, be fake site miravad.
- Data path-haye karbar (`/<node>`) bedoon taghir mimanand.
- Client core `path = "..."` ra dar handshake mifrestad.
- Dastoor-e nasb node va hub control path ra be node montaghel mikonand.
- `ratholenode show` path ra mask mikonad va file-haye state mode `0600` darand.

Path secret jaye token-e rathole ra nemigirad؛ yek laye-ye defense-in-depth baraye kam-kardan-e fingerprint va active probing ast. Rotation-e path yek operation-e coordinated ast: panel aval path-e ghadim va jadid ra baraye yek grace window mipazirad, node-ha update mishavand, sepas path-e ghadim hazf mishavad.

## Tashkhis-e filtering

`ratholenode adaptive test [--json]` probe-ha ra az kam-hazine be por-hazine ejra mikonad:

1. **DNS:** resolve-e domain va, agar `EXPECTED_IP` tanzim shode, moghayese ba IP-e entezari.
2. **TCP:** connect-e mahdood-be-zaman be domain/IP va port-e hadaf.
3. **TLS/SNI:** handshake ba SNI-e domain va verify-e certificate chain/name.
4. **WS/TLS:** handshake-e vaghei be control path va entezar-e `HTTP 101`.
5. **KCP:** handshake-e WebSocket az local kcptun listener; `101` yani UDP/FEC + server control end-to-end salem ast.
6. **Plain:** faghat agar config va `ALLOW_INSECURE=1` bashad, handshake-e `101` rooye listener-e plain.
7. **Noise readiness:** faal-boodan-e service/server, vojood-e key va reachability-e TCP; failover-e khodkar nadarad.

Natije ba reason code-haye paydar sabt mishavad: `dns_failed`, `dns_mismatch`, `tcp_timeout`, `tls_failed`, `ws_rejected`, `ws_timeout`, `kcp_unreachable`, `healthy`. State shamel timestamp, latency, consecutive success/failure, carrier-e fali va akharin switch ast. File-e state ba mode `0600` neveshte va output-e JSON-e sanitize-shode baraye hub tolid mishavad؛ secret, token va key hich-gah dar JSON/log nemiayad.

## Adaptive controller

Dastoor-ha:

```text
ratholenode adaptive on [--interval 30] [--failures 3] [--recoveries 5]
ratholenode adaptive off
ratholenode adaptive status [--json]
ratholenode adaptive test [--json]
```

`on` systemd timer ra faal mikonad. `off` timer ra khamosh mikonad va carrier-e fali ra dast nemizanad. Tasmim-giri:

- tartib-e pishfarz: `ws` sepas `kcp`;
- `plain` faghat ba `--allow-insecure`/`ALLOW_INSECURE=1` varede candidate-ha mishavad;
- switch pas az 3 failure-e motavali va salem-boodan-e candidate anjam mishavad;
- bazgasht be carrier-e ba olaviat-e balatar pas az 5 success-e motavali va cooldown-e 5 daghighe;
- har switch config-e kamel ra dar temp misazad, validate mikonad, ba lock commit mikonad va service ra controlled restart mikonad;
- agar candidate baad az switch healthy nashod, config/carrier-e ghabli fooran rollback mishavad;
- lock-e controller az ejra-ye hamzaman-e timer, dastoor-e dasti va hub jelogiri mikonad.

KCP bayad az ghabl ba remote/key/profile provision shode bashad. Dar halat-e `ws`, kcptun mitavanad roshan bemanad ta probe va failover bedoon startup delay anjam shavad. Plain be dalil nabood-e ramznegari default va auto-enable nemishavad.

## Hub va API

Action-haye jadid-e hub faghat be argv-haye allow-listed map mishavand:

- `adaptive_on` ba interval/failures/recoveries-e regex-validated;
- `adaptive_off`;
- `adaptive_status`;
- `adaptive_test`.

Hub rohe kart-e node namayesh midahad:

- adaptive on/off;
- carrier-e fali;
- classification-e akharin probe;
- latency va consecutive failures;
- akharin switch va cooldown;
- amade-boodan-e WS/KCP/plain/Noise.

UI dokme-ye roshan/khamosh, test-e alan va detail-e tashkhis darad. Hich shell string-e raw az browser be server nemiravad.

## Error handling va safety

- Probe timeout-ha mahdood va process-ha cleanup mishavand.
- DNS mismatch tanha classification ast; bedoon probe-e carrier be tanhaii sabab-e switch nemishavad.
- Yek failure-e lahze-i hich switch-i ijad nemikonad.
- Agar hich candidate-i salem nist, carrier-e fali hefz, state `degraded` va log rate-limited mishavad.
- Adaptive hich-gah `plain` ra bedoon ejaze-ye sarikh entekhab nemikonad.
- Taghir-e core/config dar update zir snapshot va auto-rollback ast.
- Core asset-e bedoon checksum, architecture-e nashenas ya build-id-e mismatch nasb nemishavad.
- `control_path`, token, Noise key va KCP key dar log/Hub mask mishavand.

## Test strategy

### Core (Rust)

- unit test-e error propagation be jaye panic;
- unit test-e default/custom/invalid WebSocket path;
- watcher test ba writer-e lock-shode va event-haye motavali;
- config compatibility ba example-haye upstream;
- build va smoke test rooye har do architecture.

### Manager (Bash/Python stdlib)

- harness-e node ba stub-haye `systemctl`, `openssl`, DNS/TCP va handshake;
- RED/GREEN baraye log-e peyvast: timeout nabayad process ra abort konad;
- test-e config read-safe ke hich snapshot-e khali/partial be watcher nemidahad;
- classification-e har reason code;
- threshold, hysteresis, cooldown, rollback va `off`;
- test-e `plain` ke bedoon allow-insecure candidate nist;
- nginx config test: secret path → control, `/`/path-e ghalat → fake site, data path-ha bedoon taghir;
- hub command-builder test baraye validation va argv isolation;
- `bash -n`, shellcheck error-severity, `py_compile`, `nginx -t` ba config-e sandbox, package content/checksum audit.

### Release verification

- install/update-e sandbox baraye panel va node;
- upgrade az `v1.4.8` ba core `v0.5.0` be `v1.5.0`;
- rollback-e ejbari ba health-check-e namovafagh va tasdiq-e bazgasht-e binary;
- extraction va `--version`-e har asset;
- SHA-256 va bundle inventory;
- GitHub Actions CI va release job sabz ghabl az elam-e release.

## Documentation

`CHANGELOG.md`, README-e do-zabane, `docs/README.fa.md`, manual-haye EN/FA, transport modes va hub docs update mishavand. Dastoor-e roshan/khamosh, maani-ye classification-ha, risk-e plain va recovery-e dasti mostanad mishavad. Diagram faghat agar rabete-ye detector/controller/carrier-ha bedoon an mobham bemanad update mishavad va style-e fali-ye asset-ha hefz mishavad.

## Kharej az dame-ye v1.5.0

- failover-e khodkar be Noise;
- taghir-e DNS ya routing-e karbaran bein chand Iran server;
- domain fronting ya vabastegi be CDN-e shakhs-e sevom;
- random-sazi-ye protocol payload ba hadaf-e shekl-dahi-ye traffic;
- dastkari-ye Xray/VLESS config-e karbar.

In mavared mitavanand baad az telemetry-e release-e adaptive dar tarh-e joda barresi shavand.
