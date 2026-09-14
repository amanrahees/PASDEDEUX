# PASDEDEUX Ecommerce API

Production-minded Django REST API for a fashion store selling clothing, shoes,
eyewear, belts, caps, and accessories for everyone.

## Features

- Email/password registration with six-digit, hashed, expiring email OTPs
- Status-aware JWT access and rotating refresh tokens with logout blacklisting
- Password reset with generic account-discovery-safe responses
- Customer profiles and multiple shipping/billing addresses
- Hierarchical categories, brands, products, images, and SKU variants
- Audience and fashion product-type filtering, full-text search, and ordering
- Transaction-safe inventory adjustments and stock reservations
- Customer cart with quantity and availability validation
- Idempotent checkout with immutable order/address/item snapshots
- Provider-neutral payment records and shipment tracking
- PostgreSQL, Redis, Celery, Gunicorn, health checks, and OpenAPI documentation

The API never stores card numbers or CVVs. Connect a PCI-compliant payment
provider to the `Payment` boundary before accepting live payments.

## Local Docker setup

1. Copy `.env.example` to `.env` and replace every development secret.
2. Install Docker Desktop.
3. Start the stack:

```powershell
docker compose up --build
```

4. Seed the standard fashion categories:

```powershell
docker compose exec backend python manage.py seed_fashion_catalog
```

5. Create an administrator:

```powershell
docker compose exec backend python manage.py createsuperuser
```

The API is available at `http://localhost:8000`. Swagger documentation is at
`/api/docs/` for staff users. Liveness and dependency readiness endpoints are
`/health/live/` and `/health/ready/`.

## Main API routes

### Authentication

- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/verify-email/`
- `POST /api/v1/auth/resend-verification/`
- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/refresh/`
- `POST /api/v1/auth/logout/`
- `POST /api/v1/auth/forgot-password/`
- `POST /api/v1/auth/reset-password/`
- `GET /api/v1/auth/me/`

### Customer

- `GET/PATCH /api/v1/profile/`
- `GET/POST /api/v1/addresses/`
- `GET/PATCH/DELETE /api/v1/addresses/{id}/`
- `POST /api/v1/addresses/{id}/default_shipping/`
- `POST /api/v1/addresses/{id}/default_billing/`

### Catalog

- `GET /api/v1/categories/`
- `GET /api/v1/brands/`
- `GET /api/v1/products/`
- `GET /api/v1/products/{slug}/`

Catalog writes and variant/image management require a staff account.

### Cart and orders

- `GET /api/v1/cart/`
- `POST /api/v1/cart/items/`
- `PATCH/DELETE /api/v1/cart/items/{id}/`
- `POST /api/v1/checkout/`
- `GET /api/v1/orders/`
- `GET /api/v1/orders/{order_number}/`
- `POST /api/v1/orders/{order_number}/cancel/`

Checkout requires a unique `Idempotency-Key` request header. Repeating the same
key returns the original order without reserving stock twice.

## Filtering examples

```text
/api/v1/products/?product_type=SHOES&audience=EVERYONE
/api/v1/products/?category__slug=clothing&ordering=base_price
/api/v1/products/?search=sneaker
```

## Development checks

From `backend` with the virtual environment active:

```powershell
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
ruff check .
pytest -q
```

Tests use an isolated in-memory SQLite database. Runtime and production use the
PostgreSQL URL supplied through the environment.

## Production checklist

- Use long independent `SECRET_KEY`, `JWT_SIGNING_KEY`, and database passwords.
- Set `DJANGO_SETTINGS_MODULE=config.settings.production`.
- Restrict `ALLOWED_HOSTS`, CORS origins, and CSRF trusted origins.
- Place the API behind HTTPS and a trusted reverse proxy.
- Protect Redis with private networking/authentication and never log OTP payloads.
- Use object storage for uploaded product/customer media.
- Connect and verify signed webhooks from a real payment provider.
- Configure transactional email and error monitoring.
- Back up PostgreSQL and test restore procedures.
