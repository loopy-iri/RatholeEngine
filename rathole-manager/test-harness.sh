#!/usr/bin/env bash
# harns tst mahalli baraye ratholectl bedoon niaz be root/systemd/nginx vaghai
set -uo pipefail

BASE="/mnt/d/MohammadHosein/projectsupertunnel/rathole-manager"
ROOT="$(mktemp -d)"
mkdir -p "$ROOT/bin" "$ROOT/etc/rathole" "$ROOT/etc/rathole-manager" "$ROOT/etc/nginx/conf.d"

# jq ra dar sandbox/bin gharar bdh va rooye PATH bgzar
cp "$BASE/jq-linux" "$ROOT/bin/jq"; chmod +x "$ROOT/bin/jq"
export PATH="$ROOT/bin:$PATH"
echo "sandbox: $ROOT ; jq: $(jq --version)"

# nskhh tst az ratholectl ba msirhai sandbox va bedoon kht akhr (main)
sed \
  -e "s#^STATE=.*#STATE=\"$ROOT/etc/rathole-manager/state.json\"#" \
  -e "s#^SERVER_TOML=.*#SERVER_TOML=\"$ROOT/etc/rathole/server.toml\"#" \
  -e "s#^NGINX_CONF=.*#NGINX_CONF=\"$ROOT/etc/nginx/conf.d/rathole.conf\"#" \
  -e '/^main "\$@"$/d' \
  -e 's/\r$//' \
  "$BASE/ratholectl" > "$ROOT/ratholectl.lib"

# wrapper: aval source, baad override tavabe sistmi, baad ejra
RUN="$ROOT/run.sh"
cat > "$RUN" <<EOF
#!/usr/bin/env bash
set -uo pipefail
export PATH="$ROOT/bin:\$PATH"
source "$ROOT/ratholectl.lib"
# khnsisazi tavabe niazmnd system vaghai
need_root(){ :; }
nginx(){ return 0; }
systemctl(){ return 0; }
"\$@"
EOF
chmod +x "$RUN"

line(){ echo "=============================================="; echo "$*"; echo "=============================================="; }

line "tst 1: init gheyre-taamoli"
# aval-e input: pasokh be prompt-e 'restore file' (khali = nasb-e tazh), sepas damnh va baghi.
printf '\nbtli.ir\n/tmp/fc.pem\n/tmp/key.pem\n\n2333\n8080\n2096\n1001\n7001\n' | bash "$RUN" cmd_init
echo "--- state.json ---"; jq . "$ROOT/etc/rathole-manager/state.json"

line "tst 2: afzoodan se node (usa01 ba api)"
bash "$RUN" cmd_add trk01 2087
bash "$RUN" cmd_add nld01 2087
bash "$RUN" cmd_add usa01 2087 62050
echo "--- list nodeha ---"; bash "$RUN" cmd_ls

line "tst 3: server.toml tvlidshdh"
cat "$ROOT/etc/rathole/server.toml"

line "tst 4: config nginx tvlidshdh"
cat "$ROOT/etc/nginx/conf.d/rathole.conf"

line "tst 5: hazf node nld01 va baztolid"
bash "$RUN" cmd_rm nld01
echo "--- map baad az hazf ---"; sed -n '/map \$uri/,/}/p' "$ROOT/etc/nginx/conf.d/rathole.conf"

line "tst 6: tkhsis port azad (bayad 1002 azadshdh ra bgird)"
bash "$RUN" cmd_add pol01 2087
bash "$RUN" cmd_ls

line "tst 7: jlvgiri az name tekrari"
bash "$RUN" cmd_add trk01 9999 || echo "OK: name tekrari rad shod"

line "tst 8: direct_port dar set-e rezerv (node nabayad port-e direct ra begirad)"
# aval port-e azad-e badi ra keshf kon (yek node-e movaghat bezar, port-esh ra bardar, hazfesh kon).
# sepas hamon port ra be onvan direct_port rezerv kon; node-e vaghai bayad an ra RAD konad va port-e digari begirad.
bash "$RUN" cmd_add probe01 2087
NEXT="$(jq -r '.nodes[]|select(.name=="probe01")|.port' "$ROOT/etc/rathole-manager/state.json")"
bash "$RUN" cmd_rm probe01
jq --argjson p "$NEXT" '.direct_port=$p' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
bash "$RUN" cmd_add rez01 2087
GOT="$(jq -r '.nodes[]|select(.name=="rez01")|.port' "$ROOT/etc/rathole-manager/state.json")"
[ "$GOT" != "$NEXT" ] && echo "OK: node port ($GOT) ba direct_port ($NEXT) tadakhol nadarad" || echo "FAIL: node port ba direct_port ($NEXT) yeksan ast"

