# CoursesSalesBot

Микросервис для продажи доступа к видеокурсам через Telegram.

Сайт после успешной оплаты вызывает API, API создаёт одноразовый токен, пользователь открывает Telegram-ссылку, бот активирует токен и выдаёт доступ к одному или нескольким курсам.

## Архитектура

```text
Website backend
    ↓ POST /api/tokens
FastAPI API
    ↓
PostgreSQL + Redis
    ↓ telegram_link
Telegram Bot
    ↓ /start TOKEN или /activate TOKEN
User gets course access
```

Сервисы:

- `api` — FastAPI HTTP API.
- `bot` — aiogram Telegram bot.
- `postgres` — основная БД.
- `redis` — rate limit для API.
- `migrate` — production-only сервис для Alembic migrations.
- `caddy` — production-only HTTPS reverse proxy.

Токен — это opaque token: внутри него нет `course_id`, `telegram_id` или `payment_id`. В БД хранится только `sha256(token)`. Raw token возвращается сайту один раз.

## Environment

Создай `.env` в корне проекта. `.env` нельзя коммитить.

```env
BOT_TOKEN=123456789:YOUR_TELEGRAM_BOT_TOKEN
BOT_USERNAME=YourBotUsername
ADMIN_IDS=123456789

POSTGRES_DB=bot_db
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=bot_password
DATABASE_URL=postgresql+asyncpg://bot_user:bot_password@postgres:5432/bot_db

SITE_API_KEY=change-me-long-random-secret

REDIS_URL=redis://redis:6379/0
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

Важно:

- Для Docker `DATABASE_URL` должен использовать host `postgres`.
- Для Docker `REDIS_URL` должен использовать host `redis`.
- `SITE_API_KEY` должен храниться только на backend-е сайта, не во frontend-е.

## Local development

Полный чистый запуск:

```bash
sudo docker compose down -v
sudo docker compose up -d postgres redis
sudo docker compose run --rm api alembic upgrade head
sudo docker compose up --build
```

Проверить контейнеры:

```bash
sudo docker compose ps
```

Проверить Redis:

```bash
sudo docker compose exec redis redis-cli ping
```

Ожидаемо:

```text
PONG
```

Проверить API:

```bash
curl http://localhost:8000/health
```

Ожидаемо:

```json
{"status":"ok"}
```

## Production startup

Production compose лежит в `deploy/docker-compose.prod.yml`.

Он отличается от dev compose:

- PostgreSQL не пробрасывается наружу.
- Нет volume `.:/app` для кода.
- Есть `migrate`, который запускает `alembic upgrade head`.
- Есть `caddy` для HTTPS reverse proxy.
- Есть healthchecks для API, Redis и PostgreSQL.

Запуск:

```bash
sudo docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Caddy config:

```bash
cp deploy/Caddyfile.example deploy/Caddyfile
```

Потом в `deploy/docker-compose.prod.yml` лучше заменить volume:

```yaml
- ./Caddyfile.example:/etc/caddy/Caddyfile:ro
```

на:

```yaml
- ./Caddyfile:/etc/caddy/Caddyfile:ro
```

В `deploy/Caddyfile` замени `api.example.com` на реальный домен и временный IP `192.168.0.194` на публичный IP backend-а сайта.

## Database schema

Основные таблицы:

### `courses`

Курсы, которые можно продавать.

Поля:

- `id` — стабильный ID курса, например `python-backend`.
- `title` — название курса.
- `description` — описание.
- `invite_link` — fallback-ссылка, если `telegram_chat_id` не настроен.
- `telegram_chat_id` — ID приватного Telegram-канала курса.
- `is_active` — можно ли продавать курс.

### `access_tokens`

Одноразовые токены.

- `token_hash` — hash raw token.
- `token_preview` — preview для админки/логов.
- `payment_id` — ID платежа сайта.
- `is_used` — активирован ли токен.
- `used_by_tg_id` — Telegram ID активировавшего пользователя.

### `token_courses`

Связь один токен → много курсов.

### `user_course_accesses`

Реальный доступ пользователя к курсам.

### `payment_event_logs`

События для аудита: создание токена, дубль платежа, активация токена, ошибки.

