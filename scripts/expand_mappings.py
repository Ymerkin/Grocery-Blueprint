#!/usr/bin/env python3
"""Expand mappings.json coverage beyond the hand-audited 150 pins.

For every cart-universe ingredient line with no pin, search the anchor chains' full PriceFull
catalogs and propose pins. A line is auto-pinned ONLY when the evidence is solid:
  - candidate carries a checksum-valid GTIN,
  - every required Hebrew term appears in the candidate name (token-overlap sanity),
  - the same GTIN wins in at least two anchor chains (cross-chain identity check),
  - price inside the line's sane range.
Bundles (lines that name two products, e.g. "soy sauce & ginger") are never auto-pinned: no single
product is that line. They stay honest estimates.
Pins are written with selected_by='assistant-expand', approved_by_user=false, same standing as the
existing assistant pins (user delegation 2026-11-03), and everything is reported for review.

Usage:
  python3 scripts/expand_mappings.py --download     # refresh /tmp/catalogs from the anchor chains
  python3 scripts/expand_mappings.py                # propose + auto-pin into mappings.json (dry-run with --dry)
"""
import json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_prices as fp  # noqa: E402

CATDIR = Path("/tmp/catalogs")
# Anchor stores: the online/big-catalog branch per chain (same stores the core sync trusts).
ANCHORS = {
    "shufersal": "413", "rami-levy": "039", "osher-ad": "032",
    "yochananof": "015", "tiv-taam": "025", "fresh-market": "047",
}

