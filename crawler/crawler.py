import os, time, re, json as _json, requests, psycopg2
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

DB_URL  = os.environ.get("DATABASE_URL", "postgresql://rduser:rd_pass_2026@localhost:5432/robotdefense")
PROXY   = os.environ.get("SOCKS5_PROXY", "socks5://100.106.168.18:1080")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
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
                image_url        TEXT,
                published_at     TIMESTAMP,
                created_at       TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS image_url TEXT")
    conn.commit()


def search_google_news(browser, keyword):
    """Search Google News, return list of (title, url, thumbnail_url)."""
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
            // article thumbnails are 200x112, class includes 'Quavad'
            const thumbs = Array.from(document.querySelectorAll('img'))
                .filter(img => img.src && !img.src.startsWith('data:') &&
                               (img.naturalWidth || img.width) >= 150)
                .map(img => img.src);
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const text = a.textContent.trim();
                if (href.includes('news.google.com/read/') && text.length > 20 && !seen.has(href)) {
                    seen.add(href);
                    links.push({href, text});
                }
            });
            return links.slice(0, 7).map((link, i) => ({
                href: link.href,
                text: link.text,
                img: thumbs[i] || ''
            }));
        }""")
        results = [(i["text"], i["href"], i["img"]) for i in items]
    finally:
        context.close()
    return results[:5]


def resolve_url(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10, headers=HEADERS)
        return r.url
    except Exception:
        return url


def extract_image(soup):
    """Try all image sources from a parsed page, return best URL or None."""
    # 1. og:image / twitter:image meta tags
    for attr in [{"property": "og:image"}, {"property": "og:image:url"},
                 {"name": "twitter:image"}, {"name": "twitter:image:src"}]:
        tag = soup.find("meta", attrs=attr)
        if tag:
            src = tag.get("content", "").strip()
            if src.startswith("http"):
                return src

    # 2. JSON-LD structured data (NewsArticle, Article)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            img = data.get("image") or data.get("thumbnailUrl")
            if isinstance(img, dict):
                img = img.get("url") or img.get("contentUrl")
            if isinstance(img, list):
                img = img[0] if img else None
                if isinstance(img, dict):
                    img = img.get("url")
            if img and str(img).startswith("http"):
                return str(img)
        except Exception:
            continue

    # 3. First large <img> in article body (skip tiny icons/trackers)
    skip = {"icon", "logo", "avatar", "pixel", "1x1", "spacer", "placeholder", "spinner"}
    for img_tag in soup.find_all("img"):
        src = (img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src") or "").strip()
        if not src.startswith("http"):
            continue
        if any(s in src.lower() for s in skip):
            continue
        try:
            w = int(str(img_tag.get("width", "0")).replace("px", ""))
            if w < 200:
                continue
        except ValueError:
            pass
        return src

    return None


def fetch_wiki_image(query):
    """Wikipedia page image search — free, no API key, no rate limiting."""
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php",
                         params={"action": "query", "list": "search",
                                 "srsearch": query, "srlimit": 3,
                                 "format": "json", "srprop": ""},
                         headers=HEADERS, timeout=10)
        results = r.json().get("query", {}).get("search", [])
        if not results:
            return None
        titles = "|".join(res["title"] for res in results)
        r2 = requests.get("https://en.wikipedia.org/w/api.php",
                          params={"action": "query", "titles": titles,
                                  "prop": "pageimages", "pithumbsize": 800,
                                  "format": "json", "pilicense": "any"},
                          headers=HEADERS, timeout=10)
        for page in r2.json().get("query", {}).get("pages", {}).values():
            src = page.get("thumbnail", {}).get("source", "")
            if src.startswith("http"):
                return src
    except Exception:
        pass
    return None


def scrape(url):
    """Fetch article, return (content, image_url)."""
    try:
        r = requests.get(url, timeout=15, allow_redirects=True, headers=HEADERS)
        soup = BeautifulSoup(r.content, "html.parser")
        image_url = extract_image(soup)

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        for sel in ["article", "[class*='article-body']", "[class*='story-body']",
                    "[class*='post-content']", "[class*='entry-content']", "main", ".content"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 300:
                    return text[:4000], image_url
        text = soup.get_text(" ", strip=True)
        return (text[:4000] if len(text) > 300 else None), image_url
    except Exception as e:
        print(f"  scrape error: {e}", flush=True)
        return None, None


def backfill_images(conn):
    """Fill image_url for articles that have none: try scrape then DDG search."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, original_url, title, keyword
            FROM articles WHERE image_url IS NULL LIMIT 60
        """)
        rows = cur.fetchall()
    if not rows:
        return
    print(f"[~] Backfilling images for {len(rows)} articles...", flush=True)
    for aid, url, title, keyword in rows:
        img_url = None
        try:
            r = requests.get(url, timeout=10, allow_redirects=True, headers=HEADERS)
            soup = BeautifulSoup(r.content, "html.parser")
            img_url = extract_image(soup)
        except Exception:
            pass

        if not img_url:
            query = f"{title} {keyword}" if title else keyword
            img_url = fetch_wiki_image(query) or fetch_wiki_image(keyword)

        if img_url:
            print(f"  wiki image: {title[:50]}", flush=True)
            with conn.cursor() as cur:
                cur.execute("UPDATE articles SET image_url=%s WHERE id=%s", (img_url, aid))
            conn.commit()
        time.sleep(0.5)


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

                for title, google_url, thumbnail in entries:
                    real_url = resolve_url(google_url)

                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM articles WHERE original_url=%s", (real_url,))
                        if cur.fetchone():
                            print(f"  skip (exists): {title[:60]}", flush=True)
                            continue

                    content, og_image = scrape(real_url)
                    if not content:
                        print(f"  skip (no content): {title[:60]}", flush=True)
                        continue

                    # prefer og:image → GN thumbnail → DDG search
                    image_url = og_image or thumbnail or fetch_wiki_image(f"{title} {keyword}")

                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO articles
                                (original_url, title, original_content, rewritten_title, rewritten_body,
                                 keyword, image_url, published_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (original_url) DO NOTHING
                        """, (real_url, title, content, title, content, keyword, image_url, datetime.utcnow()))
                    conn.commit()
                    print(f"  saved: {title[:60]}", flush=True)
                    time.sleep(2)

                time.sleep(3)
        finally:
            browser.close()

    backfill_images(conn)
    conn.close()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