line "tst 9: direct on (halat standalone) — map va server block"
jq 'del(.direct_port,.direct_header,.plain_port)' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
jq '.direct_port=8081 | .direct_header="X-Cdn-Id"' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
bash "$RUN" regenerate
CONF="$ROOT/etc/nginx/conf.d/rathole.conf"
grep -q 'map \$http_x_cdn_id \$direct_node' "$CONF" && echo "OK: map 1 (\$http var) hast" || echo "FAIL: map 1 nist"
grep -q 'map \$direct_node \$direct_backend' "$CONF" && echo "OK: map 2 hast" || echo "FAIL: map 2 nist"
grep -qE '^\s*listen 8081;' "$CONF" && echo "OK: listen 8081 hast" || echo "FAIL: listen 8081 nist"
grep -q 'proxy_pass http://127.0.0.1:\$direct_backend;' "$CONF" && echo "OK: proxy_pass direct_backend" || echo "FAIL: proxy_pass direct_backend nist"
# node-e non-SNI bayad dar map 1 bashad; trk01 az tst 2 hast
grep -qE '"trk01"\s+[0-9]+;' "$CONF" && echo "OK: trk01 dar map" || echo "FAIL: trk01 dar map nist"

line "tst 10: header-e delkhah -> motaghayer-e \$http dorost"
jq '.direct_header="X-My-Route"' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
bash "$RUN" regenerate
grep -q 'map \$http_x_my_route \$direct_node' "$CONF" && echo "OK: X-My-Route -> \$http_x_my_route" || echo "FAIL: transform-e header ghalat"
# baazgardandan be pishfarz baraye testhaye baadi
jq '.direct_header="X-Cdn-Id"' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"

line "tst 11: node-e SNI dar map-e direct nabashad"
bash "$RUN" cmd_add gm01 2087 2>/dev/null
jq '(.nodes[]|select(.name=="gm01")|.sni)="ex.com"' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
bash "$RUN" regenerate
sed -n '/map \$http_x_cdn_id \$direct_node/,/}/p' "$CONF" | grep -q '"gm01"' && echo "FAIL: node SNI dar map" || echo "OK: node SNI hazf shod az map"

line "tst 12: direct_port == plain_port -> yek block (bedoon duplicate listen)"
jq 'del(.direct_port,.direct_header) | .plain_port=9000 | .direct_port=9000 | .direct_header="X-Cdn-Id"' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
bash "$RUN" regenerate
# faghat yek 'listen 9000;' bayad bashad
CNT="$(grep -cE '^\s*listen 9000;' "$CONF")"
[ "$CNT" = "1" ] && echo "OK: yek listen 9000" || echo "FAIL: $CNT listen 9000 (duplicate)"
# map 2 branch-e khali bayad be $backend_port bashad, na fake_port
sed -n '/map \$direct_node \$direct_backend/,/}/p' "$CONF" | grep -qE '""\s+\$backend_port;' && echo "OK: fallback = backend_port (fall-through)" || echo "FAIL: fallback ghalat"
# location plain bayad be direct_backend proxy konad
awk '/listen 9000;/{f=1} f&&/proxy_pass http:\/\/127.0.0.1:\$direct_backend;/{print "found"; exit}' "$CONF" | grep -q found && echo "OK: plain location -> direct_backend" || echo "FAIL: plain location -> direct_backend nist"

line "tst 13: regression — plain-only (bedoon direct) hanooz backend_port"
jq 'del(.direct_port,.direct_header) | .plain_port=8880' "$ROOT/etc/rathole-manager/state.json" > "$ROOT/s.tmp" && mv "$ROOT/s.tmp" "$ROOT/etc/rathole-manager/state.json"
bash "$RUN" regenerate
awk '/listen 8880;/{f=1} f&&/proxy_pass http:\/\/127.0.0.1:\$backend_port;/{print "found"; exit}' "$CONF" | grep -q found && echo "OK: plain-only -> backend_port" || echo "FAIL: plain-only regression"
grep -q 'map .* \$direct_node' "$CONF" && echo "FAIL: map direct baraye plain-only tvlid shod" || echo "OK: bedoon direct, map direct nist"

echo "SANDBOX=$ROOT"
