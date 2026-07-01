# CoursesSalesBot

Telegram-бот — **витрина видеокурсов с тарифами**. Пользователь оплачивает один из трёх
тарифов на сайте, получает персональную ссылку, открывает бота — и внутри бота смотрит
видео, разложенные по группам и подгруппам. Что именно видно — зависит от тарифа; доступ
выдаётся на ограниченный срок.

Контент наполняет владелец прямо в боте: создаёт группы/подгруппы, добавляет видео, кидая
ссылку на YouTube (название и обложку бот подтягивает сам через yt-dlp).

## Концепция

```text
Сайт (после оплаты Monobank)
    │  POST /api/tokens { payment_id, tier }     ← заголовок X-API-Key
    ▼
FastAPI API  ──►  создаёт одноразовый токен под тариф
    │  возвращает telegram_link
    ▼
Пользователь открывает https://t.me/<bot>?start=<token>
    ▼
Бот активирует токен → выдаёт тариф на N дней → показывает каталог
```

Сервисы (docker compose):

- `api` — FastAPI HTTP API (его дёргает бэкенд сайта).
- `bot` — aiogram-бот (витрина + админка), long polling.
- `postgres` — основная БД.
- `redis` — rate limit для API.
- `migrate` — прод-сервис, прогоняет `alembic upgrade head` на старте.
- `caddy` — прод HTTPS reverse proxy.

## Тарифы

Единый источник правды — `app/tiers.py`. Тариф определяется префиксом `reference`
с сайта (`lite-...`, `pro-...`, `vip-...`).

| Тариф | Ранг | Срок доступа |
|-------|------|--------------|
| `lite` | 1 | 30 дней |
| `pro`  | 2 | 30 дней |
| `vip`  | 3 | 90 дней |

**Гейтинг контента:** у каждой группы и каждого видео есть `min_tier`. Пользователь видит
элемент, если **ранг его тарифа ≥ ранг `min_tier` элемента**. Так «разный контент по тарифам»
делается без отдельных каталогов: общие видео ставишь `min_tier=lite`, бонусные —
`pro`/`vip`. Срок доступа — просто проверка `expires_at` при заходе в каталог; отзывать или
кикать никого не нужно, потому что видео живут внутри бота.

## Токен

Opaque-токен: внутри него нет тарифа или id. В БД хранится только `sha256(token)`, а сам
тариф и срок (`tier`, `duration_days`) лежат в строке токена. Сырой токен возвращается сайту
один раз. Токен одноразовый: после активации помечается `is_used`.

## Модель данных

| Таблица | Назначение |
|---------|------------|
| `access_tokens` | Одноразовые токены покупки: `token_hash`, `token_preview`, `tier`, `duration_days`, `payment_id` (уникальный — защита от дублей вебхука), `is_used`, `used_by_tg_id`, `used_at`. |
| `content_groups` | Группы и подгруппы: `parent_id` (NULL = группа верхнего уровня, иначе подгруппа), `title`, `min_tier`, `position`, `is_active`. Каскадное удаление детей. |
| `videos` | Видео внутри группы: `group_id`, `title`, `youtube_url`, `thumbnail_url`, `min_tier`, `position`, `is_active`. |
| `user_tier_accesses` | Выданные доступы: `telegram_id`, `tier`, `expires_at`, `token_id`, `payment_id`. У юзера может быть несколько записей (докупки) — действует высший непросроченный тариф. |
| `payment_event_logs` | Аудит: `event_type` (`token_create`/`token_activate`), `status` (`success`/`duplicate_payment`/…), `payment_id`, `telegram_id`, `token_id`, `message`. |

> Легаси-таблицы `courses`, `token_courses`, `user_course_accesses` остались от прошлой
> (course-based) модели и больше не используются — их можно удалить отдельной миграцией.

## Структура проекта

