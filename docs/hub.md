# ratholehub — پنل وب مدیریت (REST API + UI)

پنل مرکزی برای مدیریت ویژوال چند سرور ایران و چند نود، بدون تداخل با سیستم فعلی.

![معماری هاب](assets/hub-architecture.svg)

*هاب روی `127.0.0.1` پشت nginx `/hub/` می‌شنود و با SSH (کلید) روی هر سرور، `ratholectl`/`ratholenode` را با یک **argv اعتبارسنجی‌شده** اجرا می‌کند — هرگز رشته‌ی شل خام.*

## چرا این طراحی
- **بدون agent روی نودها**: پنل فقط روی یک سرور (معمولاً rp01) نصب می‌شود و از طریق **SSH با کلید** همان `ratholectl`/`ratholenode` تست‌شده را روی بقیه اجرا می‌کند. هیچ پورت/سرویس جدیدی روی نودها باز نمی‌شود.
- **بدون وابستگی pip**: فقط پایتون stdlib. با هیچ‌چیز روی سرور تداخل نمی‌کند.
- **REST API توکن‌دار**: برای اتصال ابزارهای دیگر/اتوماسیون و کنترل وضعیت.
- **امن**: روی `127.0.0.1` می‌شنود؛ دسترسی از طریق SSH-forward یا nginx زیر همان دامنه (یک پورت/یک دامنه حفظ می‌شود). جزئیات در [مدل امنیتی](#مدل-امنیتی).

## نصب
```bash
cd rathole-manager/ratholehub
sudo bash install-hub.sh          # رمز مدیریت می‌پرسد، API TOKEN تولید می‌کند
```

### افزودن سرورها — دو راه

**راه ساده (پیشنهادی): دکمه‌ی «نصب خودکار» (provision) در داشبورد** — یا `POST /api/provision`. یک‌بار با **رمز SSH** به سرور وصل می‌شود (نیازمند `sshpass` روی هاب)، کلید عمومی هاب را به `authorized_keys` اضافه می‌کند (idempotent)، همان‌جا deploy از GitHub را اجرا و سرور را در inventory ثبت می‌کند. کلید هاب از config (`ssh_key_path`؛ نصاب `/root/.ssh/id_ed25519` می‌سازد) می‌آید و اگر خالی باشد هاب خودش `/etc/ratholehub/id_ed25519` تولید می‌کند.

**راه دستی:** خودت کلید را ست کن:
```bash
ssh-copy-id -i /root/.ssh/id_ed25519.pub root@<node_ip>
ssh-copy-id -i /root/.ssh/id_ed25519.pub root@<iran2_ip>
```

## دسترسی
امن‌ترین (بدون باز کردن پورت) — از سیستم خودت:
```bash
ssh -L 8088:127.0.0.1:8088 root@<rp01_ip>
# مرورگر:  http://localhost:8088
```
یا پشت nginx زیر همان دامنه: `sudo ratholectl hub on 8088` → `https://<domain>/hub/`. (بار اول اگر هاب نصب نباشد خودش `install-hub.sh` را اجرا می‌کند؛ دفعات بعد پورت واقعی هاب را عوض و سرویس را ری‌استارت می‌کند.)

## رابط کاربری (UI)

UI تک‌فایل داخل `hub.py` است: **sidebar + hash-router** (پس زیر `/hub/` هم کار می‌کند)، دوزبانه‌ی **فارسی/انگلیسی**، ریسپانسیو، با رفرش خودکار هوشمند (هر ۲۰ ثانیه فقط داده‌ی صفحه‌ی فعال؛ قابل خاموش‌کردن).

| صفحه | محتوا |
|------|-------|
| **داشبورد** (`#/dashboard`) | کارت هر سرور (ایران/نود) با نقش، وضعیت دسترس‌پذیری، badge نسخه و دکمه‌های سریع. فرم **افزودن سرور** و **نصب خودکار** (provision)، و دکمه‌ی **«آپدیت همه»** (پایینِ توضیحات). |
| **صفحه سرور** (`#/server/<name>`) | نمای کاملِ یک سرور: برای سرور ایران جدول نودها + مدیریت transport (kcp/plain/game/noise)، و برای نود جدول سرویس‌ها + تانل اصلی. دکمه‌های **وضعیت**، **آپدیت** و badge نسخه اینجا هم هستند. |
| **مسیریابی / کنسول** (`#/routing`) | نمای گرافیکی مسیر ترافیک: ورودی کاربر (ingress) در برابر تانل نود (transport)، با دیاگرام SVG قابل‌کلیک (هر نود به صفحه‌ی خودش لینک می‌شود). |
| **لاگ‌ها / audit** (`#/audit`) | تاریخچه‌ی همه‌ی عملیات انجام‌شده روی سرورها (چه کسی، کدام سرور، کدام action، rc). هر عمل روی سرور از طریق `audit_log` ثبت می‌شود. |
| **تنظیمات** (`#/settings`) | پیکربندی هاب: زبان (فارسی/انگلیسی)، رفرش خودکار، مسیر کلید SSH، slug مخزن GitHub و توکن API. |

## قابلیت‌های تازه (v1.4.5–v1.4.7)

- **دکمه «وضعیت» (Status)** روی صفحه‌ی هر سرور ایران — action `status` را می‌زند (`ratholectl status --json`) و خروجی را به‌جای متن خام، به‌صورت یک **داشبورد** زیبا رندر می‌کند: جدول پورت‌ها (کنترل/sub/internal/plain/direct/hub/noise)، وضعیت **گواهی** (تاریخ انقضا + badge اگر self-signed)، و جدول **نودها** (name / port / inbound / URL کاربر). اگر خروجی JSON معتبر نبود، به نمایش متنی برمی‌گردد.

- **دکمه «آپدیت همه» (apdit-e hame)** در داشبورد — همه‌ی سرورها را **یکی‌یکی و ترتیبی** از طریق action `deploy` (معادل `install.sh --update` با snapshot + rollback خودکار) آپدیت می‌کند. یک **progress bar** با شمارنده‌ی `done/total` نشان داده می‌شود و وضعیت زنده‌ی هر سرور کنار نامش می‌آید: **در صف** (upd_wait) → **در حال آپدیت** → **✓** (به‌همراه نسخه‌ی جدیدِ خوانده‌شده) یا **✗ (rc=…)**. نکته‌ی مهم: خودِ سروری که هاب روی آن اجرا می‌شود هم در این لیست است؛ چون آپدیت ممکن است سرویس هاب را ری‌استارت کند، ممکن است progress همان یک سطر نیمه‌کاره بماند (بقیه با موفقیت تمام می‌شوند).

- **نمایش نسخه روی هر سرور** — روی کارت/صفحه‌ی هر سرور یک **badge نسخه** نشان داده می‌شود: **سبز** یعنی هم‌سان با آخرین نسخه، **زرد** به‌شکل `vX → vY` یعنی قدیمی است و نیاز به آپدیت دارد. نسخه‌ی هر سرور از خروجی `ratholectl`/`ratholenode version` خوانده می‌شود (خطوط `manager_version=`/`rathole_version=`) و با `latest_version` در `GET /api/hubstatus` مقایسه می‌گردد — که خودِ هاب آن را از `MANAGER_VERSION` در `common.sh` (بخشی از bundle که deploy می‌شود) می‌خواند.

- **دکمه «افزودن به نود» (wire-to-node)** در جدول نودهای هر سرور ایران — یک نود ایران (با name/token/inbound واقعی‌اش) را روی یک نود خارج یا اپ‌استریمِ آن به‌عنوان سرویس اضافه می‌کند تا سیم‌کشی تانل کامل شود. مقصدها همه‌ی نودها و اپ‌استریم‌هایشان‌اند؛ آن‌هایی که تانلشان به همین سرور ایران وصل است با ✓ علامت خورده و پیش‌فرض انتخاب می‌شوند. endpoint تازه: `GET /api/servers/<iran>/nodeconnect/<node>` که token/inbound واقعی نود ایران را می‌گیرد (چون در `ls` ماسک شده)، سپس با `add_svc` (یا `upstream_add_svc` برای اپ‌استریم) روی مقصد اجرا می‌شود.

- **دکمه «تنظیم تانل اصلی» (set main tunnel)** در صفحه‌ی هر نود — نود را با ست‌کردن `SERVER=host:443` (از طریق action `set_server`) به یک سرور ایرانِ ثبت‌شده در هاب وصل می‌کند. علاوه‌بر این، فرمِ **نصب خودکار** (provision) حالا یک select «سرور ایران» دارد؛ اگر نقش سرورِ در حال نصب `node` باشد، هاب بعد از deploy موفق به‌طور خودکار تانل اصلی را به آن سرور ایران ست می‌کند تا نود از همان ابتدا «?» نشان ندهد.

## REST API (نمونه)

همه‌ی مسیرها با هدر `Authorization: Bearer <API_TOKEN>` (یا کوکی نشست از UI).

```
GET    /api/health
POST   /api/login                            {"password":"..."} → {token}
GET    /api/hubstatus                         وضعیت هاب + latest_version (آخرین نسخه‌ی bundle)
GET    /api/servers                           لیست سرورها
POST   /api/servers                           {name,role(iran|node),host,ssh_user,ssh_port}
DELETE /api/servers/<name>
POST   /api/provision                         نصب خودکار (کلید SSH + deploy + ثبت)
GET    /api/servers/<name>/status             وضعیت (doctor/kcp/upstreamها)
POST   /api/servers/<name>/action             {"action":"...","args":{...}}
GET    /api/servers/<iran>/nodeconnect/<node> token/inbound واقعی نود ایران (برای wire-to-node)
```

نمونه:

```bash
TOKEN=... ; B=http://localhost:8088
curl -s -H "Authorization: Bearer $TOKEN" $B/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST $B/api/servers/rp01/action \
  -d '{"action":"status","args":{}}'
```

## مدل امنیتی

هاب هیچ‌وقت **رشته‌ی خام** روی سرورها اجرا نمی‌کند. هر درخواست به یک `action` مجاز از allow-list نگاشت می‌شود و آرگومان‌ها با regex (خانواده‌ی `RE_*`) اعتبارسنجی می‌شوند؛ سپس `build_iran_cmd`/`build_node_cmd` آن را به یک **argv لیستی** تبدیل می‌کنند که هر آرگومان جدا از طریق SSH پاس می‌شود (`run_on_server` → `_ssh_base`) — نه interpolation در شل.

- **whitelist دقیق**: هر action تازه باید هم به `build_*_cmd` مربوطه و هم به allow-list افزوده شود و هر آرگومانش با regex بررسی شود.
- **مشترک (هر دو نقش)**: `deploy` (آپدیت از راه دور: در خودِ سرور `install.sh --update` از آخرین Release گرفته می‌شود؛ snapshot + rollback خودکار)، `status`, `version`.
- **iran**: `ls`, `doctor`, `status`, `regen`, مدیریت transport (`kcp_*`, `plain_*`, `noise_*`, `direct_*`)، مدیریت game (`game_*` — `game_cert` گواهی Let's Encrypt می‌گیرد و خروجی شامل **کلید خصوصی** است؛ فقط از هابِ احرازشده استفاده کن و لاگ نگه ندار)، و مدیریت نود (`add_node`, `rm_node`, `show_node`).
- **node**: `show`, `ls`, `upstream_ls`, `set_server`, مدیریت سرویس (`add_svc`, `rm_svc`, `upstream_add`, `upstream_add_svc`)، transport (`kcp_*`, `upstream_kcp_*`, `noise_*`) و `apply`.
- روی `127.0.0.1` می‌شنود (پشت nginx زیر `/hub/` یا SSH-forward)؛ هیچ پورت عمومی جدیدی باز نمی‌شود.
- `deploy_to_server` (دکمه‌ی «آپدیت»/«آپدیت همه») روی خودِ سرور آخرین `install.sh` را از GitHub (از طریق حلقه‌ی mirror ghproxy) می‌گیرد و با `--update` اجرا می‌کند؛ slug مخزن از config (`gh_repo`، پیش‌فرض `loopy-iri/RatholeEngine`، اعتبارسنجی با `RE_SLUG`) می‌آید و تنها همان slugِ اعتبارسنجی‌شده در دستور ثابت `bash -c` جای‌گذاری می‌شود.
- هر عمل موفق/ناموفق در **audit log** ثبت می‌شود (کاربر، سرور، action، rc) — قابل‌مشاهده در صفحه‌ی `#/audit`.