import os, time, requests, psycopg2
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.sync_api import sync_playwright

KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS",
    "robot hacked,robot cyberattack,robot exploit,robot vulnerability,robot malware,"
    "autonomous vehicle hacked,drone hacked,drone exploit,self-driving car hack,"
    "industrial robot attack,ICS robot,OT security robot,SCADA robot,"
    "AI weapon attack,AI autonomous weapon,LLM jailbreak attack,AI safety incident,"
    "Boston Dynamics security,surgical robot hack,military robot attack"
).split(",")]

DB_URL = os.environ.get("DATABASE_URL", "postgresql://rduser:rd_pass_2026@localhost:5432/robotdefense")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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


def search_google_news(browser, keyword):
    """Search Google News in headless browser, return list of (title, url)."""
    context = browser.new_context(
        user_agent=HEADERS["User-Agent"],
        locale="en-US",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = context.new_page()
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        pass
    results = []
    try:
        search_url = f"https://news.google.com/search?q={requests.utils.quote(keyword)}&hl=en-US&gl=US&ceid=US:en"
        page.goto(search_url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3000)

        items = page.evaluate("""() => {
            const seen = new Set();
            const out = [];
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const text = a.textContent.trim();
                if (href.includes('news.google.com/read/') && text.length > 20 && !seen.has(href)) {
                    seen.add(href);
                    out.push({href, text});
                }
            });
            return out.slice(0, 7);
        }""")
        results = [(i["text"], i["href"]) for i in items]
    finally:
        context.close()
    return results[:5]


def resolve_url(url):
    """Follow Google News redirect to get the real article URL."""
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


PROXY = os.environ.get("SOCKS5_PROXY", "socks5://100.106.168.18:1080")


def main():
    conn = psycopg2.connect(DB_URL)
    init_db(conn)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy={"server": PROXY},
        )
        try:
            for keyword in KEYWORDS:
                print(f"[+] Keyword: {keyword}", flush=True)
                try:
                    entries = search_google_news(browser, keyword)
                except Exception as e:
                    print(f"  search error: {e}", flush=True)
                    continue

                for title, google_url in entries:
                    real_url = resolve_url(google_url)

                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM articles WHERE original_url=%s", (real_url,))
                        if cur.fetchone():
                            print(f"  skip (exists): {title[:60]}", flush=True)
                            continue

                    content = scrape(real_url)
                    if not content:
                        print(f"  skip (no content): {title[:60]}", flush=True)
                        continue

                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO articles (original_url,title,original_content,rewritten_title,rewritten_body,keyword,published_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (original_url) DO NOTHING
                        """, (real_url, title, content, title, content, keyword, datetime.utcnow()))
                    conn.commit()
                    print(f"  saved: {title[:60]}", flush=True)
                    time.sleep(2)

                time.sleep(3)  # pause between keywords to avoid rate limiting
        finally:
            browser.close()

    conn.close()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
