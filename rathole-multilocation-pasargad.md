# تونل ریورس مولتی‌لوکیشن: پنل پاسارگارد (ایران) + نودهای خارج + rathole + Nginx روی یک پورت/دامنه

> **هشدار جدی (بدبینی مطلق):** این سند با فرض «هر چیزی که می‌تواند خراب شود، خراب خواهد شد» نوشته شده.
> یک path ناهماهنگ، یک توکن اشتباه، یک TLS دوبل، یا فراموش‌کردن کانال مدیریت پنل‑نود،
> باعث می‌شود سیستم «ظاهراً وصل ولی عملاً بی‌فایده» شود و ساعت‌ها سرگردان شوی.
> هر خط را با حوصله بزن و از پایین‌ترین لایه تست کن.

---

## معماری واقعی (همان چیزی که می‌خواهی)

```
                         ┌──────────── سرور ایران (دامنه + Let's Encrypt) ───────────┐
 کاربر ──TLS/443──────►  │  nginx :443  (تنها سرویس عمومی روی پورت ۴۴۳)               │
                         │    بر اساس path تصمیم می‌گیرد:                              │
                         │      /node1     → 127.0.0.1:9001  (دیتای نود ۱)            │
                         │      /node2     → 127.0.0.1:9002  (دیتای نود ۲)            │
                         │      /node3     → 127.0.0.1:9003  (دیتای نود ۳)            │
                         │      /tunnel    → 127.0.0.1:2333  (کانال کنترلی rathole)   │
                         │      /api-node1 → 127.0.0.1:7001  (مدیریت پنل↔نود ۱)        │
                         │                                                            │
                         │  پنل پاسارگارد + rathole (نقش SERVER) اینجا                │
                         └──────────────────────────────▲─────────────────────────────┘
                                                         │ همه از طریق همان تونل WS/443
        ┌────────────────────────────────────────────────┴───────────────┐
        │ نود خارج ۱ (rathole = CLIENT)   نود خارج ۲   نود خارج ۳ ...        │
        │  Xray ws inbound (بدون TLS) + پاسارگارد‑نود  ──► اینترنت آزاد      │
        └──────────────────────────────────────────────────────────────────┘
```

### نقش‌ها (این را اشتباه نزن)

| جزء | محل | نقش rathole | توضیح |
|-----|-----|-------------|-------|
| پنل پاسارگارد + Nginx + Let's Encrypt | **ایران** | **server** (گوش می‌دهد) | دامنه عمومی، تک نقطه ورود کاربر |
| نودهای Xray | **خارج** | **client** (به ایران وصل می‌شود) | اینباند ws، خروج به اینترنت |

«ریورس» یعنی: نودهای خارج از بیرون به سرور ایران SYN می‌زنند و تونل را برقرار می‌کنند — نه برعکس.

### چند لایه روی همان پورت ۴۴۳ مالتی‌پلکس می‌شوند

1. **کانال کنترلی rathole** (نود → ایران): یک اتصال websocket پایدار per node که همه ترافیک تونل‌شده داخلش جریان دارد. → nginx path `/tunnel` → `127.0.0.1:2333`.
2. **دیتای کاربر** (VLESS-over-WS): کاربر → nginx path `/nodeX` → `127.0.0.1:90xx` → از داخل تونل به Xray نود.
3. **کانال مدیریت پنل↔نود** (API پاسارگارد/Marzban-style): پنل → `127.0.0.1:70xx` → از داخل تونل به پورت API نود. **این لایه را اکثر آدم‌ها فراموش می‌کنند.**

---

## ۱. پیش‌نیازها و فرضیات

| مورد | مقدار فرضی (عوضش کن) |
|------|----------------------|
| دامنه | `panel.example.ir` (روی IP سرور ایران اشاره می‌کند) |
| سرور ایران | IP عمومی، Ubuntu 22.04+، پنل پاسارگارد رویش |
| نودهای خارج | ۳ عدد: node1, node2, node3 |
| پورت کنترلی rathole (لوکال) | `127.0.0.1:2333` |
| پورت‌های دیتا (لوکال، روی سرور ایران) | `9001`, `9002`, `9003` |
| پورت‌های مدیریت (لوکال، روی سرور ایران) | `7001`, `7002`, `7003` |
| پورت ws inbound Xray روی هر نود (لوکال) | `127.0.0.1:8080` |
| پورت API پاسارگارد‑نود روی هر نود (لوکال) | `127.0.0.1:62050` (سبک Marzban؛ ممکن است در پاسارگارد فرق کند — تأیید کن) |

