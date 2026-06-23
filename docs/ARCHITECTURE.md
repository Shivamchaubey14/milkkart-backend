# MilkKart — Architecture & Scaling

This document describes how the three MilkKart apps fit together, the
gateway‑agnostic UPI payment design, and the production path to ~1M users. It
covers what is implemented today and the load‑bearing changes still recommended.

## 1. System shape (one backend, three clients)

```
            ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
            │  iOS (Expo)  │   │ Android(Expo)│   │  Web (PWA)   │
            └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
                   └──────────────────┼──────────────────┘
                              HTTPS / JSON (REST)
                                      │
                          ┌───────────▼───────────┐
                          │  Django REST API (DRF) │  stateless, horizontally
                          │  JWT auth, throttled   │  scalable behind an LB
                          └───────────┬───────────┘
        ┌──────────────┬──────────────┼───────────────┬───────────────┐
        ▼              ▼              ▼               ▼               ▼
     MySQL/        Redis          Celery          Payment         Email/SMS
   PostgreSQL    (cache +        workers          gateway         providers
   (primary +    channels +     (async I/O)      (Razorpay)
    replicas)    broker)
```

* **Mobile (`milkkart-mobile`)** — Expo / React Native. The *same* codebase
  targets **iOS and Android**, and can render on **web** via `react-native-web`
  (Expo ships the web target). UI primitives that aren't web‑safe are isolated so
  the web target degrades gracefully (e.g. UPI app‑intent launch is Android‑only;
  the QR/poll path below is the cross‑platform fallback).
* **Web storefront (`milkkart-web`)** — static HTML/JS/CSS, CDN‑friendly, talks to
  the same REST API. Zero server render → trivially cacheable.
* **Backend (`milkkart-backend`)** — Django + DRF. Stateless request handlers
  (JWT, no server session affinity) so it scales out horizontally; all shared
  state lives in MySQL/Postgres, Redis, and the broker.

The API is the single contract. A feature is built once in the backend and all
three clients consume it — which is exactly how payments are structured below.

## 2. Gateway‑agnostic UPI payments

**Goal:** let a customer pay **without forcing a single gateway**. Any UPI app can
pay by scanning a QR (web/desktop) or via an app intent (mobile), and the wallet
is credited only after **server‑side confirmation**.

### Pieces

* `apps/payments/upi.py` — builds the NPCI `upi://pay?...` intent string from the
  merchant VPA (`settings.UPI_VPA` / `UPI_PAYEE_NAME`). The same string is the
  mobile deep link **and** the web QR payload. `tr` (transaction ref) = the
  gateway order id, so one value reconciles the payment everywhere.
* `POST /wallet/topup/` — creates a `WalletTopup`, returns:
  * `upi`: `{ intent, vpa, payee_name }` — always present (gateway‑independent),
  * `gateway`: order info — used when a real gateway (Razorpay) is configured.
* `GET /wallet/topup/<id>/status/` — **the single source of truth**, polled by all
  clients. Returns `created | success | failed` plus the fresh wallet.
* `POST /payments/webhook/` — the authoritative async confirmation. Verifies the
  signature over the raw body, dedupes by event id (`PaymentWebhookEvent`), and
  applies an **idempotent** transition via `services.capture()` (which already
  handles both order payments *and* wallet top‑ups by `gateway_order_id`).

### Flow (identical across iOS / Android / web)

```
client                         backend                         gateway / bank
  │  POST /wallet/topup/          │                                   │
  │ ────────────────────────────►│  create WalletTopup               │
  │ ◄──────────────── upi+gateway│                                   │
  │  show QR / launch UPI app     │                                   │
  │ ─────────────── user pays ───────────────────────────────────────►│
  │  GET …/status/ (poll 3s)      │                                   │
  │ ────────────────────────────►│   webhook: payment.captured       │
  │                               │◄──────────────────────────────────│
  │                               │  services.capture() → credit (idempotent)
  │ ◄────────────── success + ₩   │                                   │
```

* **With a gateway (Razorpay configured):** the webhook confirms; the poll just
  reports the resulting state. Robust auto‑reconciliation.
* **Plain merchant‑VPA QR (no gateway):** auto‑confirmation requires the VPA to be
  attached to a PSP that posts webhooks to `/payments/webhook/`. Until then the
  top‑up stays `created` (the gateway/checkout path remains the reliable fallback).
  This is the documented trade‑off of being gateway‑optional.
* **Dev (mock gateway):** there is no live webhook, so a `status` poll stands in
  for the gateway confirming — strictly a dev/demo convenience, never in prod.

### Client specifics

* **Web** (`js/pay.js`) — a method chooser offers **“Scan UPI QR”** (renders the
  intent as a QR via `qrcodejs`, polls status) or the gateway/sandbox sheet.
* **Mobile** (`WalletScreen.tsx`) — uses the backend‑built `upi.intent`. On Android
  it launches the chosen app with `expo-intent-launcher` (real UPI result read from
  the intent extras as a fast hint); on iOS it opens the link. **Both then poll
  `/status/`** — the server, not the client, decides crediting. A blocking
  “Confirming your payment…” overlay covers the wait.

