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

echo "SANDBOX=$ROOT"