```text
app/
├── config.py                 # Settings (pydantic-settings): чтение .env
├── tiers.py                  # тарифы: ранги, сроки, тайтлы, нормализация
├── main.py                   # entrypoint бота (aiogram polling)
├── database/
│   ├── session.py            # async engine + session_maker
│   └── models.py             # SQLAlchemy ORM-модели (все таблицы)
├── middlewares/
│   ├── db.py                 # ⭐ DI: на каждый апдейт открывает сессию,
│   │                         #    собирает сервисы/репозитории, коммитит/роллбэчит
│   └── auth.py               # (пусто, легаси)
├── repositories/             # слой доступа к данным (тонкие, без бизнес-логики)
│   ├── token_repository.py            # ⭐ access_tokens
│   ├── tier_access_repository.py      # ⭐ user_tier_accesses
│   ├── content_group_repository.py    # ⭐ content_groups (CRUD + позиции)
│   ├── video_repository.py            # ⭐ videos (CRUD + позиции)
│   ├── payment_event_repository.py    # ⭐ payment_event_logs
│   └── *_repository.py (course/access/token_course/user) # легаси, не используются
├── services/                 # бизнес-логика
│   ├── token_service.py      # ⭐ создание/активация токена, расчёт доступа
│   ├── catalog_service.py    # ⭐ выборки каталога с тир-гейтингом
│   ├── youtube_parser.py     # ⭐ yt-dlp: вытащить title + обложку из ссылки
│   ├── payment_service.py    # легаси
│   └── user_service.py       # легаси
├── handlers/                 # роутеры aiogram
│   ├── __init__.py           # порядок роутеров
│   ├── token/__init__.py     # ⭐ активация: /start TOKEN, /activate TOKEN
│   ├── user_catalog.py       # ⭐ витрина: /start, /catalog, /myaccess, /help, callbacks cat:*
│   ├── admin_panel.py        # ⭐ админка: /admin + FSM + callbacks adm:*
│   └── course_parser.py      # легаси (отключён, мешал бы FSM)
└── api/
    ├── main.py               # ⭐ FastAPI приложение и все эндпоинты
    ├── limiter.py            # ⭐ Redis fixed-window rate limiter
    └── link_cache.py         # легаси (не подключён)
migrations/versions/          # Alembic: 0001..0004
```

(⭐ — активный модуль текущей тарифной модели; «легаси» — наследие старой course-модели,
не подключено, безопасно игнорировать/удалить позже.)

## Функционал бэкенда по слоям

### `app/config.py`

`Settings` на `pydantic-settings`, читает `.env`. Поля: `BOT_TOKEN`, `BOT_USERNAME`,
`ADMIN_IDS` (CSV → `admin_ids: set[int]`), `SITE_API_KEY`/`API_TOKEN`
(`site_api_key` — что не пусто), `SUPPORT_USERNAME`, `YOUTUBE_COOKIES_FILE`, `DATABASE_URL`,
`REDIS_URL`, `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`.

### `app/tiers.py`

Константы тарифов и helpers: `normalize_tier`, `tier_rank`, `tier_title`,
`duration_days_for_tier`, `ALL_TIERS`. Меняешь сроки/набор тарифов — только здесь.

### `app/database/`

- `session.py` — асинхронный движок SQLAlchemy + `session_maker` (`expire_on_commit=False`).
- `models.py` — ORM-модели всех таблиц (см. «Модель данных»).

### `app/middlewares/db.py` (ключевой)

aiogram-мидлварь на уровне апдейта. На каждый апдейт: открывает сессию, создаёт
`TokenService`, `CatalogService`, `ContentGroupRepository`, `VideoRepository`, кладёт их в
`data` (откуда aiogram инъектит в хендлеры по имени аргумента), затем `commit` при успехе
или `rollback` при исключении. FSM-состояние админки хранится в `MemoryStorage` (по умолчанию
в `Dispatcher`).

### `app/repositories/` (активные)

Тонкий слой над БД, без бизнес-логики:

- `TokenRepository` — `create` (с tier/duration), `get_by_hash` / `get_by_hash_for_update`
  (SELECT FOR UPDATE при активации), `get_by_payment_id`, `exists_by_hash`.
- `TierAccessRepository` — `create` (выдать доступ), `list_active(telegram_id, now)`
  (непросроченные гранты).
- `ContentGroupRepository` — `get_by_id`, `list_children(parent_id)`, `create`, `update`,
  `delete`, `next_position`, `count_videos`.
- `VideoRepository` — `get_by_id`, `list_by_group`, `create`, `update`, `delete`,
  `next_position`.
- `PaymentEventRepository` — `create` (запись в аудит-лог).

### `app/services/` (активные)

