import os
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

def page(body, title="robotdefense.io"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0a0a0a;color:#ccc;font-family:'Segoe UI',sans-serif;min-height:100vh}}
  header{{border-bottom:1px solid #1a1a1a;padding:1.2rem 2rem;display:flex;align-items:center;gap:1rem}}
  header h1{{font-size:1.5rem;color:#00ff88;letter-spacing:2px;text-transform:uppercase}}
  header span{{color:#555;font-size:.8rem}}
  .tag{{display:inline-block;background:#0f2e1e;color:#00ff88;font-size:.7rem;padding:.2rem .5rem;border-radius:3px;letter-spacing:1px;text-transform:uppercase;border:1px solid #00ff8844}}
  main{{max-width:960px;margin:0 auto;padding:2rem 1.5rem}}
  .empty{{text-align:center;padding:4rem;color:#333}}
  .empty h2{{color:#00ff8833;font-size:2rem;margin-bottom:.5rem}}
  .card{{background:#111;border:1px solid #1e1e1e;border-radius:6px;margin-bottom:1.5rem;overflow:hidden;transition:border-color .2s}}
  .card:hover{{border-color:#00ff8844}}
  .card-img{{width:100%;height:200px;object-fit:cover;display:block;filter:brightness(.85) saturate(.9)}}
  .card-header{{padding:1.2rem 1.5rem .8rem;cursor:pointer}}
  .card-header h2{{font-size:1.1rem;color:#e0e0e0;margin-bottom:.5rem;line-height:1.4}}
  .meta{{display:flex;gap:1rem;align-items:center;flex-wrap:wrap}}
  .date{{color:#555;font-size:.8rem}}
  .card-body{{padding:0 1.5rem 1.2rem;display:none;border-top:1px solid #1a1a1a;margin-top:.8rem;padding-top:.8rem;line-height:1.7;color:#aaa;font-size:.95rem}}
  .card-body p{{margin-bottom:.8rem}}
  .src{{font-size:.75rem;color:#333;margin-top:.8rem}}
  .src a{{color:#444;text-decoration:none}}
  .src a:hover{{color:#00ff88}}
  footer{{text-align:center;padding:2rem;color:#222;font-size:.8rem;border-top:1px solid #111}}
</style>
</head>
<body>
<header>
  <h1>&#9888; robotdefense.io</h1>
  <span>AI &amp; Robot Security Intelligence</span>
</header>
<main>{body}</main>
<footer>robotdefense.io &mdash; automated threat intelligence</footer>
<script>
document.querySelectorAll('.card-header').forEach(h=>h.addEventListener('click',()=>{{
  const b=h.nextElementSibling;
  b.style.display=b.style.display==='block'?'none':'block';
}}));
</script>
</body></html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    try:
        rows = query("""
            SELECT id, rewritten_title, rewritten_body, keyword, published_at, original_url, created_at, image_url
            FROM articles ORDER BY created_at DESC LIMIT 50
        """)
    except Exception:
        rows = []

    if not rows:
        body = """<div class="empty">
          <h2>// NO INTEL YET</h2>
          <p>The crawler hasn't run yet. Articles will appear here once it does.</p>
        </div>"""
    else:
        cards = []
        for (aid, title, body_text, keyword, pub, src_url, created, image_url) in rows:
            date_str = (pub or created).strftime("%Y-%m-%d %H:%M UTC") if (pub or created) else ""
            paras = "".join(f"<p>{p.strip()}</p>" for p in (body_text or "").split("\n") if p.strip())
            img_src = image_url or f"https://picsum.photos/seed/{aid}/960/200"
            cards.append(f"""<div class="card">
  <img class="card-img" src="{img_src}" onerror="this.src='https://picsum.photos/seed/{aid}/960/200'" alt="" loading="lazy">
  <div class="card-header">
    <h2>{title or 'Untitled'}</h2>
    <div class="meta">
      <span class="tag">{keyword}</span>
      <span class="date">{date_str}</span>
    </div>
  </div>
  <div class="card-body">
    {paras}
    <p class="src">Source: <a href="{src_url}" target="_blank" rel="noopener">{src_url[:80]}...</a></p>
  </div>
</div>""")
        body = "\n".join(cards)

    return HTMLResponse(page(body))

@app.get("/health")
def health():
    return {"status": "ok"}