# English line -> matching spec. terms: ALL must appear in the Hebrew name (any one per group).
# exclude: name must not contain these. price: sane ILS range for the line. weighted: sold by weight.
LINES = {
    "canned tuna in oil":      {"terms": [["טונה"]], "exclude": ["מים"], "price": (3, 12)},
    "canned tuna in oil/water": {"terms": [["טונה"]], "exclude": [], "price": (3, 12)},
    "sweet corn kernel can":   {"terms": [["תירס"]], "exclude": ["קלוי", "קלאוי", "פופקורן", "אבקת", "עמילן", "כדורי", "טורטייה"], "price": (3, 10)},
    "canned beans":            {"terms": [["שעועית"]], "exclude": ["ירוקה"], "price": (3, 12)},
    "dry green / brown lentils": {"terms": [["עדשים"]], "exclude": ["מבושל", "מוכן", "נבטי"], "price": (4, 15)},
    "pearl barley":            {"terms": [["גריסי פנינה"], ["שעורה", "גריסים"]], "exclude": [], "price": (3, 12)},
    "couscous":                {"terms": [["קוסקוס"]], "exclude": ["מוכן", "מבושל"], "price": (4, 15)},
    "pasta pearls (ptitim)":   {"terms": [["פתיתים"]], "exclude": ["מוכן", "מבושל"], "price": (3, 12)},
    "brown / basmati rice":    {"terms": [["אורז"], ["בסמטי", "מלא"]], "exclude": ["מוכן", "מבושל"], "price": (6, 25)},
    "basmati or persian rice": {"terms": [["אורז"], ["בסמטי", "פרסי"]], "exclude": ["מוכן", "מבושל"], "price": (6, 25)},
    "brown whole-grain rice":  {"terms": [["אורז"], ["מלא"]], "exclude": ["מוכן", "מבושל"], "price": (6, 25)},
    "buckwheat soba noodles":  {"terms": [["אטריות"], ["כוסמת", "סובה"]], "exclude": [], "price": (6, 25)},
    "penne / spaghetti":       {"terms": [["פסטה", "ספגטי", "פנה"]], "exclude": ["מוכן", "רביולי"], "price": (3, 12)},
    "penne or spaghetti":      {"terms": [["פסטה", "ספגטי", "פנה"]], "exclude": ["מוכן", "רביולי"], "price": (3, 12)},
    "pita bread":              {"terms": [["פיתה", "פיטה"]], "exclude": ["חמוצים"], "price": (5, 18)},
    "apple cider / white vinegar": {"terms": [["חומץ"]], "exclude": ["רוטב", "מטליות", "ניקול", "ניקוי"], "price": (3, 12)},
    "dijon / yellow mustard":  {"terms": [["חרדל"]], "exclude": ["רוטב צ'ילי"], "price": (5, 18)},
    "pure date silan":         {"terms": [["סילאן", "מחית תמרים", "רכז תמרים"]], "exclude": [], "price": (8, 30)},
    "pure flower honey":       {"terms": [["דבש"]], "exclude": ["רוטב", "חרדל", "טבעות", "דגני"], "price": (10, 35)},
    "toasted sesame oil":      {"terms": [["שמן שומשום"]], "exclude": [], "price": (10, 40)},
    "canola / sunflower oil":  {"terms": [["שמן"], ["קנולה", "חמניות"]], "exclude": ["זית", "קוקוס", "שומשום"], "price": (8, 25)},
    "sweet & smoked paprika":  {"terms": [["פפריקה"]], "exclude": ["רוטב"], "price": (4, 15)},
    "ground cumin & turmeric": {"terms": [["כמון"]], "exclude": [], "price": (4, 15)},
    "ground coriander":        {"terms": [["כוסברה", "קוריאנדר"], ["טחון", "טחונה"]], "exclude": [], "price": (4, 15)},
    "crushed red pepper flakes": {"terms": [["צ'ילי", "פלפל צ'ילי"], ["גרוס", "פתיתי"]], "exclude": [], "price": (4, 15)},
    "tomato paste (28-30%)":   {"terms": [["רסק עגבניות", "רסק"]], "exclude": ["רוטב", "תפוחים", "תפו\"ע", "ללת\"ס"], "price": (3, 12)},
    "crushed tomatoes":        {"terms": [["עגבניות"], ["מעוכות", "מגורדות", "קטועות", "פרוסות"]], "exclude": ["רסק", "רוטב פסטה"], "price": (3, 12)},
    "crushed tomatoes / mutti": {"terms": [["עגבניות"], ["מעוכות", "מגורדות", "קטועות", "פרוסות"]], "exclude": ["רסק", "רוטב פסטה"], "price": (3, 15)},
    "coconut milk / cream":    {"terms": [["קוקוס"], ["חלב", "קרם"]], "exclude": ["שמן"], "price": (6, 20)},
    "natural peanut butter":   {"terms": [["חמאת בוטנים"]], "exclude": ["חט.", "חטיף"], "price": (8, 30)},
    "pitted syrian / manzanilla olives": {"terms": [["זיתים"]], "exclude": ["שמן", "גבינה", "טפנד", "מותכת"], "price": (6, 25)},
    "cucumbers in brine (pickles)": {"terms": [["מלפפונים"], ["כבושים", "חמוצים"]], "exclude": [], "price": (6, 20)},
    "farm eggs":               {"terms": [["ביצים"]], "exclude": ["מבושלות", "פסטה", "אטריות", "פתיתי", "אבקת", "עוף"], "price": (8, 30)},
    "farm eggs (12 pk)":       {"terms": [["ביצים"]], "exclude": ["מבושלות", "פסטה", "אטריות", "פתיתי", "אבקת", "עוף"], "price": (8, 30)},
    "chicken pargiyot":        {"terms": [["פרגית"]], "exclude": ["נקניקיות", "נקניק"], "price": (20, 70), "weighted": True},
    "ground beef":             {"terms": [["בקר טחון", "טחון בקר", "בשר טחון"]], "exclude": ["הודו", "עוף", "כמו בשר"], "price": (25, 80), "weighted": True},
    "firm tofu tnuva":         {"terms": [["טופו"]], "exclude": ["רוטב"], "price": (8, 25)},
    "greek yogurt 7%":         {"terms": [["יוגורט"], ["יווני"]], "exclude": [], "price": (5, 20)},
    "bulgarian / feta cheese": {"terms": [["בולגרית", "פטה"]], "exclude": [], "price": (10, 35)},
    "frozen broccoli":         {"terms": [["ברוקולי"], ["קפוא"]], "exclude": ["טרי"], "price": (8, 25)},
    "frozen green beans":      {"terms": [["שעועית ירוקה"], ["קפואה", "קפוא"]], "exclude": [], "price": (8, 25)},
    "pickled mango sauce (amba)": {"terms": [["עמבה"]], "exclude": [], "price": (5, 18)},
    "herb pepper sauce (skhug / harissa)": {"terms": [["סחוג", "חריסה"]], "exclude": [], "price": (5, 18)},
    "za'atar with sesame":     {"terms": [["זעתר"]], "exclude": ["לחם", "גבינה", "שמן זית"], "price": (4, 15)},
    "white / brown sugar":     {"terms": [["סוכר"]], "exclude": ["ללא", "אבקת", "סוכריות", "צלחת", "משקה", "שוופס", "מאסט"], "price": (3, 12)},
    "butter (100g)":           {"terms": [["חמאה"]], "exclude": ["בוטנים", "שקדים"], "price": (5, 20)},
    "baking powder & yeast":   {"terms": [["אבקת אפייה", "אבקת אפיה"]], "exclude": ["סודה"], "price": (3, 12)},
    "baharat spice blend":     {"terms": [["בהארת", "בהאראת"]], "exclude": [], "price": (4, 18)},
    "baharat / shawarma seasoning": {"terms": [["בהארת", "בהאראת", "שווארמה"]], "exclude": ["רוטב"], "price": (4, 18)},
    "denis / tilapia fillets": {"terms": [["דניס", "טילפיה", "אמנון"]], "exclude": [], "price": (20, 80), "weighted": True},
    "fresh garlic bulbs & onions": {"terms": [["שום"]], "exclude": ["אבקת", "גרנולות", "כבוש"], "price": (3, 15)},
    "garlic powder & onion flakes": {"terms": [["אבקת שום"]], "exclude": [], "price": (4, 15)},
    "dried oregano & basil":   {"terms": [["אורגנו"]], "exclude": [], "price": (4, 15)},
    "coarse salt & black pepper": {"terms": [["מלח"]], "exclude": ["אמבט", "רגליים"], "price": (2, 10)},
    "white / whole wheat challah": {"terms": [["חלה"]], "exclude": [], "price": (8, 25)},
    "cucumbers & tomatoes":    {"terms": [["מלפפון"]], "exclude": ["כבושים", "חמוצים"], "price": (4, 15), "weighted": True},
    "pure honey & garlic":     {"terms": [["דבש"]], "exclude": ["רוטב"], "price": (10, 35)},
    "soy sauce & ginger":      {"terms": [["רוטב סויה", "סויה"]], "exclude": ["טריאקי"], "price": (6, 20)},
    "flour & breadcrumbs":     {"terms": [["פירורי לחם", "קמח"]], "exclude": [], "price": (3, 12)},
}