- **`TokenService`** — ядро доступа:
  - `create_token(created_by_tg_id, tier, payment_id?, duration_days?)` — валидирует тариф,
    проверяет дубль по `payment_id` (→ `TokenAlreadyExistsError`), генерит уникальный
    `secrets.token_urlsafe(32)`, хранит `sha256`, пишет аудит. Возвращает `CreatedToken`.
  - `activate_token(raw_token, used_by_tg_id)` — берёт токен `FOR UPDATE`, если валиден и не
    использован — помечает `is_used`, создаёт `user_tier_accesses` с `expires_at = now + срок`.
    Возвращает `ActivatedAccess` или `None`.
  - `get_active_access(telegram_id)` — высший по рангу непросроченный тариф (`ActiveAccess`)
    или `None`.
- **`CatalogService`** — read-model с гейтингом: `visible_groups(parent_id, tier)`,
  `visible_videos(group_id, tier)`, `get_group_if_visible`, `get_video_if_visible`
  (фильтр по `tier_rank(item.min_tier) <= tier_rank(user)`).
- **`YoutubeCourseParser`** — `parse(text)`: находит YouTube-ссылку, через yt-dlp вытаскивает
  `title`, `description`, лучшую `thumbnail`. Работает для public/unlisted; для private нужен
  `YOUTUBE_COOKIES_FILE`.

### `app/api/`

- `main.py` — FastAPI-приложение, мидлварь rate limit на `/api/*`, зависимость
  `authorize_site` (проверка `X-API-Key == SITE_API_KEY`), эндпоинты (ниже).
- `limiter.py` — `RedisRateLimiter`: фиксированное окно, ключ `rate-limit:<key>:<window>`,
  `INCR` + `EXPIRE`; при превышении — `429`. Ключ = `X-API-Key` или IP клиента.

### `app/handlers/`

Роутеры подключаются в порядке (важно): `token_router` → `admin_router` →
`user_catalog_router`. Так deep-link `/start TOKEN` ловится раньше обычного `/start`, а
FSM-сообщения админки имеют приоритет над общими хендлерами.

### `app/main.py`

Поднимает `Bot` + `Dispatcher` (FSM на `MemoryStorage`), вешает `DbMiddleware`, регистрирует
роутеры и глобальный error-handler (`@dp.errors()` — пишет traceback в лог и шлёт юзеру «Сталася
помилка»). На старте берёт **Postgres advisory-lock** (`pg_try_advisory_lock`) — второй инстанс на
той же БД не запустится; делает `delete_webhook(drop_pending_updates=True)` и `start_polling` с
ретраями на сетевые ошибки.

## Environment

Все переменные бэкенда. **Новых переменных под тарифную модель нет** — сроки/ранги тарифов
зашиты в `app/tiers.py`, не в env.

| Переменная | Обяз. | Назначение |
|------------|:----:|------------|
| `BOT_TOKEN` | да | Токен бота от @BotFather. |
| `BOT_USERNAME` | да | Username бота без `@` — для deep link `?start=`. |
| `ADMIN_IDS` | да | TG id админов через запятую (доступ к `/admin`). |
| `SITE_API_KEY` | да | Общий секрет с сайтом; **должен совпадать** с `COURSES_BOT_API_KEY` в `.env` сайта. |
| `DATABASE_URL` | да | `postgresql+asyncpg://user:pass@postgres:5432/db` (host `postgres` в Docker). |
| `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` | да | Для контейнера postgres. |
| `REDIS_URL` | да | `redis://redis:6379/0` (host `redis` в Docker). |
| `RATE_LIMIT_REQUESTS` | нет | Лимит запросов в окне (по умолч. 60). |
| `RATE_LIMIT_WINDOW_SECONDS` | нет | Длина окна, сек (по умолч. 60). |
| `SUPPORT_USERNAME` | нет | Username для кнопки «Написати тренеру». Пусто → кнопки нет. |
| `YOUTUBE_COOKIES_FILE` | нет | Путь к cookies.txt — только если видео PRIVATE (для unlisted не нужен). |

### Пример `.env`