> **بدبینی، قبل از هر کاری:**
> - `dig panel.example.ir +short` → باید IP سرور ایران را بدهد.
> - `sudo ss -ltnp | grep ':443'` → باید **خالی** باشد قبل از نصب nginx. اگر پاسارگارد خودش روی ۴۴۳ نشسته، باید جابه‌جایش کنی (بخش ۶).
> - فایروال/security group ابری: ۴۴۳ و ۸۰ باز.
> - `timedatectl` روی **همه** سرورها sync. اختلاف ساعت = خرابی TLS.
> - پورت‌های API پاسارگارد را از مستندات/پنل خودت تأیید کن؛ مقادیر بالا فرضی‌اند.

---

## ۲. نصب rathole (روی سرور ایران و همه نودها)

```bash
cd /tmp
VER="v0.5.0"   # آخرین نسخه را از https://github.com/rapiz1/rathole/releases بگیر
wget https://github.com/rapiz1/rathole/releases/download/${VER}/rathole-x86_64-unknown-linux-gnu.zip
unzip rathole-x86_64-unknown-linux-gnu.zip
sudo install -m 755 rathole /usr/local/bin/rathole
rathole --help
```

> **بدبینی:**
> - نسخه rathole روی سرور ایران و همه نودها **باید یکی باشد** (پروتکل بین نسخه‌ها گاهی ناسازگار است).
> - معماری باینری را با `uname -m` چک کن (x86_64 یا aarch64).
> - دانلود از GitHub از داخل ایران ممکن است کند/مسدود باشد؛ روی نود خارج دانلود کن و به سرور ایران کپی کن (`scp`).
> - glibc قدیمی → نسخه `musl` را بردار.

---

## ۳. کانفیگ rathole روی سرور ایران (نقش SERVER)

فایل `/etc/rathole/server.toml`:

```toml
# server.toml — روی سرور ایران (پنل پاسارگارد)
[server]
bind_addr = "127.0.0.1:2333"   # فقط لوکال؛ nginx جلویش می‌نشیند. هرگز 0.0.0.0.
heartbeat_interval = 30

[server.transport]
type = "websocket"
[server.transport.websocket]
tls = false   # TLS را nginx ترمینیت می‌کند

# ===== نود ۱ =====
# سرویس دیتا (ترافیک VLESS کاربر)
[server.services.node1_data]
token = "TOKEN_NODE1_DATA_عوضش_کن"
bind_addr = "127.0.0.1:9001"
type = "tcp"
# سرویس مدیریت (پنل پاسارگارد به API نود وصل می‌شود)
[server.services.node1_api]
token = "TOKEN_NODE1_API_عوضش_کن"
bind_addr = "127.0.0.1:7001"
type = "tcp"

# ===== نود ۲ =====
[server.services.node2_data]
token = "TOKEN_NODE2_DATA_عوضش_کن"
bind_addr = "127.0.0.1:9002"
type = "tcp"
[server.services.node2_api]
token = "TOKEN_NODE2_API_عوضش_کن"
bind_addr = "127.0.0.1:7002"
type = "tcp"

# ===== نود ۳ =====
[server.services.node3_data]
token = "TOKEN_NODE3_DATA_عوضش_کن"
bind_addr = "127.0.0.1:9003"
type = "tcp"
[server.services.node3_api]
token = "TOKEN_NODE3_API_عوضش_کن"
bind_addr = "127.0.0.1:7003"
type = "tcp"
```

تولید توکن قوی برای هرکدام:

```bash
openssl rand -hex 32
```

> **بدبینی:**
> - برای **هر نود دو سرویس** داری: یکی دیتا (`_data`)، یکی مدیریت (`_api`). اگر `_api` را فراموش کنی، نود در پنل آفلاین می‌ماند یا کاربرها sync نمی‌شوند.
> - نام هر سرویس یکتا و در دو طرف **مو‑به‑مو** یکسان.
> - همه `bind_addr`ها روی `127.0.0.1`؛ اگر `0.0.0.0` بزنی پورت‌های داخلی روی اینترنت لو می‌روند و کل منطق «یک پورت» می‌شکند.

---