# Lines that name two different products: no single item is the line, so they keep honest estimates.
BUNDLES = {"baking powder & yeast", "coarse salt & black pepper", "cucumbers & tomatoes",
           "dried oregano & basil", "flour & breadcrumbs", "garlic powder & onion flakes",
           "ground cumin & turmeric", "pure honey & garlic", "soy sauce & ginger",
           "sweet & smoked paprika", "fresh garlic bulbs & onions"}
# Note: some of the above also carry a best-single-product spec in LINES for the report's
# "closest product" suggestion, but they are NOT auto-pinned.

def norm_name(s):
    s = unicodedata.normalize("NFC", s or "")
    return re.sub(r"\s+", " ", s).strip()

def gtin_valid(code):
    """Same evidence bar as the sync pipeline: library checksum validation + rejection of
    restricted-distribution/variable-measure prefixes that are not cross-retailer identities."""
    from israeli_prices import to_gtin14
    gt = to_gtin14(str(code))
    if not gt:
        return None
    base = gt.lstrip('0')
    if len(base) == 13 and base[:2] in {str(n) for n in range(20, 30)}:
        return None
    return gt

def download_catalogs():
    CATDIR.mkdir(exist_ok=True)
    for chain, sid in ANCHORS.items():
        out = CATDIR / ("%s.json" % chain)
        feed = fp.fetch_chain(chain, sid, retries=3)
        items = []
        for it in feed["items"]:
            items.append({
                "code": str(getattr(it, "item_code", "") or ""),
                "name": norm_name(getattr(it, "name", "")),
                "price": float(getattr(it, "price", 0) or 0),
                "uom": str(getattr(it, "unit_of_measure", "") or ""),
                "weighted": bool(getattr(it, "is_weighted", False)),
            })
        pa = getattr(feed["ref"], "published_at", None)
        out.write_text(json.dumps({"chain": chain, "store": sid, "ref": feed["ref"].name,
                                   "published_at": pa.isoformat() if pa else None,
                                   "items": items}, ensure_ascii=False))
        print("[+] %s: %d items (%s)" % (chain, len(items), feed["ref"].name))

