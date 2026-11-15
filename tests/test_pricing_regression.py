"""Regression tests for the Nov 2026 price-comparison fixes:
1. By-weight goods are charged at actual weight (no whole-kilo rounding).
2. Packaged goods still round up to whole packages.
3. Benchmark estimates ACCUMULATE across recipes that share an ingredient (no overwrite).
4. Chain totals equal the sum of their item costs (published purchase basis / estimate basis).
5. Comparison grid separates published-feed chains from estimate-only chains and shows no static rank badges.
6. Pantry-owned items are excluded from cart totals.
Loads the REAL package (index.html + prices.json) in headless Chrome. Needs: pip install playwright; Chrome.
Run: python tests/test_pricing_regression.py [path-to-chrome]"""
import http.server, json, os, shutil, socketserver, sys, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CHROME = sys.argv[1] if len(sys.argv) > 1 else shutil.which("google-chrome") or shutil.which("chromium")

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(s, *a): pass

srv = socketserver.TCPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

fails = []
def check(label, cond, info=""):
    print(("PASS " if cond else "FAIL ") + label + ((" -> " + str(info)) if (info and not cond) or True else ""))
    if not cond: fails.append(label)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:%d/index.html" % srv.server_address[1])
    pg.wait_for_timeout(2500)

    # Deterministic plan: three dinners sharing chicken breast + one repeated lunch; no pantry, 4 servings.
    pg.evaluate("""() => {
      state.servings = 4;
      state.pantryState = {};
      state.twoNightBatchDays = {};
      state.activeSchedule = [{recipeId:'mealprep_chicken_broccoli'},{recipeId:'schnitzel_ptitim'},{recipeId:'shawarma_strips'}];
      state.lunchSchedule = [{recipeId:'mealprep_chicken_broccoli'}];
      state.bfastSchedule = [];
    }""")

    r = pg.evaluate("""() => {
      const w = getIngredientPricing('Fresh Chicken Breast', 2500, 'g', 1.0, 'shufersal');
      const t = getIngredientPricing('Firm Tofu', 1400, 'g', 1.0, 'shufersal');
      // expected estimate sum for shared chicken across the 4 recipe placements
      let expected = 0;
      ['mealprep_chicken_broccoli','schnitzel_ptitim','shawarma_strips','mealprep_chicken_broccoli'].forEach(id => {
        const rec = RECIPES.find(x => x.id === id);
        const ing = rec.ingredients.find(i => i.name === 'Fresh Chicken Breast');
        expected += getIngredientPricing(ing.name, ing.qty, ing.unit, state.servings/4, 'carrefour').storePrice;
      });
      const vl = getAggregatedGroceryList('carrefour');
      const chickenEst = vl['fresh chicken breast'] ? vl['fresh chicken breast'].storePrice : null;
      const sl = getAggregatedGroceryList('shufersal');
      const chickenLive = sl['fresh chicken breast'];
      let estSum = 0; Object.values(vl).forEach(it => { if (!it.isPantry) estSum += it.storePrice; });
      const vicl = getAggregatedGroceryList('victory');
      let vicPubSum = 0; Object.values(vicl).forEach(it => { if (!it.isPantry && it.isLiveMatch) vicPubSum += it.purchaseCost; });
      let pubSum = 0; Object.values(sl).forEach(it => { if (!it.isPantry && it.isLiveMatch) pubSum += it.purchaseCost; });
      const w500vic = getIngredientPricing('Fresh Chicken Breast', 500, 'g', 1.0, 'victory');
      const beef500oa = getIngredientPricing('Fresh Ground Beef', 500, 'g', 1.0, 'osher-ad');
      const beef500yo = getIngredientPricing('Fresh Ground Beef', 500, 'g', 1.0, 'yochananof');
      const w500rami = getIngredientPricing('Fresh Chicken Breast', 500, 'g', 1.0, 'rami-levy');
      const w500shuf = getIngredientPricing('Fresh Chicken Breast', 500, 'g', 1.0, 'shufersal');
      const beef500rami = getIngredientPricing('Fresh Ground Beef', 500, 'g', 1.0, 'rami-levy');
      const beef500shuf = getIngredientPricing('Fresh Ground Beef', 500, 'g', 1.0, 'shufersal');
      return {
        w, t, w500vic, beef500oa, beef500yo, w500rami, w500shuf, beef500rami, beef500shuf, expected: Math.round(expected*100)/100, chickenEst,
        chickenLiveCost: chickenLive ? chickenLive.purchaseCost : null,
        chickenLivePacks: chickenLive ? chickenLive.packsNeeded : null,
        chickenQty: chickenLive ? chickenLive.qty : null,
        estSum: Math.round(vicPubSum*100)/100,
        vicTotal: calculateCartTotals('victory').publishedTotal,
        pubSum: Math.round(pubSum*100)/100,
        shufTotal: calculateCartTotals('shufersal').publishedTotal,
        mult: getStoreMultiplier('victory')
      };
    }""")
    print(json.dumps(r, indent=1))
    check("weighted 2.5kg charged as 2.5kg not 3kg", abs(r["w"]["purchaseCost"] - 2.5*r["w"]["matchedData"]["packPrice"]) < 0.01 and r["w"]["packsNeeded"] == 2.5, f'got {r["w"]["purchaseCost"]} packs={r["w"]["packsNeeded"]}')
    check("weighted purchase == consumption", abs(r["w"]["purchaseCost"] - r["w"]["recipeCost"]) < 0.01, f'{r["w"]["purchaseCost"]} vs {r["w"]["recipeCost"]}')
    check("packaged tofu still rounds up to whole packs", abs(r["t"]["purchaseCost"] - 5*r["t"]["matchedData"]["packPrice"]) < 0.01 and r["t"]["packsNeeded"] == 5, f'got {r["t"]["purchaseCost"]} packs={r["t"]["packsNeeded"]}')
    check("estimate accumulates across repeated ingredient (chicken x4 placements, carrefour)", r["chickenEst"] is not None and abs(r["chickenEst"] - r["expected"]) < 0.05, f'est={r["chickenEst"]} expected={r["expected"]}')
    check("live chicken aggregated across 4 placements then priced at actual weight", r["chickenQty"] == 2650 and abs(r["chickenLiveCost"] - (r["chickenQty"]/1000*r["w"]["matchedData"]["packPrice"])) < 0.01, f'qty={r["chickenQty"]} cost={r["chickenLiveCost"]}')
    check("victory totalCart equals summed live purchase costs", abs(r["vicTotal"] - r["estSum"]) < 0.05, f'{r["vicTotal"]} vs {r["estSum"]}')
    check("Victory: stale source cannot supply an actual line; a fresh weighted source uses half a kg", (not r["w500vic"]["isLiveMatch"] and not pg.evaluate("isChainPublished('victory')")) or (r["w500vic"]["isLiveMatch"] and abs(r["w500vic"]["purchaseCost"]-0.5*r["w500vic"]["matchedData"]["packPrice"])<0.01 and r["w500vic"]["packsNeeded"]==0.5),r["w500vic"])
    check("Reconfigured Osher Ad Kiryat Ono branch supplies an actual price", r["beef500oa"]["isLiveMatch"], r["beef500oa"])
    check("Unconfigured former Yohananof Tel Aviv branch supplies no actual price", not r["beef500yo"]["isLiveMatch"], r["beef500yo"])
    check("500g raw chicken at Rami Levy costs half the per-kg price (34.5/kg)", r["w500rami"]["isLiveMatch"] and abs(r["w500rami"]["purchaseCost"] - r["w500rami"]["matchedData"]["packPrice"]*0.5) < 0.01 and r["w500rami"]["packsNeeded"] == 0.5, json.dumps(r["w500rami"]))
    check("500g raw chicken at Shufersal costs half the per-kg price (39.9/kg)", r["w500shuf"]["isLiveMatch"] and abs(r["w500shuf"]["purchaseCost"] - r["w500shuf"]["matchedData"]["packPrice"]*0.5) < 0.01 and r["w500shuf"]["packsNeeded"] == 0.5, json.dumps(r["w500shuf"]))
    check("500g ground beef at Rami Levy at actual weight (current feed price)", r["beef500rami"]["isLiveMatch"] and abs(r["beef500rami"]["purchaseCost"] - r["beef500rami"]["matchedData"]["packPrice"]*0.5) < 0.01 and r["beef500rami"]["packsNeeded"] == 0.5, json.dumps(r["beef500rami"]))
    check("500g ground beef at Shufersal at actual weight (73.9/kg)", r["beef500shuf"]["isLiveMatch"] and abs(r["beef500shuf"]["purchaseCost"] - r["beef500shuf"]["matchedData"]["packPrice"]*0.5) < 0.01 and r["beef500shuf"]["packsNeeded"] == 0.5, json.dumps(r["beef500shuf"]))
    check("shufersal publishedTotal equals summed live purchase costs", abs(r["shufTotal"] - r["pubSum"]) < 0.05, f'{r["shufTotal"]} vs {r["pubSum"]}')

    # pantry exclusion: mark a staple owned, verify its estimate leaves the total
    r2 = pg.evaluate("""() => {
      const before = calculateCartTotals('shufersal').combinedTotal;
      state.pantryState = { olive_oil: true };
      const after = calculateCartTotals('shufersal').combinedTotal;
      const list = getAggregatedGroceryList('shufersal');
      const oil = list['extra virgin olive oil'];
      return { before, after, oilPantry: oil ? !!oil.isPantry : null, oilCost: oil ? oil.storePrice : 0 };
    }""")
    check("pantry-owned staple excluded from cart total", r2["oilPantry"] and abs((r2["before"] - r2["after"]) - r2["oilCost"]) < 0.05, json.dumps(r2))

    # UI separation: published first, estimates segregated, no static rank badges
    r3 = pg.evaluate("""() => {
      state.pantryState = {};
      renderSupermarketComparison();
      const g = document.getElementById('supermarketPriceGrid');
      const kids = [...g.children];
      const texts = kids.map(k => k.innerText || '');
      return {
        n: kids.length,
        hasBasisNote: texts.some(t => t.includes('Complete cart at every store')),
        basisInFootnotes: (document.getElementById('cartBasisNote')||{innerText:''}).innerText.includes('Complete cart at every store'),
        hasEstNote: texts.some(t => t.includes('Estimate-only chains')),
        hasRankBadge: texts.some(t => t.includes('Lowest Avg Price') || t.includes('Widest Variety') || t.includes('Suburban Convenience') || t.includes('Hypermarket Fresh') || t.includes('European Imports')),
        pubFeedCount: texts.filter(t => t.includes('Published online prices')).length,
        branchCount: texts.filter(t => t.includes('Published branch prices')).length,
        liveCatCount: texts.filter(t => t.includes('No current branch prices - estimates')).length,
        estAvgCount: texts.filter(t => t.includes('No current branch prices - estimates')).length
      };
    }""")
    print(json.dumps(r3, indent=1))
    check("basis note moved out of the grid into footnotes", not r3["hasBasisNote"] and r3["basisInFootnotes"])
    check("no estimate-separator note (cards stay together)", not r3["hasEstNote"])
    check("12 configured store cards together (note now in footnotes)", r3["n"] == 12, json.dumps(r3))
    check("3 current online + 9 current physical branch cards", r3["pubFeedCount"] == 3 and r3["branchCount"] == 9 and r3["liveCatCount"] == 0 and r3["estAvgCount"] == 0, json.dumps(r3))
    check("no static rank badges in comparison", not r3["hasRankBadge"])

    # savings line only over identical shared items, weighted now at actual weight
    r4 = pg.evaluate("""() => {
      const list = getAggregatedGroceryList('shufersal');
      let s = 0, rr = 0, n = 0;
      Object.values(list).forEach(item => {
        if (item.isPantry) return;
        const rp = getIngredientPricing(item.name, item.qty, item.unit, 1.0, 'rami-levy');
        const sp = getIngredientPricing(item.name, item.qty, item.unit, 1.0, 'shufersal');
        if (rp.isLiveMatch && sp.isLiveMatch) { s += sp.purchaseCost; rr += rp.purchaseCost; n++; }
      });
      return { n, s: Math.round(s*100)/100, r: Math.round(rr*100)/100 };
    }""")
    print("shared basket:", json.dumps(r4))
    check("shared basket recompute sane (both chains priced same items)", r4["n"] > 0 and r4["s"] > 0 and r4["r"] > 0)

    check("no page errors", not errs, errs)
    b.close()

print("\n%d failures" % len(fails))
sys.exit(1 if fails else 0)
