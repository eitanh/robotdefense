import os, time, json, re, psycopg2, urllib.parse
from datetime import datetime
import anthropic

KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS",
    "robot hacked,robot cyberattack,robot exploit,robot vulnerability,robot malware,"
    "autonomous vehicle hacked,drone hacked,drone exploit,self-driving car hack,"
    "industrial robot attack,ICS robot,OT security robot,SCADA robot,"
    "AI weapon attack,AI autonomous weapon,LLM jailbreak attack,AI safety incident,"
    "Boston Dynamics security,surgical robot hack,military robot attack"
).split(",")]

DB_URL = os.environ["DATABASE_URL"]
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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


def ask_claude(keyword):
    """Ask Claude (with web search) for recent news articles on the keyword."""
    prompt = f"""Use web search to find 3 recent, real news articles about: "{keyword}"

Focus on security incidents, cyberattacks, vulnerabilities, hacks, or notable events.
Return ONLY a valid JSON array — no markdown, no extra text:
[
  {{
    "title": "article headline",
    "body": "detailed 3-4 paragraph summary of what happened",
    "url": "https://actual-source-url",
    "published_at": "YYYY-MM-DD",
    "image_prompt": "cinematic photo: [15-word visual scene that represents this article]"
  }}
]"""

    messages = [{"role": "user", "content": prompt}]

    for _ in range(8):
        try:
            resp = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                messages=messages,
            )
        except Exception as e:
            print(f"  api error: {e}", flush=True)
            return []

        text = "".join(getattr(b, "text", "") for b in resp.content)

        if resp.stop_reason == "end_turn":
            m = re.search(r"\[[\s\S]*?\]", text)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            return []

        # Model requested a tool call — continue conversation
        messages.append({"role": "assistant", "content": resp.content})
        tool_results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": ""}
            for b in resp.content if getattr(b, "type", "") == "tool_use"
        ]
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return []


def make_image_url(prompt, seed):
    """Deterministic image URL via pollinations.ai — free, no API key."""
    safe = urllib.parse.quote(prompt[:200])
    return f"https://image.pollinations.ai/prompt/{safe}?width=800&height=450&nologo=true&model=flux&seed={seed}"


def main():
    conn = psycopg2.connect(DB_URL)
    init_db(conn)

    seen_urls = set()

    for keyword in KEYWORDS:
        print(f"[+] {keyword}", flush=True)
        try:
            articles = ask_claude(keyword)
        except Exception as e:
            print(f"  error: {e}", flush=True)
            continue

        if not articles:
            print(f"  no results", flush=True)
            continue

        for art in articles:
            url = (art.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            with conn.cursor() as cur:
                cur.execute("SELECT id FROM articles WHERE original_url=%s", (url,))
                if cur.fetchone():
                    print(f"  skip: {art.get('title','')[:60]}", flush=True)
                    continue

            title = art.get("title", "")
            body = art.get("body", "")
            pub_str = art.get("published_at", "")
            try:
                pub_dt = datetime.strptime(pub_str, "%Y-%m-%d") if pub_str else None
            except ValueError:
                pub_dt = None

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO articles
                        (original_url, title, original_content, rewritten_title,
                         rewritten_body, keyword, published_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (original_url) DO NOTHING
                    RETURNING id
                """, (url, title, body, title, body, keyword, pub_dt))
                row = cur.fetchone()
            conn.commit()

            if not row:
                continue

            article_id = row[0]
            image_prompt = art.get("image_prompt") or f"robot cybersecurity technology {keyword}"
            image_url = make_image_url(image_prompt, article_id)

            with conn.cursor() as cur:
                cur.execute("UPDATE articles SET image_url=%s WHERE id=%s",
                            (image_url, article_id))
            conn.commit()

            print(f"  saved: {title[:60]}", flush=True)
            time.sleep(1)

        time.sleep(2)

    conn.close()
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