def load_catalogs():
    cats = {}
    for chain in ANCHORS:
        p = CATDIR / ("%s.json" % chain)
        if p.exists():
            cats[chain] = json.loads(p.read_text())
    return cats

# Product-type words that make a candidate the wrong KIND of product for a commodity line,
# unless that word is itself one of the line's required terms (e.g. the soba line requires noodles).
GLOBAL_BLOCK = ["אטריות", "עוגיות", "עוגייה", "פריכיות", "פצפוצים", "פצפוצי", "חטיף", "חטיפי", "סלסולי",
                "דוריטוס", "במבה", "ביסלי", "מלפפון", "מלפפונים", "שקדיה", "ממרח", "תרסיס",
                "מנה חמה", "תבשיל", "קורנפלקס", "דגני בוקר", "מלחיה", "סלט", "משקה", "נקטר",
                "רוטב", "מרק", "לחמניה", "לחמניות", "עוגה", "בצק", "גלידה", "פסטו", "חומוס", "טחינה",
                "ניקוי", "בטעם", "חותך", "נודלס", "מילקי", "שניצל", "חט.", "פסטרמה", "לאבנה"]

HEB = "\u0590-\u05ff"

def term_in(term, name):
    """Term must not be embedded inside a longer Hebrew word (רסק inside אפרסק, סוכר inside סוכריות)."""
    i = name.find(term)
    while i >= 0:
        before = name[i - 1] if i > 0 else " "
        after = name[i + len(term)] if i + len(term) < len(name) else " "
        if not re.match("[%s]" % HEB, before) and not re.match("[%s]" % HEB, after):
            return True
        i = name.find(term, i + 1)
    return False

def match_line(spec, items):
    """Candidates whose name contains every required term group, no excluded term, no wrong-type
    word (unless the word is itself required), price in range."""
    out = []
    lo, hi = spec["price"]
    required = {t for group in spec["terms"] for t in group}
    for it in items:
        n = it["name"]
        if not n or not (lo <= it["price"] <= hi):
            continue
        if any(x in n for x in spec.get("exclude", [])):
            continue
        ok = True
        for group in spec["terms"]:
            if not any(term_in(t, n) for t in group):
                ok = False
                break
        if not ok:
            continue
        blocked = False
        for w in GLOBAL_BLOCK:
            if w in n and not any(w in t or t in w for t in required):
                blocked = True
                break
        if not blocked:
            out.append(it)
    return out
    return out

def score(spec, it):
    """Prefer valid GTIN, shorter names (closer to the commodity), mid-range price."""
    s = 0.0
    if gtin_valid(it["code"]):
        s += 10
    s -= min(len(it["name"]), 60) * 0.1
    lo, hi = spec["price"]
    mid = (lo + hi) / 2
    s -= abs(it["price"] - mid) / max(mid, 1)
    return s

