import os, time, subprocess, requests, psycopg2
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
    """Open Google News search in headless browser, return list of (title, google_url)."""
    context = browser.new_context(
        user_agent=HEADERS["User-Agent"],
        locale="en-US",
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()
    results = []
    try:
        search_url = f"https://news.google.com/search?q={requests.utils.quote(keyword)}&hl=en-US&gl=US&ceid=US:en"
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        articles = page.query_selector_all("article")
        for article in articles[:7]:
            try:
                a = article.query_selector("h3 a, h4 a")
                if not a:
                    continue
                title = a.inner_text().strip()
                href = a.get_attribute("href") or ""
                if href.startswith("./"):
                    href = "https://news.google.com" + href[1:]
                elif href.startswith("/"):
                    href = "https://news.google.com" + href
                if title and href:
                    results.append((title, href))
            except Exception:
                continue
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
    rewritten_title = title
    rewritten_body = text
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

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
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

                    print(f"  rewriting: {title[:60]}", flush=True)
                    try:
                        rt, rb = rewrite(title, content)
                    except Exception as e:
                        print(f"  rewrite error: {e}", flush=True)
                        continue

                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO articles (original_url,title,original_content,rewritten_title,rewritten_body,keyword,published_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (original_url) DO NOTHING
                        """, (real_url, title, content, rt, rb, keyword, datetime.utcnow()))
                    conn.commit()
                    print(f"  saved: {rt[:60]}", flush=True)
                    time.sleep(2)

                time.sleep(3)  # pause between keywords to avoid rate limiting
        finally:
            browser.close()

    conn.close()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