## ۴. کانفیگ rathole روی نودهای خارج (نقش CLIENT)

روی **نود ۱**، فایل `/etc/rathole/client.toml`:

```toml
# client.toml — روی نود خارج ۱
[client]
remote_addr = "panel.example.ir:443"   # دامنه سرور ایران + پورت 443 (nginx)
retry_interval = 1
heartbeat_timeout = 40                  # باید > heartbeat_interval سرور (۳۰)

[client.transport]
type = "websocket"
[client.transport.websocket]
tls = true                              # به wss://443 وصل می‌شویم
[client.transport.tls]
hostname = "panel.example.ir"           # باید با گواهی Let's Encrypt یکی باشد

# سرویس دیتا: اینباند ws ایکس‌ری این نود را منتشر می‌کند
[client.services.node1_data]
token = "TOKEN_NODE1_DATA_عوضش_کن"      # دقیقاً مثل سرور
local_addr = "127.0.0.1:8080"           # ws inbound ایکس‌ری (بدون TLS)
type = "tcp"

# سرویس مدیریت: پورت API پاسارگارد‑نود را منتشر می‌کند
[client.services.node1_api]
token = "TOKEN_NODE1_API_عوضش_کن"
local_addr = "127.0.0.1:62050"          # پورت API نود (تأیید کن)
type = "tcp"
```

روی **نود ۲** فقط نام سرویس‌ها، توکن‌ها و در صورت لزوم پورت‌ها فرق می‌کند:

```toml
[client.services.node2_data]
token = "TOKEN_NODE2_DATA_عوضش_کن"
local_addr = "127.0.0.1:8080"
type = "tcp"
[client.services.node2_api]
token = "TOKEN_NODE2_API_عوضش_کن"
local_addr = "127.0.0.1:62050"
type = "tcp"
```

و نود ۳ به همین ترتیب با `node3_*`.

> **بدبینی:**
> - `remote_addr` همه نودها یکی است: `panel.example.ir:443`. تفاوت نودها فقط در نام سرویس و توکن است.
> - `heartbeat_timeout` کلاینت **باید** از `heartbeat_interval` سرور بزرگ‌تر باشد، وگرنه تونل مدام flap می‌کند.
> - اگر `hostname` با دامنه گواهی یکی نباشد → `certificate verify failed`.
> - اگر دامنه پشت Cloudflare proxy (ابر نارنجی) است، برای شروع DNS-only (ابر خاکستری) کن؛ لایه TLS اضافه Cloudflare منبع دردسرهای عجیب است.

---

## ۵. کانفیگ Nginx روی سرور ایران (همه چیز روی ۴۴۳)

### گام ۱: گواهی Let's Encrypt

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d panel.example.ir
```

> **بدبینی:** certbot اگر پورت ۸۰ بسته یا DNS هنوز propagate نشده باشد، شکست می‌خورد. اول `dig` و باز بودن ۸۰ را چک کن. پشت Cloudflare از DNS challenge استفاده کن.

### گام ۲: map برای websocket (یک‌بار در http block)

در `/etc/nginx/nginx.conf` داخل `http { ... }`:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
```

> **بدبینی:** اگر دوبار تعریف شود nginx بالا نمی‌آید (`duplicate map`). اگر اصلاً نباشد، WebSocket ارتقا نمی‌یابد و تونل وصل نمی‌شود.

### گام ۳: فایل سایت `/etc/nginx/sites-available/tunnel.conf`

```nginx
server {
    listen 443 ssl http2;
    server_name panel.example.ir;

    ssl_certificate     /etc/letsencrypt/live/panel.example.ir/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.example.ir/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # ---------- کانال کنترلی rathole ----------
    location /tunnel {
        proxy_pass http://127.0.0.1:2333;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout  86400s;
        proxy_send_timeout  86400s;
    }

    # ---------- دیتای کاربر: نود ۱ ----------
    # توجه: بدون اسلش انتهایی تا path حفظ شود (با path اینباند Xray نود یکی بماند)
    location /node1 {
        proxy_pass http://127.0.0.1:9001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400s;
    }
    location /node2 {
        proxy_pass http://127.0.0.1:9002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }
    location /node3 {
        proxy_pass http://127.0.0.1:9003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    # ---------- (اختیاری) پنل پاسارگارد روی همین دامنه ----------
    # اگر می‌خواهی UI پنل هم روی همین دامنه باشد، روی یک path یا root بگذار
    location / {
        proxy_pass http://127.0.0.1:8000;   # پورت داخلی UI پاسارگارد را اینجا بگذار
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> **هشدار درباره کانال مدیریت پنل↔نود:** پورت‌های `7001/7002/7003` (که API نودها از داخل تونل آنجا ظاهر می‌شوند) **نباید** از طریق nginx عمومی شوند. پنل پاسارگارد مستقیماً به `127.0.0.1:7001` (لوکال) وصل می‌شود. این‌ها هیچ‌وقت بیرون نمی‌روند، پس در nginx location نمی‌خواهند.

### گام ۴: فعال‌سازی

```bash
sudo ln -s /etc/nginx/sites-available/tunnel.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

