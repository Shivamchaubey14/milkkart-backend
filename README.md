# MilkKart Backend

Dairy quick-commerce platform backend — Blinkit-style hyper-local delivery for dairy products.

## Tech Stack

- **Runtime:** Python 3.12, Django 5, Django REST Framework (async via adrf)
- **Async:** ASGI with Uvicorn, Django Channels
- **Database:** MySQL 8 (utf8mb4)
- **Cache / Broker:** Redis 7
- **Task Queue:** Celery
- **Containerisation:** Docker & Docker Compose

## Quick Start

```bash
cp .env.example .env          # configure environment variables
docker compose up --build -d  # start all services
docker compose exec django python manage.py migrate
docker compose exec django python manage.py createsuperuser
```

## Project Layout

```
milkkart-backend/
├── apps/             # Django applications
│   ├── accounts/     # Custom User model (phone-based auth)
│   └── core/         # Health-check, shared utilities
├── config/           # Django project settings & ASGI/WSGI entry
│   └── settings/     # Split settings: base / dev / prod / test
├── requirements/     # Pip requirement files
├── Dockerfile
├── docker-compose.yml
└── manage.py
```

## Development

```bash
# Run linter
ruff check .

# Run tests
pytest
```

## License

Proprietary — all rights reserved.
