import os, html as h
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import psycopg2

DB_URL = os.environ["DATABASE_URL"]
app = FastAPI()


def query(sql, params=()):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def e(s): return h.escape(str(s or ""))
def fmt_date(pub, created):
    d = pub or created
    return d.strftime("%d %b %Y") if d else ""
def excerpt(body):
    paras = [p.strip() for p in (body or "").split("\n") if p.strip()]
    return e(paras[0][:200]) + "…" if paras else ""
def full_body(body):
    paras = [p.strip() for p in (body or "").split("\n") if p.strip()]
    return "".join(f"<p>{e(p)}</p>" for p in paras)


PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='800' height='450'%3E%3Crect width='800' height='450' fill='%23111'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23333' font-family='monospace' font-size='14'%3E no image %3C/text%3E%3C/svg%3E"


def img_tag(image_url, cls=""):
    src = e(image_url) if image_url else PLACEHOLDER
    err = f"this.src='{PLACEHOLDER}'"
    return f'<img class="{cls}" src="{src}" onerror="{err}" alt="" loading="lazy">'


def card_featured(row):
    aid, title, body, keyword, pub, url, created, image_url = row
    return f"""
<a class="card card--featured" href="/article/{aid}">
  <div class="card-img-wrap">{img_tag(image_url)}</div>
  <div class="card-content">
    <span class="tag">{e(keyword)}</span>
    <h2 class="card-title">{e(title) or "Untitled"}</h2>
    <p class="card-excerpt">{excerpt(body)}</p>
    <span class="card-date">{fmt_date(pub, created)}</span>
  </div>
</a>"""


def card_side(row):
    aid, title, body, keyword, pub, url, created, image_url = row
    return f"""
<a class="card card--side" href="/article/{aid}">
  {img_tag(image_url, "card-img-side")}
  <div class="card-content">
    <span class="tag">{e(keyword)}</span>
    <h2 class="card-title">{e(title) or "Untitled"}</h2>
    <span class="card-date">{fmt_date(pub, created)}</span>
  </div>
</a>"""


def card_grid(row):
    aid, title, body, keyword, pub, url, created, image_url = row
    return f"""
<a class="card card--grid" href="/article/{aid}">
  <div class="card-img-wrap">{img_tag(image_url)}</div>
  <div class="card-content">
    <span class="tag">{e(keyword)}</span>
    <h2 class="card-title">{e(title) or "Untitled"}</h2>
    <span class="card-date">{fmt_date(pub, created)}</span>
  </div>
</a>"""


def build_body(rows):
    if not rows:
        return '<div class="empty"><h2>// NO INTEL YET</h2><p>Crawler hasn\'t run yet.</p></div>'
    parts = []
    i = 0
    group = 0
    while i < len(rows):
        left = len(rows) - i
        if group % 2 == 0 and left >= 3:
            parts.append(f"""
<section class="featured-group">
  {card_featured(rows[i])}
  <div class="side-stack">
    {card_side(rows[i+1])}
    {card_side(rows[i+2])}
  </div>
</section>""")
            i += 3
        else:
            chunk = rows[i:i+3]
            inner = "".join(card_grid(r) for r in chunk)
            parts.append(f'<section class="grid-section">{inner}</section>')
            i += len(chunk)
        group += 1
    return "\n".join(parts)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#ccc;font-family:'Segoe UI',Arial,sans-serif;min-height:100vh}
a{color:inherit;text-decoration:none}