```env
# --- Telegram ---
BOT_TOKEN=123456789:AA-yourtelegrambottoken
BOT_USERNAME=your_course_bot
ADMIN_IDS=692080442,111111111
SUPPORT_USERNAME=trainer_username
YOUTUBE_COOKIES_FILE=

# --- База ---
POSTGRES_DB=bot_db
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=super-secret-db-password
DATABASE_URL=postgresql+asyncpg://bot_user:super-secret-db-password@postgres:5432/bot_db

# --- Безопасность API (общий секрет с сайтом) ---
SITE_API_KEY=change-me-to-a-long-random-secret

# --- Redis / rate limit ---
REDIS_URL=redis://redis:6379/0
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

> `.env` не коммитить (он в `.gitignore`). В репозитории — только `.env.example`.

## ⚠️ Главное правило: один инстанс на токен

Telegram отдаёт long-polling (`getUpdates`) **только одному** процессу. Если на одном
`BOT_TOKEN` крутятся два бота — они дерутся за апдейты (`TelegramConflictError`), сообщения
теряются, бот «работает через раз».

В коде есть защита: на старте бот берёт **Postgres advisory-lock** — второй инстанс на той же
БД просто не запустится. Но это **не спасает между разными БД** (например, dev-стек и prod-стек
поднимают свои отдельные postgres). Поэтому правило простое:

> **Никогда не держи dev- и prod-стек запущенными одновременно на одном `BOT_TOKEN`.**
> Перед запуском другого стека — погаси текущий (`down`). Для параллельной работы — разные боты/токены.

FSM-состояние админки хранится в `MemoryStorage` (в памяти процесса): сбрасывается при рестарте
бота — это нормально, отдельный Redis для FSM не нужен.

## Полный чистый запуск — Dev

Dev-compose: корневой `docker-compose.yml`. Сервисы: `postgres` (порт хоста **5433**→5432),
`redis` (без внешнего порта), `api` (**8000**→8000), `bot`. Код примонтирован томом `.:/app`.
Сервиса `migrate` тут нет — миграции прогоняем руками.

```bash
# 0. убедись, что prod-стек не запущен (один инстанс на токен!)
sudo docker compose -f deploy/docker-compose.prod.yml down 2>/dev/null

# 1. .env
cp .env.example .env          # затем впиши реальные значения

# 2. чистый старт инфраструктуры (-v сносит и тома → пустая БД)
sudo docker compose down -v
sudo docker compose up -d postgres redis

# 3. миграции (создаст все таблицы: каталог, тарифы, токены, аудит)
sudo docker compose run --rm api alembic upgrade head

# 4. поднять API + бота
sudo docker compose up -d --build

# 5. логи бота — должно быть "Run polling ..." без TelegramConflictError
sudo docker compose logs -f bot
```

Проверки в другом терминале:

```bash
curl http://localhost:8000/health                  # {"status":"ok"}
sudo docker compose exec redis redis-cli ping       # PONG
sudo docker compose exec postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
sudo docker compose ps                              # postgres/redis/api/bot — Up
```

Отдать локальный API сайту (без домена) — быстрый туннель Cloudflare:

```bash
docker run --rm -it --network coursessalesbot_default \
  cloudflare/cloudflared:latest tunnel --url http://api:8000
# выдаст https://<random>.trycloudflare.com — этот URL пропиши в COURSES_BOT_API_URL на сайте.
# ВНИМАНИЕ: URL новый при КАЖДОМ запуске туннеля — после рестарта обнови env на сайте.
```

## Полный чистый запуск — Prod

Prod-compose: `deploy/docker-compose.prod.yml`. Отличия от dev: PostgreSQL **не** торчит наружу;
есть сервис **`migrate`** (сам гоняет `alembic upgrade head` до старта `api`/`bot`), **`caddy`**
(HTTPS reverse-proxy на `api:8000`), healthcheck'и на всех сервисах.

```bash
# 0. погаси dev-стек (один инстанс на токен!)
sudo docker compose down 2>/dev/null

# 1. .env с боевыми значениями:
#    - BOT_TOKEN / BOT_USERNAME — реальный бот заказчицы
#    - ADMIN_IDS — её telegram id
#    - SITE_API_KEY — длинный случайный секрет (== COURSES_BOT_API_KEY на сайте)
#    - DATABASE_URL → host postgres, REDIS_URL → host redis
nano .env

# 2. Caddy: вписать реальный домен и IP бэкенда сайта.
#    Compose монтирует deploy/Caddyfile.example напрямую — правим именно его:
nano deploy/Caddyfile.example
#    api.example.com  → твой домен API бота
#    remote_ip 192.168.0.194 → публичный IP бэкенда сайта (allowlist)

