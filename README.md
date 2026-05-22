# CoursesSalesBot

Production-oriented microservice for selling video-course access through Telegram.

## Architecture

The project has three main parts:

- FastAPI API: creates courses, creates payment tokens, checks access.
- Aiogram bot: activates tokens and shows user courses.
- PostgreSQL: stores courses, tokens, token-course bindings, user access records and payment event logs.

A token is an opaque random secret. It does not contain course data. The database stores only `sha256(token)`, and the raw token is returned once to the website.

## Environment

Create `.env` from `.env.example` and never commit `.env`.

```env
BOT_TOKEN=123456789:YOUR_TELEGRAM_BOT_TOKEN
BOT_USERNAME=YourBotUsername
ADMIN_IDS=123456789

POSTGRES_DB=bot_db
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql+asyncpg://bot_user:change-me@postgres:5432/bot_db

SITE_API_KEY=change-me-long-random-secret
```

## Local development startup

```bash
sudo docker compose down -v
sudo docker compose up -d postgres
sudo docker compose run --rm api alembic upgrade head
sudo docker compose up --build
```

## API authentication

All `/api/*` endpoints require:

```http
X-API-Key: SITE_API_KEY
```

The site must call this API from its backend, not from browser JavaScript.

## Endpoints

### GET /health

```bash
curl http://localhost:8000/health
```

Response:

```json
{"status":"ok"}
```

### POST /api/courses

Creates or updates a course.

```bash
curl -X POST http://localhost:8000/api/courses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-long-random-secret" \
  -d '{"id":"python-backend","title":"Python Backend","description":"Backend course","invite_link":"https://t.me/+example","is_active":true}'
```

### GET /api/courses

Returns active courses.

```bash
curl http://localhost:8000/api/courses \
  -H "X-API-Key: change-me-long-random-secret"
```

### GET /api/courses/{course_id}

Returns one course or 404.

### POST /api/tokens

Creates one token for one or many courses.

```bash
curl -X POST http://localhost:8000/api/tokens \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-long-random-secret" \
  -d '{"course_ids":["python-backend","csharp-aspnet"],"payment_id":"payment-123"}'
```

Response:

```json
{
  "token": "raw-token",
  "course_ids": ["python-backend", "csharp-aspnet"],
  "payment_id": "payment-123",
  "token_preview": "abc123...xyz",
  "telegram_link": "https://t.me/YourBotUsername?start=raw-token"
}
```

Errors:

- `401`: invalid API key.
- `404`: one or more courses do not exist or are inactive.
- `409`: token for this `payment_id` already exists.
- `429`: rate limit exceeded.

### GET /api/access/check

Checks access to one course.

```bash
curl "http://localhost:8000/api/access/check?telegram_id=123456789&course_id=python-backend" \
  -H "X-API-Key: change-me-long-random-secret"
```

### POST /api/access/check

Checks access to multiple courses.

```bash
curl -X POST http://localhost:8000/api/access/check \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-long-random-secret" \
  -d '{"telegram_id":123456789,"course_ids":["python-backend","csharp-aspnet"]}'
```

## Bot commands

- `/start` — help text.
- `/start TOKEN` — activates token from a Telegram deep link.
- `/activate TOKEN` — activates token manually.
- `/mycourses` — shows activated courses and invite links.
- `/help` — command list.
- `/token COURSE_ID COURSE_ID2` — admin-only manual token generation.

## Production checklist

- Use HTTPS through Caddy, Nginx, Traefik or another reverse proxy.
- Do not expose PostgreSQL to the internet.
- Use a long random `SITE_API_KEY`.
- Run `alembic upgrade head` before starting API and bot.
- Keep `.env` outside Git.
- Configure PostgreSQL backups.
- Use backend-to-backend integration only; never expose `SITE_API_KEY` in frontend code.
