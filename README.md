# FastLM API

[![CI](https://github.com/kiurakku/FastLM-API/actions/workflows/ci.yml/badge.svg?branch=main&event=push)](https://github.com/kiurakku/FastLM-API/actions/workflows/ci.yml?query=branch%3Amain)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

OpenAI-compatible LLM gateway with API keys, request quotas, token budgeting, webhook delivery, and plugin-based request processing.

Designed as a practical backend service, not a toy endpoint: it has auth, quota controls, logs, tests, Docker runtime, and CI for both unit and integration flows.

<p align="center">
  <img src="docs/images/fastlm-cover.jpg" alt="FastLM project visual" width="720" />
</p>

## Where this fits

FastLM is the service layer in a 3-repository stack:

- [Hookify](https://github.com/kiurakku/Hookify): reusable hook/plugin framework.
- **FastLM-API**: OpenAI-compatible gateway + governance controls.
- [BOLA](https://github.com/kiurakku/BOLA): security training lab that demonstrates auth pitfalls.

## Features

- OpenAI-style `POST /v1/chat/completions` endpoint.
- JSON response mode and SSE streaming mode.
- API-key authentication (`Authorization: Bearer sk-...`).
- Admin endpoints for key creation, webhooks, usage aggregation.
- Per-minute rate limiting via Redis.
- Monthly token budget checks with webhook notification.
- Token counting via `tiktoken` (`cl100k_base`).
- HMAC-SHA256 webhook signatures (`X-Signature: sha256=...`).
- Hookify plugin pipeline (`before_request` / `after_response`).

## Architecture

```text
Client
  -> FastAPI app (app/main.py)
      -> routers/admin.py
      -> routers/completions.py
      -> services/quota.py        (Redis window counters)
      -> services/tokens.py       (tiktoken)
      -> services/request_log.py  (PostgreSQL)
      -> services/webhooks.py     (signed delivery + retries)
      -> plugins_setup.py         (Hookify registry)

Data layer:
  PostgreSQL (keys, request logs, webhook subscriptions)
  Redis      (minute buckets: quota:{user_id}:{bucket})
```

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/admin/keys` | Create API key (requires `X-Admin-Secret`) |
| `POST` | `/admin/webhooks` | Register webhook targets |
| `GET` | `/admin/usage` | Aggregate usage by user/time range |
| `POST` | `/v1/chat/completions` | Chat completion (JSON or stream) |

## Quick start (Docker)

```bash
git clone https://github.com/kiurakku/FastLM-API.git
cd FastLM-API
cp .env.example .env
# set FASTLM_ADMIN_SECRET (and OPENAI_API_KEY if needed)
docker compose up --build
```

Service URL: `http://localhost:8001`

## Quick API examples

Create key:

```bash
curl -sS -X POST http://localhost:8001/admin/keys \
  -H "X-Admin-Secret: $FASTLM_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"label":"demo"}'
```

Non-stream request:

```bash
curl -sS -X POST http://localhost:8001/v1/chat/completions \
  -H "Authorization: Bearer sk-REPLACE_ME" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}]}'
```

SSE stream:

```bash
curl -sS -N -X POST http://localhost:8001/v1/chat/completions \
  -H "Authorization: Bearer sk-REPLACE_ME" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"stream this"}]}'
```

## Plugin pipeline behavior

1. Request payload is converted into Hookify `RequestContext`.
2. `plugin_registry.run_before(ctx)` may mask content, reject request, or audit data.
3. Completion executes (OpenAI call or local mock fallback).
4. `plugin_registry.run_after(ctx, response)` can post-process response.

Currently wired in `plugins_setup.py`: `pii_mask`, `prompt_injection`, `audit`.

## Environment variables

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | SQLAlchemy async DB URL |
| `REDIS_URL` | Redis URL for rate-limiting buckets |
| `ADMIN_SECRET` | Secret for admin endpoints |
| `OPENAI_API_KEY` | Optional; if empty service uses deterministic mock response |
| `OPENAI_BASE_URL` | Upstream OpenAI-compatible base URL |
| `WEBHOOK_HMAC_SECRET` | Secret used to sign webhook body |
| `ENABLED_PLUGINS` | Comma-separated plugins |
| `DEFAULT_MONTHLY_TOKEN_BUDGET` | Per-user monthly token cap |
| `REQUESTS_PER_MINUTE` | Per-user per-minute request cap |

## Testing

### Unit tests (fast, isolated)

- SQLite in-memory DB
- mocked Redis client
- tests for admin auth, API-key auth, mock completions, quota 429, webhook signature

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/unit -v --tb=short
```

### Integration test (stream + SDK)

```bash
docker compose up -d --build
pip install -r requirements.txt -r tests/requirements.txt
pip install ./sdk
FASTLM_BASE=http://127.0.0.1:8001 FASTLM_ADMIN_SECRET=$FASTLM_ADMIN_SECRET pytest tests/test_stream.py -v --tb=short
```

## CI

GitHub Actions runs:

- `unit` job: install + Ruff + unit tests.
- `integration` job: Docker Compose stack + stream/SDK integration test.

## SDK

Python SDK lives in `sdk/` and supports sync + async chat and streaming.
See `sdk/README.md`.

---

Recommended GitHub About fields:

- **Description**: `OpenAI-compatible LLM gateway with API keys, Redis quotas, webhooks and plugin pipeline`
- **Topics**: `python`, `fastapi`, `openai`, `llm`, `api-gateway`, `redis`
