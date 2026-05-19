import os, time, subprocess, feedparser, requests, psycopg2
from bs4 import BeautifulSoup
from datetime import datetime

KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "robot hacked,robot attack,robot security,AI robot threat,robot vulnerability").split(",")]
DB_URL   = os.environ.get("DATABASE_URL", "postgresql://rduser:rd_pass_2026@localhost:5432/robotdefense")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def init_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id               SERIAL PRIMARY KEY,
                original_url     TEXT UNIQUE,
                title            TEXT,
                original_content TEXT,
                rewritten_title  TEXT,
                rewritten_body   TEXT,
                keyword          TEXT,
                published_at     TIMESTAMP,
                created_at       TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()

def fetch_feed(keyword):
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(keyword)}&hl=en-US&gl=US&ceid=US:en"
    return feedparser.parse(url).entries

def resolve_url(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10, headers=HEADERS)
        return r.url
    except Exception:
        return url

def scrape(url):
    try:
        r = requests.get(url, timeout=15, allow_redirects=True, headers=HEADERS)
        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        for sel in ["article", "[class*='article-body']", "[class*='story-body']",
                    "[class*='post-content']", "[class*='entry-content']", "main", ".content"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 300:
                    return text[:4000]
        text = soup.get_text(" ", strip=True)
        return text[:4000] if len(text) > 300 else None
    except Exception as e:
        print(f"  scrape error: {e}", flush=True)
        return None

def get_content(entry):
    """Try full scrape first, fall back to RSS summary."""
    url = resolve_url(entry.get("link", ""))
    content = scrape(url)
    if content and len(content) > 300:
        return url, content

    # Fall back to RSS summary/description
    summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)
    if len(summary) > 100:
        print("  using RSS summary as fallback", flush=True)
        return url, summary

    return url, None

def rewrite(title, content):
    prompt = (
        "You are an editor for robotdefense.io, a cybersecurity news site focused on robot and AI security threats. "
        "Rewrite this article in a sharp, professional security-focused tone.\n"
        "Return ONLY in this exact format:\n"
        "TITLE: <rewritten title>\n"
        "BODY: <rewritten article, 2-4 paragraphs>\n\n"
        f"Original title: {title}\n\nContent:\n{content}"
    )
    result = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "claude exited non-zero")
    text = result.stdout.strip()
    if "TITLE:" not in text or "BODY:" not in text:
        raise RuntimeError(f"Bad format: {text[:100]}")
    rewritten_title, rewritten_body = title, text
    for line in text.splitlines():
        if line.startswith("TITLE:"):
            rewritten_title = line[6:].strip()
        if line.startswith("BODY:"):
            rewritten_body = text[text.index("BODY:") + 5:].strip()
            break
    return rewritten_title, rewritten_body

def main():
    conn = psycopg2.connect(DB_URL)
    init_db(conn)
    for keyword in KEYWORDS:
        print(f"[+] Keyword: {keyword}", flush=True)
        for entry in fetch_feed(keyword)[:5]:
            if not entry.get("link"):
                continue

            real_url, content = get_content(entry)

            with conn.cursor() as cur:
                cur.execute("SELECT id FROM articles WHERE original_url=%s", (real_url,))
                if cur.fetchone():
                    print(f"  skip (exists): {entry.title[:60]}", flush=True)
                    continue

            if not content:
                print(f"  skip (no content): {entry.title[:60]}", flush=True)
                continue

            print(f"  rewriting: {entry.title[:60]}", flush=True)
            try:
                rt, rb = rewrite(entry.title, content)
            except Exception as e:
                print(f"  rewrite error: {e}", flush=True)
                continue

            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6])

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO articles (original_url,title,original_content,rewritten_title,rewritten_body,keyword,published_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (original_url) DO NOTHING
                """, (real_url, entry.title, content, rt, rb, keyword, pub))
            conn.commit()
            print(f"  saved: {rt[:60]}", flush=True)
            time.sleep(2)

    conn.close()
    print("Done.", flush=True)

if __name__ == "__main__":
    main()
