"""Feature test: recognized-ingredient typeahead dropdown in Custom Dish modal, extras form, Shabbat custom dish.
Uses REAL clicks/keyboard on the rendered dropdown; screenshots of the open dropdown at phone size."""
import http.server, os, shutil, socketserver, tempfile, threading
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = "/tmp/typeahead_shots"; os.makedirs(OUT, exist_ok=True)
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
    for tag, vw in (("desktop", {"width": 1280, "height": 900}), ("mobile", {"width": 390, "height": 844})):
        pg = b.new_page(viewport=vw); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(url); pg.wait_for_timeout(1500)

        # --- recognized index populated ---
        r = pg.evaluate("""(() => {
          let n = 0, hasChicken = false, hasCarrots = false;
          recognizedIngredientsIndex().forEach(k => { n++; if (k.name === 'Chicken Thighs & Drumsticks') hasChicken = true; if (k.name === 'Fresh Carrots') hasCarrots = true; });
          return {n, hasChicken, hasCarrots};
        })()""")
        check("%s recognized index: recipes+shabbat+catalog union available" % tag, r["n"] > 100 and r["hasChicken"] and r["hasCarrots"], r)

        # --- extras: REAL click on the rendered dropdown (phone-sized proof) ---
        pg.evaluate("switchTab('Cart')"); pg.wait_for_timeout(400)
        pg.click("#customItemName")
        pg.keyboard.type("fresh chic", delay=40); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => { const p = document.querySelector('#customItemName').parentElement.querySelector('.typeahead-option');
          const panel = document.querySelector('#customItemName').parentElement.querySelector('div.absolute');
          return {open: panel && !panel.classList.contains('hidden'), first: p ? p.textContent : null}; })()""")
        check("%s extras: dropdown opens while typing, first option is the chicken" % tag,
              r["open"] and r["first"] and "Fresh Chicken Breast" in r["first"], r)
        pg.screenshot(path="%s/%s_extras_dropdown_open.png" % (OUT, tag))
        pg.click("#customItemName ~ div.absolute .typeahead-option >> nth=0"); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => ({v: document.getElementById('customItemName').value,
          aisle: document.getElementById('customItemAisle').value, price: document.getElementById('customItemPrice').value,
          hint: document.getElementById('customItemKnownHint').textContent,
          hintShown: !document.getElementById('customItemKnownHint').classList.contains('hidden'),
          focusQty: document.activeElement && document.activeElement.id }))()""")
        check("%s extras: CLICKING the recognized option fills exact name + aisle, no frozen price, hint explains, focus on qty" % tag,
              r["v"] == "Fresh Chicken Breast" and r["aisle"] == "meat" and r["price"] == ""
              and r["hintShown"] and "live store prices" in r["hint"] and r["focusQty"] == "customItemQty", r)
        pg.evaluate("document.getElementById('customItemName').value=''; document.getElementById('customItemName').dispatchEvent(new Event('input',{bubbles:true}))")

        # --- extras: keyboard-only pick (ArrowDown + Enter), Hebrew matching ---
        pg.click("#customItemName"); pg.keyboard.type("עוף", delay=50); pg.wait_for_timeout(300)
        heb = pg.evaluate("document.querySelectorAll('#customItemName ~ div.absolute .typeahead-option').length")
        pg.keyboard.press("ArrowDown"); pg.wait_for_timeout(150); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => ({v: document.getElementById('customItemName').value,
          known: !!recognizedIngredientsIndex().get(document.getElementById('customItemName').value.trim().toLowerCase()) }))()""")
        check("%s extras: Hebrew search matches; ArrowDown+Enter picks without submitting the form" % tag,
              heb > 0 and r["known"] and not pg.evaluate("state.customItems.some(c => c.name === 'עוף')"), r)
        pg.evaluate("document.getElementById('customItemName').value=''; document.getElementById('customItemName').dispatchEvent(new Event('input',{bubbles:true}))")

        # --- custom dish modal: real click pick, autofill, scale, override, macros ---
        pg.evaluate("openCreateCustomMealModal()"); pg.wait_for_timeout(300)
        pg.click("#newIngName"); pg.keyboard.type("thighs & dr", delay=40); pg.wait_for_timeout(300)
        pg.screenshot(path="%s/%s_customdish_dropdown_open.png" % (OUT, tag))
        pg.click("#newIngName ~ div.absolute .typeahead-option >> nth=0"); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => ({
          name: document.getElementById('newIngName').value,
          qty: document.getElementById('newIngQty').value, unit: document.getElementById('newIngUnit').value,
          aisle: document.getElementById('newIngAisle').value, price: document.getElementById('newIngPrice').value,
          hint: document.getElementById('newIngKnownHint').textContent,
          focusQty: document.activeElement && document.activeElement.id }))()""")
        check("%s custom dish: click pick fills everything, hint names macros, focus jumps to amount" % tag,
              r["name"] == "Chicken Thighs & Drumsticks" and r["qty"] == "800" and r["unit"] == "g" and r["aisle"] == "meat"
              and r["price"] == "30" and "macros counted" in r["hint"] and r["focusQty"] == "newIngQty", r)
        pg.fill("#newIngQty", "400"); pg.evaluate("document.getElementById('newIngQty').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.wait_for_timeout(100)
        price = pg.evaluate("document.getElementById('newIngPrice').value")
        check("%s custom dish: estimate scales with amount (30 -> 15)" % tag, price == "15", price)
        pg.fill("#newIngPrice", "12.5"); pg.evaluate("document.getElementById('newIngPrice').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.fill("#newIngQty", "900"); pg.evaluate("document.getElementById('newIngQty').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.wait_for_timeout(100)
        price = pg.evaluate("document.getElementById('newIngPrice').value")
        check("%s custom dish: user-edited price is not overwritten" % tag, price == "12.5", price)
        pg.evaluate("document.getElementById('btnAddCustomIngRow').click()"); pg.wait_for_timeout(200)
        r = pg.evaluate("(() => { const i = state.tempCustomIngredients[0]; return {name: i.name, searchHe: i.searchHe, qty: i.qty, price: i.storePrice}; })()")
        check("%s custom dish: added ingredient keeps exact recognized name (unescaped &) and searchHe" % tag,
              r["name"] == "Chicken Thighs & Drumsticks" and r["searchHe"] == "ירכיים ושוקיים עוף" and r["qty"] == 900 and r["price"] == 12.5, r)
        pg.fill("#newIngName", "Unobtainium Powder"); pg.evaluate("document.getElementById('newIngName').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.wait_for_timeout(100)
        hintHidden = pg.evaluate("document.getElementById('newIngKnownHint').classList.contains('hidden')")
        pg.evaluate("document.getElementById('btnAddCustomIngRow').click()"); pg.wait_for_timeout(200)
        r2 = pg.evaluate("(() => { const i = state.tempCustomIngredients[1]; return {name: i.name, searchHe: i.searchHe}; })()")
        check("%s custom dish: unmatched name stays fully manual, hint hidden" % tag,
              hintHidden and r2["name"] == "Unobtainium Powder" and r2["searchHe"] == "Unobtainium Powder", r2)
        pg.fill("#customMealNameInput", "Typeahead Test Dish")
        pg.evaluate("saveCustomMeal()"); pg.wait_for_timeout(400)
        r = pg.evaluate("""(() => {
          const rec = RECIPES.find(r => r.title === 'Typeahead Test Dish');
          const m = computeRecipeMacros(rec.id);
          return {covered: m.covered, missing: m.missing, kcal: Math.round(m.kcal)};
        })()""")
        check("%s custom dish: macros cover the recognized ingredient; manual one honestly missing" % tag,
              r["covered"] == 1 and r["missing"] == ["Unobtainium Powder"] and r["kcal"] > 0, r)

        # --- extras: recognized item with NO typed price -> real store pricing pathway ---
        pg.evaluate("switchTab('Cart'); state.currentStore='shufersal';"); pg.wait_for_timeout(400)
        pg.fill("#customItemName", "Fresh Chicken Breast")
        pg.evaluate("document.getElementById('customItemName').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.wait_for_timeout(200)
        stdQty = pg.evaluate("recognizedIngredientsIndex().get('fresh chicken breast').qty")
        pg.fill("#customItemQty", "2")
        pg.evaluate("document.getElementById('addCustomItemForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}))")
        pg.wait_for_timeout(400)
        r = pg.evaluate("""(() => {
          const ci = state.customItems.find(c => c.name === 'Fresh Chicken Breast');
          const l = getAggregatedGroceryList(); const li = l['custom_' + ci.id];
          const t = calculateCartTotals();
          const base = (() => { const sv = state.customItems; state.customItems = []; const x = calculateCartTotals(); state.customItems = sv; return x; })();
          return {price: ci.price, qty: li.qty, unit: li.unit, src: li.priceSource, live: li.isLiveMatch,
                  storePrice: li.storePrice, delta: Math.round((t.totalCart - base.totalCart) * 100) / 100};
        })()""")
        check("%s extras: recognized item priced via store pathway (actual shufersal price, coherent grams)" % tag,
              r["price"] is None and r["unit"] == "g" and r["qty"] == stdQty * 2 and r["src"] == "actual"
              and r["live"] and r["storePrice"] > 0 and r["delta"] == r["storePrice"], r)
        # estimate chain fallback honesty: carrefour (estimate-only chain) marks it an estimate
        r = pg.evaluate("""(() => { state.currentStore='carrefour';
          const l = getAggregatedGroceryList(); const ci = state.customItems.find(c => c.name === 'Fresh Chicken Breast');
          const li = l['custom_' + ci.id]; return {src: li.priceSource, chains: li.estimateChains}; })()""")
        check("%s extras: estimate-only chain marks recognized extra as estimate, not actual" % tag,
              r["src"] in ("estimate-chains", "estimate-baseline"), r)
        pg.evaluate("state.currentStore='shufersal'")
        # recognized + typed price = fixed override at every store, amount shown in the standard unit
        pg.fill("#customItemName", "Fresh Carrots")
        pg.evaluate("document.getElementById('customItemName').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.wait_for_timeout(100)
        pg.fill("#customItemQty", "3"); pg.fill("#customItemPrice", "4.5")
        pg.evaluate("document.getElementById('addCustomItemForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}))")
        pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => { const ci = state.customItems.find(c => c.name === 'Fresh Carrots'); const l = getAggregatedGroceryList();
          const li = l['custom_' + ci.id]; return {price: ci.price, src: li.priceSource, storePrice: li.storePrice, qty: li.qty, unit: li.unit}; })()""")
        check("%s extras: recognized + typed price = user-entered fixed (3 x 4.5 = 13.5, 900 g shown)" % tag,
              r["price"] == 4.5 and r["src"] == "user-entered" and r["storePrice"] == 13.5 and r["qty"] == 900 and r["unit"] == "g", r)
        # manual unpriced item: untouched no-price flow
        before = pg.evaluate("calculateCartTotals().noPriceCount")
        pg.fill("#customItemName", "Mystery Powder")
        pg.evaluate("document.getElementById('customItemName').dispatchEvent(new Event('input', {bubbles:true}))")
        pg.wait_for_timeout(100)
        hintHidden = pg.evaluate("document.getElementById('customItemKnownHint').classList.contains('hidden')")
        pg.evaluate("document.getElementById('addCustomItemForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}))")
        pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => { const ci = state.customItems.find(c => c.name === 'Mystery Powder'); const t = calculateCartTotals();
          const l = getAggregatedGroceryList(); return {price: ci.price, src: l['custom_' + ci.id].priceSource, noPriceCount: t.noPriceCount}; })()""")
        check("%s extras: unknown unpriced item stays no-price, out of totals, no hint" % tag,
              hintHidden and r["price"] is None and r["src"] == "no-price" and r["noPriceCount"] == before + 1, r)
        pg.evaluate("(()=>{document.querySelector('#customItemName').scrollIntoView({block:'center'});})()")
        pg.wait_for_timeout(200); pg.screenshot(path="%s/%s_extras_list.png" % (OUT, tag))

        # --- Shabbat custom dish: real click pick, auto-price scales, save flows to macros ---
        pg.evaluate("openShabbatBuilder('friday')"); pg.wait_for_timeout(400)
        pg.click("button[data-custom-category]"); pg.wait_for_timeout(300)
        nameSel = "#shabbatCustomRows .shabbat-custom-row [data-field='name']"
        pg.click(nameSel); pg.keyboard.type("fresh chic", delay=40); pg.wait_for_timeout(300)
        pg.screenshot(path="%s/%s_shabbat_dropdown_open.png" % (OUT, tag))
        pg.click(nameSel + " ~ div.absolute .typeahead-option >> nth=0"); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => ({v: document.querySelector("%s").value,
          focusQty: document.activeElement && document.activeElement.getAttribute('data-field') }))()""" % nameSel)
        check("%s shabbat custom: click pick lands exact recognized name, focus on quantity" % tag,
              r["v"] == "Fresh Chicken Breast" and r["focusQty"] == "qty", r)
        pg.fill("#shabbatCustomRows .shabbat-custom-row [data-field='qty']", "500")
        pg.evaluate("document.querySelector(\"#shabbatCustomRows .shabbat-custom-row [data-field='qty']\").dispatchEvent(new Event('change', {bubbles:true}))")
        pg.wait_for_timeout(200)
        r = pg.evaluate("""(() => {
          const known = shabbatKnownIngredients().get('fresh chicken breast');
          return {price: document.querySelector("#shabbatCustomRows .shabbat-custom-row [data-field='price']").value,
                  expected: (known.storePrice * 500 / known.qty).toFixed(2)}; })()""")
        check("%s shabbat custom: auto-price scales recognized ingredient to the typed amount" % tag, r["price"] == r["expected"], r)
        pg.fill("#shabbatCustomName", "Typeahead Shabbat Dish")
        pg.evaluate("document.getElementById('shabbatCustomKosher').value='meat'")
        pg.evaluate("saveShabbatCustom()"); pg.wait_for_timeout(300)
        r = pg.evaluate("""(() => {
          const cat = Object.keys(shabbatDraft.customDishes || {})[0];
          const d = (shabbatDraft.customDishes || {})[cat][0];
          const known = shabbatKnownIngredients().get('fresh chicken breast');
          return {cat, name: d.ingredients[0].name, searchHe: d.ingredients[0].searchHe, aisle: d.ingredients[0].aisle, expected: known.searchHe};
        })()""")
        check("%s shabbat custom: saved dish carries recognized identity (name/searchHe/aisle)" % tag,
              r["name"] == "Fresh Chicken Breast" and r["searchHe"] == r["expected"] and r["aisle"] == "meat", r)
        pg.evaluate("saveShabbatMeal()"); pg.wait_for_timeout(500)
        r = pg.evaluate("""(() => {
          const slot = state.activeSchedule.find(s => s.day === 'Friday Shabbat' || (s.day||'').includes('Friday'));
          const m = slot && slot.recipeId && slot.recipeId !== 'no_meal' ? computeRecipeMacros(slot.recipeId) : null;
          return {recipeId: slot && slot.recipeId, missing: m ? m.missing : null, covered: m ? m.covered : 0};
        })()""")
        check("%s shabbat custom: saved meal compiles; recognized ingredient counted in macros" % tag,
              r["recipeId"] and r["missing"] is not None and "Fresh Chicken Breast" not in r["missing"] and r["covered"] > 0, r)
        pg.screenshot(path="%s/%s_shabbat_custom.png" % (OUT, tag))

        # --- layout: no element overflows the viewport on the touched views (dropdown open included) ---
        pg.evaluate("closeShabbatBuilder(); switchTab('Cart')"); pg.wait_for_timeout(300)
        pg.click("#customItemName"); pg.keyboard.type("fresh", delay=40); pg.wait_for_timeout(300)
        overflow = pg.evaluate("""(() => {
          const vw = document.documentElement.clientWidth; const bad = [];
          document.querySelectorAll('body *').forEach(el => {
            const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
            const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return;
            let a = el.parentElement, scrollClip = false;
            while (a) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll' || o === 'clip' || o === 'hidden') { scrollClip = true; break; } a = a.parentElement; }
            if (scrollClip) return;
            if (r.right > vw + 1 || r.left < -1) bad.push((el.id || el.className || el.tagName) + ' right=' + Math.round(r.right));
          });
          return bad.slice(0, 6);
        })()""")
        check("%s layout: no clipped/overflowing elements at %dpx (dropdown open)" % (tag, vw["width"]), not overflow, overflow)
        check("%s: zero page errors" % tag, not errs, errs[:2])
        pg.close()
    b.close()
print("FAILURES:", fails if fails else "none")
raise SystemExit(1 if fails else 0)
