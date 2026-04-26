# fastlm-sdk

Мінімальний Python-клієнт для [FastLM API](../fastlm-api): синхронний `chat()` та `stream_chat()` з парсингом SSE.

## Встановлення

```bash
pip install ./fastlm-sdk
```

## Приклад

```python
from fastlm_sdk import FastLMClient, Message

c = FastLMClient(base_url="http://localhost:8001", api_key="sk-...")
r = c.chat(model="gpt-4o-mini", messages=[Message(role="user", content="Привіт!")])
print(r.assistant_text)

for delta in c.stream_chat(model="gpt-4o-mini", messages=[Message(role="user", content="1..2..3")]):
    print(delta, end="", flush=True)
```

### Асинхронно

```python
import asyncio
from fastlm_sdk import AsyncFastLMClient, Message

async def main():
    c = AsyncFastLMClient(base_url="http://localhost:8001", api_key="sk-...")
    r = await c.chat(model="gpt-4o-mini", messages=[Message(role="user", content="Hi")])
    print(r.assistant_text)
    async for d in c.stream_chat(model="gpt-4o-mini", messages=[Message(role="user", content="Stream")]):
        print(d, end="", flush=True)

asyncio.run(main())
```
