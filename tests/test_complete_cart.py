"""Complete-cart estimates (user decision 4 Nov 14:17-14:18): item-level fill only. Run: python3 tests/test_complete_cart.py
Uses the shipped prices.json with publish times moved to 'now - 3 h' so the 48 h rule never makes the result date-dependent."""
import http.server, json, os, shutil, socketserver, sys, tempfile, threading
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CHROME = shutil.which("google-chrome") or shutil.which("chromium")
fails = []
def check(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else " -> %s" % (info,)))
    if not ok: fails.append(name)
d = json.load(open(os.path.join(ROOT, "prices.json")))
for c in d["metadata"]["chains"].values(): c["published_at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
tmp = tempfile.mkdtemp(); shutil.copy(os.path.join(ROOT, "index.html"), tmp); json.dump(d, open(os.path.join(tmp, "prices.json"), "w"))
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=tmp, **k)
    def log_message(s, *a): pass
srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

RECON = """(ck) => { const l = getAggregatedGroceryList(ck), t = calculateCartTotals(ck); const c = v => Math.round(v * 100);
  let sum = 0, cat = {actual: 0, 'estimate-chains': 0, 'estimate-baseline': 0, 'user-entered': 0}, n = 0, bad = [];
  Object.values(l).forEach(i => { if (i.isPantry) return; n++; sum += c(i.storePrice); cat[i.priceSource] = (cat[i.priceSource] || 0) + c(i.storePrice);
    if (!isFinite(i.storePrice) || !(i.storePrice > 0 || ((i.priceSource === 'user-entered' || i.priceSource === 'no-price') && i.storePrice === 0))) bad.push(i.name); if (!i.priceSource) bad.push('nosrc ' + i.name); });
  return {sum, n, t, cat, bad, ok: sum === Math.round(t.totalCart * 100) && n === t.totalItemsToBuy && cat.actual === Math.round(t.actualTotal * 100)
    && cat['estimate-chains'] === Math.round(t.estimatedChainsTotal * 100) && cat['estimate-baseline'] === Math.round(t.estimatedBaselineTotal * 100)
    && Math.round(t.actualTotal * 100) + Math.round(t.estimatedTotal * 100) + Math.round(t.userEnteredTotal * 100) === sum}; }"""
