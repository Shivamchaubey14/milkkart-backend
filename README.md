<div align="center">

# 🥛 MilkKart Backend

**The REST API powering MilkKart — a hyperlocal dairy quick-commerce platform.**

One stateless Django backend serving three clients: the customer storefront, the admin console and the rider delivery app (web + React Native mobile).

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.1-092E20?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.15-A30000?logo=django&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8-4479A1?logo=mysql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.4-37814A?logo=celery&logoColor=white)
![CI](https://img.shields.io/badge/CI-ruff%20%2B%20pytest-2088FF?logo=githubactions&logoColor=white)

</div>

---

## 🏗️ System Shape

```
   iOS / Android (Expo)        Web storefront (static JS)        Rider & Admin surfaces
            └──────────────────────────┬──────────────────────────────────┘
                              HTTPS / JSON (REST)
                                       │
                        ┌──────────────▼──────────────┐
                        │   Django REST API (DRF)     │   stateless · JWT · throttled
                        └──────────────┬──────────────┘
          ┌───────────────┬────────────┼───────────────┬───────────────┐
          ▼               ▼            ▼               ▼               ▼
        MySQL 8         Redis        Celery        UPI / Razorpay    Email / SMS
     (primary store)  (cache +     (async tasks:    (payments +      (OTP & receipts)
                       channels)    OTP, emails)      webhook)
```

The API is the single contract — every feature is built once here and consumed by all three clients. See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full design, the gateway-agnostic UPI payment flow, and the scaling path to ~1M users.

## 🚀 Features

| Domain | What it does |
|---|---|
| 🔐 **Auth** (`accounts`) | Passwordless **phone OTP login** (SMS + email delivery) → JWT access/refresh. Phone numbers are normalized (`9876543210` ≡ `+919876543210`). Role-based access: customer / support / ops / warehouse / admin |
| 🛍️ **Catalog** (`catalog`) | Products, categories, pack variants, discounts, ratings & reviews |
| 🛒 **Cart & Orders** (`cart`, `orders`) | Server-side cart, coupons, delivery-fee rules, order lifecycle (pending → confirmed → packed → out for delivery → delivered) with a **delivery-OTP handshake** |
| 💳 **Payments** (`payments`) | Gateway-agnostic **UPI intent/QR** payments + Razorpay integration, signature-verified webhooks with event dedup, mock gateway for dev |
| 👛 **Wallet** (`wallet`) | Balance, top-ups (UPI QR / gateway), transaction ledger; pays subscriptions |
| 🔁 **Subscriptions** (`subscriptions`) | Daily milk plans, vacation pauses, wallet billing, next-day delivery forecasts |
| 🛵 **Delivery** (`delivery`) | Rider (delivery-partner) profiles, duty status, order assignment, COD reconciliation (cash vs UPI), earnings |
| 📍 **Serviceability** (`serviceability`) | Pincode areas & map zones, delivery ETAs, waitlist for unserved areas |
| 🎯 **Promotions** (`promotions`) | Coupon codes with usage limits & validity windows, home-screen banners |
| 📦 **Inventory** (`inventory`) | Stock levels, low-stock alerts, movement ledger (sales, cancellations, imports) |
| 🧾 **Invoices & Reports** (`invoices`, `reports`) | Order invoices, sales dashboards, CSV exports |
| 🔔 **Notifications** (`notifications`) | Order events, push tokens (Expo), read/unread state |
| 🆘 **Support** (`support`) | Help-desk tickets linked to orders |
| 📥 **Bulk import** (`core`) | Admin .xlsx/.csv imports for customers, riders and inventory |

## 🛠️ Tech Stack

- **Runtime:** Python 3.12 · Django 5.1 · Django REST Framework (async views via `adrf`)
- **Async:** ASGI (Uvicorn) · Django Channels (Redis channel layer in prod)
- **Data:** MySQL 8 (utf8mb4) · Redis 7 (cache + broker)
- **Tasks:** Celery (OTP delivery, receipts, notifications) — eager in dev, workers in prod
- **Auth:** `djangorestframework-simplejwt` (JWT access/refresh)
- **API docs:** `drf-spectacular` — OpenAPI 3 schema + Swagger UI + ReDoc
- **Quality:** `ruff` linting · `pytest` test suite · GitHub Actions CI (lint → test against MySQL 8)
- **Packaging:** Docker & Docker Compose

## 📡 API Overview

All endpoints live under `/api/v1/`:

```
/api/v1/auth/            OTP send/verify, me, token refresh
/api/v1/categories/      Catalog browsing
/api/v1/products/
/api/v1/cart/            Cart & coupons
/api/v1/orders/          Orders & delivery-OTP verification
/api/v1/addresses/       Saved addresses
/api/v1/payments/        Initiate, verify, UPI confirm, webhook
/api/v1/wallet/          Balance, top-ups, transactions
/api/v1/subscriptions/   Plans, vacations, forecasts
/api/v1/coupons/         Coupon validation
/api/v1/banners/         Home banners
/api/v1/rider/           Rider app: deliveries, duty, earnings
/api/v1/serviceability/  Pincode/zone checks, waitlist
/api/v1/notifications/   User notifications
/api/v1/invoices/        Invoices
/api/v1/support/         Tickets
/api/v1/admin/…          Back-office: orders, catalog, promotions,
                         subscriptions, riders, imports, reports, settings
```

**Interactive docs:** `GET /api/docs/` (Swagger UI) · `GET /api/redoc/` (ReDoc) · `GET /api/schema/` (raw OpenAPI 3).

## ⚡ Quick Start

### Local (Windows/macOS/Linux)

```bash
# 1. Environment
cp .env.example .env                  # set DB credentials, secrets

# 2. Dependencies (Python 3.12)
python -m venv .venv
.venv/Scripts/pip install -r requirements/dev.txt     # Windows
# .venv/bin/pip install -r requirements/dev.txt       # macOS/Linux

# 3. Database (MySQL 8 running locally)
python manage.py migrate
python manage.py createsuperuser

# 4. Run — bind 0.0.0.0 so phones on your LAN can reach it
python manage.py runserver 0.0.0.0:8000
```

> 🧪 **Dev settings** (`config.settings.dev`) use an in-memory cache/channel layer and eager Celery — **no Redis or workers needed locally**; only MySQL is required. OTPs are logged and emailed in dev.

### Docker

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec django python manage.py migrate
docker compose exec django python manage.py createsuperuser
```

## 🧪 Development

```bash
ruff check .          # lint
pytest                # test suite (uses config.settings.test)
```

CI runs both on every push/PR to `main` against a real MySQL 8 service container (`.github/workflows/ci.yml`).

## 📂 Project Layout

```
milkkart-backend/
├── apps/                  # 17 domain apps (accounts, catalog, orders, payments, …)
├── config/
│   ├── settings/          # split settings: base / dev / prod / test
│   ├── urls.py            # /api/v1/… routing + OpenAPI docs
│   └── asgi.py, wsgi.py
├── docs/ARCHITECTURE.md   # system design, UPI payment flow, scaling plan
├── requirements/          # base / dev / prod pins
├── docker-compose.yml     # django + mysql + redis + celery
└── manage.py
```

## 🔗 Related Repositories

| Repo | Description |
|---|---|
| [`milkkart-mobile`](https://github.com/Shivamchaubey14/milkkart-mobile) | React Native (Expo) app — customer, admin & rider in one codebase (**screenshots there** 📱) |
| [`milkkart-web`](https://github.com/Shivamchaubey14/milkkart-web) | Web storefront + admin & rider portals (static HTML/JS) |

## 📄 License

Proprietary — all rights reserved.