> **بدبینی:**
> - `proxy_pass ...:9001;` **بدون** اسلش انتهایی باشد تا `/node1` حفظ شود. اگر `.../;` بزنی path حذف می‌شود و Xray نود اینباند را پیدا نمی‌کند → کاربر «وصل ولی بدون نت».
> - `proxy_read_timeout` همه location‌های تونلی ≥ `86400s`؛ پیش‌فرض ۶۰ ثانیه تونل را هر دقیقه می‌بندد.
> - خطای `duplicate default server`؟ یعنی پاسارگارد قبلاً روی ۴۴۳ یک server block دارد؛ پیدا و غیرفعالش کن.
> - اگر مسیر کنترلی `/tunnel` جواب نداد، نسخه rathole مسیر ws را روی `/` می‌خواهد؛ آن‌وقت کانال کنترلی را روی یک ساب‌دامین مجزا با `location /` بگذار (همچنان روی ۴۴۳).

---

## ۶. تنظیم Xray روی نودها و کانفیگ کاربر (هم‌ترازی path)

### قانون طلایی هم‌ترازی path

path باید در **سه جا** دقیقاً یکی باشد، وگرنه کاربر «وصل می‌شود ولی نت ندارد»:

```
کانفیگ VLESS کاربر  =  location در nginx  =  path اینباند ws در Xray نود
       /node1               /node1                    /node1
```

### اینباند پیشنهادی روی هر نود (در پنل پاسارگارد)

برای **نود ۱**:

- Protocol: `VLESS`
- Network: `ws`
- Path: `/node1`   (برای نود ۲ → `/node2` و ...)
- Listen: `127.0.0.1`
- Port: `8080`
- TLS: **خاموش** (nginx ترمینیت می‌کند؛ اگر اینجا هم روشن کنی دابل‌TLS و خرابی)

### کانفیگ سمت کاربر (همان یک دامنه و پورت)

```
Address : panel.example.ir
Port    : 443
Network : ws
Path    : /node1        ← برای اتصال از طریق نود ۱
Host/SNI: panel.example.ir
TLS     : tls (روشن — چون nginx گواهی Let's Encrypt دارد)
```

برای استفاده از نود ۲، کاربر فقط `Path` را به `/node2` عوض می‌کند؛ همه چیز دیگر یکی است. **یک دامنه، یک پورت، یک گواهی، چند نود — فقط با path.**

### مدیریت پنل↔نود

در پنل پاسارگارد هنگام افزودن نود، به‌جای IP عمومی نود، آدرس را `127.0.0.1` و پورت را `7001` (نود۱)، `7002` (نود۲)... بده — چون API نودها از طریق تونل rathole روی لوکال‌هاست سرور ایران ظاهر شده‌اند.

> **بدبینی شدید:**
> - **Reality روی نود کار نمی‌کند** اگر بخواهی پشت nginx روی همان ۴۴۳ باشد. Reality خودش TLS را هندل می‌کند و با ترمینیت‌شدن توسط nginx ناسازگار است. حتماً **VLESS/VMess + WS** بزن.
> - **gRPC** هم ممکن است ولی با `grpc_pass` و تنظیمات حساس؛ WS ساده‌تر و کم‌دردسرتر است.
> - گواهی client/SSL داخلی پاسارگارد‑نود (برای احراز هویت پنل با نود) جدا از Let's Encrypt است و همچنان لازم است؛ Let's Encrypt فقط برای لایه بیرونی ۴۴۳ است.
> - اگر اینباند را روی `0.0.0.0:8080` بگذاری (به‌جای `127.0.0.1`)، پورت نود مستقیم لو می‌رود و دور زدن از nginx ممکن می‌شود — هم امنیت هم منطق «یک پورت» را می‌شکند.