### Why this is the right shape

* Money is **never credited on the client's word** — only the server, via webhook
  (prod) or status reconciliation, credits the wallet.
* Transitions are **idempotent** and **deduped**, so a webhook + a poll + a retry
  can all arrive without double‑crediting.
* Adding a second gateway later is a `gateway.py` backend change; clients are
  untouched.

## 3. Scaling to ~1M users

### Implemented now (high‑impact, low‑risk)

* **Indexes on hot paths** — `gateway_order_id` (Payment & WalletTopup; the
  reconciliation key hit on every webhook/poll) and a composite
  `(wallet, ‑created_at)` for the ledger query, which is the wallet's most
  frequent read and grows into the millions of rows.
* **Idempotent, deduped payment writes** — `PaymentWebhookEvent` unique
  `event_id`; `services.*` transitions are safe to replay.
* **Throttling** — per‑endpoint scopes: `topup` (60/h) caps gateway‑order creation;
  `topup_status` (1200/h) allows ~2 min of 3s polls; defaults `anon` 100/h,
  `user` 1000/h, `otp` 5/h.
* **Stateless JWT auth** — no server sessions → any node serves any request.
* **Async side‑effects** — email/receipts/confirmations run on Celery, off the
  request path.
* **Redis** already wired for cache + channels.

### Recommended next (documented plan)

1. **Database**
   * Move prod to **PostgreSQL** (better concurrency/partitioning) or managed MySQL
     with **read replicas**; route read‑only queries (catalog, order history,
     ledger reads) to replicas.
   * **PgBouncer / connection pooling** in front of the DB — at 1M users the
     connection count, not CPU, is usually the first wall.
   * Keep the **`select_for_update`** on wallet debits/credits (already present) to
     serialize balance mutations per‑wallet without locking the table.
   * Partition/retention for `wallet_transactions` and `payment_webhook_events`
     (time‑based) so hot tables stay small.
2. **Caching (Redis)**
   * Cache catalog/banners/categories (read‑heavy, rarely changing) with short TTLs
     and explicit invalidation on write.
   * Cache `serviceability` lookups by pincode.
   * Use Redis for rate‑limit counters (DRF throttle backend) so limits are global
     across API nodes, not per‑process.
3. **Horizontal scale & edge**
   * Run the API under **gunicorn/uvicorn workers** behind a load balancer;
     autoscale on CPU/RTT. Stateless design already supports this.
   * Serve `milkkart-web` and all static/media from a **CDN**; product images
     already come from a separate origin.
   * Offload long tasks (notifications, invoices, route ETA) to Celery; scale
     workers independently of web nodes.
4. **Payments at scale**
   * Webhook handler is already idempotent + deduped; ensure it's **fast and
     returns 200 quickly** (heavy work → Celery) so the gateway doesn't retry‑storm.
   * Add a **reconciliation job** (periodic Celery beat) that sweeps `created`
     top‑ups/payments and reconciles against the gateway — the safety net behind
     polling and webhooks.
5. **Observability & resilience**
   * Structured logging + request tracing; metrics on payment success rate, webhook
     lag, poll volume, DB pool saturation.
   * Sentry (or similar) for errors; alert on webhook signature failures and
     top‑up `created`→never‑`success` rates.
   * Graceful degradation: if Redis is down, fall back to DB‑backed throttling/
     no‑cache rather than failing requests.

### Capacity sketch

1M registered users ≈ tens of thousands of DAU; the bottlenecks in order are
(1) DB connections, (2) write contention on wallet/order rows, (3) payment webhook
throughput. The mitigations above (pooling, per‑wallet row locks, async + idempotent
webhooks, read replicas, CDN) address them in that order.

## 4. Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PAYMENT_GATEWAY` | `mock` | `mock` (dev/tests) or `razorpay` (prod) |
| `PAYMENT_GATEWAY_KEY_ID` / `_SECRET` | test | Gateway checkout credentials |
| `PAYMENT_WEBHOOK_SECRET` | test | Verifies inbound webhook signatures |
| `UPI_VPA` | `milkkart@upi` | Merchant VPA for gateway‑agnostic UPI QR/intent |
| `UPI_PAYEE_NAME` | `MilkKart` | Display name in the UPI app |
| `REDIS_URL` | `redis://redis:6379/0` | Cache + channels + broker |

To actually **receive** UPI funds, set `UPI_VPA` to a real registered VPA. For
**auto‑reconciliation** without a gateway, that VPA must be attached to a PSP that
delivers webhooks to `/payments/webhook/`; otherwise use the Razorpay path for
hands‑off confirmation.

### Mobile production builds (Android UPI)

The targeted UPI app launch works in Expo Go as‑is. For an EAS/standalone build,
add a `<queries>` entry for the `upi://` intent and the target packages
(`com.google.android.apps.nbu.paisa.user`, `com.phonepe.app`, `net.one97.paytm`) to
the Android manifest (via an Expo config plugin), so package visibility on
Android 11+ lets the intent resolve.
