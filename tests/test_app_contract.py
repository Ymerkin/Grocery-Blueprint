"""Loads index.html in headless Chrome against prices.json variants and checks badges, coverage and schema rejection.
Fixtures are SYNTHETIC (see test_script_contract.py) and only exercise the contract. Needs: pip install playwright; Chrome.
Run: python tests/test_app_contract.py [path-to-chrome]"""
import copy, http.server, json, os, shutil, socketserver, sys, tempfile, threading
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CHROME = sys.argv[1] if len(sys.argv) > 1 else shutil.which("google-chrome") or shutil.which("chromium")
fixture = json.load(open(os.environ.get("GB_FIXTURE", "/tmp/fixture_v21.json"), encoding="utf-8"))


def iso(h):
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


def variant(name):
    d = copy.deepcopy(fixture)
    for c in d["metadata"]["chains"].values():
        c["published_at"] = iso(3)
    if name == "stale":
        for c in d["metadata"]["chains"].values(): c["published_at"] = iso(60)
    if name == "v1":
        d["metadata"]["version"] = "1.0"; d["metadata"]["chains"]["rami_levy"] = d["metadata"]["chains"].pop("rami-levy")
    if name == "underscore":
        d["metadata"]["chains"]["rami_levy"] = d["metadata"]["chains"]["rami-levy"]
    if name == "empty":
        d["ingredients"] = {}
        for c in d["metadata"]["chains"].values(): c["priced_count"] = 0
    if name == "partial":
        del d["metadata"]["chains"]["shufersal"]
        for e in d["ingredients"].values(): e.pop("shufersal", None)
    return d


def serve(prices):
    tmp = tempfile.mkdtemp()
    shutil.copy(os.path.join(ROOT, "index.html"), tmp)
    if prices is not None: json.dump(prices, open(os.path.join(tmp, "prices.json"), "w", encoding="utf-8"))
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(s, *a, **k): super().__init__(*a, directory=tmp, **k)
        def log_message(s, *a): pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


