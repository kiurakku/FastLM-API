# FastLM API

OpenAI-сумісний шлюз: `POST /v1/chat/completions` (JSON і **SSE-стримінг**), API-ключі, Redis (ліміт/хв), PostgreSQL, webhooks, інтеграція з [Hookify](https://github.com/kiurakku/Hookify).

## Залежність від Hookify

Docker-збірка виконує `pip install git+https://github.com/kiurakku/Hookify.git@main`. Спочатку запуште репозиторій **Hookify**, потім цей.

## Швидкий старт

```bash
git clone https://github.com/kiurakku/FastLM-API.git
cd FastLM-API
cp .env.example .env
# Задайте FASTLM_ADMIN_SECRET; опційно OPENAI_API_KEY
docker compose up --build
```

- API: [http://localhost:8001](http://localhost:8001)  
- Ключ: `curl -sS -X POST http://localhost:8001/admin/keys -H "X-Admin-Secret: $FASTLM_ADMIN_SECRET" -H "Content-Type: application/json" -d '{"label":"demo"}'`

## Python SDK

Каталог `sdk/` (встановлення: `pip install ./sdk`). Див. `sdk/README.md`.

## Git: порядок публікації

1. [Hookify](https://github.com/kiurakku/Hookify) — `git push origin main`  
2. **FastLM-API** (цей репо) — після того, як Hookify доступний на GitHub  
3. За потреби [BOLA](https://github.com/kiurakku/BOLA) — окремий стенд

```bash
cd /шлях/до/FastLM-API
git status
git add -A
git commit -m "Опис коміту"
git push -u origin main
```

## Ліцензія

Навчальний / демо-код; не використовуйте дефолтні секрети в проді.
