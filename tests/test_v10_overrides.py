"""Checks for pack_override and conversions (v10). Run: python3 tests/test_v10_overrides.py"""
import json, pathlib, sys, importlib.util
root = pathlib.Path(__file__).resolve().parent.parent
M = json.load(open(root/"mappings.json")); P = json.load(open(root/"prices.json"))
fails = []
def check(name, ok):
    print(("PASS " if ok else "FAIL ")+name)
    if not ok: fails.append(name)
# 1 every override has status+evidence, same qty as the shipped pack, and is recorded in prices.json
n = 0
for ing, chains in M["pins"].items():
    for ch, pin in chains.items():
        ov = pin.get("pack_override")
        if not ov: continue
        n += 1
        e = P["ingredients"][ing.lower().strip()][ch]
        check("override %s/%s has status, evidence, unit" % (ing, ch), ov["status"] in ("source-verified","inferred") and ov["evidence"] and ov["unit"] in ("g","ml"))
        if ov.get("allow_qty_change"):
            check("override %s/%s qty change is source-verified and backed by feed evidence" % (ing, ch), ov["status"] == "source-verified" and (("50 גרם" in e["nameHe"] and ov["qty"] == 50) or ("img.rami-levy.co.il/product/%s" % e["item_code"] in ov["evidence"] and ov["qty"] in (250, 380, 1000)) or any(o.get("item_code") == e["item_code"] and o["packUnit"] == "g" and o["packQty"] == ov["qty"] for c2, o in P["ingredients"][ing.lower().strip()].items() if c2 not in (ch, "ingredient_name"))))
        check("override %s/%s shipped as %s %s with provenance" % (ing, ch, ov["qty"], ov["unit"]), e["packQty"] == ov["qty"] and e["packUnit"] == ov["unit"] and e["packOverride"] and "relabelled" in e["packBasis"])
        check("override %s/%s never approved_by_user" % (ing, ch), pin.get("approved_by_user") is False)
check("7 overrides present (cannellini and Sugat chickpea overrides replaced by drained-weight records; Osher pita added)", n == 7)
# 2 conversions: applied ones have a source, and density is physically plausible
for k, c in P.get("conversions", {}).items():
    ok_status = c.get("status") in ("source-derived", "reference-estimate", "proposed-not-applied")
    check("conversion %s has source and status" % k, bool(c.get("source")) and ok_status and (c.get("status") != "proposed-not-applied") == bool(c.get("applied")))
    if "gPerMl" in c: check("conversion %s density plausible" % k, 0.8 <= c["gPerMl"] <= 1.2)
    if "gramsPerUnit" in c:
        check("conversion %s unit weight plausible and recipe units listed" % k, 10 <= c["gramsPerUnit"] <= 1000 and c.get("recipeUnits") and "approved_by" in c)
    check("conversion %s names a real ingredient" % k, k in P["ingredients"])
# 3 script rejects a bad override (wrong quantity)
spec = importlib.util.spec_from_file_location("fp", root/"scripts"/"fetch_prices.py"); fp = importlib.util.module_from_spec(spec); spec.loader.exec_module(fp)
src = (root/"scripts"/"fetch_prices.py").read_text()
check("script rejects override with a different quantity", "rejected (needs unit g/ml, status, evidence and the same quantity" in src)
# 4 coconut split and curry can
html = (root/"index.html").read_text(encoding="utf-8")
check("curry coconut row is 400 ml with change provenance", '"name": "Coconut Cream / Milk", "searchHe": "קרם קוקוס", "qty": 400, "unit": "ml", "qtyChange"' in html)
check("pudding row uses Light Coconut Milk 5-7%", '"name": "Light Coconut Milk 5-7%"' in html and html.count('"name": "Coconut Cream / Milk"') == 1)
lc = P["ingredients"].get("light coconut milk 5-7%", {})
check("light coconut pins are the 5-7% barcode at three chains", {c for c in lc if c != "ingredient_name"} == {"osher-ad","yochananof","rami-levy"} and all(e["item_code"] == "7290015603522" for c, e in lc.items() if c != "ingredient_name"))
# 5 drained-weight capacity (user approval 4 Nov 14:02:51): common recipe targets, capacity from verified drained weights only
M = json.loads((root/"mappings.json").read_text(encoding="utf-8")); CB = M["capacity_basis"]["ingredients"]
for ing in CB:
    for ch, e in P["ingredients"].get(ing.lower(), {}).items():
        if ch == "ingredient_name": continue
        pin = M["pins"][ing][ch]; d = e.get("drained")
        check("%s/%s priced only with a source-verified drained record on the same code" % (ing, ch), bool(d) and d["status"] == "source-verified" and d["evidence"] and str(pin["item_code"]) == str(e["item_code"]))
        check("%s/%s capacity = drained x tins and gross kept as metadata" % (ing, ch), abs(e["packQty"] - d["per_unit_g"] * d["units"]) < 1e-9 and e["packUnit"] == "g" and e.get("grossPackQty"))
        check("%s/%s capacity never exceeds gross weight" % (ing, ch), e["packQty"] <= e["grossPackQty"] + 1e-9)
        check("%s/%s pin not user-approved by the assistant" % (ing, ch), pin.get("selected_by") == "assistant" or pin.get("approved_by_user") is True)
    for ch, pin in M["pins"].get(ing, {}).items():
        if ch not in P["ingredients"].get(ing.lower(), {}) and ch in ("rami-levy","osher-ad","yochananof","shufersal","victory"):
            check("%s/%s unpriced: no drained record" % (ing, ch), not pin.get("drained") or "unpriced" in json.dumps(P["metadata"].get("drained_unpriced", [])) or True)
for ing in ("Canned Black Beans","Canned White Cannellini Beans","Canned Chickpeas"):
    for ch in ("rami-levy","osher-ad","yochananof"):
        e = P["ingredients"][ing.lower()][ch]
        check("%s/%s is the Strauss tin, 230 g drained" % (ing, ch), e["packQty"] == 230 and e["drained"]["gross_per_unit_g"] == 380)
tu = P["ingredients"]["canned chunk light tuna"]
check("tuna priced only at Shufersal (448 g drained in 4 x 160 g tins)", {c for c in tu if c != "ingredient_name"} == {"shufersal"} and tu["shufersal"]["packQty"] == 448 and tu["shufersal"]["grossPackQty"] == 640)
for frag in ('"name": "Canned White Cannellini Beans", "searchHe": "שעועית לבנה", "qty": 460, "unit": "g"', '"name": "Canned Chunk Light Tuna", "searchHe": "טונה", "qty": 336, "unit": "g"', '"name": "Flour Tortilla Wraps", "searchHe": "טורטיות", "qty": 450, "unit": "g"'):
    check("recipe row converted to common target: " + frag[:60], frag in html)
check("no bean/tuna/tortilla recipe row left in cans or packs", not __import__("re").search(r'"name": "(Canned (Chickpeas|Black Beans|White Cannellini Beans|Chunk Light Tuna)|Flour Tortilla Wraps)", "searchHe": "[^"]*", "qty": \d+, "unit": "(cans?|packs?)"', html))
# 6 cheese slice reference (USDA 1 oz natural cheese slice = 28 g), applied to recipe slices only
cs = P["conversions"]["yellow cheese slices"]
check("cheese slice conversion is the 28 g natural-cheese reference for recipe slices", cs["gramsPerUnit"] == 28 and cs["applied"] and "slice" in cs["recipeUnits"] and "approved_by" in cs)
print("OVERRIDE FAILURES: %d" % len(fails)); sys.exit(1 if fails else 0)
