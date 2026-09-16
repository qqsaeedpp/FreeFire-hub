# 🎮 FreeFire Hub — ربات فروشگاهی تلگرام

رباتی حرفه‌ای و **Production-Ready** برای فروش جم و خرید/فروش اکانت بازی Free Fire،
ساخته‌شده با **Aiogram 3**، **SQLAlchemy 2.0 Async + MySQL 8**، **Redis** و **Alembic**،
بر پایهٔ معماری **Clean Architecture + Repository Pattern + Service Layer**.

---

## ✨ امکانات

| بخش | توضیح |
|------|-------|
| 💎 خرید جم | با **UID** یا با **اطلاعات اکانت** (ایمیل/رمز/کد بکاپ/روش ورود) |
| 🛒 خرید اکانت | لیست، صفحه‌بندی، جستجو، فیلتر قیمت، جزئیات و تصاویر، رزرو موقت |
| 💰 فروش اکانت | ارسال مشخصات و تصاویر توسط کاربر و ثبت در پنل مدیریت |
| 📝 اکانت درخواستی | ثبت سفارش با بیعانه (پیش‌فرض ۳۰۰٬۰۰۰ تومان) |
| 🎁 زیرمجموعه‌گیری | کد و لینک دعوت، پاداش پس از **تکمیل احراز هویت** زیرمجموعه |
| 🔐 احراز هویت | تأیید شمارهٔ موبایل ایران با دکمهٔ رسمی تلگرام + کپچای ریاضی ساده |
| 👛 کیف پول | موجودی، شارژ، تاریخچهٔ تراکنش‌ها |
| 🎧 تیکت و پشتیبانی | ثبت تیکت با فایل/عکس، پاسخ و بستن توسط ادمین |
| 🛠 پنل مدیریت | آمار، مدیریت سفارش‌ها، افزودن اکانت، قیمت جم، کیف پول، پیام همگانی |
| 📋 سیستم لاگ | ارسال همهٔ رویدادها به کانال لاگ |

**قابلیت‌های فنی:** Async کامل، Dependency Injection، Rate-Limit/Anti-Spam، Structured Logging،
مدیریت خطا و گزارش به کانال، Retry، بکاپ خودکار دیتابیس، رمزنگاری اطلاعات حساس اکانت، Docker.

---

## 🏗 معماری

```
app/
├── core/          # config, database, redis, security, logger, constants
├── models/        # SQLAlchemy models
├── repositories/  # Repository Pattern (data access)
├── services/      # Service Layer (business logic)
├── handlers/      # user / admin / support (Aiogram routers)
├── middlewares/   # database, throttling (anti-spam), ban
├── filters/       # IsAdmin
├── keyboards/     # reply / inline / callback factories
├── states/        # FSM (user/admin) با قابلیت Back/Cancel
├── scheduler/     # APScheduler tasks (cleanup + backup)
├── utils/         # validators, helpers, error notifier
├── container.py   # DI container (Services)
└── main.py        # entrypoint
```

جریان هر آپدیت: `Throttling → Database (load user + Services) → Ban check → Handler`.
هر هندلر یک `Services` آماده دریافت می‌کند که تمام repository و service ها را در خود دارد.

---

## 🚀 اجرا با Docker (پیشنهادی)

```bash
sudo git clone git@github.com:qqsaeedpp/FreeFire-hub.git /opt/freefire-hub
sudo chown -R $USER:$USER /opt/freefire-hub
cd /opt/freefire-hub
cp .env.example .env
nano .env          # مقادیر واقعی را وارد کنید (حداقل BOT_TOKEN)
docker compose up -d --build
docker compose logs -f bot
```

migration ها هنگام استارت کانتینر به‌صورت خودکار اجرا می‌شوند (`alembic upgrade head`).

---

## 🐧 اجرا روی سرور Ubuntu 24.04

```bash
# 1) نصب Docker + Compose plugin
sudo apt update && sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2) دریافت کد در مسیر /opt و تنظیم محیط
sudo git clone git@github.com:qqsaeedpp/FreeFire-hub.git /opt/freefire-hub
sudo chown -R $USER:$USER /opt/freefire-hub
cd /opt/freefire-hub
cp .env.example .env && nano .env

# 3) اجرا
sudo docker compose up -d --build
sudo docker compose logs -f bot
```

> مسیر استقرار پروژه روی سرور: <code>/opt/freefire-hub</code>.
> برای به‌روزرسانی بعدی کافی است در همین مسیر `git pull` بزنید و دوباره
> `sudo docker compose up -d --build` را اجرا کنید.

ربات با `restart: unless-stopped` پس از ری‌استارت سرور هم خودکار بالا می‌آید.

### اجرای دستی (بدون Docker)

```bash
sudo apt install -y python3.12 python3.12-venv build-essential default-libmysqlclient-dev pkg-config
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# MySQL و Redis باید در دسترس باشند و مقادیر .env تنظیم شده باشد
alembic upgrade head
python -m app.main
```

---

## ⚙️ متغیرهای محیطی (`.env`)

