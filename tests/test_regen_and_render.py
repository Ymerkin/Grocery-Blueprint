"""40 plan regenerations on the real shipped prices.json state and on the synthetic fixture, with invariants on the cart,
then screenshots (desktop + 390px) of the Cart tab. Run: python tests/test_regen_and_render.py [outdir]"""
import http.server, json, os, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/render"; os.makedirs(OUT, exist_ok=True)
CHROME = shutil.which("google-chrome") or shutil.which("chromium")

def serve(prices_path):
    tmp = tempfile.mkdtemp(); shutil.copy(os.path.join(ROOT, "index.html"), tmp); shutil.copy(prices_path, os.path.join(tmp, "prices.json"))
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(s, *a, **k): super().__init__(*a, directory=tmp, **k)
        def log_message(s, *a): pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv

INV = """(() => {
  const l = getAggregatedGroceryList(); const bad = []; const seen = {};
  Object.entries(l).forEach(([k, i]) => {
    if (!isFinite(i.qty) || i.qty <= 0) bad.push('qty ' + k);
    const n = i.name.toLowerCase(); (seen[n] = seen[n] || []).push(String(i.unit).toLowerCase());
    if (i.isLiveMatch && !i.matchedData) bad.push('live without data ' + k);
    if (!i.isLiveMatch && i.matchedData) bad.push('data without live ' + k);
  });
  Object.entries(seen).forEach(([n, u]) => { if (new Set(u).size !== u.length) bad.push('duplicate unit lines ' + n); });
  const s = calculateCartTotals(state.currentStore);
  if (![s.totalCart, s.publishedTotal, s.unpricedEstimate].every(isFinite)) bad.push('nonfinite totals');
  return {bad, n: Object.keys(l).length, pub: s.isPublishedStore, priced: s.pricedCount};
})()"""
fails = 0
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    for label, prices in (("shipped", os.path.join(ROOT, "prices.json")), ("fixture", os.environ.get("GB_FIXTURE", "/tmp/fixture_v21.json"))):
        if label == "fixture":
            d = json.load(open(prices)); from datetime import datetime, timedelta, timezone
            for c in d["metadata"]["chains"].values(): c["published_at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            prices = os.path.join(tempfile.mkdtemp(), "p.json"); json.dump(d, open(prices, "w"))
        srv = serve(prices)
        for vw, tag in (({"width": 1280, "height": 900}, "desktop"), ({"width": 390, "height": 844}, "mobile")):
            pg = b.new_page(viewport=vw); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://127.0.0.1:%d/index.html" % srv.server_address[1]); pg.wait_for_timeout(1200)
            if tag == "desktop":
                for i in range(40):
                    pg.evaluate("regenerateWeek()"); r = pg.evaluate(INV)
                    if r["bad"] or (label == "shipped" and not r["pub"]): fails += 1; print("FAIL", label, i, r)
                print(label, "40 regenerations done; last:", r)
            if tag == "desktop": pg.reload(); pg.wait_for_timeout(1200)
            pg.evaluate("switchTab('Cart')"); pg.wait_for_timeout(600)
            pg.screenshot(path="%s/%s_%s_cart.png" % (OUT, label, tag), full_page=False)
            # scroll to the grocery list lines for cucumbers
            pg.evaluate("(()=>{const e=[...document.querySelectorAll('*')].find(x=>x.children.length===0&&/Fresh Cucumbers/.test(x.textContent));if(e)e.scrollIntoView({block:'center'});})()")
            pg.wait_for_timeout(400); pg.screenshot(path="%s/%s_%s_cucumbers.png" % (OUT, label, tag))
            if errs: fails += 1; print("FAIL js errors", errs)
            horiz = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
            print(label, tag, "horizontal overflow:", horiz)
            pg.close()
        srv.shutdown()
    b.close()
print("REGEN/RENDER FAILURES:", fails); sys.exit(1 if fails else 0)
