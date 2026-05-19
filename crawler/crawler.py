import os, time, feedparser, requests, psycopg2, anthropic
from bs4 import BeautifulSoup
from datetime import datetime

KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "robot hacked,robot attack,robot security,AI robot threat").split(",")]
DB_URL   = os.environ["DATABASE_URL"]
client   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

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

def scrape(url):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 (compatible; RobotDefenseBot/1.0)"})
        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup(["script","style","nav","footer","header","aside"]):
            tag.decompose()
        for sel in ["article", "[class*='article-body']", "[class*='story-body']", "main", ".content"]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(" ", strip=True)[:4000]
        return soup.get_text(" ", strip=True)[:4000]
    except Exception as e:
        print(f"  scrape error: {e}")
        return None

def rewrite(title, content):
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system="You are an editor for robotdefense.io, a cybersecurity news site focused on robot and AI security threats. Rewrite articles in a sharp, professional security-focused tone.",
        messages=[{"role": "user", "content": (
            f"Rewrite this article. Return ONLY:\n"
            f"TITLE: <rewritten title>\n"
            f"BODY: <rewritten article body, 2-4 paragraphs>\n\n"
            f"Original title: {title}\n\nContent:\n{content}"
        )}]
    )
    text = msg.content[0].text
    rewritten_title = title
    rewritten_body  = text
    for line in text.splitlines():
        if line.startswith("TITLE:"):
            rewritten_title = line[6:].strip()
        if line.startswith("BODY:"):
            rewritten_body = text[text.index("BODY:")+5:].strip()
            break
    return rewritten_title, rewritten_body

def main():
    conn = psycopg2.connect(DB_URL)
    init_db(conn)
    for keyword in KEYWORDS:
        print(f"[+] Keyword: {keyword}")
        for entry in fetch_feed(keyword)[:5]:
            url = entry.get("link", "")
            if not url:
                continue
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM articles WHERE original_url=%s", (url,))
                if cur.fetchone():
                    print(f"  skip (exists): {entry.title[:60]}")
                    continue
            print(f"  scraping: {entry.title[:60]}")
            content = scrape(url)
            if not content or len(content) < 100:
                print("  skip (no content)")
                continue
            print(f"  rewriting...")
            try:
                rt, rb = rewrite(entry.title, content)
            except Exception as e:
                print(f"  rewrite error: {e}")
                continue
            pub = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub = datetime(*entry.published_parsed[:6])
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO articles (original_url,title,original_content,rewritten_title,rewritten_body,keyword,published_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (original_url) DO NOTHING
                """, (url, entry.title, content, rt, rb, keyword, pub))
            conn.commit()
            print(f"  saved: {rt[:60]}")
            time.sleep(2)
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
