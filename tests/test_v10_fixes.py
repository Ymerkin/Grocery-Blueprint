"""v10 regression tests: pantry matching, quarantine consistency, feed pack derivation, whole-cart invariants.
Run: python tests/test_v10_fixes.py [path-to-chrome]
The whole-cart section needs fresh price data (each chain's file must be < 48 h old, the app's own rule);
it is skipped with a clear message otherwise. All other sections run on any date."""
import http.server, json, os, shutil, socketserver, sys, threading, types
from decimal import Decimal
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fetch_prices as fp
CHROME = sys.argv[1] if len(sys.argv) > 1 else shutil.which("google-chrome") or shutil.which("chromium")
fails = []
def check(label, cond, info=""):
    print(("PASS " if cond else "FAIL ") + label + ((" -> " + str(info)) if not cond else ""))
    if not cond: fails.append(label)

# ---- 1. quarantine consistency (pure data)
P = json.load(open(os.path.join(ROOT, "prices.json"), encoding="utf-8"))
M = json.load(open(os.path.join(ROOT, "mappings.json"), encoding="utf-8"))["pins"]
Q = json.load(open(os.path.join(ROOT, "quarantine.json"), encoding="utf-8"))["items"]
for it in Q:
    k = it["ingredient"].lower().strip(); ent = P["ingredients"].get(k, {}).get(it["chain"])
    check("quarantined pin not priced: %s / %s" % (it["ingredient"], it["chain"]), not ent or ent["item_code"] != it["item_code"])
    pin = next((v for n, v in M.items() if n.lower() == k), {}).get(it["chain"])
    check("quarantined pin not in mappings: %s / %s" % (it["ingredient"], it["chain"]), not pin or str(pin["item_code"]) != it["item_code"])
for ch, meta in P["metadata"]["chains"].items():
    n = sum(1 for e in P["ingredients"].values() if ch in e)
    check("priced_count matches entries: " + ch, meta["priced_count"] == n, (meta["priced_count"], n))
check("prices schema version unchanged (app requires 2.1)", str(P["metadata"]["version"]) == "2.1")
check("every priced entry has a mapping pin", all(
    any(n.lower() == k and ch in v for n, v in M.items())
    for k, e in P["ingredients"].items() for ch in e if ch != "ingredient_name"))

# ---- 2. feed pack derivation (osher-style rows) and name tolerance
def item(name, qty, uom, uq="לא ידוע", weighted=False, price="9.90", code="1"):
    return types.SimpleNamespace(item_code=code, name=name, quantity=Decimal(qty), unit_of_measure=uom, unit_qty=uq,
                                 is_weighted=weighted, price=Decimal(price), unit_price=Decimal("0"), manufacturer="", gtin=None)
d = fp.derive_pack(item("שיבולת שועל עבה אינד", "750.00", "100 גרם"))
check("osher-style grams row -> 750 g", d and d["qty"] == 750 and d["unit"] == "g", d)
d = fp.derive_pack(item("גזר", "1.00", "יחידה ", uq="יחידות", weighted=True))
check("osher loose goods -> per kg", d and d["qty"] == 1000 and d["unit"] == "g", d)
d = fp.derive_pack(item("פיתות ברמן 10 יח", "1.00", 'ק"ג'))
check("count in name beats per-kg comparison unit", d and d["qty"] == 10 and d["unit"] == "units", d)
check("promo prefix + truncation accepted", fp.same_product_name("*מבצע* פסטה פרפלה 50", "פסטה פרפלה 500 גרם"))
check("extended name accepted", fp.same_product_name("עוף שלם טרי עטרה הרב", "עוף שלם טרי עטרה"))
check("different product rejected", not fp.same_product_name("עוגיות מיני פריך שקד", "מיני פריך שקדים"))
check("mappings allow preserved (victory) chain", "victory" in fp.PRESERVE_CHAINS and fp.load_mappings(os.path.join(ROOT, "mappings.json")))

