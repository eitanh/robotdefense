# crawler

Python job that fetches robot/AI security news, scrapes article content, rewrites it with Claude, and stores it in PostgreSQL.

## How it works

1. Queries Google News RSS for each keyword in `KEYWORDS`
2. Resolves redirect URLs (Google News wraps links)
3. Scrapes article body — tries `article`, `[class*='article-body']`, `main`, etc.
4. Falls back to RSS `<summary>` if scrape returns < 300 chars
5. Calls `claude -p` on the host to rewrite in a security-editor voice
6. Inserts into `articles` table; skips duplicates via `original_url` UNIQUE constraint

## Database schema

```sql
CREATE TABLE articles (
    id               SERIAL PRIMARY KEY,
    original_url     TEXT UNIQUE,
    title            TEXT,
    original_content TEXT,
    rewritten_title  TEXT,
    rewritten_body   TEXT,
    keyword          TEXT,
    published_at     TIMESTAMP,
    created_at       TIMESTAMP DEFAULT NOW()
);
```

## Running

```bash
pip install -r requirements.txt
DATABASE_URL="postgresql://..." python crawler.py
```

Or via the host script (used by systemd / cron on bare metal):
```bash
./run-crawler.sh
```

## Docker

```bash
docker build -t robot-news-crawler:latest .
docker run --rm -e DATABASE_URL="..." robot-news-crawler:latest
```

## Notes

- The `claude` binary must be on `PATH` and authenticated
- Scraping sleeps 2s between articles to avoid rate limits
- `ANTHROPIC_API_KEY` env var is passed in k8s but the Claude CLI manages its own auth on bare metal