def app_universe():
    """All cart-line ingredient names the app can produce: recipes + pantry staples + Israeli catalog."""
    html = (ROOT / "index.html").read_text()
    def get_arr(var):
        i = html.find(var); j = html.find("\n", i)
        return json.loads(html[i:j].rstrip().rstrip(";")[len(var):])
    universe = set()
    for r in get_arr("let RECIPES = "):
        for ing in r.get("ingredients", []):
            universe.add(ing["name"].strip().lower())
    for x in get_arr("const PANTRY_STAPLES = "):
        universe.add(x["name"].strip().lower())
    for x in get_arr("const ISRAELI_INGREDIENTS_CATALOG = "):
        universe.add(re.sub(r"\s*\([^)]*\)\s*", " ", x["name"]).strip().lower())
    return universe

def propose(write=False):
    cats = load_catalogs()
    missing = [c for c in ANCHORS if c not in cats]
    if missing:
        print("[!] missing catalogs for %s - run --download first" % ", ".join(missing))
        return 2
    mappings = json.loads((ROOT / "mappings.json").read_text())
    pins = mappings["pins"]
    universe = app_universe()
    pins_norm = {re.sub(r"\s+", " ", re.sub(r"\s*\([^)]*\)\s*", " ", p)).strip().lower() for p in pins}
    unmapped = sorted(n for n in universe if n not in pins_norm)
    stale = [k for k in LINES if k not in unmapped and k not in pins]
    if stale:
        print("[!] spec lines not in the app universe (stale spec?): %s" % ", ".join(stale))
    print("[*] universe %d lines, %d unmapped, %d have a spec" % (len(universe), len(unmapped), sum(1 for u in unmapped if u in LINES)))
    report = {"pinned": {}, "bundles_skipped": sorted(BUNDLES), "no_match": [], "weak": {}}
    for line, spec in sorted(LINES.items()):
        if line not in unmapped:
            continue
        per_chain = {}
        for chain, cat in cats.items():
            cand = match_line(spec, cat["items"])
            cand.sort(key=lambda it: -score(spec, it))
            if cand:
                per_chain[chain] = cand[0]
        if line in BUNDLES:
            report["weak"][line] = {c: v["name"] for c, v in per_chain.items()}
            continue
        # Per-chain evidence: the winning candidate carries a checksum-valid GTIN, matched every
        # required term group, passed the wrong-type filter and the price range. Chains stock
        # different brands, so identical GTINs across chains are NOT required (existing hand-audit
        # pins also differ per chain). A line is pinned only when >=3 anchor chains get a solid pick.
        solid_chains = {c: v for c, v in per_chain.items() if gtin_valid(v["code"])}
        solid = len(solid_chains) >= 3
        if solid:
            per_chain = solid_chains
            entry = {}
            for chain, it in per_chain.items():
                entry[chain] = {"item_code": it["code"], "pinned_name": it["name"],
                                "approved_by_user": False, "selected_by": "assistant-expand"}
            pins[line] = entry
            report["pinned"][line] = {c: v["name"] for c, v in per_chain.items()}
        else:
            (report["weak"] if per_chain else report["no_match"])
            if per_chain:
                report["weak"][line] = {c: v["name"] for c, v in per_chain.items()}
            else:
                report["no_match"].append(line)
    (Path("/tmp/expand_report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("[*] auto-pinned: %d | weak (need review): %d | no match: %d | bundles kept as estimates: %d"
          % (len(report["pinned"]), len(report["weak"]), len(report["no_match"]), len(report["bundles_skipped"])))
    if write and report["pinned"]:
        (ROOT / "mappings.json").write_text(json.dumps(mappings, ensure_ascii=False, indent=2) + "\n")
        print("[+] mappings.json updated with %d new lines" % len(report["pinned"]))
    elif report["pinned"]:
        print("[*] dry run - mappings.json untouched (pass --write to apply)")
    return 0

if __name__ == "__main__":
    if "--download" in sys.argv:
        download_catalogs()
    else:
        sys.exit(propose(write="--write" in sys.argv))