# ---- 3. browser: pantry matcher + invariants
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(s, *a): pass
srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
CASES = [  # (name, searchHe, expected staple id or None)
 ("Red Bell Peppers", "", None), ("Bell Peppers", "", None), ("Bulgarian / Feta Salty Cheese", "", None),
 ("Flour Tortilla Wraps", "", None), ("Matzo Meal", "קמח מצה", None), ("Crispy Brown Rice Cakes", "", None),
 ("Red Lentil Protein Pasta", "פסטה", None), ("Soy Sauce & Ginger", "", None), ("Pure Honey & Garlic", "", None),
 ("Butternut Squash", "", None), ("Popcorn Kernels", "", None), ("Cornstarch", "", None), ("Goats Cheese", "", None),
 ("Snap Peas", "", None), ("Sugar Snap Peas", "", None),
 ("Black Pepper", "", "salt_pepper"), ("Sea Salt", "", "salt_pepper"), ("All-Purpose Flour", "", "flour_breadcrumbs"),
 ("Seasoned Breadcrumbs", "", "flour_breadcrumbs"), ("Soy Sauce", "", "soy_sauce"), ("Pure Honey", "", "honey"),
 ("Pure Butter", "", "butter"), ("Fresh Milk 3%", "", "milk"), ("Farm Fresh Eggs", "", "eggs"), ("Rolled Oats (Oatmeal)", "", "oats"),
 ("Whole Grain Brown Rice", "", "brown_rice"), ("Penne Rigate Pasta", "", "pasta"), ("Sweet Corn Kernels", "", "canned_corn"),
 ("Extra Virgin Olive Oil", "", "olive_oil"), ("Raw Sesame Tahini", "", "tahini"), ("Fragrant Basmati Rice", "", "basmati_rice"),
 ("Fresh Garlic Bulbs", "", "garlic_onions"), ("Yellow Onions", "", "garlic_onions"),
 ("Brown / Basmati Rice (אורז מלא / בסמטי)", "", "basmati_rice"),  # documented v9 design choice, unchanged
]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1280, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:%d/index.html" % srv.server_address[1]); pg.wait_for_timeout(2500)
    for name, he, exp in CASES:
        got = pg.evaluate("([n,h])=>matchIngredientToPantryStapleId({name:n,searchHe:h})", [name, he])
        check("pantry match %-40s -> %s" % (name, exp), got == exp, got)
    # every recipe/catalog ingredient: the pantry decision must be identical to v9 EXCEPT the documented false matches
    allowed_changes = {"Red Bell Peppers", "Bell Peppers", "Bulgarian / Feta Salty Cheese", "Flour Tortilla Wraps", "Matzo Meal",
                       "Crispy Brown Rice Cakes", "Red Lentil Protein Pasta", "Soy Sauce & Ginger", "Pure Honey & Garlic"}
    rows = pg.evaluate("RECIPES.flatMap(r => (r.ingredients||[]).map(i => ({r:r.id,n:i.name,q:i.qty,u:String(i.unit||'').toLowerCase(),e:i.qtyEstimate||''})))")
    vague = [x for x in rows if x["u"] in ("set","serving","basket","units","loaf","jar","carton","can","bottle","tub","pack","cloves") and x["n"] not in ("Canned Black Beans","Canned Chickpeas","Canned White Cannellini Beans","Sweet Corn Kernels","Canned Chunk Light Tuna","Flour Tortilla Wraps","Yellow Cheese Slices","Fresh Eggplant","Fresh Zucchini","Sweet Potatoes","Fresh Hummus Tub x") and x["n"] not in ("Farm Fresh Eggs",)]
    check("no vague unit remains for the approved ingredients (user-approved estimates applied)", not [x for x in vague if x["n"] in ("Fresh Champignon Mushrooms","Fresh Cucumbers","Fresh Basil Leaves","Yellow Onions","Red Onions","Fresh Carrots","Fresh Bananas","Fresh Lemons","Red Bell Peppers","Sliced Sandwich Bread","Whole Wheat Bread","Cooking Cream 15%","Basil Pesto Spread","Crushed Canned Tomatoes","Fresh Hummus Tub","Sweet Cherry Tomatoes","Fresh Strawberries","Toasted Pasta Pearls (Ptitim)","Fresh Garlic Bulbs","Raw Sesame Tahini","Paprika","Sweet Paprika","Extra Virgin Olive Oil")], vague)
    check("every converted row carries qtyEstimate provenance (47 rows: 14 placeholders + 14 produce + 18 container + 1 garlic fix)", len([x for x in rows if x["e"]]) == 47, len([x for x in rows if x["e"]]))
    check("garlic data error fixed (no garlic row above 30 g)", not [x for x in rows if x["n"] == "Fresh Garlic Bulbs" and x["u"] == "g" and x["q"] > 30], [x for x in rows if x["n"] == "Fresh Garlic Bulbs"])
    fresh = pg.evaluate("() => PRICE_CHAINS.every(c => state.chainFresh[c])")
    if fresh:
        res = pg.evaluate(open(os.path.join(HERE, "whole_cart_invariants.js")).read())
        check("whole-cart invariants (%d checks, 100 weeks x 6 chains)" % res["checks"], not res["fails"], res["fails"][:5])
    else:
        print("SKIP whole-cart invariants: price files are older than 48 h (the app treats them as stale). Re-run after the workflow refreshes prices.json.")
    check("no page errors", not errs, errs)
print("\nV10 FAILURES: %d" % len(fails)); sys.exit(1 if fails else 0)