## API auth

Все `/api/*` endpoint-ы требуют header:

```http
X-API-Key: SITE_API_KEY
```

Нельзя вызывать API напрямую из браузера, потому что `SITE_API_KEY` утечёт. Правильно:

```text
frontend сайта → backend сайта → CoursesSalesBot API
```

## API endpoints

Base URL локально:

```text
http://localhost:8000
```

### GET /health

```bash
curl http://localhost:8000/health
```

Response:

```json
{"status":"ok"}
```

### POST /api/courses

Создаёт или обновляет курс.

```bash
curl -X POST http://localhost:8000/api/courses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SITE_API_KEY" \
  -d '{
    "id": "python-backend",
    "title": "Python Backend",
    "description": "Backend course",
    "invite_link": null,
    "telegram_chat_id": -1001234567890,
    "is_active": true
  }'
```

`telegram_chat_id` нужен для одноразовых invite links. Бот должен быть администратором этого приватного канала и иметь право создавать invite links.

Response:

```json
{
  "id": "python-backend",
  "title": "Python Backend",
  "description": "Backend course",
  "invite_link": null,
  "telegram_chat_id": -1001234567890,
  "is_active": true
}
```

### GET /api/courses

```bash
curl http://localhost:8000/api/courses \
  -H "X-API-Key: $SITE_API_KEY"
```

Возвращает активные курсы.

### GET /api/courses/{course_id}

```bash
curl http://localhost:8000/api/courses/python-backend \
  -H "X-API-Key: $SITE_API_KEY"
```

Возвращает один курс или `404`.

### POST /api/tokens

Создаёт одноразовый токен на один или несколько курсов.

```bash
curl -X POST http://localhost:8000/api/tokens \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SITE_API_KEY" \
  -d '{
    "course_ids": ["python-backend", "csharp-aspnet"],
    "payment_id": "payment-123"
  }'
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

- `401` — invalid API key.
- `404` — курс не найден или выключен.
- `409` — `payment_id` уже использован.
- `429` — rate limit.

### GET /api/access/check

Проверяет доступ к одному курсу.

```bash
curl "http://localhost:8000/api/access/check?telegram_id=123456789&course_id=python-backend" \
  -H "X-API-Key: $SITE_API_KEY"
```

Response:

```json
{
  "has_access": true,
  "telegram_id": 123456789,
  "course_id": "python-backend"
}
```

### POST /api/access/check

Проверяет доступ к нескольким курсам.

```bash
curl -X POST http://localhost:8000/api/access/check \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SITE_API_KEY" \
  -d '{
    "telegram_id": 123456789,
    "course_ids": ["python-backend", "csharp-aspnet", "sql-basics"]
  }'
```

Response:

```json
{
  "telegram_id": 123456789,
  "access": {
    "python-backend": true,
    "csharp-aspnet": true,
    "sql-basics": false
  }
}
```

## Telegram bot commands

- `/start` — описание бота.
- `/start TOKEN` — активация токена из deep link.
- `/activate TOKEN` — ручная активация токена.
- `/mycourses` — список активированных курсов.
- `/help` — список команд.
- `/token COURSE_ID COURSE_ID2` — admin-only создание токена вручную.

При активации токена бот создаёт Telegram invite link с `member_limit=1`, если у курса задан `telegram_chat_id`. Если `telegram_chat_id` не задан, бот использует fallback `invite_link`.

## How to test everything

### 1. Pull latest code

```bash
cd ~/Documents/repos/CoursesSalesBot
git pull --rebase origin main
```

### 2. Check `.env`

```bash
cat .env
```

Проверь, что есть:

```env
DATABASE_URL=postgresql+asyncpg://admin:67584738567@postgres:5432/UsersDb
REDIS_URL=redis://redis:6379/0
SITE_API_KEY=LoshkoAndTohskoInEveryProject
BOT_USERNAME=test_courses_sales_bot
```

### 3. Clean run

```bash
sudo docker compose down -v
sudo docker compose up -d postgres redis
sudo docker compose run --rm api alembic upgrade head
sudo docker compose up --build
```

### 4. Health checks

В другом терминале:

```bash
curl http://localhost:8000/health
sudo docker compose exec redis redis-cli ping
sudo docker compose exec postgres pg_isready -U admin -d UsersDb
```

### 5. Create courses

Fallback-link course:

```bash
curl -X POST http://localhost:8000/api/courses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: LoshkoAndTohskoInEveryProject" \
  -d '{
    "id": "python-backend",
    "title": "Python Backend",
    "description": "Backend course",
    "invite_link": "https://t.me/+example_python",
    "telegram_chat_id": null,
    "is_active": true
  }'