header{border-bottom:2px solid #00ff8833;padding:1.2rem 2rem;display:flex;align-items:center;gap:1rem}
header h1{font-size:1.4rem;color:#00ff88;letter-spacing:3px;text-transform:uppercase;font-weight:700}
header span{color:#444;font-size:.8rem;letter-spacing:1px}
.back-link{color:#00ff88;font-size:.85rem;margin-right:.5rem;white-space:nowrap}
.back-link:hover{color:#00ffaa}

main{max-width:1200px;margin:0 auto;padding:2rem 1.5rem}
.empty{text-align:center;padding:4rem;color:#333}
.empty h2{color:#00ff8833;font-size:2rem;margin-bottom:.5rem}

.tag{display:inline-block;background:#0f2e1e;color:#00ff88;font-size:.65rem;
     padding:.15rem .5rem;border-radius:2px;letter-spacing:1px;text-transform:uppercase;
     border:1px solid #00ff8830;margin-bottom:.5rem}
.card-date{color:#555;font-size:.75rem;margin-top:.5rem;display:block}

.card{background:#111;border:1px solid #1c1c1c;border-radius:5px;overflow:hidden;
      display:block;transition:border-color .2s,transform .15s}
.card:hover{border-color:#00ff8855;transform:translateY(-2px)}
.card-img-wrap{overflow:hidden}
.card-img-wrap img,.card-img-side{width:100%;display:block;object-fit:cover;
    filter:brightness(.88) saturate(.85);transition:transform .3s}
.card:hover .card-img-wrap img,.card:hover .card-img-side{transform:scale(1.03)}
.card-content{padding:1rem 1.1rem .8rem}
.card-title{font-size:1rem;color:#e2e2e2;line-height:1.4;font-weight:600}
.card-excerpt{font-size:.85rem;color:#888;line-height:1.6;margin-top:.4rem}

.featured-group{display:grid;grid-template-columns:2fr 1fr;gap:1.2rem;margin-bottom:1.2rem}
.side-stack{display:flex;flex-direction:column;gap:1.2rem}
.card--featured .card-img-wrap{height:280px}
.card--featured .card-title{font-size:1.2rem;line-height:1.35}

.card--side{display:flex;flex-direction:row}
.card-img-side{width:130px;min-width:130px;height:130px;object-fit:cover;flex-shrink:0}
.card--side .card-content{padding:.8rem;display:flex;flex-direction:column;justify-content:flex-start}
.card--side .card-title{font-size:.88rem}

.grid-section{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem;margin-bottom:1.2rem}
.card--grid .card-img-wrap{height:170px}
.card--grid .card-title{font-size:.95rem}

@media(max-width:900px){
  .featured-group{grid-template-columns:1fr}
  .side-stack{flex-direction:row}
}
@media(max-width:600px){
  .grid-section{grid-template-columns:1fr}
  .side-stack{flex-direction:column}
  header h1{font-size:1.1rem}
}
footer{text-align:center;padding:2rem;color:#252525;font-size:.75rem;
       border-top:1px solid #141414;margin-top:1rem}
"""

ARTICLE_CSS = """
.article-wrap{max-width:860px;margin:0 auto;padding:2rem 1.5rem}
.article-hero{position:relative;height:420px;overflow:hidden;border-radius:6px;margin-bottom:2rem}
.article-hero img{width:100%;height:100%;object-fit:cover;filter:brightness(.7);display:block}
.article-hero-overlay{position:absolute;bottom:0;left:0;right:0;padding:2rem;
  background:linear-gradient(transparent,rgba(0,0,0,.9))}
.article-hero-overlay .card-date{margin-top:.4rem}
.article-h1{font-size:1.9rem;color:#f0f0f0;line-height:1.3;font-weight:700;margin:.4rem 0}
.article-body{background:#111;border:1px solid #1c1c1c;border-radius:5px;padding:2rem}
.article-body p{font-size:1rem;color:#bbb;line-height:1.85;margin-bottom:1.2rem}
.article-body p:last-child{margin-bottom:0}
.article-src{margin-top:1.5rem;padding-top:1rem;border-top:1px solid #1e1e1e;
  font-size:.8rem;color:#444}
.article-src a{color:#00ff88}
.article-src a:hover{color:#00ffaa}
@media(max-width:600px){
  .article-hero{height:220px}
  .article-h1{font-size:1.3rem}
  .article-body{padding:1.2rem}
}
"""


def page(title, body, extra_css="", extra_header=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}{extra_css}</style>
</head>
<body>
<header>
  {extra_header}
  <h1>&#9888; robotdefense.io</h1>
  <span>AI &amp; Robot Security Intelligence</span>
</header>
{body}
<footer>robotdefense.io &mdash; automated threat intelligence &mdash; updated every 30 min</footer>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        rows = query("""
            SELECT id, rewritten_title, rewritten_body, keyword,
                   published_at, original_url, created_at, image_url
            FROM articles ORDER BY created_at DESC LIMIT 500
        """)
    except Exception:
        rows = []
    body = f"<main>{build_body(rows)}</main>"
    return HTMLResponse(page("robotdefense.io — AI &amp; Robot Security Intelligence", body))


@app.get("/article/{article_id}", response_class=HTMLResponse)
def article(article_id: int):
    rows = query("""
        SELECT id, rewritten_title, rewritten_body, keyword,
               published_at, original_url, created_at, image_url
        FROM articles WHERE id = %s
    """, (article_id,))
    if not rows:
        return HTMLResponse("Not found", status_code=404)

    aid, title, body, keyword, pub, url, created, image_url = rows[0]
    src = e(image_url) if image_url else PLACEHOLDER
    err = f"this.src='{PLACEHOLDER}'"

    content = f"""
<div class="article-wrap">
  <div class="article-hero">
    <img src="{src}" onerror="{err}" alt="">
    <div class="article-hero-overlay">
      <span class="tag">{e(keyword)}</span>
      <h1 class="article-h1">{e(title) or "Untitled"}</h1>
      <span class="card-date">{fmt_date(pub, created)}</span>
    </div>
  </div>
  <div class="article-body">
    {full_body(body)}
    <p class="article-src">Source: <a href="{e(url)}" target="_blank" rel="noopener">{e(url[:90])}</a></p>
  </div>
</div>"""

    back = '<a class="back-link" href="/">← feed</a>'
    return HTMLResponse(page(
        f"{e(title)} — robotdefense.io",
        content,
        extra_css=ARTICLE_CSS,
        extra_header=back,
    ))


@app.get("/health")
def health():
    return {"status": "ok"}
