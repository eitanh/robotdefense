# robotdefense.io

Automated robot and AI security threat intelligence. Crawls Google News for relevant articles, rewrites them with Claude, and displays them on a dark-themed news feed.

## Architecture

```
[Google News RSS] → crawler → PostgreSQL → web (FastAPI) → robotdefense.io
```

Three services:

| Service | Description |
|---------|-------------|
| `crawler/` | Python job — fetches RSS, scrapes articles, rewrites with Claude CLI, stores to Postgres |
| `web/` | FastAPI app — reads from Postgres, serves dark-themed HTML news feed |
| `k8s/` | Kubernetes manifests — deploys all services + CronJob + Ingress |

## Local dev

### Requirements
- Python 3.11+
- PostgreSQL running locally
- `claude` CLI installed and authenticated

### Run the crawler
```bash
cd crawler
pip install -r requirements.txt
DATABASE_URL="postgresql://rduser:rd_pass_2026@localhost:5432/robotdefense" python crawler.py
```

### Run the web server
```bash
cd web
pip install -r requirements.txt
DATABASE_URL="postgresql://..." uvicorn main:app --reload
```

## Kubernetes deployment

All resources live in the `robotdefense` namespace.

```bash
# Set your real API key first
sed -i '' 's/REPLACE_ME/your-key/' k8s/deploy.yaml

kubectl create namespace robotdefense
kubectl apply -f k8s/deploy.yaml
```

The crawler runs as a **CronJob every hour** (`0 * * * *`). The web app is exposed via Traefik Ingress with Let's Encrypt TLS at `robotdefense.io`.

### Build images (local cluster)
```bash
docker build -t robot-news-crawler:latest ./crawler
docker build -t robotdefense-web:latest ./web
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://rduser:rd_pass_2026@localhost:5432/robotdefense` | Postgres connection string |
| `KEYWORDS` | `robot hacked,robot attack,robot security,AI robot threat,robot vulnerability` | Comma-separated search terms |
| `ANTHROPIC_API_KEY` | — | Required in k8s; on host the `claude` CLI uses its own auth |

## How the crawler works

1. For each keyword, fetches top 5 entries from Google News RSS
2. Resolves redirect URLs and scrapes article body text
3. Falls back to RSS summary if the full scrape returns < 300 chars
4. Calls `claude -p` with a security-editor prompt to rewrite title + body
5. Inserts into `articles` table (deduped on `original_url`)