---

## ۷. سرویس systemd

### روی سرور ایران — `/etc/systemd/system/rathole-server.service`

```ini
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
```

### روی هر نود خارج — `/etc/systemd/system/rathole-client.service`

```ini
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
```

### فعال‌سازی

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rathole-server     # روی سرور ایران
sudo systemctl enable --now rathole-client     # روی هر نود
journalctl -u rathole-server -f                # لاگ زنده سرور
journalctl -u rathole-client -f                # لاگ زنده نود
```

> **بدبینی:**
> - `LimitNOFILE` بالا؛ با تعداد زیاد کاربر، file descriptorها تمام شده و اتصالات جدید بی‌صدا fail می‌شوند.
> - اول با اجرای دستی `RUST_LOG=debug rathole /etc/rathole/server.toml` تست کن؛ اگر کانفیگ خراب باشد systemd بی‌نهایت restart می‌کند.

---

## ۸. عیب‌یابی کامل (با بدبینی مطلق)

| نشانه | علت محتمل | راه‌حل |
|-------|-----------|--------|
| نود مدام «retrying» | دامنه/پورت غلط، nginx پایین، فایروال | `curl -v https://panel.example.ir` و `ss -ltnp` |
| قطع بلافاصله بعد اتصال | عدم تطابق توکن | توکن‌ها را کاراکتر‑به‑کاراکتر مقایسه کن |
| کاربر وصل می‌شود ولی نت ندارد | **عدم تطابق path** (سه‌جانبه) یا اسلش در proxy_pass | path کاربر = nginx = Xray؛ proxy_pass بدون اسلش |
| نود در پنل آفلاین است | کانال `_api` تنظیم نشده یا پورت API غلط | سرویس `_api` و پورت `7001/62050` را چک کن |
| `certificate verify failed` | hostname با گواهی نمی‌خواند | `hostname` = دامنه واقعی |
| WebSocket `400/502` | nginx هدر Upgrade/Connection پاس نمی‌دهد | `map` و `proxy_set_header`ها |
| تونل هر ۶۰ ثانیه قطع | `proxy_read_timeout` پایین | `86400s` |
| کاربر با Reality وصل نمی‌شود | Reality پشت nginx کار نمی‌کند | به VLESS+WS سوییچ کن |
| `502 Bad Gateway` | rathole/Xray بالا نیست | `systemctl status` و پورت لوکال |
| `duplicate default server` | server block تکراری پاسارگارد روی ۴۴۳ | کانفیگ قدیمی را غیرفعال کن |

### دستورات طلایی دیباگ

```bash
# روی سرور ایران: پورت‌های لوکال باز است؟
sudo ss -ltnp | grep -E '2333|9001|7001'
# nginx روی 443؟
sudo ss -ltnp | grep ':443'
# تست کانال کنترلی از بیرون:
curl -v --http1.1 -H "Upgrade: websocket" -H "Connection: Upgrade" https://panel.example.ir/tunnel
# روی نود: اینباند Xray واقعاً جواب می‌دهد؟
curl -v http://127.0.0.1:8080
# لاگ دو سمت همزمان:
journalctl -u rathole-server -f   # ایران
journalctl -u rathole-client -f   # نود
```

> **روش طلایی:** از پایین‌ترین لایه شروع کن:
> ۱) اینباند Xray روی نود لوکال جواب می‌دهد؟ → ۲) سرویس‌های rathole (`_data` و `_api`) برقرارند؟ → ۳) nginx path درست پروکسی می‌کند؟ → ۴) از بیرون TLS/DNS سالم است؟

---

## ۹. مشکلات خاص شبکه ایران (بدترین حالت)

