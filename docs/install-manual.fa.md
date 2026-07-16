<div align="center">

<img src="assets/logo.svg" alt="RatholeEngine" width="110" height="110" />

# نصب کامل و دستی — RatholeEngine

**پنل ایران + کانفیگ پاسارگارد + نودهای خارج + هاب مرکزی**

_گام‌به‌گام، بدون اسکریپت خودکار — دقیقاً همان کاری که نصاب‌ها می‌کنند._

[**English version**](install-manual.md) · [**مرجع کامل CLI**](README.fa.md) · [نصب خودکار](README.fa.md#شروع-سریع)

</div>

<div dir="rtl">

> **این سند برای چه کسی است؟** وقتی می‌خواهی **دستی** و با آگاهی کامل از هر لایه نصب کنی (به‌جای `install.sh` تک‌کامانده)، یا وقتی نصبِ خودکار در جایی گیر کرده و می‌خواهی همان مرحله را دستی جلو ببری. همه‌ی دستورها عیناً از اسکریپت‌های واقعی (`install-panel.sh`، `install-node.sh`، `install-hub.sh`، `ratholectl init`) استخراج شده‌اند.
>
> اگر نصب خودکار برایت کافی است، سراغ [نصب تک‌کامانده](README.fa.md#شروع-سریع) برو. برای طراحی مفهومی و بدبینی عمیق‌تر، [سند پاسارگاد](../rathole-multilocation-pasargad.md) را بخوان.

## فهرست

- [۰. پیش‌نیازها و بدبینی اولیه](#۰-پیشنیازها-و-بدبینی-اولیه)
- [۱. نصب باینری rathole (هر دو نقش)](#۱-نصب-باینری-rathole-هر-دو-نقش)
- [۲. سرور ایران (پنل) — نصب دستی](#۲-سرور-ایران-پنل--نصب-دستی)
- [۳. کانفیگ پاسارگارد (Xray inbound + کاربر)](#۳-کانفیگ-پاسارگارد-xray-inbound--کاربر)
- [۴. نود خارج — نصب دستی](#۴-نود-خارج--نصب-دستی)
- [۵. نصب کامل هاب مرکزی](#۵-نصب-کامل-هاب-مرکزی)
- [۶. راستی‌آزمایی و عیب‌یابی](#۶-راستیآزمایی-و-عیبیابی)
- [۷. چک‌لیست نهایی](#۷-چکلیست-نهایی)

---

## ۰. پیش‌نیازها و بدبینی اولیه

| مورد | مقدار فرضی (عوضش کن) |
|------|----------------------|
| دامنه | `panel.example.ir` (به IP سرور ایران اشاره کند) |
| سرور ایران | IP عمومی، Ubuntu 22.04+ |
| نودهای خارج | مثلاً `trk01`، `nld01` … |
| پورت کنترلی rathole (لوکال) | `127.0.0.1:2333` |
| شروع پورت دیتا (لوکال، روی ایران) | از `1001` |
| شروع پورت مدیریت/API (لوکال، روی ایران) | از `7001` |
| اینباند ws ایکس‌ری روی هر نود (لوکال) | `127.0.0.1:<inbound>` (بدون TLS) |

**قبل از هر کاری روی سرور ایران این‌ها را چک کن:**

```bash
dig panel.example.ir +short         # باید IP سرور ایران را بدهد
sudo ss -ltnp | grep ':443'         # باید خالی باشد؛ فقط nginx باید 443 را بگیرد
timedatectl                         # ساعت sync؛ اختلاف ساعت = خرابی TLS
sudo timedatectl set-ntp true       # در صورت نیاز
```

> **بدبینی:**
> - فایروال/security group ابری: پورت‌های **۴۴۳ و ۸۰** باز باشند (۸۰ برای certbot).
> - اگر دامنه پشت Cloudflare است، برای شروع **DNS-only** (ابر خاکستری) کن؛ لایه TLS اضافه‌ی Cloudflare منبع دردسر است.
> - نسخه‌ی rathole روی **سرور ایران و همه‌ی نودها باید یکی باشد** (`v0.5.0`).

---

## ۱. نصب باینری rathole (هر دو نقش)

معماری را با `uname -m` چک کن، بعد باینری را نصب کن. **این مرحله روی سرور ایران و همه‌ی نودها یکسان است.**

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

> **تحریم GitHub از داخل ایران:** اگر دانلود مستقیم کار نکرد، دو راه داری:
> 1. باینری را روی **نود خارج** بگیر و با `scp` به سرور ایران کپی کن، سپس `install -m 755` بزن.
> 2. از میرورها استفاده کن (همان‌هایی که `install-panel.sh` به‌صورت fallback امتحان می‌کند):
>    `https://ghproxy.net/https://github.com/…` · `https://gh-proxy.com/https://github.com/…` · `https://mirror.ghproxy.com/https://github.com/…`
>
> glibc قدیمی؟ نسخه‌ی `musl` را بردار.

---

## ۲. سرور ایران (پنل) — نصب دستی

این‌ها همان کارهای `install-panel.sh` است، مرحله‌به‌مرحله.

### ۲.۱ پیش‌نیازها

```bash
sudo apt-get update -y
export DEBIAN_FRONTEND=noninteractive
# sshpass برای provision خودکار نود از پنل/هاب لازم است
sudo apt-get install -y nginx jq curl unzip openssl ca-certificates \
     certbot python3-certbot-nginx sshpass
```

### ۲.۲ نصب `ratholectl`

از پوشه‌ی `rathole-manager/` بسته:

```bash
sudo mkdir -p /etc/rathole /etc/rathole-manager /usr/local/share/rathole
sudo install -m 755 ratholectl        /usr/local/bin/ratholectl
sudo install -m 644 common.sh         /usr/local/share/rathole/common.sh
```

### ۲.۳ یونیت systemd سرور

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

### ۲.۴ map ارتقای WebSocket (یک‌بار)

```bash
sudo tee /etc/nginx/conf.d/rathole-upgrade-map.conf >/dev/null <<'MAP'
# lazem baraye WebSocket/HTTPUpgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAP
```

> **بدبینی:** این `map` فقط **یک‌بار** باید در http context تعریف شود؛ اگر دوبار شود `nginx -t` خطای `duplicate map` می‌دهد.

### ۲.۵ رفع تداخل ۴۴۳

هر کانفیگی که از قبل روی ۴۴۳ نشسته (مثلاً یک پنل قدیمی) باید کنار برود:

```bash
grep -rlE 'listen[[:space:]]+(\[::\]:)?443' /etc/nginx/sites-enabled /etc/nginx/conf.d
# فایل‌های مزاحم را به یک پوشه‌ی بکاپ منتقل کن (نه حذف):
sudo mkdir -p /etc/nginx/rathole-backup-$(date +%Y%m%d-%H%M%S)
# سایت پیش‌فرض nginx هم اگر default_server دارد:
sudo rm -f /etc/nginx/sites-enabled/default
```

### ۲.۶ init — تولید state و کانفیگ‌ها

اصل مرکزی سیستم: **تغییر state → بازتولید کانفیگ → `nginx -t` → hot-reload.** هیچ‌وقت `server.toml` یا `rathole.conf` را دستی ویرایش نکن؛ فقط با `ratholectl` کار کن.

```bash
sudo ratholectl init \
  --domain     panel.example.ir \
  --fullchain  /root/cert/panel.example.ir/fullchain.pem \
  --key        /root/cert/panel.example.ir/privkey.pem
```

آرگومان‌های اختیاری `init` (پیش‌فرض‌ها معمولاً درست‌اند):

| آرگومان | پیش‌فرض | کار |
|---------|---------|-----|
| `--control-port` | `2333` | پورت کنترلی لوکال rathole |
| `--fake-port` | `8080` | سایت فیک/پنل روی root |
| `--sub-port` | `2096` | ساب‌اسکریپشن |
| `--data-start` | `1001` | شروع شماره‌ی پورت‌های دیتا |
| `--api-start` | `7001` | شروع شماره‌ی پورت‌های مدیریت |
| `--nginx-conf` | `/etc/nginx/conf.d/rathole.conf` | فایل کانفیگ تولیدی nginx |
| `--certbot` | — | اگر گواهی نداری، با certbot بگیرد |

> **گواهی:** اگر گواهی از قبل در مسیر `--fullchain/--key` باشد، همان استفاده می‌شود. اگر نه و `--certbot` بدهی (یا در حالت تعاملی تأیید کنی)، `certbot` گواهی Let's Encrypt می‌گیرد (نیاز: DNS به این سرور + پورت ۸۰ آزاد).

### ۲.۷ تست و بالا آوردن سرویس

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now rathole-server
sudo ratholectl doctor        # بررسی سلامت
sudo ratholectl status        # داشبورد کامل: دامنه، پورت‌ها، گواهی، سرویس‌ها، نودها
sudo ratholectl paths         # مسیر همه‌ی فایل‌ها با ✓/✗ (وقتی مرحله‌ای گیر کرده مفید است)
sudo ratholectl version       # manager_version + rathole_version
```

> `ratholectl status --json` همان خروجی machine-readable است که دکمه‌ی **وضعیت (Status)** هاب مصرف می‌کند.

> **آپدیت‌های بعدی:** `sudo ratholectl update` آخرین Release گیت‌هاب را می‌گیرد و آپدیت
> کامل (snapshot + health-check + rollback خودکار) را اجرا می‌کند. روی نود هم
> `sudo ratholenode update`. هر دو از mirrorهای ghproxy fallback دارند، پس از داخل
> ایران کار می‌کنند. دکمه‌ی **آپدیت** هاب هم همین را از راه SSH انجام می‌دهد، و دکمه‌ی
> **آپدیت همه**‌ی آن این کار را روی همه‌ی سرورها یکی‌یکی اجرا می‌کند (progress bar +
> badge نسخه‌ی سبز/زرد روی هر سرور).

### ۲.۸ افزودن نود

هر بار که نودی اضافه می‌کنی، `ratholectl` state را عوض و کانفیگ‌ها را بازتولید و hot-reload می‌کند (بدون قطع تونل‌های فعال):

```bash
# نودِ فقط-دیتا:
sudo ratholectl add trk01 2087

# نود با کانال مدیریت پنل↔نود (سرویس <name>_api روی 127.0.0.1):
sudo ratholectl add trk01 2087 --api-port 62050

sudo ratholectl ls                 # لیست نودها + مسیرهای کاربر
sudo ratholectl show trk01         # دستور دقیق نصب همان نود را چاپ می‌کند
```

`add` (و `show`) یک دستور آماده‌ی `curl -fsSL …/install.sh | sudo bash -s -- --node -- --server <panel>:443 --name … --token … --inbound-port …` هم چاپ می‌کنند (با token/inbound پرشده از state) — همان را مستقیم روی نود خارج کپی کن.

خروجی `show` دقیقاً چیزی است که باید روی نود خارج بزنی — برو بخش [۴](#۴-نود-خارج--نصب-دستی).

> **یادآوری کلیدی:** نام نود (`trk01`) هم‌زمان **مسیر URL**، **ورودی map در nginx** و **path اینباند Xray روی نود** است. این سه باید مو‌به‌مو یکی بمانند.

---

## ۳. کانفیگ پاسارگارد (Xray inbound + کاربر)

### قانون طلایی هم‌ترازی path

path باید در **سه جا** دقیقاً یکی باشد، وگرنه کاربر «وصل می‌شود ولی نت ندارد»:

```
کانفیگ VLESS کاربر  =  مسیر در nginx  =  path اینباند ws در Xray نود
       /trk01              /trk01                   /trk01
```

### اینباند روی هر نود (در پنل پاسارگارد)

برای نود `trk01`:

- Protocol: **VLESS**
- Network: **ws**
- Path: **`/trk01`**  (همان نامِ نود)
- Listen: **`127.0.0.1`**
- Port: همان `inbound` که موقع `ratholectl add` دادی (اینجا `2087`)
- TLS: **خاموش** — nginx روی سرور ایران ترمینیت می‌کند؛ اگر اینجا هم روشن کنی دابل‌TLS و خرابی.

### کانفیگ سمت کاربر (یک دامنه، یک پورت، یک گواهی)

```
Address : panel.example.ir
Port    : 443
Network : ws
Path    : /trk01          ← برای اتصال از طریق نود trk01
Host/SNI: panel.example.ir
TLS     : tls (روشن — چون nginx گواهی Let's Encrypt دارد)
```

برای استفاده از نود دیگر، کاربر فقط `Path` را عوض می‌کند (`/nld01` و…). **همه‌چیز دیگر یکی است.**

### کانال مدیریت پنل↔نود (`_api`)

اگر با `--api-port` نود ساختی، یک سرویس `<name>_api` روی `127.0.0.1:<api_local_port>` سرور ایران ظاهر می‌شود (خروجی `ratholectl show` این پورت را می‌گوید). در پنل پاسارگارد هنگام افزودن نود:

- آدرس نود را **`127.0.0.1`** بگذار (نه IP عمومی نود)
- پورت API را همان `api_local_port` بگذار (مثلاً `7001`)

چون API نود از داخل تونل روی لوکال‌هاست سرور ایران بالا آمده است.

> **بدبینی شدید (از سند پاسارگاد):**
> - **Reality پشت nginx کار نمی‌کند** — حتماً **VLESS/VMess + WS**.
> - اینباند را روی `127.0.0.1` بگذار نه `0.0.0.0`؛ وگرنه پورت نود مستقیم لو می‌رود و منطق «یک پورت» می‌شکند.
> - گواهی داخلی پاسارگارد‑نود (احراز هویت پنل↔نود) جدا از Let's Encrypt است و همچنان لازم است.
>
> جزئیات کامل و troubleshooting سه‌لایه در [سند پاسارگاد](../rathole-multilocation-pasargad.md).

---

## ۴. نود خارج — نصب دستی

### راه ساده: با نصاب

خروجی `ratholectl show <name>` روی سرور ایران دقیقاً همین را می‌دهد. از پوشه‌ی `rathole-manager/` روی نود:

```bash
sudo bash install-node.sh --server panel.example.ir:443 --name trk01 \
     --token <TOKEN> --inbound-port 2087 \
     [--api-token <API_TOKEN> --api-inbound-port 62050]
```

نصاب: rathole را نصب، `ratholenode` و `common.sh` را کپی، یونیت `rathole-client` را می‌سازد، `node.env` و `services.conf` را می‌نویسد و کلاینت را استارت می‌کند.

### راه دستی کامل (بدون نصاب)

اگر می‌خواهی خودت هر فایل را بسازی:

```bash
# ۱) rathole طبق بخش ۱ نصب باشد
sudo mkdir -p /etc/rathole /usr/local/share/rathole
sudo install -m 755 ratholenode /usr/local/bin/ratholenode
sudo install -m 644 common.sh   /usr/local/share/rathole/common.sh

# ۲) یونیت systemd کلاینت
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

سپس `client.toml` (دقیقاً همان چیزی که `install-node.sh` تولید می‌کند):

```toml
# /etc/rathole/client.toml — روی نود خارج
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

# سرویس دیتا: اینباند ws ایکس‌ری این نود را منتشر می‌کند
[client.services.trk01]
token = "<TOKEN>"
local_addr = "127.0.0.1:2087"
type = "tcp"

# (اختیاری) کانال مدیریت — فقط اگر --api-port داده باشی
[client.services.trk01_api]
token = "<API_TOKEN>"
local_addr = "127.0.0.1:62050"
type = "tcp"
```

```bash
sudo systemctl enable --now rathole-client
journalctl -u rathole-client -f      # باید "control channel established" بدهد
```

> **بدبینی:**
> - `remote_addr` همه‌ی نودها یکی است: `panel.example.ir:443`. تفاوت نودها فقط در **نام سرویس و توکن** است.
> - `heartbeat_timeout` کلاینت (`40`) **باید** از `heartbeat_interval` سرور (`30`) بزرگ‌تر باشد، وگرنه تونل مدام flap می‌کند.
> - `hostname` باید مو‌به‌مو با دامنه‌ی گواهی یکی باشد، وگرنه `certificate verify failed`.
> - توکن‌ها را با خروجی `ratholectl show` **کاراکتر‑به‑کاراکتر** مقایسه کن.

### سرویس/آپ‌استریم بیشتر روی همان نود

```bash
# سرویس (IP/اینباند) دیگر روی همین تونل:
sudo ratholenode add-svc <name> <token> <inbound>

# وصل‌کردن همین نود به یک سرور ایرانِ دوم (چند-موقعیتی):
sudo ratholenode upstream add <id> <server:443>
sudo ratholenode upstream add-svc <id> <name> <token> <inbound>

sudo ratholenode backup              # بکاپ state نود
sudo ratholenode update              # آپدیت کامل از GitHub (آخرین Release؛ snapshot + rollback خودکار)
```

---

## ۵. نصب کامل هاب مرکزی

هاب (`ratholehub`) یک پنل وب تک‌فایل (Python stdlib) است که روی **یک سرور مدیریت** (معمولاً همان پنل ایران) نصب می‌شود و از طریق **SSH با کلید** روی بقیه‌ی سرورها `ratholectl`/`ratholenode` را با **argv اعتبارسنجی‌شده** اجرا می‌کند — هرگز رشته‌ی شل خام. روی `127.0.0.1` می‌شنود.

### ۵.۱ نصب

```bash
cd rathole-manager/ratholehub
sudo bash install-hub.sh          # رمز مدیریت می‌پرسد، API TOKEN تولید می‌کند
```

نصاب این کارها را می‌کند:

- `hub.py` → `/opt/ratholehub/hub.py`
- کپی `ratholectl`/`ratholenode`/`update.sh`/… به `/opt/ratholehub/bundle/` (برای deploy از راه دور)
- تولید `/etc/ratholehub/config.json` (شامل `api_token`، هشِ رمز مدیریت، مسیر کلید SSH) و `inventory.json` خالی
- یونیت `ratholehub.service` روی `127.0.0.1:8088` (متغیر `HUB_PORT` قابل تغییر)
- ساخت کلید SSH هاب: `/root/.ssh/id_ed25519`

> `config.json` شامل توکن و هش رمز است؛ `chmod 600` می‌شود و **نباید** جایی commit یا لو برود.

### ۵.۲ authorize کردن کلید SSH روی هر سرور

هاب فقط با کلید SSH وصل می‌شود (بدون رمز). کلید عمومی هاب را روی هر سروری که می‌خواهی مدیریت کنی بگذار:

```bash
# روی سرور هاب:
ssh-copy-id -i /root/.ssh/id_ed25519.pub -p 22 root@<server_ip>
# تست:
ssh -i /root/.ssh/id_ed25519 root@<server_ip> 'ratholenode show || ratholectl ls'
```

### ۵.۳ دسترسی به پنل

**راه امن (بدون باز کردن هیچ پورت)** — SSH local-forward از سیستم خودت:

```bash
ssh -L 8088:127.0.0.1:8088 root@<hub_ip>
# مرورگر:  http://localhost:8088
```

**یا پشت nginx زیر همان دامنه** — اگر هاب روی همان سرور پنل ایران است، `install-hub.sh` خودکار این را انجام می‌دهد؛ در غیر این صورت دستی:

```bash
sudo ratholectl hub on 8088          # location /hub/ پایدار پشت nginx
# بار اول: هاب را هم خودکار نصب می‌کند (install-hub.sh، رمز ادمین را می‌پرسد)
# دفعات بعد: listen_port واقعی هاب را عوض می‌کند + ratholehub ری‌استارت + nginx هماهنگ
# دسترسی:  https://panel.example.ir/hub/
sudo ratholectl hub status           # وضعیت سرویس ratholehub و هشدار ناهماهنگی پورت را هم نشان می‌دهد
sudo ratholectl hub off              # برداشتن از nginx (سرویس روی 127.0.0.1 روشن می‌ماند)
```

> چون با `hub on` پنل عمومی می‌شود، مطمئن شو **رمز قوی** گذاشته‌ای.

### ۵.۴ REST API (نمونه)

همه‌ی مسیرها با هدر `Authorization: Bearer <API_TOKEN>` (یا کوکی نشست از UI):

```bash
TOKEN=... ; B=http://localhost:8088
curl -s -H "Authorization: Bearer $TOKEN" $B/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST $B/api/servers/rp01/action \
  -d '{"action":"kcp_on","args":{"port":"443","profile":"balanced"}}'
```

جزئیات کامل action های مجاز و مدل امنیتی: [`docs/hub.md`](hub.md).

> **دکمه‌های مفید هاب:** هر سرور ایران یک دکمه‌ی **وضعیت (Status)** دارد (خروجی `ratholectl status --json` را به‌شکل داشبورد render می‌کند) و داشبورد یک دکمه‌ی **آپدیت همه** دارد (همه‌ی سرورها را یکی‌یکی با progress bar + badge نسخه آپدیت می‌کند). در جدول نودهای هر سرور، **افزودن به نود** یک نود ایران (name/token/inbound) را روی نود/آپ‌استریم خارج به‌عنوان سرویس سیم‌کشی می‌کند، و در صفحه‌ی هر نود **تنظیم تونل اصلی** آن را به سرور ایرانش وصل می‌کند.

---

## ۶. راستی‌آزمایی و عیب‌یابی

### دستورات طلایی دیباگ

```bash
# روی سرور ایران: پورت‌های لوکال باز است؟
sudo ss -ltnp | grep -E '2333|1001|7001'
# nginx روی 443؟
sudo ss -ltnp | grep ':443'
# روی نود: اینباند Xray واقعاً جواب می‌دهد؟
curl -v http://127.0.0.1:2087
# لاگ دو سمت همزمان:
journalctl -u rathole-server -f   # ایران
journalctl -u rathole-client -f   # نود
```

### جدول عیب‌یابی

| نشانه | علت محتمل | راه‌حل |
|-------|-----------|--------|
| نود مدام «retrying» | دامنه/پورت غلط، nginx پایین، فایروال | `curl -v https://panel.example.ir` و `ss -ltnp` |
| قطع بلافاصله بعد اتصال | عدم تطابق توکن | با `ratholectl show` مقایسه کن |
| کاربر وصل ولی نت ندارد | **عدم تطابق path** سه‌جانبه | path کاربر = nginx = Xray |
| نود در پنل آفلاین | کانال `_api` تنظیم نشده / پورت غلط | سرویس `_api` و `api_local_port` را چک کن |
| `certificate verify failed` | hostname با گواهی نمی‌خواند | `hostname` = دامنه واقعی |
| WebSocket `400/502` | nginx هدر Upgrade پاس نمی‌دهد | `map` و `proxy_set_header`ها |
| تونل هر ۶۰ ثانیه قطع | تایم‌اوت پایین nginx | کانفیگ تولیدی را دست‌کاری نکن؛ `ratholectl regen` |
| `duplicate default server` | server block قدیمی روی ۴۴۳ | بخش [۲.۵](#۲۵-رفع-تداخل-۴۴۳) |
| `ratholehub` بالا نمی‌آید | خطای config/پایتون | `journalctl -u ratholehub -n 30` |

> **روش طلایی:** از پایین‌ترین لایه شروع کن — ۱) اینباند Xray روی نود لوکال جواب می‌دهد؟ → ۲) سرویس‌های rathole (`_data`/`_api`) برقرارند؟ → ۳) nginx path درست پروکسی می‌کند؟ → ۴) از بیرون TLS/DNS سالم است؟

---

## ۷. چک‌لیست نهایی

- [ ] `rathole` با **نسخه‌ی یکسان** (`v0.5.0`) روی ایران و همه‌ی نودها.
- [ ] DNS دامنه به IP سرور ایران؛ پورت ۴۴۳ و ۸۰ روی فایروال باز.
- [ ] روی ۴۴۳ فقط nginx نشسته (نه Xray مستقیم، نه پنل قدیمی).
- [ ] گواهی گرفته و `nginx -t` بدون خطا؛ `map $http_upgrade` فقط یک‌بار.
- [ ] `rathole-server` روی ایران و `rathole-client` روی هر نود **فعال و enable**.
- [ ] برای نودهای نیازمند مدیریت، `--api-port` داده شده (سرویس `_api`).
- [ ] توکن‌ها با `ratholectl show` مو‌به‌مو یکی؛ همه‌ی `bind_addr`/`local_addr` روی `127.0.0.1`.
- [ ] `heartbeat_timeout` کلاینت (۴۰) > `heartbeat_interval` سرور (۳۰).
- [ ] **path در سه جا یکی:** کانفیگ کاربر = nginx = اینباند Xray.
- [ ] اینباند Xray روی نود **بدون TLS** و روی `127.0.0.1`؛ پروتکل **VLESS+WS** (نه Reality).
- [ ] در پنل، آدرس نود `127.0.0.1` و پورت API `70xx`.
- [ ] ساعت همه‌ی سرورها sync؛ لاگ دو سمت «control channel established».
- [ ] (هاب) کلید SSH هاب روی همه‌ی سرورهای inventory authorize شده.
- [ ] اتصال انتها‑به‑انتها از کلاینت واقعی کاربر تست شده.

---

**مرجع کامل CLI و نصب خودکار:** [`README.fa.md`](README.fa.md) · **طراحی و بدبینی عمیق:** [سند پاسارگاد](../rathole-multilocation-pasargad.md) · **هاب:** [`hub.md`](hub.md)

</div>