| متغیر | توضیح |
|-------|-------|
| `BOT_TOKEN` | توکن ربات از BotFather |
| `ADMIN_ID` | آیدی عددی ادمین اصلی (پیش‌فرض: `707967792`) |
| `LOG_CHAT_ID` | آیدی کانال لاگ (پیش‌فرض: `-1001546889015`) |
| `LISTING_CHANNEL_ID` | کانالی که هر آگهی «اکانت جدید برای فروش» عیناً در آن هم منتشر می‌شود؛ ربات باید ادمین کانال باشد، `0` = خاموش (پیش‌فرض: `-1003783566987`) |
| `LISTING_BUY_USERNAME` | مقصد دکمهٔ سبز «✅ خرید» زیر آگهی اکانت جدید (پیش‌فرض: `ffshah_bot`) |
| `MYSQL_*` | تنظیمات اتصال MySQL |
| `REDIS_*` | تنظیمات اتصال Redis |
| `REFERRAL_REWARD` | پاداش زیرمجموعه (پیش‌فرض ۱۰٬۰۰۰) |
| `REQUESTED_ACCOUNT_DEPOSIT` | بیعانهٔ اکانت درخواستی (پیش‌فرض ۳۰۰٬۰۰۰) |
| `CARD_NUMBER` / `CARD_HOLDER` | شماره کارت و نام صاحب کارت |
| `RATE_LIMIT_PER_SECOND` | سقف پیام در ثانیه برای هر کاربر |
| `CAPTCHA_TTL_SECONDS` | مدت اعتبار هر کپچا (پیش‌فرض ۳۰۰ ثانیه) |
| `CAPTCHA_MAX_ATTEMPTS` | تعداد پاسخ غلط مجاز پیش از وقفه (پیش‌فرض ۳) |
| `CAPTCHA_COOLDOWN_SECONDS` | مدت وقفهٔ پس از پاسخ‌های غلط (پیش‌فرض ۶۰ ثانیه) |

> **نکته امنیتی:** فایل `.env` در `.gitignore` قرار دارد و نباید کامیت شود.
> کلید رمزنگاری اطلاعات اکانت از `BOT_TOKEN` مشتق می‌شود؛ برای پروداکشن می‌توانید
> متغیر `ENCRYPTION_KEY` مستقل تنظیم کنید.

---

## 🔐 احراز هویت و زیرمجموعه‌گیری

هر کاربر غیرادمین پیش از دسترسی به امکانات ربات این مسیر را طی می‌کند:

```
/start  →  عضویت در کانال‌های اجباری  →  تأیید شماره موبایل  →  کپچا  →  منوی اصلی
```

* شماره فقط با دکمهٔ رسمی «📱 ارسال شماره تلفن من» گرفته می‌شود؛ شمارهٔ تایپ‌شده،
  فوروارد‌شده یا متعلق به شخص دیگر پذیرفته نمی‌شود.
* فقط شمارهٔ موبایل معتبر ایران با پیش‌شمارهٔ `+98` قبول می‌شود و به‌صورت E.164
  ذخیره می‌شود. هر شماره تنها به **یک** حساب تلگرام تعلق می‌گیرد.
  (پیش‌شمارهٔ `+98` صرفاً نشان‌دهندهٔ اپراتور ایرانی است، نه اثبات تابعیت.)
* کپچا یک جمع سادهٔ دو عدد یک‌رقمی با چهار گزینه است؛ سؤال و پاسخ روی سرور
  نگهداری می‌شود و پاسخ هرگز داخل `callback_data` قرار نمی‌گیرد.

> **زیرمجموعه زمانی ثبت می‌شود که کاربر جدید با لینک دعوت وارد شود،
> شماره موبایل ایرانی متعلق به حساب خود را تأیید کند
> و کپچای امنیتی را با موفقیت پشت سر بگذارد.**

کد دعوت از همان لحظهٔ `/start` در MySQL نگهداری می‌شود، بنابراین قفل کانال،
ری‌استارت ربات، پاک‌شدن FSM یا از دست رفتن Redis آن را از بین نمی‌برد. ثبت
زیرمجموعه، پاداش و تراکنش کیف پول همگی در **یک تراکنش واحد** انجام می‌شوند و
اعلان‌ها فقط **پس از Commit** ارسال می‌گردند.

مسیر احراز برای ادمین‌ها (چه `ADMIN_ID` و چه ادمین‌های دیتابیس) غیرفعال است.
کاربران قدیمی در اولین تعامل بعد از بروزرسانی وارد این مسیر می‌شوند؛ هیچ
زیرمجموعه یا موجودی تاریخی تغییر نمی‌کند.

---

## 🗃 مدل‌های دیتابیس

`User`, `Wallet`, `WalletTransaction`, `Order` (پایه) →
`DiamondOrder` / `AccountOrder`, `Account`, `AccountSaleRequest`, `RequestedAccount`,
`Payment`, `Referral`, `Ticket`, `TicketMessage`, `AdminLog`.

---

## 🧪 تست

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

تست‌ها روی SQLite در حافظه اجرا می‌شوند و نیازی به MySQL ندارند.

> ابزارهای تست عمداً در `requirements-dev.txt` جدا شده‌اند و داخل ایمیج Docker
> نصب نمی‌شوند: وابستگی `lupa` باید از سورس C کامپایل شود و بیلد سرور را حدود
> ۱۰ دقیقه کندتر می‌کرد، در حالی که ربات هرگز آن را import نمی‌کند.

---

## 🔧 Alembic

```bash
alembic upgrade head           # اعمال migration ها
alembic revision --autogenerate -m "message"   # ساخت migration جدید پس از تغییر مدل‌ها
```

---

## 📋 رویدادهای لاگ‌شده در کانال

کاربر جدید • سفارش جم • خرید اکانت • فروش اکانت • اکانت درخواستی •
ثبت تیکت • ثبت زیرمجموعه • پرداخت/شارژ • تکمیل سفارش • خطاهای سیستم.

---

## 📄 لایسنس

استفادهٔ شخصی/تجاری آزاد است.
