# web

FastAPI app that reads rewritten articles from PostgreSQL and renders a dark-themed security news feed.

## Routes

| Route | Description |
|-------|-------------|
| `GET /` | HTML news feed — latest 50 articles, expandable cards |
| `GET /health` | Health check — returns `{"status": "ok"}` |

## Running

```bash
pip install -r requirements.txt
DATABASE_URL="postgresql://..." uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t robotdefense-web:latest .
docker run --rm -p 8000:8000 -e DATABASE_URL="..." robotdefense-web:latest
```

## UI

- Dark theme (`#0a0a0a` background, `#00ff88` accent)
- Article cards collapse/expand on click
- Shows keyword tag, publish date, rewritten body, and link to original source
- Displays a "NO INTEL YET" placeholder if the crawler hasn't run