# 3. чистый старт — migrate прогонит миграции сам
sudo docker compose -f deploy/docker-compose.prod.yml down
sudo docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. проверки
sudo docker compose -f deploy/docker-compose.prod.yml ps
#   migrate → Exited (0); api → Up (healthy); bot/caddy/redis/postgres → Up
sudo docker compose -f deploy/docker-compose.prod.yml logs --tail=20 bot
#   "Run polling ..." без TelegramConflictError
curl https://<домен>/health                         # {"status":"ok"}
./scripts/prod_healthcheck.sh
```

Бэкап БД: `./scripts/backup_postgres.sh` (каталог `backups/` в `.gitignore` — не коммитить).

### Прод без своего домена/VPS (например, Google Cloud Shell)

Вместо Caddy можно отдать API через быстрый туннель Cloudflare и пропустить сервис `caddy`:

```bash
docker run --rm -it --network deploy_default \
  cloudflare/cloudflared:latest tunnel --url http://api:8000
```

Выдаст `https://<random>.trycloudflare.com` → этот URL в `COURSES_BOT_API_URL` на сайте.
Это **временное** решение: URL меняется при каждом перезапуске туннеля, аптайм не гарантирован.
Для постоянной работы — VPS + Caddy + свой домен (вариант выше).

## Команды бота

### Пользовательские

| Команда | Что делает |
|---------|------------|
| `/start` | Без токена. Есть активный доступ — показывает каталог тренировок; иначе подсказку «оплати на сайте». |
| `/start <TOKEN>` | Deep link с сайта. Активирует токен, выдаёт тариф на срок, сразу открывает каталог. Если ссылка уже использована, но доступ активен — просто откроет каталог. |
| `/activate <TOKEN>` | Ручная активация токена (если deep link не сработал). |
| `/catalog` | Каталог («Мої тренування»): группы → подгруппы → видео. Показывает тариф и сколько дней осталось. |
| `/myaccess` | Синоним `/catalog` («мій доступ і термін»). |
| `/mycourses` | Синоним `/catalog` (для совместимости). |
| `/help` | Список команд. Админам дополнительно показывает `/admin`. |

Навигация по каталогу — инлайн-кнопками: `📁 Група` → подгруппы/видео → `▶️ Відео` (карточка
с обложкой и кнопкой **«▶️ Дивитись»** на YouTube), `⬅️ Назад`. Контент фильтруется по тарифу,
доступ проверяется по сроку на каждом заходе.

### Админские (только id из `ADMIN_IDS`)

| Команда | Что делает |
|---------|------------|
| `/admin` | Открывает панель управления каталогом. |

Внутри `/admin` всё на инлайн-кнопках (отдельных команд нет):

- **➕ Нова група** — создать группу верхнего уровня (бот спросит название).
- В группе: **➕ Підгрупа**, **➕ Відео**, **✏️ Назва**, **🗑 Видалити**, ряд тарифов
  **`Lite / Pro / VIP`** (минимальный тариф для показа группы), **⬅️ Назад**.
- **➕ Відео** — бот просит ссылку на YouTube; сам подтягивает название и обложку (yt-dlp) и
  создаёт видео. `min_tier` видео наследуется от группы, меняется кнопками `Lite/Pro/VIP` на
  экране видео.
- Удаление группы каскадно удаляет её подгруппы и видео (с подтверждением).

> **Важно про видео:** заливай ролики на YouTube как **«Доступ за посиланням» (unlisted)**, а не
> «Приватне». Приватные видны только приглашённым по почте — бот не вытащит обложку и не покажет
> их покупателю. Для истинно приватных нужен `YOUTUBE_COOKIES_FILE`.

## API endpoints

Базовый URL локально: `http://localhost:8000`. Все `/api/*` требуют заголовок
`X-API-Key: <SITE_API_KEY>` и лимитированы (`429` при превышении). Вызывать только с
бэкенда сайта, не из браузера.

### `GET /health`

Без авторизации. Health-check. → `{ "status": "ok" }`

### `POST /api/tokens`

Создаёт одноразовый токен под тариф. Идемпотентно по `payment_id`.

```bash
curl -X POST http://localhost:8000/api/tokens \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SITE_API_KEY" \
  -d '{ "tier": "pro", "payment_id": "pro-3f1c...uuid" }'
```

Поля запроса:

- `tier` (обяз.) — `lite` | `pro` | `vip`.
- `payment_id` (опц., ≤128) — id платежа. Повтор с тем же → `409`.
- `duration_days` (опц., 1…3650) — переопределяет срок тарифа. Обычно не передаётся.

Ответ `200`:

