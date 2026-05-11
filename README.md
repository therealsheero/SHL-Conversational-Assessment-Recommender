# SHL Conversational Assessment Recommender

## Endpoints

- `GET /health` returns `{"status": "ok"}`
- `POST /chat` accepts stateless conversation history and returns:

```json
{
  "reply": "string",
  "recommendations": [
    {"name": "Assessment name", "url": "https://www.shl.com/...", "test_type": "K"}
  ],
  "end_of_conversation": false
}
```

## Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then visit `http://localhost:8000/health`.

## Design

The service is stateless. Each `/chat` call reads the full provided conversation,
extracts role, seniority, assessment type, duration, and refinement signals, and
uses local catalog retrieval to choose only URLs that exist in the scraped SHL
catalog.

The runtime path does not call an LLM. This keeps cold start predictable, avoids
API-key failures, and prevents prompt-injection attempts from changing scope.
Retrieval combines weighted keyword matching, catalog metadata, test-type
intent mapping, duration filtering, and diversification across requested test
types.