CH = ["shufersal", "rami-levy", "osher-ad", "yochananof", "victory", "carrefour"]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 900}); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:%d/index.html" % srv.server_address[1]); pg.wait_for_timeout(1500)
    check("fresh fixture: all five chains fresh", pg.evaluate("PRICE_CHAINS.every(c => state.chainFresh[c])"))
    # 1 whole-cart invariants, 100 weeks x 6 chains, on date-independent data
    res = pg.evaluate(open(os.path.join(HERE, "whole_cart_invariants.js")).read())
    check("100-week whole-cart invariants (%d checks)" % res["checks"], not res["fails"], res["fails"][:5])
    pg.evaluate("regenerateWeek()")
    # 2 reconciliation per chain, real plan
    for ck in CH:
        r = pg.evaluate("([f, ck]) => (%s)(ck)" % RECON, [None, ck]) if False else pg.evaluate("(%s)('%s')" % (RECON, ck))
        check("%s: rows add up exactly to the headline, categories and counts reconcile, no zero/NaN line" % ck, r["ok"] and not r["bad"], r)
    # 3 item-level fill only: every chain's actual lines are byte-identical to what the old pricing gave; estimates only where no real price
    r = pg.evaluate("""(() => { const out = []; PRICE_CHAINS.forEach(ck => { const l = getAggregatedGroceryList(ck); Object.values(l).forEach(i => { if (i.isPantry || i.isCustom) return;
        const own = getIngredientPricing(i.name, i.qty, i.unit, 1.0, ck, 0);
        if (own.isLiveMatch && (i.priceSource !== 'actual' || i.storePrice !== own.purchaseCost)) out.push(ck + ' real price not kept: ' + i.name);
        if (!own.isLiveMatch && i.priceSource === 'actual') out.push(ck + ' actual without real price: ' + i.name); }); }); return out; })()""")
    check("item-level fill only: no real price replaced, no estimate where a real price exists", not r, r[:5])
    # 4 identical quantity set at every chain
    r = pg.evaluate("""(() => { const base = getAggregatedGroceryList('rami-levy'); const bad = []; ['shufersal','osher-ad','yochananof','victory','carrefour'].forEach(ck => { const l = getAggregatedGroceryList(ck);
        if (Object.keys(l).join('|') !== Object.keys(base).join('|')) bad.push(ck + ' keys'); Object.keys(base).forEach(k => { if (!l[k] || l[k].qty !== base[k].qty || l[k].unit !== base[k].unit || l[k].isPantry !== base[k].isPantry) bad.push(ck + ' ' + k); }); }); return bad; })()""")
    check("same needed-basket lines, quantities, units and pantry flags at every chain", not r, r[:5])
    # 5 pack rounding: an actual line costs whole packs; an estimate is the average of the other chains' whole-pack costs
    r = pg.evaluate("""(() => { const out = {actual: 0, est: 0, bad: []}; PRICE_CHAINS.forEach(ck => { const l = getAggregatedGroceryList(ck);
        Object.values(l).forEach(i => { if (i.isPantry || i.isCustom) return;
          if (i.priceSource === 'actual' && !i.matchedData.isWeighted) { out.actual++; const need = getIngredientPricing(i.name, i.qty, i.unit, 1.0, ck, 0).neededInPackUnit; const packs = Math.max(1, Math.ceil(need / i.matchedData.packQty - 1e-6)); if (Math.abs(i.storePrice - packs * i.matchedData.packPrice) > 0.011) out.bad.push(ck + ' actual ' + i.name); }
          if (i.priceSource === 'estimate-chains') { out.est++; const o = PRICE_CHAINS.filter(c => c !== ck && isChainPublished(c)).map(c => getIngredientPricing(i.name, i.qty, i.unit, 1.0, c, 0)).filter(p => p.isLiveMatch);
            const avg = Math.round(o.reduce((a, p) => a + p.purchaseCost, 0) / o.length * 100) / 100; if (Math.abs(avg - i.storePrice) > 0.011) out.bad.push(ck + ' est ' + i.name); } }); }); return out; })()""")
    check("pack rounding: actual lines = whole packs x pack price (%d lines), estimates = average of other chains' whole-pack costs (%d lines)" % (r["actual"], r["est"]), not r["bad"] and r["actual"] > 20 and r["est"] > 0, r)
    # 6 pantry toggles never change the quantity set across chains and never enter totals
    r = pg.evaluate("""(() => { const bad = []; const before = calculateCartTotals('rami-levy').totalCart; PANTRY_STAPLES.forEach(p => { state.pantryState[p.id] = true; });
        ['rami-levy','shufersal','carrefour'].forEach(ck => { const l = getAggregatedGroceryList(ck); const t = calculateCartTotals(ck); let s = 0; Object.values(l).forEach(i => { if (!i.isPantry) s += Math.round(i.storePrice * 100); }); if (s !== Math.round(t.totalCart * 100)) bad.push(ck); });
        const after = calculateCartTotals('rami-levy').totalCart; PANTRY_STAPLES.forEach(p => { state.pantryState[p.id] = false; }); return {bad, before, after}; })()""")
    check("pantry toggles: owned staples leave every chain's cart, rows still equal headline", not r["bad"] and r["after"] <= r["before"], r)
    # 7 mixed unit families (g and units of the same item) stay separate lines, each priced or estimated on its own, no double count
    r = pg.evaluate("""(() => { const sv = {a: state.activeSchedule, l: state.lunchSchedule, b: state.bfastSchedule, t: state.twoNightBatchDays};
        RECIPES.push({id: '__mix', title: 'mix', ingredients: [{name: 'Fresh Cucumbers', qty: 300, unit: 'g', aisle: 'produce', storePrice: 5, isPantry: false}, {name: 'Fresh Cucumbers', qty: 2, unit: 'units', aisle: 'produce', storePrice: 5, isPantry: false}, {name: 'Zz Unknown Thing', qty: 2, unit: 'units', aisle: 'produce', storePrice: 7, isPantry: false}]});
        state.activeSchedule = [{recipeId: '__mix'}]; state.lunchSchedule = []; state.bfastSchedule = []; state.twoNightBatchDays = {};
        const out = {}; ['rami-levy','shufersal','carrefour'].forEach(ck => { const l = getAggregatedGroceryList(ck); const t = calculateCartTotals(ck); out[ck] = {lines: Object.values(l).map(i => [i.name, i.unit, i.priceSource, i.storePrice]), total: t.totalCart, sum: Object.values(l).reduce((a, i) => a + Math.round(i.storePrice * 100), 0) / 100}; });
        RECIPES.pop(); state.activeSchedule = sv.a; state.lunchSchedule = sv.l; state.bfastSchedule = sv.b; state.twoNightBatchDays = sv.t; return out; })()""")
    ok = all(len(v["lines"]) == 3 and abs(v["total"] - v["sum"]) < 1e-9 for v in r.values()) and all(any(x[0] == "Zz Unknown Thing" and x[2] == "estimate-baseline" for x in v["lines"]) for v in r.values())
    check("mixed unit families: separate lines, no double count, an unpriced-everywhere item is a recipe-baseline estimate at every chain", ok, r)
    # 8 recipe-baseline estimate is the same at every store (no hidden store multiplier)
    zz = [next(x[3] for x in v["lines"] if x[0] == "Zz Unknown Thing") for v in r.values()]
    check("recipe-baseline estimate is identical at every chain (%s)" % zz, len(set(zz)) == 1 and zz[0] > 0, zz)
    # 9 custom items: the user's price, same at every chain; no price -> labelled baseline
    r = pg.evaluate("""(() => { state.customItems = [{id: 'c1', name: 'Birthday candles', price: 12.5, aisle: 'pantry'}, {id: 'c2', name: 'Mystery', aisle: 'pantry'}];
        const out = ['rami-levy','shufersal','carrefour'].map(ck => { const l = getAggregatedGroceryList(ck); const t = calculateCartTotals(ck); return [l.custom_c1.storePrice, l.custom_c1.priceSource, l.custom_c2 ? l.custom_c2.priceSource + '/' + l.custom_c2.storePrice : 'absent', t.userEnteredTotal, t.totalCart, t.noPriceCount]; });
        const rc = ['rami-levy','carrefour'].map(ck => (%s)(ck).ok); state.customItems = []; return {out, rc}; })()""" % RECON)
    check("custom items: user price kept (12.5) at every chain, labelled user-entered; a priceless item stays listed as no-price at 0 and is excluded from every total (counted in noPriceCount); totals reconcile", all(o[0] == 12.5 and o[1] == "user-entered" and o[2] == "no-price/0" and o[3] == 12.5 and o[5] == 1 for o in r["out"]) and all(r["rc"]), r)
    # 10 servings extremes and two-night batches
    r = pg.evaluate("""(() => { const bad = []; [1, 2, 8, 50].forEach(sv => { state.servings = sv; CH_ = ['shufersal','rami-levy','osher-ad','yochananof','victory','carrefour']; CH_.forEach(ck => { const x = (%s)(ck); if (!x.ok || x.bad.length) bad.push(sv + ' ' + ck); }); });
        state.servings = 4; state.twoNightBatchDays = {0: true, 2: true}; ['shufersal','carrefour'].forEach(ck => { const x = (%s)(ck); if (!x.ok) bad.push('batch ' + ck); }); state.twoNightBatchDays = {}; return bad; })()""" % (RECON, RECON))
    check("servings 1/2/8/50 and two-night batches reconcile at every chain", not r, r)
    # 11 stale feeds, one fresh chain, zero overlap, all missing
    sc = pg.evaluate("""(() => { const out = {}; const ing = state.livePrices.ingredients; const save = {fresh: {...state.chainFresh}, priced: {...state.chainPriced}, pf: state.isPricesFresh};
        // a) only Rami fresh
        PRICE_CHAINS.forEach(c => { state.chainFresh[c] = (c === 'rami-levy'); }); out.oneFresh = ['shufersal','rami-levy','carrefour'].map(ck => { const x = (%s)(ck); const t = x.t; return [ck, x.ok, t.actualCount, t.estimatedChainsCount, t.estimatedBaselineCount]; });
        // b) all stale
        PRICE_CHAINS.forEach(c => { state.chainFresh[c] = false; }); state.isPricesFresh = false; out.allStale = CH_.map(ck => { const x = (%s)(ck); return [ck, x.ok, x.t.actualCount, x.t.estimatedChainsCount, x.t.estimatedBaselineCount, x.t.totalItemsToBuy, x.t.totalCart]; });
        Object.assign(state.chainFresh, save.fresh); state.isPricesFresh = save.pf;
        // c) zero overlap: Rami prices only even ingredients, Shufersal only odd ones
        const keys = Object.keys(ing); const backup = {}; keys.forEach((k, i) => { backup[k] = {...ing[k]}; if (i %% 2 === 0) delete ing[k]['shufersal']; else delete ing[k]['rami-levy']; });
        PRICE_CHAINS.forEach(c => { state.chainFresh[c] = (c === 'rami-levy' || c === 'shufersal'); }); out.disjoint = ['shufersal','rami-levy','carrefour'].map(ck => { const x = (%s)(ck); return [ck, x.ok, x.t.actualCount, x.t.estimatedChainsCount, x.t.estimatedBaselineCount]; });
        keys.forEach(k => { ing[k] = backup[k]; }); Object.assign(state.chainFresh, save.fresh);
        // d) no price data at all
        const lp = state.livePrices; state.livePrices = null; state.isPricesFresh = false; PRICE_CHAINS.forEach(c => { state.chainFresh[c] = false; }); out.none = CH_.map(ck => { const x = (%s)(ck); return [ck, x.ok, x.t.actualCount, x.t.estimatedBaselineCount, x.t.totalItemsToBuy]; });
        state.livePrices = lp; state.isPricesFresh = save.pf; Object.assign(state.chainFresh, save.fresh); return out; })()""" % (RECON, RECON, RECON, RECON))
    check("only Rami fresh: Rami keeps its actual lines, every other chain is all-estimate and each reconciles", all(x[1] for x in sc["oneFresh"]) and sc["oneFresh"][1][2] > 0 and sc["oneFresh"][0][2] == 0 and sc["oneFresh"][2][2] == 0, sc["oneFresh"])
    check("all feeds stale: no actual lines anywhere, every line an estimate, headline = baseline estimates, finite and reconciled", all(x[1] and x[2] == 0 and x[3] == 0 and x[4] == x[5] and x[6] > 0 for x in sc["allStale"]), sc["allStale"])
    check("zero common items (Rami and Shufersal price disjoint ingredients): each prices its own, estimates the other's from the other chain, reconciles", all(x[1] for x in sc["disjoint"]) and sc["disjoint"][0][3] > 0 and sc["disjoint"][1][3] > 0, sc["disjoint"])
    check("no price file at all: all baseline estimates, no crash", all(x[1] and x[2] == 0 and x[3] == x[4] for x in sc["none"]), sc["none"])
    # 13 (added 14:30) all-stale baseline carries no hidden store/city/kosher multiplier; custom zero; same ingredient in two recipes; exports mark estimates
    r = pg.evaluate("""(() => { const out = {}; const save = {fresh: {...state.chainFresh}, pf: state.isPricesFresh, city: state.city, cert: state.kosherCert};
        PRICE_CHAINS.forEach(c => { state.chainFresh[c] = false; }); state.isPricesFresh = false; const tot = [];
        ['center','north'].forEach(city => ['rabbanut','mehadrin'].forEach(cert => { state.city = city; state.kosherCert = cert; tot.push(CH_.map(ck => calculateCartTotals(ck).totalCart)); }));
        out.stale = tot; state.city = save.city; state.kosherCert = save.cert; Object.assign(state.chainFresh, save.fresh); state.isPricesFresh = save.pf;
        state.customItems = [{id: 'z0', name: 'Zero', price: 0, aisle: 'pantry'}, {id: 'zn', name: 'Nan', price: NaN, aisle: 'pantry'}, {id: 'zm', name: 'Neg', price: -5, aisle: 'pantry'}];
        out.custom = ['rami-levy','carrefour'].map(ck => { const l = getAggregatedGroceryList(ck); const x = (%s)(ck); return [l.custom_z0.priceSource, l.custom_z0.storePrice, l.custom_zn ? 'present' : 'absent', x.ok && !l.custom_zm, l.custom_zm ? 'present' : 'absent']; }); state.customItems = [];
        RECIPES.push({id: '__a', title: 'a', ingredients: [{name: 'Zz Unknown Thing', qty: 1, unit: 'units', aisle: 'produce', storePrice: 4, isPantry: false}]}, {id: '__b', title: 'b', ingredients: [{name: 'Zz Unknown Thing', qty: 3, unit: 'units', aisle: 'produce', storePrice: 4, isPantry: false}]});
        const sv = {a: state.activeSchedule, l: state.lunchSchedule, b: state.bfastSchedule, t: state.twoNightBatchDays}; state.activeSchedule = [{recipeId: '__a'}, {recipeId: '__b'}]; state.lunchSchedule = []; state.bfastSchedule = []; state.twoNightBatchDays = {};
        out.two = ['rami-levy','shufersal'].map(ck => { const l = getAggregatedGroceryList(ck); const v = Object.values(l).filter(i => i.name === 'Zz Unknown Thing'); return [v.length, v[0] && v[0].qty, v[0] && v[0].storePrice, v[0] && v[0].priceSource]; });
        RECIPES.pop(); RECIPES.pop(); state.activeSchedule = sv.a; state.lunchSchedule = sv.l; state.bfastSchedule = sv.b; state.twoNightBatchDays = sv.t; return out; })()""" % RECON)
    st = r["stale"]
    check("all feeds stale: totals identical at every chain and unchanged by city and kosher setting (no old multipliers)", all(len(set(row)) == 1 for row in st) and len({row[0] for row in st}) == 1, st)
    check("custom item typed 0 stays a valid free user-entered 0.00; stored NaN / negative / missing items are NOT turned into invented lines (absent from every cart); totals reconcile", all(o[0] == "user-entered" and o[1] == 0 and o[2] == "absent" and o[3] and o[4] == "absent" for o in r["custom"]), r["custom"])
    check("same ingredient in two DIFFERENT recipes: one combined line (qty 4); the baseline is the SUM of both recipes' own contributions (4 + 4 = 8), nothing dropped, same at every chain", all(o[0] == 1 and o[1] == 4 and abs(o[2] - 8) < 0.011 and o[3] == "estimate-baseline" for o in r["two"]), r["two"])
    pg.evaluate("regenerateWeek()"); pg.evaluate("state.currentStore = 'shufersal'; renderAll()")
    ex = pg.evaluate("""(() => { openWhatsAppModal(); const sel = document.getElementById('whatsappFormatSelect'); sel.value = 'detailed'; updateWhatsAppPreview(); const txt = document.getElementById('whatsappPreviewText').value;
        const t = calculateCartTotals('shufersal'); const lines = txt.split('\\n').filter(l => l.startsWith('•')); const est = lines.filter(l => l.endsWith('(est.)')).length;
        const checklistEst = (document.getElementById('whatsappItemsChecklist').innerText.match(/est\\./g) || []).length; return {est, checklistEst, expect: t.estimatedCount, split: txt.includes('actual ₪' + t.actualTotal.toFixed(2)) && txt.includes('estimated ₪' + t.estimatedTotal.toFixed(2)), n: lines.length}; })()""")
    check("export: every estimated line marked (est.) in the detailed export and the modal checklist, actual lines unmarked, split totals shown", ex["est"] == ex["expect"] and ex["checklistEst"] >= ex["expect"] and ex["split"] and ex["expect"] > 0, ex)
    # 13b analytic fixtures: identical recipe twice doubles consumption and baseline; different recipes keep their own costs; weighted lines are pro-rata, packaged lines whole packs
    r = pg.evaluate("""(() => { const sv = {a: state.activeSchedule, l: state.lunchSchedule, b: state.bfastSchedule, t: state.twoNightBatchDays, s: state.servings}; state.servings = 4;
        RECIPES.push({id: '__x', title: 'x', ingredients: [{name: 'Zz Unknown Thing', qty: 2, unit: 'units', aisle: 'produce', storePrice: 5, isPantry: false}]}, {id: '__y', title: 'y', ingredients: [{name: 'Zz Unknown Thing', qty: 1, unit: 'units', aisle: 'produce', storePrice: 7, isPantry: false}, {name: 'Zz Other Thing', qty: 1, unit: 'units', aisle: 'produce', storePrice: 3, isPantry: false}]});
        state.lunchSchedule = []; state.bfastSchedule = []; state.twoNightBatchDays = {}; const out = {};
        state.activeSchedule = [{recipeId: '__x'}]; out.one = ['rami-levy','carrefour'].map(ck => { const l = getAggregatedGroceryList(ck); const v = Object.values(l).filter(i => i.name === 'Zz Unknown Thing')[0]; return [v.qty, v.storePrice]; });
        state.activeSchedule = [{recipeId: '__x'}, {recipeId: '__x'}]; out.two = ['rami-levy','carrefour'].map(ck => { const l = getAggregatedGroceryList(ck); const v = Object.values(l).filter(i => i.name === 'Zz Unknown Thing')[0]; return [v.qty, v.storePrice, calculateCartTotals(ck).totalCart]; });
        state.activeSchedule = [{recipeId: '__x'}, {recipeId: '__y'}]; out.mix = ['rami-levy','shufersal'].map(ck => { const l = getAggregatedGroceryList(ck); const a = Object.values(l).filter(i => i.name === 'Zz Unknown Thing')[0], o = Object.values(l).filter(i => i.name === 'Zz Other Thing')[0]; return [a.qty, a.storePrice, o.qty, o.storePrice, calculateCartTotals(ck).totalCart]; });
        // weighted line pro-rata and packaged line ceil, from the raw matched pack
        out.w = []; PRICE_CHAINS.forEach(ck => { const l = getAggregatedGroceryList(ck); Object.values(l).forEach(i => { if (i.isPantry || i.isCustom || i.priceSource !== 'actual') return; const m = i.matchedData, need = getIngredientPricing(i.name, i.qty, i.unit, 1.0, ck, 0).neededInPackUnit;
          const exp = m.isWeighted ? need / m.packQty * m.packPrice : Math.max(1, Math.ceil(need / m.packQty - 1e-6)) * m.packPrice; if (Math.abs(exp - i.storePrice) > 0.011) out.w.push(ck + ' ' + i.name); }); });
        RECIPES.pop(); RECIPES.pop(); state.activeSchedule = sv.a; state.lunchSchedule = sv.l; state.bfastSchedule = sv.b; state.twoNightBatchDays = sv.t; state.servings = sv.s; return out; })()""")
    check("fixture: one recipe = baseline 5 for qty 2; the identical recipe twice = qty 4 and baseline 10 (doubled consumption), cart total follows", all(o[0] == 2 and abs(o[1] - 5) < 0.011 for o in r["one"]) and all(o[0] == 4 and abs(o[1] - 10) < 0.011 and abs(o[2] - 10) < 0.011 for o in r["two"]), r)
    check("fixture: two different recipes keep their own cost contributions (5 + 7 = 12 for the shared ingredient, 3 for the other)", all(o[0] == 3 and abs(o[1] - 12) < 0.011 and abs(o[3] - 3) < 0.011 and abs(o[4] - 15) < 0.011 for o in r["mix"]), r["mix"])
    check("actual lines: weighted items are priced pro-rata on actual weight, packaged items by whole packs (all chains, whole plan)", not r["w"], r["w"][:5])
    # 13c invalid custom input through the real form is visibly rejected; no item created
    r = pg.evaluate("""(() => { const n0 = state.customItems.length; const res = []; ['-3', '', '2001', 'abc', '0'].forEach(v => { const before = state.customItems.length; document.getElementById('customItemName').value = 'Probe ' + v; document.getElementById('customItemPrice').value = v;
        document.getElementById('toastContainer') && (document.getElementById('toastContainer').innerHTML = ''); document.getElementById('addCustomItemForm').dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
        res.push([v, state.customItems.length - before, (document.body.innerText.match(/valid price/g) || []).length > 0]); }); const added = state.customItems.slice(n0); state.customItems = state.customItems.slice(0, n0); return {res, added: added.map(i => i.price)}; })()""")
    check("custom form: -3 and 2001 rejected with a visible 'valid price' message and no item; empty accepted as a no-price line (null); 0 accepted as free ('abc' is sanitized to empty by the number input, so it also lands as a no-price line)", all(x[1] == 0 and x[2] for x in [r["res"][0], r["res"][2]]) and r["res"][1][1] == 1 and r["res"][3][1] == 1 and r["res"][4][1] == 1 and r["added"] == [None, None, 0], r)
    # 13e (7 Nov) macros engine + meals export + no-price cart display
    r = pg.evaluate("""(() => { const out = {};
        state.customItems = [{id: 'np1', name: 'Paper towels', price: null, aisle: 'pantry'}, {id: 'p1', name: 'Dish soap', price: 15, aisle: 'pantry'}];
        renderAll();
        const l = getAggregatedGroceryList('rami-levy'); const t = calculateCartTotals('rami-levy');
        out.noPriceLine = l.custom_np1.priceSource === 'no-price' && l.custom_np1.storePrice === 0 && t.noPriceCount === 1;
        out.userLine = l.custom_p1.priceSource === 'user-entered' && t.userEnteredTotal === 15;
        out.note = !document.getElementById('noPriceItemsNote').classList.contains('hidden') && document.getElementById('noPriceItemsNote').textContent.includes('Paper towels');
        // meals export checkbox
        state.exportIncludeMeals = true; openWhatsAppModal(); updateWhatsAppPreview();
        const txt = document.getElementById('whatsappPreviewText').value;
        out.mealsInExport = txt.includes('Planned Meals') && txt.indexOf('Planned Meals') < txt.indexOf('Sent from');
        out.noPriceInExport = txt.includes('without a price');
        state.exportIncludeMeals = false; updateWhatsAppPreview();
        out.mealsOutByDefault = !document.getElementById('whatsappPreviewText').value.includes('Planned Meals');
        closeWhatsAppModal();
        // macros: known recipe fully covered vs custom unknown
        const m1 = computeRecipeMacros(state.activeSchedule.find(s => s.recipeId && s.recipeId !== 'no_meal').recipeId);
        out.macrosFinite = m1 && [m1.kcal, m1.p, m1.c, m1.f].every(isFinite) && m1.covered > 0;
        RECIPES.push({id: '__nomac', title: 'nm', ingredients: [{name: 'Zz Unknown Thing', qty: 100, unit: 'g', aisle: 'produce', storePrice: 4, isPantry: false}]});
        const m2 = computeRecipeMacros('__nomac');
        out.macrosMissing = m2 && m2.covered === 0 && m2.missing.length === 1;
        RECIPES.pop();
        switchTab('Macros');
        out.macrosView = !document.getElementById('viewMacros').classList.contains('hidden') && document.getElementById('macrosDaysContainer').children.length > 0;
        state.customItems = []; renderAll(); switchTab('Plan');
        return out; })()""")
    check("macros tab renders with finite per-serving values and coverage badges; unknown-ingredient meal is not calculated; no-price extras listed at 0 outside totals with a visible note; meals checkbox toggles the planned-meals section in the export",
        all(r.values()), r)
    # 13d lines with no verified pack/unit (unit gaps, Baharat, soba, composites) are never actual
    r = pg.evaluate("""(() => { const seen = {}; RECIPES.forEach(rc => (rc.ingredients || []).forEach(i => { seen[i.name + '|' + i.unit] = i; })); const ings = Object.values(seen).map(i => ({name: i.name, qty: i.qty, unit: i.unit, aisle: i.aisle, storePrice: i.storePrice, isPantry: false}));
        const sv = {a: state.activeSchedule, l: state.lunchSchedule, b: state.bfastSchedule, t: state.twoNightBatchDays}; RECIPES.push({id: '__all', title: 'all', ingredients: ings}); state.activeSchedule = [{recipeId: '__all'}]; state.lunchSchedule = []; state.bfastSchedule = []; state.twoNightBatchDays = {};
        const bad = [], est = {}; PRICE_CHAINS.forEach(ck => { const l = getAggregatedGroceryList(ck); est[ck] = 0; Object.values(l).forEach(i => { if (i.isPantry) return; if (i.priceSource === 'actual') { const p = getIngredientPricing(i.name, i.qty, i.unit, 1.0, ck, 0); if (!i.isLiveMatch || !i.matchedData || !(p.neededInPackUnit > 0) || !p.isConvertible) bad.push(ck + ' ' + i.name); } else { est[ck]++; if (!/^estimate-/.test(i.priceSource)) bad.push(ck + ' src ' + i.name); } }); });
        const names = ['Baharat Spice Blend', 'Soba Noodles', 'Fresh Dill', 'Fresh Parsley']; const hit = {}; const l = getAggregatedGroceryList('rami-levy'); Object.values(l).forEach(i => { names.forEach(n => { if (i.name.toLowerCase().includes(n.split(' ').pop().toLowerCase())) hit[i.name] = i.priceSource + (i.isPantry ? ' (pantry)' : ''); }); });
        RECIPES.pop(); state.activeSchedule = sv.a; state.lunchSchedule = sv.l; state.bfastSchedule = sv.b; state.twoNightBatchDays = sv.t; return {bad, est, n: ings.length, hit}; })()""")
    check("every ingredient in the app (%d lines incl. unit gaps, Baharat, soba): an actual price only with a verified convertible pack, otherwise an explicit estimate" % r["n"], not r["bad"], r)
    # 12 UI: Cart tab rows and chain cards show actual vs estimate distinctly, with matching counts
    pg.evaluate("regenerateWeek()"); pg.evaluate("state.currentStore = 'shufersal'; renderAll(); switchTab('Cart')"); pg.wait_for_timeout(700)
    ui = pg.evaluate("""(() => { const t = calculateCartTotals('shufersal'); const txt = document.getElementById('supermarketPriceGrid').innerText;
        return {est: document.querySelectorAll('[data-testid=estimated-price]').length, act: document.querySelectorAll('[data-testid=actual-price]').length, t: [t.estimatedCount, t.actualCount + t.userEnteredCount],
                cards: document.querySelectorAll('[data-testid=card-breakdown]').length, head: txt.includes('₪' + t.totalCart.toFixed(2)), brk: txt.includes('actual ₪' + t.actualTotal.toFixed(2)) && txt.includes('estimated ₪' + t.estimatedTotal.toFixed(2)),
                old: /Matched items only|not in total/.test(document.body.innerText)}; })()""")
    check("UI: estimated rows = estimated count, actual rows = actual count, six card breakdowns, headline and split shown, old 'matched only' wording gone", ui["est"] == ui["t"][0] and ui["act"] == ui["t"][1] and ui["cards"] == 6 and ui["head"] and ui["brk"] and not ui["old"], ui)
    pg.screenshot(path="/tmp/shot_complete_cart.png", full_page=False)
    check("no page errors", not errs, errs)
    b.close()
print("\nCOMPLETE CART FAILURES: %d" % len(fails)); sys.exit(1 if fails else 0)
