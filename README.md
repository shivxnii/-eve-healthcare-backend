# EVE Healthcare — SDE Intern Backend Assignment

A production-minded FastAPI backend for diagnostic test bookings and simulated payments.

## Features

- User signup/login with JWT authentication and password hashing
- Request validation with Pydantic
- Diagnostic centres and tests with centre-specific prices
- Authenticated booking creation/list/detail/cancellation
- Ownership/authorization checks
- Mock payment processing with SUCCESS/FAILED outcomes
- Payment idempotency using `Idempotency-Key`
- Idempotent payment-provider webhook using a unique `event_id`
- Transaction-safe booking/payment state transitions
- Pagination for list endpoints
- Redis cache for centre listings (graceful fallback when Redis is unavailable)
- Celery background job for simulated booking confirmation notification
- Structured request logging and request IDs
- Rate limiting via SlowAPI
- Swagger/OpenAPI at `/docs`
- Pytest unit/integration coverage for core and edge cases
- Docker + docker-compose with PostgreSQL, Redis and Celery worker

## Architecture

Routers handle HTTP concerns, schemas validate input/output, SQLAlchemy models represent persistence, and security/service helpers isolate reusable logic. Payment webhook processing is protected by both application-level event checks and database uniqueness constraints.

## Database Schema

- `users`: authenticated users
- `diagnostic_centres`: diagnostic locations
- `diagnostic_tests`: reusable test catalogue
- `centre_tests`: many-to-many centre/test relationship with price
- `bookings`: appointment and booking state
- `payments`: simulated payment attempts/transactions
- `webhook_events`: webhook delivery/idempotency state

Key constraints:

- `users.email` UNIQUE
- `centre_tests(centre_id, test_id)` UNIQUE
- `payments.transaction_id` UNIQUE
- `payments.idempotency_key` UNIQUE when supplied
- `payments.provider_event_id` UNIQUE when supplied
- `webhook_events.event_id` UNIQUE

## Booking State Machine

```text
PENDING -> CONFIRMED
PENDING -> FAILED
PENDING -> CANCELLED
```

A confirmed or failed booking cannot be paid again through the normal payment endpoint. A confirmed booking cannot be cancelled in this version.

## Payment Flow

`POST /payments` accepts a booking and `simulate=SUCCESS|FAILED`. The server reads the amount from the database rather than trusting the client. SUCCESS moves the booking to `CONFIRMED`; FAILED moves it to `FAILED`.

## Webhook Idempotency

`POST /payments/webhook/` requires a provider `event_id`. The event is stored with a UNIQUE constraint. Repeated delivery of the same event returns `Event already processed` and does not create another payment or booking.

## API Endpoints

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/signup` | No | Register user |
| POST | `/auth/login` | No | Obtain JWT |
| GET | `/auth/me` | Yes | Current user |
| GET | `/centres` | No | Paginated centre list |
| GET | `/centres/{id}` | No | Centre + available tests/prices |
| GET | `/centres/catalog/tests` | No | Paginated test catalogue |
| GET | `/centres/catalog/tests/{id}` | No | Test details |
| POST | `/centres` | Admin | Create centre |
| PATCH | `/centres/{id}` | Admin | Update centre |
| DELETE | `/centres/{id}` | Admin | Delete centre when unused |
| POST | `/centres/catalog/tests` | Admin | Create test |
| PATCH | `/centres/catalog/tests/{id}` | Admin | Update test |
| DELETE | `/centres/catalog/tests/{id}` | Admin | Delete test when unused |
| POST | `/centres/{id}/tests` | Admin | Add test offering + price |
| POST | `/bookings` | Yes | Create booking |
| GET | `/bookings` | Yes | User's bookings, paginated |
| GET | `/bookings/{id}` | Yes | User-owned booking |
| POST | `/bookings/{id}/cancel` | Yes | Cancel pending booking |
| POST | `/payments` | Yes | Simulate payment |
| POST | `/payments/webhook` | No | Provider payment update |
| GET | `/health` | No | Health check |

## Example Requests

### Signup

```bash
curl -X POST http://localhost:8000/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"name":"Aditya","email":"aditya@example.com","password":"password123"}'
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"aditya@example.com","password":"password123"}'
```

### Create booking

```bash
curl -X POST http://localhost:8000/bookings \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"centre_test_id":1,"appointment_datetime":"2026-10-01T10:00:00+00:00"}'
```

### Simulate payment

```bash
curl -X POST http://localhost:8000/payments \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: payment-demo-1' \
  -d '{"booking_id":1,"simulate":"SUCCESS"}'
```

### Webhook

```bash
curl -X POST http://localhost:8000/payments/webhook \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"evt_123","transaction_id":"txn_external_123","booking_id":1,"status":"SUCCESS"}'
```

Send the same webhook again: it is treated as a duplicate and no second payment is created.

## Local Setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
uvicorn app.main:app --reload
```

Open Swagger: `http://localhost:8000/docs`

Demo admin: `admin@evehealthcare.com` / `Admin12345!` (change/remove this seed credential before production use).

The default local database is SQLite for fast setup. Set `DATABASE_URL` to PostgreSQL if desired.

## Docker

```bash
docker compose up --build
```

This starts FastAPI, PostgreSQL, Redis and a Celery worker.

## Tests

```bash
pytest -q
```

## Important Assumptions

1. This is a simulated payment service; no real payment provider is integrated.
2. Appointment slots are represented by a datetime. Slot inventory/doctor scheduling is outside the assignment scope.
3. JWT access tokens are sufficient for the requested basic authentication flow.
4. Webhook authenticity/signature verification is not implemented because no provider signing scheme was supplied. In a real integration, signature verification and timestamp/replay protection would be required.
5. A confirmed booking is not cancellable in this simplified implementation.
6. Redis and Celery are optional runtime components; the API remains usable without Redis for local development.

## What I Would Improve With More Time

- Alembic migrations and CI/CD
- Real payment provider signature verification
- Refresh-token/session management
- Appointment slot locking to prevent double booking
- More granular roles/admin APIs for centre/test management
- OpenTelemetry/centralized logs and metrics
- Contract tests against a real payment-provider sandbox
- Stronger database transaction/retry strategy for distributed webhook processing
- Secret management and production deployment configuration