- **شناسایی DPI و reset تونل:** کانال کنترلی WS باید روی دامنه تمیز و غیرمشهور باشد، با `Host` واقعی و ترجیحاً دامنه‌ای که سایت واقعی هم رویش سرو می‌شود (camouflage). اگر بعد از چند مگابایت قطع می‌شود، احتمالاً DPI شناسایی کرده.
- **تک‌نقطه‌شکست (SPOF):** سرور ایران بیفتد یا دامنه‌اش فیلتر شود، **همه نودها می‌افتند**. حداقل یک دامنه/IP پشتیبان آماده داشته باش.
- **دو بار عبور از مرز:** ترافیک از ایران به نود خارج می‌رود و خروجی نود دوباره به اینترنت؛ پس لتنسی ذاتاً بالاتر است. این طبیعت معماری است، باگ نیست.
- **Throttle روی ۴۴۳ طولانی:** بعضی اپراتورها اتصالات بلندمدت ۴۴۳ را کند می‌کنند؛ با همراه اول/ایرانسل/مخابرات جدا تست کن.
- **MTU/Fragmentation:** اگر اتصال برقرار است ولی دانلود بزرگ گیر می‌کند، MTU را روی نودها کاهش بده (مثلاً `1400`).
- **NTP/ساعت:** ساعت ناهماهنگ = خرابی TLS بین نود و ایران. `sudo timedatectl set-ntp true`.
- **تحریم GitHub:** باینری rathole را روی نود خارج دانلود و به سرور ایران کپی کن.

> **بدبینی:** هیچ تنظیمی ابدی نیست؛ روش‌های فیلترینگ تغییر می‌کنند. همیشه پلن جایگزین (دامنه دوم، پورت دوم، پروتکل دوم) آماده داشته باش.

---

## ۱۰. چک‌لیست نهایی

- [ ] `rathole` با **نسخه یکسان** روی سرور ایران و همه نودها نصب است.
- [ ] DNS دامنه به IP سرور ایران اشاره می‌کند.
- [ ] پورت ۴۴۳ و ۸۰ روی فایروال/security group باز است.
- [ ] روی ۴۴۳ فقط nginx نشسته (نه Xray مستقیم، نه پاسارگارد قدیمی).
- [ ] گواهی Let's Encrypt گرفته و `nginx -t` بدون خطا.
- [ ] `map $http_upgrade` فقط یک‌بار در http block.
- [ ] `proxy_read_timeout` همه location‌های تونلی ≥ `86400s`.
- [ ] `proxy_pass` سرویس‌های دیتا **بدون** اسلش انتهایی (path حفظ شود).
- [ ] برای **هر نود دو سرویس** ساخته شده: `_data` و `_api`.
- [ ] توکن‌ها در سرور و کلاینت مو‑به‑مو یکی و قوی‌اند.
- [ ] نام سرویس‌ها در دو طرف یکسان است.
- [ ] همه `bind_addr`/`listen` روی `127.0.0.1` (نه `0.0.0.0`).
- [ ] `heartbeat_timeout` کلاینت > `heartbeat_interval` سرور.
- [ ] **path در سه جا یکی است:** کانفیگ کاربر = nginx = اینباند Xray.
- [ ] اینباند Xray روی نود **بدون TLS** و روی `127.0.0.1:8080`.
- [ ] پروتکل اینباند **VLESS+WS** است (نه Reality پشت nginx).
- [ ] در پنل، آدرس نود `127.0.0.1` و پورت API `70xx` تنظیم شده.
- [ ] ساعت همه سرورها sync است.
- [ ] لاگ rathole دو سمت «control channel established» را نشان می‌دهد.
- [ ] اتصال انتها‑به‑انتها از کلاینت واقعی کاربر تست شده.
- [ ] دامنه/IP پشتیبان آماده است.

---

### جمع‌بندی

پنل پاسارگارد روی ایران نقش rathole **server** را دارد و نودهای خارج نقش **client**؛ نودها با ریورس از بیرون به ایران وصل می‌شوند. `nginx` تنها سرویس عمومی روی **یک پورت (۴۴۳)** و **یک دامنه** با **یک گواهی Let's Encrypt** است و بر اساس **path** مشخص می‌کند ترافیک به کدام نود برود. سه لایه (کانال کنترلی، دیتای کاربر، مدیریت پنل‑نود) همه روی همان ۴۴۳ از داخل تونل مالتی‌پلکس می‌شوند. کلید موفقیت: جهت درست rathole، هم‌ترازی سه‌جانبه path، بدون اسلش بودن proxy_pass، تایم‌اوت بالا، اینباند بدون TLS، پرهیز از Reality، و فراموش‌نکردن کانال مدیریت `_api`. و یادت باشد — هر چیزی که می‌تواند خراب شود یک روز خراب می‌شود؛ مانیتورینگ و پلن جایگزین داشته باش.
