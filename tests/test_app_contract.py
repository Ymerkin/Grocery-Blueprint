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
        check(name + ": same ingredient in different unit families stays on separate lines (cucumbers)", len(agg) >= 2 and len({a[2] for a in agg}) == len(agg) and all(a[1] < 100 or a[2] == 'g' for a in agg), agg)
        if name == "fresh":
            check("fresh: both chains published", st["rami"] and st["shuf"])
            check("fresh: feed badge says published", "Published online prices" in st["feed"])
            check("fresh: coverage Rami 3/14 and Shufersal 3/14 (zucchini excluded: incompatible unit)", "Rami Levy (039): 3/14" in st["cov"] and "Shufersal (413): 3/14" in st["cov"], st["cov"])
            ex = pg.evaluate("(()=>{const l=getAggregatedGroceryList();const z=Object.values(l).find(i=>i.name==='Fresh Zucchini');const r=getIngredientPricing(z.name,z.qty,z.unit,1.0,'rami-levy');const c=getIngredientPricing('Fresh Chicken Breast',2500,'g',1.0,'rami-levy');return {z:r,c:c.purchaseCost,cm:c.matchedData&&c.matchedData.metadataSource}})()")
            check("fresh: incompatible unit excluded with reason", ex["z"]["isLiveMatch"] is False and "Incompatible" in (ex["z"].get("unpricedReason") or ""), ex["z"])
            check("fresh: chicken 2500g @ NIS30/kg = 3 packs x 30 = 90", abs(ex["c"] - 90.0) < 0.01, ex["c"])
            check("fresh: citation shows source file", "SYNTHETIC-TEST-FIXTURE" in (ex["cm"] or ""), ex["cm"])
            txt = pg.evaluate("document.getElementById('supermarketPriceGrid').innerText")
            check("fresh: comparison shows shared-item savings label", "shared items" in txt, txt[:300])
        if name in ("stale", "missing"):
            check(name + ": estimates only", not st["fresh"] and "estimates" in st["feed"].lower(), st)
        if name in ("v1", "underscore"):
            check(name + ": rejected with schema/key reason", not st["fresh"] and st["reason"] and ("schema" in st["reason"] or "chain key" in st["reason"]), st)
        if name == "empty":
            check("empty: not labelled published, reason explains review", not st["fresh"] and "reviewed" in (st["reason"] or ""), st)
        if name == "partial":
            check("partial: rami published, shufersal estimates only", st["rami"] and not st["shuf"] and "estimates only" in st["cov"], st)
        pg.screenshot(path="/tmp/shot_%s.png" % name); pg.close(); srv.shutdown()
    b.close()
print("FAILED: %s" % fails if fails else "ALL APP CONTRACT CHECKS PASSED")
sys.exit(1 if fails else 0)
