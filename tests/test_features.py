"""Feature-level test: macros tab, meals export checkbox, optional-price extras. Screenshots desktop+390px."""
import http.server, json, os, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = "/tmp/feature_shots"; os.makedirs(OUT, exist_ok=True)
CHROME = shutil.which("google-chrome") or shutil.which("chromium")
tmp = tempfile.mkdtemp()
for f in ("index.html", "prices.json"): shutil.copy(os.path.join(ROOT, f), tmp)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=tmp, **k)
    def log_message(s, *a): pass
srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/index.html" % srv.server_address[1]
fails = []
def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else " -> %s" % (info,)))
    if not ok: fails.append(name)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    for tag, vw in (("desktop", {"width": 1280, "height": 900}), ("mobile", {"width": 390, "height": 844}), ("small", {"width": 320, "height": 700})):
        pg = b.new_page(viewport=vw); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1500)
        # --- macros tab ---
        pg.evaluate("switchTab('Macros')"); pg.wait_for_timeout(400)
        r = pg.evaluate("""(() => {
          const days = [...document.querySelectorAll('#macrosDaysContainer > div')];
          const meals = [...document.querySelectorAll('#macrosDaysContainer .text-xs.font-bold')].length;
          const partialBadges = (document.getElementById('macrosDaysContainer').innerText.match(/PARTIAL/g) || []).length;
          const coveredBadges = (document.getElementById('macrosDaysContainer').innerText.match(/ingredients covered/g) || []).length;
          const summary = document.getElementById('macrosSummary').innerText;
          return {days: days.length, partialBadges, coveredBadges, summaryLen: summary.length, hasKcal: /kcal/i.test(summary)};
        })()""")
        check("%s macros tab: day cards, summary with kcal, coverage badges present" % tag,
              r["days"] >= 5 and r["hasKcal"] and (r["partialBadges"] + r["coveredBadges"]) > 0, r)
        pg.screenshot(path="%s/%s_macros.png" % (OUT, tag))
        # macro sanity: per-serving kcal of a chicken dinner should be 200..900
        sane = pg.evaluate("""(() => {
          const slot = state.activeSchedule.find(s => s.recipeId && s.recipeId !== 'no_meal');
          const m = computeRecipeMacros(slot.recipeId);
          const perServing = m.kcal / 4;
          return {title: slot.recipeId, perServing, covered: m.covered, total: m.total, missing: m.missing};
        })()""")
        check("%s macro sanity: %s per-serving kcal in range" % (tag, sane["title"]), 100 < sane["perServing"] < 1200 and sane["covered"] > 0, sane)
        # --- custom extras: priced + unpriced via real form ---
        pg.evaluate("switchTab('Cart')"); pg.wait_for_timeout(400)
        pg.fill("#customItemName", "Paper Towels"); pg.fill("#customItemPrice", ""); pg.evaluate("document.getElementById('addCustomItemForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}))")
        pg.wait_for_timeout(200)
        pg.fill("#customItemName", "Dish Soap"); pg.fill("#customItemQty", "3"); pg.fill("#customItemPrice", "14.5"); pg.evaluate("document.getElementById('addCustomItemForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}))")
        pg.wait_for_timeout(400)
        r = pg.evaluate("""(() => {
          const l = getAggregatedGroceryList(); const t = calculateCartTotals();
          const note = document.getElementById('noPriceItemsNote');
          const txt = document.getElementById('groceryAislesContainer').innerText;
          const base = (() => { const sv = state.customItems; state.customItems = []; const x = calculateCartTotals(); state.customItems = sv; return x; })();
          return {np: l['custom_' + state.customItems[0].id] && l['custom_' + state.customItems[0].id].priceSource,
                  priced: l['custom_' + state.customItems[1].id] && l['custom_' + state.customItems[1].id].storePrice,
                  noPriceCount: t.noPriceCount, noteShown: !note.classList.contains('hidden') && note.textContent.includes('Paper Towels'),
                  noPriceRow: txt.includes('no price - not in total'),
                  delta: Math.round((t.totalCart - base.totalCart) * 100) / 100};
        })()""")
        check("%s extras: unpriced listed as no-price (0, outside totals, visible note+row), priced qty-3 item adds exactly 43.5 to total" % tag,
              r["np"] == "no-price" and r["priced"] == 43.5 and r["noPriceCount"] == 1 and r["noteShown"] and r["noPriceRow"] and r["delta"] == 43.5, r)
        pg.evaluate("(()=>{const e=[...document.querySelectorAll('*')].find(x=>x.children.length===0&&/Paper Towels/.test(x.textContent));if(e)e.scrollIntoView({block:'center'});})()")
        pg.wait_for_timeout(300); pg.screenshot(path="%s/%s_cart_extras.png" % (OUT, tag))
        # --- whatsapp export with meals checkbox ---
        pg.evaluate("openWhatsAppModal()"); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => {
          const before = document.getElementById('whatsappPreviewText').value;
          const cb = document.getElementById('whatsappIncludeMeals');
          cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true}));
          const after = document.getElementById('whatsappPreviewText').value;
          return {beforeHas: before.includes('Planned Meals'), afterHas: after.includes('Planned Meals'),
                  sample: after.split('\\n').filter(l => l.includes('Breakfast') || l.includes('Dinner')).slice(0, 2),
                  noPriceNote: after.includes('without a price'), persisted: state.exportIncludeMeals === true};
        })()""")
        check("%s export: meals section only when checked, with day lines; no-price note; setting persisted" % tag,
              (not r["beforeHas"]) and r["afterHas"] and len(r["sample"]) > 0 and r["noPriceNote"] and r["persisted"], r)
        pg.screenshot(path="%s/%s_whatsapp_meals.png" % (OUT, tag))
        pg.evaluate("closeWhatsAppModal()")
        # cart-level toggle syncs state + fills print-only section
        r2 = pg.evaluate("""(() => {
          const cb = document.getElementById('cartIncludeMealsExport');
          const syncedFromState = cb.checked === true;
          cb.checked = false; cb.dispatchEvent(new Event('change', {bubbles: true}));
          const off = state.exportIncludeMeals === false && document.getElementById('printMealsContent').innerHTML === '';
          cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true}));
          const on = state.exportIncludeMeals === true && document.getElementById('printMealsContent').innerText.includes('Dinner');
          const printHiddenOnScreen = getComputedStyle(document.getElementById('printMealsSection')).display === 'none';
          return {syncedFromState, off, on, printHiddenOnScreen};
        })()""")
        check("%s cart-level meals toggle: synced, drives print section, print block hidden on screen" % tag,
              all(r2.values()), r2)
        # day/week partial labels present
        r3 = pg.evaluate("switchTab('Macros') || (() => { const t = document.getElementById('macrosDaysContainer').innerText + document.getElementById('macrosSummary').innerText; return {dayPartial: /partial/i.test(t), weekly: /INCOMPLETE/.test(t), mayBe: /may be (lower|higher)/.test(t)}; })()")
        r4 = pg.evaluate("(() => { const rec = RECIPES.find(r => (r.ingredients||[]).some(i => { const e = NUTRITION_DB[String(i.name).toLowerCase()]; return e && e.approx; })); const m = rec ? computeRecipeMacros(rec.id) : null; return {found: !!rec, approxListed: !!(m && m.approx.length > 0)}; })()")
        check("%s macros honest labels: day partial, weekly incomplete, may-be wording; bone/peel items flagged approx" % tag,
              all(r3.values()) and r4["found"] and r4["approxListed"], (r3, r4))
        pg.evaluate("switchTab('Cart')")
        # --- overflow checks (document AND body-level) ---
        of = pg.evaluate("({doc: document.documentElement.scrollWidth > window.innerWidth + 2, body: document.body.scrollWidth > window.innerWidth + 2})")
        check("%s no horizontal overflow" % tag, not of["doc"] and not of["body"], of)
        rb = []
        for tab in ("Plan", "Cart", "Macros", "Pantry", "Preferences"):
            pg.evaluate("switchTab('%s')" % tab); pg.wait_for_timeout(250)
            bad = pg.evaluate("""(() => {
              const bad = [];
              document.querySelectorAll('body *').forEach(el => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                if (r.right > window.innerWidth + 2 || r.left < -2) {
                  let a = el.parentElement, insideScroller = false;
                  while (a) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll') { insideScroller = true; break; } a = a.parentElement; }
                  if (!insideScroller) bad.push(el.tagName + ' right=' + Math.round(r.right) + ' ' + String(el.className).slice(0, 50));
                }
              });
              return bad.slice(0, 6);
            })()""")
            if bad: rb.append((tab, bad))
        check("%s no element exceeds viewport bounds (rect scan, all tabs)" % tag, not rb, rb)
        pg.evaluate("switchTab('Plan')")
        # cleanup custom items
        pg.evaluate("state.customItems = []; saveState(); renderAll()")
        check("%s no page errors" % tag, not errs, errs[:3])
        pg.close()
    b.close()
print("FEATURE FAILURES:", len(fails)); sys.exit(1 if fails else 0)
