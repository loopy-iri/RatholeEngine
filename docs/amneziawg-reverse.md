# تونل ریورس AmneziaWG — هاب ایران + خروجی خارج + کاربران WireGuard

سیستم جدا از rathole. هدف: کاربرِ WireGuard به **سرور ایران** وصل می‌شود، و ایران ترافیک را از
طریق یک لینک **AmneziaWG مبهم و ریورس** به سرور خارج (که IPش فیلتر است) می‌فرستد و از آنجا
به اینترنت خارج می‌شود.

```
User WG  ──plain WG (داخلی)──►  Iran HUB  ──AmneziaWG (مبهم، reverse)──►  Foreign EXIT  ──NAT──► Internet
 10.67.0.x                      wg-users 10.67.0.1                       awg-exit 10.66.0.2
                                awg-exit 10.66.0.1
        (خارج با Endpoint=ایران + keepalive وصل می‌شود → reverse)
```

- `wg-users`  : اینترفیس پلین WireGuard روی ایران برای کاربرها (داخلی، بدون مبهم‌سازی).
- `awg-exit`  : اینترفیس AmneziaWG بین ایران↔خارج (مبهم؛ خارج شروع‌کننده = reverse).
- خروجی به اینترنت روی **نود خارج** با NAT انجام می‌شود.

> پیش‌نیاز تصمیم: قبلش تست کن خارج→ایران UDP رد می‌شود (`nc -u`). اگر رد نشد، AmneziaWG ریورس
> جواب نمی‌دهد و باید لینک را داخل rathole/TLS ببری (UDP-over-TCP).

---

## ۰) نصب (روی هر دو سرور)

Ubuntu/Debian:
```bash
# AmneziaWG (برای لینک خارج↔ایران)
add-apt-repository -y ppa:amnezia/ppa || true
apt update
apt install -y amneziawg amneziawg-tools 2>/dev/null || apt install -y amneziawg-dkms amneziawg-tools
# روی هاب ایران، WireGuard معمولی هم لازم است (اینترفیس کاربرها)
apt install -y wireguard wireguard-tools
```
ابزارها: `awg` و `awg-quick` (برای AmneziaWG) و `wg`/`wg-quick` (برای کاربرها).

---

## ۱) کلیدها و پارامترهای مبهم‌سازی (یک‌بار، روی ایران بساز)

```bash
# کلید لینک خارج↔ایران
awg genkey | tee iran_exit.key  | awg pubkey > iran_exit.pub
awg genkey | tee foreign.key    | awg pubkey > foreign.pub
# کلید اینترفیس کاربرها (پلین WG)
wg  genkey | tee iran_users.key | wg  pubkey > iran_users.pub
```

پارامترهای obfuscation (باید **دو طرفِ لینک خارج↔ایران مو‌به‌مو یکی** باشند):
```
Jc=4  Jmin=40  Jmax=1000  S1=50  S2=100
H1=1234567  H2=2345678  H3=3456789  H4=4567890     # اعداد تصادفی یکتا — همین‌ها را دو طرف بگذار
```

---

## ۲) سرور ایران (HUB)

### الف) اینترفیس لینک خارج: `/etc/amnezia/amneziawg/awg-exit.conf`
```ini
[Interface]
Address = 10.66.0.1/24
ListenPort = 51821
PrivateKey = <iran_exit.key>
MTU = 1380
Jc = 4
Jmin = 40
Jmax = 1000
S1 = 50
S2 = 100
H1 = 1234567
H2 = 2345678
H3 = 3456789
H4 = 4567890
Table = off
PostUp  = sysctl -w net.ipv4.ip_forward=1
PostUp  = ip route add default dev %i table 200
PostUp  = ip rule add from 10.67.0.0/24 table 200
PostUp  = iptables -t nat -A POSTROUTING -o %i -j MASQUERADE
PostDown= ip rule del from 10.67.0.0/24 table 200
PostDown= ip route del default dev %i table 200
PostDown= iptables -t nat -D POSTROUTING -o %i -j MASQUERADE

[Peer]
# نود خارج (خروجی). بدون Endpoint چون خارج خودش وصل می‌شود (reverse)
PublicKey = <foreign.pub>
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

### ب) اینترفیس کاربرها: `/etc/wireguard/wg-users.conf`
```ini
[Interface]
Address = 10.67.0.1/24
ListenPort = 51820
PrivateKey = <iran_users.key>
MTU = 1320
# هر کاربر یک [Peer] (با awgctl/دستی اضافه می‌شود)

