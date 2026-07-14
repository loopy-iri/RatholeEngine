# ratholehub — پنل وب مدیریت (REST API + UI)

پنل مرکزی برای مدیریت ویژوال چند سرور ایران و چند نود، بدون تداخل با سیستم فعلی.

## چرا این طراحی
- **بدون agent روی نودها**: پنل فقط روی یک سرور (معمولاً rp01) نصب می‌شود و از طریق **SSH با کلید** همان `ratholectl`/`ratholenode` تست‌شده را روی بقیه اجرا می‌کند. هیچ پورت/سرویس جدیدی روی نودها باز نمی‌شود.
- **بدون وابستگی pip**: فقط پایتون stdlib. با هیچ‌چیز روی سرور تداخل نمی‌کند.
- **REST API توکن‌دار**: برای اتصال ابزارهای دیگر/اتوماسیون و کنترل وضعیت.
- **امن**: روی `127.0.0.1` می‌شنود؛ دسترسی از طریق SSH-forward یا nginx زیر همان دامنه (یک پورت/یک دامنه حفظ می‌شود).

## نصب
```bash
cd rathole-manager/ratholehub
sudo bash install-hub.sh          # رمز مدیریت می‌پرسد، API TOKEN تولید می‌کند
```
پیش‌نیاز: از سرور پنل به بقیه سرورها SSH با کلید ست باشد:
```bash
ssh-copy-id root@<node_ip>
ssh-copy-id root@<iran2_ip>
```

## دسترسی
امن‌ترین (بدون باز کردن پورت) — از سیستم خودت:
```bash
ssh -L 8088:127.0.0.1:8088 root@<rp01_ip>
# مرورگر:  http://localhost:8088
```

## REST API (نمونه)
همه‌ی مسیرها با هدر `Authorization: Bearer <API_TOKEN>` (یا کوکی نشست از UI).
```
GET    /api/health
POST   /api/login                 {"password":"..."} → {token}
GET    /api/servers               لیست سرورها
POST   /api/servers               {name,role(iran|node),host,ssh_user,ssh_port}
DELETE /api/servers/<name>
GET    /api/servers/<name>/status وضعیت (doctor/kcp/upstreamها)
POST   /api/servers/<name>/action {"action":"...","args":{...}}
```
نمونه:
```bash
TOKEN=... ; B=http://localhost:8088
curl -s -H "Authorization: Bearer $TOKEN" $B/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST $B/api/servers/rp01/action \
  -d '{"action":"kcp_on","args":{"port":"443","profile":"balanced"}}'
```

## توپولوژی: فقط یک هاب
- **یک هاب کافی است** — نیازی به هاب روی هر ایران نیست.
- هاب برای مدیریت، مستقیم به **پورت ۲۲ (SSH)** هر سرور وصل می‌شود؛ کاملاً مستقل از توپولوژی تونل.
- اینکه یک نود به دو (یا چند) ایران وصل باشد ربطی به هاب ندارد؛ هاب هر سرور را جدا و مستقیم می‌بیند.
- تنها شرط: هاب باید با کلید SSH به هر سروری که در inventory دارد وصل شود.

## action های مجاز (whitelist، بدون شل دلخواه)
- **مشترک**: `deploy` (آپدیت از راه دور: scp اسکریپت‌ها + اجرای update.sh)
- **iran**: `ls`, `doctor`, `kcp_status`, `kcp_show`, `kcp_on{port,profile}`, `kcp_off`, `tune`, `regen`, `game_ls`, `game_add{name,inbound,sni}`, `game_rm{name}`, `game_show{name}`, `game_cert{sni}`
  - `game_cert` گواهی Let's Encrypt می‌گیرد (نیاز: DNSِ SNI به سرور + پورت ۸۰ آزاد). خروجی شامل **کلید خصوصی** است؛ فقط از طریق هابِ احرازشده استفاده کن و لاگ نگه ندار.
  - مدیریت نود: `add_node{name,inbound,api_port?}`, `rm_node{name}`, `show_node{name}` (توکن نصب نود را می‌دهد)
  - **توگل حالت‌های ورودی/transport**: `plain_on{port}`/`plain_off`/`plain_status`/`plain_show`, `noise_on{port}`/`noise_off`/…, و **`direct_status`/`direct_show`/`direct_off`/`direct_on{port,header}`** برای حالتِ direct-IP (مسیریابی با هدر، بدون TLS). فرمِ UI فیلدهای `port` و `header` را می‌گیرد و هر آرگومان با regex اعتبارسنجی می‌شود (`RE_PORT`، `RE_HEADER = ^[A-Za-z0-9-]{1,40}$`) و به‌صورت argv جدا پاس می‌شود — نه رشتهٔ شل.
  - کشف: `GET /api/servers/<iran>/discover` → لیست نودهای تعریف‌شده در state آن ایران
- **node**: `show`, `ls`, `upstream_ls`, `kcp_status`, `kcp_on{remote,key,profile}`, `kcp_off`, `upstream_kcp_on{id,remote,key,profile}`, `upstream_kcp_off{id}`, `migrate`, `tune`, `apply`
  - مدیریت سرویس: `add_svc{name,token,inbound}`, `rm_svc{name}`, `upstream_add{id,server,host?}`, `upstream_add_svc{id,name,token,inbound}`

UI هنگام باز شدن، وضعیت همه‌ی سرورها را خودکار بارگذاری می‌کند.

همه‌ی ورودی‌ها با regex سخت اعتبارسنجی می‌شوند (ضد تزریق).

## وضعیت
MVP: مدیریت inventory، وضعیت زنده، و action های امن. مراحل بعد: افزودن/حذف نود و سرویس با فرم، نمودار سلامت، لاگ زنده، مدیریت گواهی game.
