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
GET    /api/servers/<name>/status وضعیت زنده (doctor/kcp/noise/upstreamها)
GET    /api/servers/<name>/overview خلاصهٔ داشبورد؛ حالا فیلد version={manager,rathole} دارد
GET    /api/servers/<iran>/nodeconnect/<node>  token/inbound واقعی یک نود ایران (برای «افزودن به نود»)
GET    /api/hubstatus             وضعیت هاب؛ حالا شامل latest_version (نسخهٔ مرجع مقایسه)
POST   /api/servers/<name>/action {"action":"...","args":{...}}
```
- `action=status` روی سرور ایران خروجی کامل JSON داشبورد را می‌دهد (`ratholectl status --json`).
- `overview` هر سرور اکنون فیلد `version` (شامل `manager` و `rathole`) دارد که در UI با `latest_version` هاب مقایسه می‌شود.
- `/api/servers/<iran>/nodeconnect/<node>`: نام/توکن/inbound واقعی یک نود تعریف‌شده روی همان ایران را برمی‌گرداند (توکن در `ls` mask است؛ از `ratholectl show <node>` گرفته می‌شود) تا با یک دکمه به نود/اپ‌استریم خارج سیم‌کشی شود.
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
- **مشترک**: `deploy` (آپدیت از راه دور: اسکریپت‌ها را روی خود سرور از GitHub می‌گیرد + اجرای `install.sh --update`)
- **iran**: `ls`, `doctor`, `kcp_status`, `kcp_show`, `kcp_on{port,profile}`, `kcp_off`, `tune`, `regen`, `game_ls`, `game_add{name,inbound,sni}`, `game_rm{name}`, `game_show{name}`, `game_cert{sni}`
  - وضعیت و نسخه: `status` (→ `ratholectl status --json`، خروجی کامل داشبورد)، `paths` (→ `ratholectl paths`)، `version` (→ `ratholectl version`).
  - `game_cert` گواهی Let's Encrypt می‌گیرد (نیاز: DNSِ SNI به سرور + پورت ۸۰ آزاد). خروجی شامل **کلید خصوصی** است؛ فقط از طریق هابِ احرازشده استفاده کن و لاگ نگه ندار.
  - مدیریت نود: `add_node{name,inbound,api_port?}`, `rm_node{name}`, `show_node{name}` (توکن نصب نود را می‌دهد)
  - **توگل حالت‌های ورودی/transport**: `plain_on{port}`/`plain_off`/`plain_status`/`plain_show`, `noise_on{port}`/`noise_off`/…, و **`direct_status`/`direct_show`/`direct_off`/`direct_on{port,header}`** برای حالتِ direct-IP (مسیریابی با هدر، بدون TLS). فرمِ UI فیلدهای `port` و `header` را می‌گیرد و هر آرگومان با regex اعتبارسنجی می‌شود (`RE_PORT`، `RE_HEADER = ^[A-Za-z0-9-]{1,40}$`) و به‌صورت argv جدا پاس می‌شود — نه رشتهٔ شل.
  - کشف: `GET /api/servers/<iran>/discover` → لیست نودهای تعریف‌شده در state آن ایران
- **node**: `show`, `ls`, `upstream_ls`, `kcp_status`, `kcp_on{remote,key,profile}`, `kcp_off`, `upstream_kcp_on{id,remote,key,profile}`, `upstream_kcp_off{id}`, `migrate`, `tune`, `apply`, `version` (→ `ratholenode version`)
  - **تنظیم تانل اصلی**: `set_server{server}` (→ `ratholenode set SERVER <host[:port]>`) — تانل اصلی نود را به یک سرور ایران وصل می‌کند؛ `server` با `RE_IPPORT` یا `RE_HOST` اعتبارسنجی می‌شود.
  - مدیریت سرویس: `add_svc{name,token,inbound}`, `rm_svc{name}`, `upstream_add{id,server,host?}`, `upstream_add_svc{id,name,token,inbound}`
    - `add_svc` (روی تانل اصلی) و `upstream_add_svc` (روی یک اپ‌استریم خاص) بدنهٔ جریانِ **«افزودن به نود»** هستند: نام/توکن/inbound از `nodeconnect` سرور ایران گرفته و همان‌جا روی نود خارج سیم‌کشی می‌شوند.

UI هنگام باز شدن، وضعیت همه‌ی سرورها را خودکار بارگذاری می‌کند.

همه‌ی ورودی‌ها با regex سخت اعتبارسنجی می‌شوند (ضد تزریق).

## امکانات UI (نسخهٔ ۱.۴.۵ به بعد)
جزئیات کامل UI در `docs/hub.md` است؛ سرفصل‌ها:
- **دکمهٔ «آپدیت همه»**: سرورها را یکی‌یکی با `deploy` آپدیت می‌کند و پیشرفت را با progress bar نشان می‌دهد.
- **نمایش نسخهٔ هر سرور**: badge سبز/زرد که `version` هر سرور (از `overview`) را با `latest_version` هاب مقایسه می‌کند؛ زرد یعنی قدیمی‌تر و نیاز به آپدیت.
- **دکمهٔ «افزودن به نود»**: نود ایران را با یک کلیک به یک نود/اپ‌استریم خارج سیم‌کشی می‌کند (token/inbound از `nodeconnect` → `add_svc`/`upstream_add_svc`).
- **دکمهٔ «تنظیم تانل اصلی»** + select **«سرور ایران»** در فرم نصب خودکار: تانل اصلی نود را به یکی از سرورهای ایرانِ ثبت‌شده در هاب وصل می‌کند (`set_server`).

## وضعیت
پیاده‌سازی‌شده: مدیریت inventory، وضعیت زنده، action های امن با whitelist، افزودن/حذف نود و سرویس با فرم، سیم‌کشی «افزودن به نود»، تنظیم تانل اصلی، آپدیت تک‌سرور و «آپدیت همه»، و نمایش نسخه با badge مقایسه‌ای. مراحل بعد: نمودار سلامت، لاگ زنده، مدیریت پیشرفتهٔ گواهی game.