[Peer]
PublicKey = <user1.pub>
AllowedIPs = 10.67.0.2/32
```

منطق routing: `ip rule from 10.67.0.0/24 table 200` ترافیک کاربرها را به جدول ۲۰۰ می‌برد که
default آن `dev awg-exit` است؛ AllowedIPs=0.0.0.0/0 روی peer خارج باعث می‌شود WG آن را
به خارج رمز/ارسال کند؛ MASQUERADE روی awg-exit باعث می‌شود خارج فقط 10.66.0.1 را ببیند.

---

## ۳) سرور خارج (EXIT) — `/etc/amnezia/amneziawg/awg-exit.conf`
```ini
[Interface]
Address = 10.66.0.2/24
PrivateKey = <foreign.key>
MTU = 1380
Jc = 4
Jmin = 40
Jmax = 1000
S1 = 50
S2 = 100
H1 = 1234567
H2 = 2345678
H3 = 3456789
H4 = 4567890
PostUp  = sysctl -w net.ipv4.ip_forward=1
PostUp  = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown= iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
# هاب ایران. خارج به ایران وصل می‌شود (reverse)
PublicKey = <iran_exit.pub>
AllowedIPs = 10.66.0.0/24
Endpoint = <IRAN_PUBLIC_IP>:51821
PersistentKeepalive = 25
```
`eth0` را با اینترفیس اینترنت واقعی نود عوض کن (`ip route get 1.1.1.1`).

---

## ۴) بالا آوردن

روی **ایران**:
```bash
awg-quick up awg-exit
wg-quick  up wg-users
systemctl enable awg-quick@awg-exit wg-quick@wg-users
```
روی **خارج**:
```bash
awg-quick up awg-exit
systemctl enable awg-quick@awg-exit
```

بررسی لینک:
```bash
awg show awg-exit            # باید latest handshake و transfer داشته باشد
```

---

## ۵) کانفیگ کاربر (پلین WireGuard)
```ini
[Interface]
PrivateKey = <user1.key>
Address = 10.67.0.2/32
DNS = 1.1.1.1
MTU = 1280

[Peer]
PublicKey = <iran_users.pub>
AllowedIPs = 0.0.0.0/0
Endpoint = <IRAN_PUBLIC_IP>:51820
PersistentKeepalive = 25
```
کاربر با اپ معمولی WireGuard وصل می‌شود (نیازی به AmneziaWG برای کاربر نیست؛ چون داخلیه).

---

## ۶) تست end-to-end
- روی خارج: `awg show` → handshake با ایران برقرار.
- کاربر وصل شود، بعد: `curl ifconfig.me` → باید **IP نود خارج** را بدهد (نه ایران).
- اگر کاربر وصل شد ولی نت نیامد → مشکل routing/NAT روی ایران (جدول ۲۰۰ یا MASQUERADE) یا forward روی خارج.

---

## نکات حیاتی
- **MTU پایین** (کاربر 1280، اینترفیس‌ها 1320/1380) — دابل‌کپسوله، وگرنه دانلود گیر می‌کند.
- **PersistentKeepalive = 25** هم روی لینک خارج (برای زنده‌ماندن reverse) هم روی کاربر.
- **پارامترهای obfuscation دو طرفِ awg-exit دقیقاً یکی** — یک رقم فرق = handshake نمی‌شود.
- اگر خارج→ایران UDP اصلاً رد نشد، این روش کار نمی‌کند؛ آن‌وقت لینک را داخل rathole/TLS ببر.
- خروجی به اینترنت روی **خارج** NAT می‌شود؛ `ip_forward=1` روی هر دو لازم است.

پس از تأیید روی سرورها، این جریان را به اسکریپت‌های `awg-iran.sh` / `awg-node.sh` / `awgctl`
(مدیریت کاربر) تبدیل می‌کنیم — کلیدها و obfuscation و routing خودکار.