fails = []
def check(label, cond, info=""):
    print(("PASS " if cond else "FAIL ") + label + ((" -> " + str(info)) if info and not cond else ""))
    if not cond: fails.append(label)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    for name in ["fresh", "stale", "v1", "underscore", "empty", "partial", "missing"]:
        srv = serve(None if name == "missing" else variant(name))
        pg = b.new_page(viewport={"width": 1280, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:%d/index.html" % srv.server_address[1]); pg.wait_for_timeout(1500)
        st = pg.evaluate("({fresh: state.isPricesFresh, reason: state.pricesRejectReason, rami: isChainPublished('rami-levy'), shuf: isChainPublished('shufersal'), "
                         "feed: document.getElementById('feedStatusBadge')?.innerText, cov: document.getElementById('planCoverageBadge')?.innerText})")
        print(name, st)
        check(name + ": no JS errors", not errs, errs)
        agg = pg.evaluate("Object.entries(getAggregatedGroceryList()).filter(([k,i])=>/cucumber/i.test(i.name)).map(([k,i])=>[k,i.qty,i.unit])")
        check(name + ": same ingredient in different unit families stays on separate lines (cucumbers; v10 converts approved one-unit rows to g, so one g line is expected)", len(agg) >= 1 and len({a[2] for a in agg}) == len(agg) and all(a[1] < 100 or a[2] == 'g' for a in agg), agg)
        mix = pg.evaluate("""(()=>{const sv={a:state.activeSchedule,l:state.lunchSchedule,b:state.bfastSchedule,t:state.twoNightBatchDays};
          RECIPES.push({id:'__mix',title:'mix test',ingredients:[{name:'Zz Mixed Item',qty:200,unit:'g',aisle:'produce',storePrice:1,isPantry:false},{name:'Zz Mixed Item',qty:2,unit:'units',aisle:'produce',storePrice:1,isPantry:false},{name:'Zz Mixed Item',qty:300,unit:'g',aisle:'produce',storePrice:1,isPantry:false}]});
          state.activeSchedule=[{recipeId:'__mix'}];state.lunchSchedule=[];state.bfastSchedule=[];state.twoNightBatchDays={};
          const l=Object.entries(getAggregatedGroceryList()).filter(([k,i])=>i.name==='Zz Mixed Item').map(([k,i])=>[i.qty,i.unit]);
          RECIPES.pop();state.activeSchedule=sv.a;state.lunchSchedule=sv.l;state.bfastSchedule=sv.b;state.twoNightBatchDays=sv.t;return l})()""")
        check(name + ": synthetic mixed unit families stay separate (g line and units line)", len(mix) == 2 and {m[1] for m in mix} == {"g", "units"} and [m[0] for m in mix if m[1] == "g"][0] > 0, mix)
        if name == "fresh":
            check("fresh: both chains published", st["rami"] and st["shuf"])
            check("fresh: feed badge says published", "Published store prices" in st["feed"])
            nlines = pg.evaluate("Object.values(getAggregatedGroceryList()).filter(i => !i.isPantry).length")
            import re as _re
            def cov_of(chain_label):
                m = _re.search(_re.escape(chain_label) + r": (\d+) actual \+ (\d+) est\. / (\d+)", st["cov"])
                return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
            rami_cov, shuf_cov = cov_of("Rami Levy Online (039)"), cov_of("Shufersal Online (413)")
            check("fresh: coverage Rami and Shufersal show actual + estimates with the plan denominator", rami_cov and shuf_cov and rami_cov[2] == nlines and shuf_cov[2] == nlines and rami_cov[0] >= 3 and shuf_cov[0] >= 3, st["cov"])
            ex = pg.evaluate("(()=>{const l=getAggregatedGroceryList();const z=Object.values(l).find(i=>i.name==='Fresh Zucchini');const r=getIngredientPricing(z.name,z.qty,z.unit,1.0,'rami-levy');const c=getIngredientPricing('Fresh Chicken Breast',2500,'g',1.0,'rami-levy');return {z:r,c:c.purchaseCost,cm:c.matchedData&&c.matchedData.metadataSource}})()")
            # Mapping growth (Nov 15): the user-approved zucchini pin (קישוא ירוק) prices per kg now.
            check("fresh: zucchini priced per kg via approved pin", ex["z"]["isLiveMatch"] is True and ex["z"]["matchedData"]["packBasis"].startswith("sold loose by weight"), ex["z"])
            check("fresh: chicken 2500g weighted @ NIS34.5/kg (today's feed price for the approved pin) = 86.25", abs(ex["c"] - 86.25) < 0.01, ex["c"])
            check("fresh: citation shows source file", "ItemCode=" in (ex["cm"] or "") and "published" in (ex["cm"] or ""), ex["cm"])
            txt = pg.evaluate("(document.getElementById('cartFootnotes')||{innerText:''}).innerText + ' ' + document.getElementById('supermarketPriceGrid').innerText")
            check("fresh: comparison/footnotes explain the same-basket line", "Same-basket" in txt, txt[:300])
        if name in ("stale", "missing"):
            check(name + ": estimates only", not st["fresh"] and "estimates" in st["feed"].lower(), st)
        if name in ("v1", "underscore"):
            check(name + ": rejected with schema/key reason", not st["fresh"] and st["reason"] and ("schema" in st["reason"] or "chain key" in st["reason"]), st)
        if name == "empty":
            check("empty: not labelled published, reason explains review", not st["fresh"] and "reviewed" in (st["reason"] or ""), st)
        if name == "partial":
            check("partial: rami published, shufersal estimates only", st["rami"] and not st["shuf"] and "all estimates" in st["cov"], st)
        pg.screenshot(path="/tmp/shot_%s.png" % name); pg.close(); srv.shutdown()
    b.close()
print("FAILED: %s" % fails if fails else "ALL APP CONTRACT CHECKS PASSED")
sys.exit(1 if fails else 0)
