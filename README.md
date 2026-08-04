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

<img width="1598" height="857" alt="image" src="https://github.com/user-attachments/assets/438c9c7a-99f1-455b-8b53-92e2e6e41058" />
<img width="1600" height="876" alt="image" src="https://github.com/user-attachments/assets/d839a088-3778-40ce-9f93-b38506687a43" />
<img width="1675" height="874" alt="image" src="https://github.com/user-attachments/assets/ba497e3e-c810-469c-84de-83d659ecf7a3" />