```

Private-channel course:

```bash
curl -X POST http://localhost:8000/api/courses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: LoshkoAndTohskoInEveryProject" \
  -d '{
    "id": "private-python",
    "title": "Private Python Channel",
    "description": "Course with one-time invite link",
    "invite_link": null,
    "telegram_chat_id": -1001234567890,
    "is_active": true
  }'
```

Для теста `private-python` замени `-1001234567890` на настоящий ID приватного канала, где бот является админом.

### 6. List courses

```bash
curl http://localhost:8000/api/courses \
  -H "X-API-Key: LoshkoAndTohskoInEveryProject"
```

### 7. Create token for multiple courses

```bash
curl -X POST http://localhost:8000/api/tokens \
  -H "Content-Type: application/json" \
  -H "X-API-Key: LoshkoAndTohskoInEveryProject" \
  -d '{
    "course_ids": ["python-backend", "private-python"],
    "payment_id": "payment-123"
  }'
```

Скопируй `telegram_link`.

### 8. Check duplicate payment protection

Повтори запрос с тем же `payment_id`. Ожидаемый результат: `409 Conflict`.

### 9. Activate token in Telegram

Открой `telegram_link`.

Ожидаемо:

```text
Доступ активирован.

Курсы:
1. Python Backend (python-backend)
   Материалы: https://t.me/+example_python

2. Private Python Channel (private-python)
   Материалы: https://t.me/+one_time_invite
```

Для `telegram_chat_id` бот должен создать новую одноразовую ссылку. Если бот не админ канала, в логах будет ошибка, и будет использован fallback `invite_link`, если он задан.

### 10. Check bot commands

В Telegram:

```text
/mycourses
/help
```

### 11. Check access API

```bash
curl "http://localhost:8000/api/access/check?telegram_id=692080442&course_id=python-backend" \
  -H "X-API-Key: LoshkoAndTohskoInEveryProject"
```

Bulk check:

```bash
curl -X POST http://localhost:8000/api/access/check \
  -H "Content-Type: application/json" \
  -H "X-API-Key: LoshkoAndTohskoInEveryProject" \
  -d '{
    "telegram_id": 692080442,
    "course_ids": ["python-backend", "private-python", "missing-course"]
  }'
```

### 12. Check database

```bash
sudo docker compose exec postgres psql -U admin -d UsersDb
```

```sql
select id, title, invite_link, telegram_chat_id, is_active from courses;
select id, payment_id, course_id, is_used, used_by_tg_id, used_at from access_tokens;
select token_id, course_id from token_courses;
select telegram_id, course_id, token_id, created_at from user_course_accesses;
select event_type, status, payment_id, course_ids, telegram_id, token_id, created_at
from payment_event_logs
order by id desc;
```

### 13. Check backup

```bash
chmod +x scripts/backup_postgres.sh scripts/prod_healthcheck.sh
./scripts/backup_postgres.sh
ls -lah backups
```

### 14. Check health script

```bash
./scripts/prod_healthcheck.sh
```

## Code review notes

Current status:

- Good: token hashing is used; raw token is not stored.
- Good: `payment_id` prevents duplicate token creation.
- Good: multi-course purchase is supported through `token_courses`.
- Good: API rate limit is Redis-backed.
- Good: prod compose does not expose PostgreSQL.
- Good: bot can create one-time Telegram invite links.

Known limitations:

- There are no automated tests yet.
- `/mycourses` intentionally does not create new one-time invite links to prevent abuse.
- Caddy allowlist currently contains temporary local IP `192.168.0.194`; replace it with the public IP of the website backend.
- Backups must not be committed. `backups/` is ignored now, but remove any already committed backup files from Git history before serious production use.
