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
    return e(paras[0][:180]) + "…" if paras else ""

def img_src(image_url, aid, w, ht):
    return e(image_url) if image_url else f"https://picsum.photos/seed/{aid}/{w}/{ht}"

# ── card templates ──────────────────────────────────────────────────────────

def card_featured(row):
    aid, title, body, keyword, pub, url, created, image_url = row
    return f"""
<a class="card card--featured" href="{e(url)}" target="_blank" rel="noopener">
  <div class="card-img-wrap">
    <img src="{img_src(image_url, aid, 960, 540)}"
         onerror="this.src='https://picsum.photos/seed/{aid}/960/540'"
         alt="" loading="lazy">
  </div>
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
<a class="card card--side" href="{e(url)}" target="_blank" rel="noopener">
  <img class="card-img-side" src="{img_src(image_url, aid, 320, 200)}"
       onerror="this.src='https://picsum.photos/seed/{aid}/320/200'"
       alt="" loading="lazy">
  <div class="card-content">
    <span class="tag">{e(keyword)}</span>
    <h2 class="card-title">{e(title) or "Untitled"}</h2>
    <span class="card-date">{fmt_date(pub, created)}</span>
  </div>
</a>"""

def card_grid(row):
    aid, title, body, keyword, pub, url, created, image_url = row
    return f"""
<a class="card card--grid" href="{e(url)}" target="_blank" rel="noopener">
  <div class="card-img-wrap">
    <img src="{img_src(image_url, aid, 640, 360)}"
         onerror="this.src='https://picsum.photos/seed/{aid}/640/360'"
         alt="" loading="lazy">
  </div>
  <div class="card-content">
    <span class="tag">{e(keyword)}</span>
    <h2 class="card-title">{e(title) or "Untitled"}</h2>
    <span class="card-date">{fmt_date(pub, created)}</span>
  </div>
</a>"""

# ── layout builder ───────────────────────────────────────────────────────────

def build_body(rows):
    if not rows:
        return '<div class="empty"><h2>// NO INTEL YET</h2><p>Crawler hasn\'t run yet.</p></div>'

    parts = []
    i = 0
    group = 0

    while i < len(rows):
        left = len(rows) - i
        if group % 2 == 0 and left >= 3:
            # Featured group: 1 big left + 2 side stacked right
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
            # Grid row: up to 3 equal cards
            chunk = rows[i:i+3]
            inner = "".join(card_grid(r) for r in chunk)
            parts.append(f'<section class="grid-section">{inner}</section>')
            i += len(chunk)
        group += 1

    return "\n".join(parts)

# ── page shell ───────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#ccc;font-family:'Segoe UI',Arial,sans-serif;min-height:100vh}
a{text-decoration:none;color:inherit}

header{border-bottom:2px solid #00ff8833;padding:1.2rem 2rem;display:flex;align-items:center;gap:1rem}
header h1{font-size:1.4rem;color:#00ff88;letter-spacing:3px;text-transform:uppercase;font-weight:700}
header span{color:#444;font-size:.8rem;letter-spacing:1px}

main{max-width:1200px;margin:0 auto;padding:2rem 1.5rem}

.empty{text-align:center;padding:4rem;color:#333}
.empty h2{color:#00ff8833;font-size:2rem;margin-bottom:.5rem}

/* ── tags & meta ── */
.tag{display:inline-block;background:#0f2e1e;color:#00ff88;font-size:.65rem;
     padding:.15rem .5rem;border-radius:2px;letter-spacing:1px;text-transform:uppercase;
     border:1px solid #00ff8830;margin-bottom:.5rem}
.card-date{color:#555;font-size:.75rem;margin-top:.5rem;display:block}

/* ── base card ── */
.card{background:#111;border:1px solid #1c1c1c;border-radius:5px;overflow:hidden;
      display:block;transition:border-color .2s,transform .15s}
.card:hover{border-color:#00ff8855;transform:translateY(-2px)}
.card-img-wrap{overflow:hidden}
.card-img-wrap img{width:100%;display:block;object-fit:cover;
                   filter:brightness(.88) saturate(.85);
                   transition:transform .3s;height:100%}
.card:hover .card-img-wrap img{transform:scale(1.03)}
.card-content{padding:1rem 1.1rem 1.1rem}
.card-title{font-size:1rem;color:#e2e2e2;line-height:1.4;font-weight:600}
.card-excerpt{font-size:.85rem;color:#888;line-height:1.6;margin-top:.4rem}

/* ── featured group: 1 big + 2 side ── */
.featured-group{display:grid;grid-template-columns:2fr 1fr;gap:1.2rem;margin-bottom:1.2rem}
.side-stack{display:flex;flex-direction:column;gap:1.2rem}

.card--featured .card-img-wrap{height:280px}
.card--featured .card-title{font-size:1.25rem;line-height:1.35}

/* ── side card: horizontal (image left, text right) ── */
.card--side{display:flex;flex-direction:row;gap:0;height:calc(50% - .6rem)}
.card-img-side{width:130px;min-width:130px;height:100%;object-fit:cover;
               filter:brightness(.88) saturate(.85);transition:transform .3s;flex-shrink:0}
.card--side:hover .card-img-side{transform:scale(1.04)}
.card--side .card-content{padding:.8rem;display:flex;flex-direction:column;justify-content:center}
.card--side .card-title{font-size:.88rem}

/* ── 3-column grid section ── */
.grid-section{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem;margin-bottom:1.2rem}
.card--grid .card-img-wrap{height:170px}
.card--grid .card-title{font-size:.95rem}

/* ── responsive ── */
@media(max-width:900px){
  .featured-group{grid-template-columns:1fr}
  .side-stack{flex-direction:row}
  .card--side{flex-direction:column;height:auto}
  .card-img-side{width:100%;height:150px;min-width:0}
}
@media(max-width:600px){
  .grid-section{grid-template-columns:1fr}
  .side-stack{flex-direction:column}
  header h1{font-size:1.1rem}
}

footer{text-align:center;padding:2rem;color:#252525;font-size:.75rem;border-top:1px solid #141414;margin-top:1rem}
"""

def page(body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>robotdefense.io — AI &amp; Robot Security Intelligence</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>&#9888; robotdefense.io</h1>
  <span>AI &amp; Robot Security Intelligence</span>
</header>
<main>{body}</main>
<footer>robotdefense.io &mdash; automated threat intelligence &mdash; updated every 30 min</footer>
</body>
</html>"""

# ── routes ───────────────────────────────────────────────────────────────────

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
    return HTMLResponse(page(build_body(rows)))

@app.get("/health")
def health():
    return {"status": "ok"}
