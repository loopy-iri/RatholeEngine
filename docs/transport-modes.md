# حالت‌های Transport — یک تونل، چند حامل

همان تونل معکوس می‌تواند ترافیک را از **چهار مسیر** حمل کند (به‌علاوه‌ی حالت ویژه‌ی game/SNI). سوییچ بین حالت‌ها **هیچ‌وقت** سرویس‌ها، توکن‌ها یا مسیر (path) کاربران را عوض نمی‌کند — فقط *حاملِ* تونل تغییر می‌کند.

![حالت‌های transport](assets/transport-modes.svg)

> **اصل ثابت (invariant):** TLS فقط توسط nginx خاتمه می‌یابد؛ transport سمت rathole-server همیشه `tls = false` است. کلاینت پیش‌فرض با `tls = true` روی websocket به nginx/۴۴۳ وصل می‌شود.

## ۱) websocket + TLS (پیش‌فرض)
- کلاینت به `wss://domain:443` وصل می‌شود.
- nginx ریشه‌ی `/` را با `$http_upgrade` بین **سایت فیک** و **کانال کنترلی rathole** تقسیم می‌کند (rathole همیشه از `/` برای کنترل استفاده می‌کند؛ path در rathole قابل‌تنظیم نیست).
- TLS روی nginx خاتمه می‌یابد (گواهی Let's Encrypt).

## ۲) kcp (UDP+FEC)
- مسیر **موازی** UDP+FEC از طریق kcptun برای لینک‌های پرافت (mitigation برای TCP-over-TCP).
- **افزودنی است** — به server/nginx/۴۴۳ دست نمی‌زند؛ یک مسیر ورودی دوم اضافه می‌کند.
- پروفایل‌ها (`balanced`/`lossy`/`aggressive`) باید دو طرف یکی باشند (در `common.sh:kcp_profile`).
- چند-ایران: هر upstream kcp مستقل دارد (`rathole-kcp-up-<id>`، پورت لوکال از ۲۹۹۰۱).
- استتار: UDP/۴۴۳ برای DPI شبیه QUIC/HTTP3 دیده می‌شود و با nginx روی TCP/۴۴۳ تداخل ندارد.
- روشن‌کردن: `ratholectl kcp on [port] [profile]` (ایران) و `ratholenode kcp on <ip:port> <key> [profile]` (نود).

## ۳) plain (بدون TLS)
- websocket بدون TLS به یک listener جداگانه‌ی HTTP (پیش‌فرض ۸۸۸۰).
- سبک‌تر، ولی مسیر تونل بدون رمز nginx است.
- روشن‌کردن: `ratholectl plain on [port]` و `ratholenode plain on <ip:port>`.

## ۴) noise (رمزنگاری‌شده، بدون TLS/گواهی)
- یک **اینستنس دوم rathole** (`rathole-noise`) روی یک پورت TCP عمومی (پیش‌فرض ۲۳۳۴).
- transport از نوع Noise (X25519)؛ کلید خصوصی روی ایران می‌ماند، کلید عمومی منتشر می‌شود.
- سرویس نودهای noise از `server.toml` به `noise-server.toml` جابه‌جا می‌شود.
- روشن‌کردن: `ratholectl noise on [port]` سپس `ratholectl noise node <name> on`؛ نود: `ratholenode noise on <ip:port> <pubkey> [pattern]`.

## ۵) game / SNI (لایه ۴ passthrough)
- وقتی هر نودی `sni` داشته باشد، پورت ۴۴۳ به حالت **stream/SNI** در nginx (passthrough لایه ۴) می‌رود و vhost لایه ۷ (path/WS) به یک پورت داخلی (`internal_port`، پیش‌فرض ۸۴۴۳) منتقل می‌شود.
- TLSِ ترافیک game روی **نود** خاتمه می‌یابد (گواهی واقعی، VLESS+TLS+Vision) — ایران فقط بایت‌ها را رد می‌کند.
- روشن‌کردن: `ratholectl game add <name> <node_tls_inbound_port> <sni>`.

---

**نکته‌ی کلیدی:** در حالت‌های ۱ تا ۴، سرویس‌ها/توکن‌ها/مسیر کاربران دست‌نخورده می‌مانند؛ فقط حاملِ تونل عوض می‌شود. برای جزئیات مسیر بسته لایه‌به‌لایه: [`traffic-flow.md`](traffic-flow.md).