```json
{
  "token": "raw-token",
  "tier": "pro",
  "duration_days": 30,
  "payment_id": "pro-3f1c...uuid",
  "token_preview": "abc123...wxyz",
  "telegram_link": "https://t.me/your_course_bot?start=raw-token"
}
```

Ошибки: `400` — неизвестный тариф; `401` — неверный `X-API-Key`; `409` — `payment_id` уже
использован (норма для ретрая вебхука); `429` — rate limit.

### `GET /api/access/check`

Текущий доступ пользователя (высший непросроченный тариф).

```bash
curl "http://localhost:8000/api/access/check?telegram_id=692080442" \
  -H "X-API-Key: $SITE_API_KEY"
```

Ответ `200`:

```json
{
  "telegram_id": 692080442,
  "has_access": true,
  "tier": "pro",
  "expires_at": "2026-07-22T10:00:00+00:00",
  "frozen": false
}
```

Нет доступа → `has_access: false`, `tier: null`, `expires_at: null`, `frozen: false`.
`frozen: true` — грант активен, но доступ к тарифу временно приостановлен админом
(см. заморозку ниже); пользователь каталог не видит.

### `POST /api/tiers/{tier}/freeze`

Приостановить или вернуть доступ к тренировкам для всех пользователей тарифа.
Грант не сгорает — при снятии заморозки доступ возвращается. `tier` — `lite` | `pro` | `vip`.

```bash
curl -X POST http://localhost:8000/api/tiers/pro/freeze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SITE_API_KEY" \
  -d '{ "frozen": true }'
```

Ответ `200`: `{ "tier": "pro", "frozen": true }`. Ошибки: `400` — неизвестный тариф; `401`; `429`.

### `GET /api/tiers/freeze`

Список замороженных тарифов. → `{ "frozen": ["pro"] }`.

### `POST /api/users/{telegram_id}/tier`

Вручную выставить тариф пользователю (админ-оверрайд). Гасит текущие активные гранты и
создаёт новый на стандартный срок тарифа (lite/pro — 30 дн, vip — 90). Работает и для
пользователя, которого ещё нет в БД. `tier: "none"` — снять доступ.

```bash
curl -X POST http://localhost:8000/api/users/692080442/tier \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SITE_API_KEY" \
  -d '{ "tier": "pro" }'
```

Поле `tier` (обяз.) — `none` | `lite` | `pro` | `vip`.

Ответ `200`: `{ "telegram_id": 692080442, "tier": "pro", "expires_at": "2026-07-31T20:00:00+00:00" }`.
Для `none` → `tier: null`, `expires_at: null`. Ошибки: `400` — неизвестный тариф; `401`; `429`.

## Контракт сайт ↔ бот

```text
фронтенд сайта → бэкенд сайта → CoursesSalesBot API
```

1. Покупатель оплачивает тариф (Monobank) на сайте.
2. Вебхук сайта вызывает `POST /api/tokens` с `{ payment_id, tier }` (tier = префикс reference).
3. Бот отдаёт `telegram_link`; сайт показывает кнопку «Перейти в Telegram».
4. Покупатель открывает ссылку → бот активирует токен → выдаёт тариф на срок → каталог.
5. (Опц.) Сайт сверяется через `GET /api/access/check`.

## How to test (E2E)

1. Подними бота локально (см. «Полный чистый запуск — Dev»).
2. В Telegram: `/admin` → создай группу → добавь видео ютуб-ссылкой. Часть видео пометь
   `min_tier=pro`.
3. Выдай себе тариф: `POST /api/tokens { "tier": "lite" }`, открой `telegram_link`.
   Убедись, что `pro`-видео НЕ видно. Повтори с `tier: "vip"` — видно всё.
4. Срок: `/myaccess` показывает оставшиеся дни.
5. Дубль платежа: повтори `POST /api/tokens` с тем же `payment_id` → `409`.

## Известные ограничения / phase 2

- Нет перестановки порядка групп/видео в UI (поле `position` есть, кнопок ↑/↓ нет).
- Нет авто-уведомления об истечении доступа.
- Легаси course-таблицы и модули не удалены.
- Тесты есть только на YouTube-парсер (`tests/test_youtube_parser.py`).

## Troubleshooting

### `TelegramConflictError: terminated by other getUpdates request`

Один токен бота = один long-polling consumer. Убедись, что бот не запущен где-то ещё:

```bash
sudo docker compose down --remove-orphans
sudo docker compose up --build
```

Для параллельного локал/прод-тестирования используй разные токены ботов.
