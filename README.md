# FastLM API

[![CI](https://github.com/kiurakku/FastLM-API/actions/workflows/ci.yml/badge.svg)](https://github.com/kiurakku/FastLM-API/actions/workflows/ci.yml)

OpenAI-сумісний шлюз: `POST /v1/chat/completions` (JSON і **SSE-стримінг**), API-ключі, Redis (ліміт запитів на хвилину), PostgreSQL, webhooks (HMAC-SHA256), інтеграція з [Hookify](https://github.com/kiurakku/Hookify). Підрахунок токенів — **tiktoken** (`cl100k_base`).

## Екосистема з трьох репозиторіїв

| Репозиторій | Роль |
|-------------|------|
| [BOLA](https://github.com/kiurakku/BOLA) | Навчальний стенд OWASP (BOLA/IDOR) на FastAPI |
| **FastLM-API** | Реалістичний API-шлюз з квотами та плагінами |
| [Hookify](https://github.com/kiurakku/Hookify) | Легка бібліотека before/after хуків для запитів до LLM |

## Архітектура (спрощено)

```
Client ──► FastAPI (app/)
            ├── routers/admin.py      … ключі, webhooks, usage
            ├── routers/completions.py … /v1/chat/completions
            ├── services/quota.py     … Redis INCR по хвилині
            ├── services/tokens.py    … tiktoken
            ├── services/webhooks.py  … підпис і відправка
            └── plugins_setup.py      … Hookify registry
                     │
PostgreSQL ◄────────┘ (ключі, логи, webhooks)
Redis ◄────────────── (quota:{user}:{bucket})
```

## Ендпоінти

| Метод | Шлях | Опис |
|--------|------|------|
| GET | `/health` | Перевірка живості |
| POST | `/admin/keys` | Створити API-ключ (заголовок `X-Admin-Secret`) |
| POST | `/admin/webhooks` | Зареєструвати webhook |
| GET | `/admin/usage` | Агреговане використання по `user_id` (query) |
| POST | `/v1/chat/completions` | OpenAI-сумісний чат (`Authorization: Bearer sk-…`) |

### Приклади curl

Створити ключ (підставте свій секрет):

```bash
curl -sS -X POST http://localhost:8001/admin/keys \
  -H "X-Admin-Secret: $FASTLM_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"label":"demo"}'
```

Чат без OpenAI (mock-режим, якщо `OPENAI_API_KEY` порожній):

```bash
curl -sS -X POST http://localhost:8001/v1/chat/completions \
  -H "Authorization: Bearer sk-ВАШ_КЛЮЧ" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Привіт"}]}'
```

Стрім (SSE):

```bash
curl -sS -N -X POST http://localhost:8001/v1/chat/completions \
  -H "Authorization: Bearer sk-ВАШ_КЛЮЧ" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"hi"}]}'
```

## Пайплайн плагінів (Hookify)

1. Запит потрапляє в `chat_completions`; тіло перетворюється на `RequestContext`.
2. `plugin_registry.run_before(ctx)` — плагіни можуть змінювати `ctx.body`, писати в `ctx.extras` або відхилити запит (`http_reject`).
3. Після відповіді (mock, OpenAI або стрім) викликається `run_after` для постобробки відповіді.

Увімкнені плагіни задаються змінною `ENABLED_PLUGINS` (наприклад `audit,pii_mask,prompt_injection,cost_limit`).

## Залежність від Hookify

Docker-збірка виконує `pip install git+https://github.com/kiurakku/Hookify.git@…`. Для локальних **unit**-тестів у `requirements-dev.txt` теж вказано встановлення Hookify з GitHub.

## Розробка та тести

- Структура коду: пакет `app/` (роутери, сервіси, моделі).
- Unit-тести (SQLite in-memory, Redis підміняється): `pytest tests/unit`
- Інтеграція (Docker Compose + SDK-стрім): `pytest tests/test_stream.py` з піднятим `docker compose` і змінними `FASTLM_BASE`, `FASTLM_ADMIN_SECRET`.

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/unit -v
```

За замовчуванням `pytest` з кореня пропускає маркер `integration`; інтеграційні тести запускайте явно.

## Швидкий старт (Docker)

```bash
git clone https://github.com/kiurakku/FastLM-API.git
cd FastLM-API
cp .env.example .env
# Задайте FASTLM_ADMIN_SECRET; опційно OPENAI_API_KEY
docker compose up --build
```

- API: [http://localhost:8001](http://localhost:8001)

## Python SDK

Каталог `sdk/` — `pip install ./sdk`. Деталі в `sdk/README.md`.

## Git: порядок публікації

1. [Hookify](https://github.com/kiurakku/Hookify) — спочатку в репозиторії має бути доступний пакет.
2. **FastLM-API** (цей репо).
3. За потреби [BOLA](https://github.com/kiurakku/BOLA) — окремий стенд.

## Ліцензія

Навчальний / демо-код; не використовуйте дефолтні секрети в проді.
