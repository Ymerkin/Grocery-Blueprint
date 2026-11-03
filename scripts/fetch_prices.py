#!/usr/bin/env python3
"""
scripts/fetch_prices.py - Grocery Blueprint price sync (israeli-prices 0.2.0).

What it does
  1. For each chain (Shufersal store 413, Rami Levy store 039) lists PriceFull files with
     list_files(chain, FileType.PRICE_FULL, store_id=..., limit=...), picks the newest one by the
     portal's own published_at, downloads THAT FileRef with adapter.download(ref) and parses the
     same bytes with parse(). The recorded filename / published_at come from that FileRef, so the
     citation is the file that was actually read. Nothing else is ever used for freshness.
  2. Writes mapping_candidates.json: real products from the parsed feed (item_code, gtin, Hebrew
     name, manufacturer, derived pack size, price, flags). It never pins anything.
  3. Prices ingredients pinned in mappings.json with "approved_by_user": true (user-confirmed) or
     "selected_by": "assistant" (assistant-selected under the user's explicit delegation; those
     entries carry selectionSource "assistant" in prices.json). Pins whose code
     is missing, whose name changed, or whose pack size cannot be derived fail the run.
  4. Writes prices.json (schema 2.1, see DATA_CONTRACT.md) atomically after validation.

Exit codes: 0 ok, 1 download/provenance failure, 2 pin validation failure, 3 bad inputs.
On any failure the previous prices.json is left untouched.
"""
import argparse, hashlib, json, os, re, sys, tempfile, time
from datetime import datetime, timezone
from decimal import Decimal

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPINGS_FILE = os.path.join(ROOT_DIR, "mappings.json")
INGREDIENTS_FILE = os.path.join(ROOT_DIR, "all_unique_ingredients.json")
PRICES_FILE = os.path.join(ROOT_DIR, "prices.json")
CANDIDATES_FILE = os.path.join(ROOT_DIR, "mapping_candidates.json")

SCHEMA_VERSION = "2.1"
FEED_TZ = "Asia/Jerusalem"   # portal timestamps are naive; assumed Israel local time (documented)
CHAINS = {
    "shufersal": {"store_id": "413", "store_name": "שופרסל ONLINE"},
    "rami-levy": {"store_id": "039", "store_name": "מרלוג אינטרנט"},
}
LIST_LIMIT = 20

HEBREW_SEARCH_KEYWORDS = {
    "fresh chicken breast": ["חזה עוף", "שניצל עוף"],
    "fresh ground beef": ["בקר טחון", "טחון בקר"],
    "lean ground turkey": ["הודו טחון", "הודו אדום טחון"],
    "chicken thighs & drumsticks": ["כרעיים"],
    "chicken drumsticks": ["שוקיים"],
    "boneless chicken thighs (pargiyot)": ["פרגית", "פרגיות", "סטייק פרגית"],
    "whole fresh chicken": ["עוף שלם טרי", "עוף שלם"],
    "chicken breast strips": ["חזה עוף", "רצועות עוף"],
    "beef stew chuck cubes": ["קדירה", "גולאש", "בקר לקדירה", "כתף בקר"],
    "smoked turkey breast slices": ["פסטרמה הודו", "פסטרמה"],
    "beef pastrami slices": ["פסטרמה בקר", "פסטרמה כתף"],
    "fresh chicken livers": ["כבד עוף", "כבדי עוף"],
    "fresh salmon fillet": ["סלמון טרי", "פילה סלמון"],
    "tilapia fillets": ["אמנון", "פילה אמנון", "מושט"],
    "fresh denis (sea bream) fillets": ["דניס", "פילה דניס"],
    "fresh denis or nile perch fillets": ["דניס", "נסיכת הנילוס", "אמנון"],
    "cod / white fish fillets": ["קוד", "פילה קוד", "בקלה"],
    "sea bass fillets": ["לברק", "פילה לברק"],
    "smoked salmon slices": ["סלמון מעושן"],
    "canned chunk light tuna": ["טונה", "נתחי טונה"],
    "firm tofu": ["טופו", "טופו קדיתא"],
    "edamame (green soybeans)": ["אדממה", "פולי סויה"],
    "frozen broccoli florets": ["ברוקולי", "פרחי ברוקולי"],
    "cut green beans": ["שעועית ירוקה", "שעועית עדינה"],
    "frozen cut green beans": ["שעועית ירוקה חתוכה", "שעועית עדינה"],
    "frozen sweet green peas": ["אפונה עדינה", "אפונה ירוקה"],
    "sweet potatoes": ["בטטה", "בטטות"],
    "potatoes": ["תפוח אדמה", "תפוחי אדמה"],
    "fresh zucchini": ["קישוא", "זוקיני"],
    "fresh cucumbers": ["מלפפון", "מלפפונים"],
    "fresh tomatoes": ["עגבניה", "עגבניות"],
    "sweet cherry tomatoes": ["עגבניות שרי", "שרי"],
    "fresh carrots": ["גזר"],
    "yellow onions": ["בצל יבש", "בצל צהוב", "בצל"],
    "red onions": ["בצל סגול", "בצל אדום"],
    "red bell peppers": ["פלפל אדום", "גמבה"],
    "fresh baby spinach": ["תרד", "עלי תרד", "בייבי תרד"],
    "fresh eggplant": ["חציל", "חצילים"],
    "fresh cauliflower head": ["כרובית", "פרחי כרובית"],
    "crisp romaine lettuce": ["חסה", "חסה ערבית", "חסה רומית"],
    "fresh champignon mushrooms": ["פטריות שמפיניון", "שמפיניון"],
    "fresh green asparagus": ["אספרגוס"],
    "ripe haas avocado": ["אבוקדו", "האס"],
    "farm fresh eggs": ["ביצים", "ביצי", "ביצה"],
    "fresh milk 3%": ["חלב 3%", "חלב טרי 3%"],
    "pure butter": ["חמאה", "חמאת"],
    "cooking cream 15%": ["שמנת לבישול 15%", "שמנת לבישול"],
    "cottage cheese 5%": ["קוטג' 5%", "קוטג 5%"],
    "yellow cheese slices": ["גבינה צהובה", "עמק", "גלבוע"],
    "bulgarian / feta salty cheese": ["בולגרית", "גבינה בולגרית", "פטה"],
    "greek strained yogurt": ["יוגורט יווני", "יוגורט"],
    "fresh pita bread pockets": ["פיתות", "פיתה"],
    "whole wheat bread": ["לחם חיטה מלאה", "לחם מלא"],
    "flour tortilla wraps": ["טורטיות", "טורטיה"],
    "fragrant basmati rice": ["אורז בסמטי", "בסמטי"],
    "whole grain brown rice": ["אורז מלא"],
    "fluffy jasmine rice": ["אורז יסמין", "יסמין"],
    "white quinoa": ["קינואה", "קינואה לבנה"],
    "rolled oats (oatmeal)": ["שיבולת שועל", "קוואקר"],
    "penne rigate pasta": ["פנה", "פסטה פנה"],
    "classic spaghetti pasta": ["ספגטי", "פסטה ספגטי"],
    "toasted pasta pearls (ptitim)": ["פתיתים", "פתיתי"],
    "quick fluffy couscous": ["קוסקוס"],
    "canned chickpeas": ["גרגירי חומוס", "חומוס גרגירים"],
    "canned black beans": ["שעועית שחורה"],
    "canned red kidney beans": ["שעועית אדומה"],
    "canned white cannellini beans": ["שעועית לבנה"],
    "sweet corn kernels": ["גרעיני תירס", "תירס"],
    "crushed canned tomatoes": ["עגבניות מרוסקות", "עגבניות חתוכות", "פולפה"],
    "pickled cucumbers in brine": ["מלפפונים חמוצים", "חמוצים"],
    "creamy natural peanut butter": ["חמאת בוטנים טבעית", "חמאת בוטנים"],
    "extra virgin olive oil": ["שמן זית כתית מעולה", "שמן זית"],
    "pure date syrup (silan)": ["סילאן", "סילאן תמרים"],
    "raw sesame tahini": ["טחינה גולמית", "טחינה"],
    "soy sauce": ["רוטב סויה", "סויה"],
    "pure honey": ["דבש טהור", "דבש"],
    "seasoned breadcrumbs": ["פירורי לחם"],
    "raw walnuts": ["אגוזי מלך", "אגוז מלך"],
    "raw whole almonds": ["שקדים", "שקד טבעי"],
    "all-purpose flour": ["קמח לבן", "קמח חיטה"],
    "bell peppers": ["פלפל גמבה", "פלפל צבעוני", "גמבה"],
    "buckwheat soba noodles": ["אטריות סובה", "סובה"],
    "burger buns": ["לחמניות המבורגר", "לחמניות להמבורגר"],
    "canned beans": ["שעועית משומרת", "שעועית בהירה", "שעועית"],
    "chickpea falafel mix": ["תערובת לפלאפל", "פלאפל"],
    "coconut cream / milk": ["קרם קוקוס", "חלב קוקוס"],
    "cooked vacuum-packed beets": ["סלק מבושל", "סלק אפוי"],
    "cream cheese spread": ["גבינת שמנת", "גבינת שמנת למריחה"],
    "crisp fresh apples": ["תפוח עץ", "תפוחי עץ", "תפוח גאלה", "תפוח גרני"],
    "crisp lettuce hearts": ["לב חסה", "לבבות חסה", "חסה"],
    "dry brown lentils": ["עדשים חומות", "עדשים"],
    "dry green lentils": ["עדשים ירוקות", "עדשים"],
    "dry red lentils": ["עדשים אדומות", "עדשים כתומות", "עדשים"],
    "egg stir-fry noodles": ["אטריות ביצים", "אטריות"],
    "farfalle (bowtie) pasta": ["פרפלה", "פפיונים"],
    "feta cheese": ["גבינת פטה", "פטה"],
    "fettuccine pasta": ["פטוצ'יני", "פטוצ'ין", "פטוצינה"],
    "fresh bananas": ["בננה", "בננות"],
    "fresh basil leaves": ["בזיליקום"],
    "fresh celery": ["סלרי", "כרפס"],
    "fresh chives": ["עירית"],
    "fresh dill": ["שמיר"],
    "fresh garlic bulbs": ["שום"],
    "fresh hummus tub": ["חומוס"],
    "fresh lemons": ["לימון", "לימונים"],
    "fresh mango": ["מנגו"],
    "fresh mushrooms": ["פטריות"],
    "fresh parsley": ["פטרוזיליה"],
    "fresh ricotta cheese": ["ריקוטה"],
    "fresh strawberries": ["תות", "תותים"],
    "fresh white cabbage": ["כרוב לבן", "כרוב"],
    "goat cheese log": ["גבינת עזים", "עזים"],
    "grated parmesan cheese": ["פרמזן"],
    "ground cinnamon": ["קינמון טחון", "קינמון"],
    "ground cumin": ["כמון טחון", "כמון"],
    "ground turmeric": ["כורכום"],
    "halloumi grilling cheese": ["חלומי", "הלומי"],
    "jumbo pasta shells": ["קונכיות", "קונכיות ענק"],
    "labneh yogurt cheese": ["לבנה", "לאבנה"],
    "mayonnaise": ["מיונז"],
    "medjool sweet dates": ["תמרים מג'הול", "מג'הול", "תמרי מג'הול"],
    "mozzarella cheese": ["מוצרלה"],
    "natural almond butter": ["חמאת שקדים"],
    "paprika": ["פפריקה"],
    "sweet paprika": ["פפריקה מתוקה", "פפריקה"],
    "pitted kalamata olives": ["זיתי קלמטה", "קלמטה"],
    "potato gnocchi": ["ניוקי"],
    "ready falafel patties": ["כדורי פלאפל", "פלאפל"],
    "ready-to-eat creamy hummus": ["חומוס"],
    "rice vermicelli noodles": ["אטריות אורז", "ורמיצ'לי"],
    "sesame bagels": ["בייגל"],
    "shelled roasted pistachios": ["פיסטוק"],
    "sliced sandwich bread": ["לחם פרוס", "לחם אחיד פרוס"],
    "soft white cheese 5%": ["גבינה לבנה 5%", "גבינה לבנה"],
    "sushi short grain rice": ["אורז לסושי", "אורז סושי"],
    "white rice": ["אורז לבן", "אורז פרסי", "אורז"],
    "whole grain granola": ["גרנולה"],
    "za'atar herb blend": ["זעתר"],
    "matzo meal": ["קמח מצה"],
    "fresh strawberries": ["תות שדה", "תותים"],
    "fresh or frozen blueberries": ["אוכמניות"],
    "fresh or ground ginger": ["ג'ינג'ר", "שורש גינגר", "גינגר"],
    "fresh sweet challah": ["חלה מתוקה"],
    "artisan sourdough loaf": ["לחם מחמצת", "מחמצת"],
    "caraway rye bread": ["לחם שיפון"],
    "crispy brown rice cakes": ["פריכיות אורז", "פריכונים"],
    "crunchy garlic croutons": ["קרוטונים"],
    "basil pesto spread": ["פסטו"],
    "shawarma seasoning": ["תבלין שווארמה", "תבלין לשווארמה"],
    "flaky cheese bourekas": ["בורקס גבינה"],
    "red lentil protein pasta": ["פסטה עדשים אדומות"],
    "frozen peas & diced carrots": ["אפונה וגזר"],
    "leek or yellow onion": ["כרישה", "לוף", "פרסה"],
    "chia seeds": ["צ'יה", "זרעי צ'יה"]
}


class FeedError(Exception):
    """Download / provenance failure (exit 1)."""


class PinError(Exception):
    """Pin validation failure (exit 2)."""


def norm_text(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%]", "", str(t or ""))).strip()


def dnum(v):
    if v is None:
        return None
    try:
        return float(Decimal(str(v)))
    except Exception:
        return None


def iso_with_tz(dt):
    """Attach the documented feed timezone to a naive FileRef.published_at."""
    from zoneinfo import ZoneInfo
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(FEED_TZ))
    return dt.isoformat()


# ---------------------------------------------------------------- download

def select_ref(refs, store_id):
    ok = [r for r in refs
          if getattr(r, "published_at", None) and getattr(r, "name", None)
          and str(getattr(r, "store_id", "")).lstrip("0") == store_id.lstrip("0")
          and "pricefull" in r.name.lower() and "promo" not in r.name.lower()]
    if not ok:
        raise FeedError("no PriceFull FileRef with name + published_at for store %s (listing had %d refs)" % (store_id, len(refs)))
    ok.sort(key=lambda r: r.published_at, reverse=True)
    return ok[0]


def fetch_chain(chain, store_id, retries=3):
    """Returns dict(ref, items, sha256, retrieved_at). Same FileRef supplies bytes AND citation."""
    from israeli_prices import FileType, get_adapter, list_files, parse
    last = None
    for attempt in range(1, retries + 1):
        try:
            refs = list_files(chain, file_type=FileType.PRICE_FULL, store_id=store_id, limit=LIST_LIMIT)
            ref = select_ref(refs, store_id)
            data = get_adapter(chain).download(ref)
            pf = parse(data)
            if not hasattr(pf, "items") or not pf.items:
                raise FeedError("parsed file for %s has no items" % ref.name)
            if str(getattr(pf, "store_id", "")).lstrip("0") != store_id.lstrip("0"):
                raise FeedError("parsed store_id %r != requested %s (%s)" % (getattr(pf, "store_id", None), store_id, ref.name))
            raw = data if isinstance(data, (bytes, bytearray)) else str(data).encode()
            return {"ref": ref, "items": pf.items, "sha256": hashlib.sha256(raw).hexdigest(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:  # noqa
            last = e
            print("[!] %s attempt %d/%d failed: %s" % (chain, attempt, retries, e), file=sys.stderr)
            if attempt < retries:
                time.sleep(attempt * 5)
    raise FeedError("%s store %s: %s" % (chain, store_id, last))


# ---------------------------------------------------------------- pack size

UOM = {"גרם": ("g", 1), "גר": ("g", 1), 'ק"ג': ("g", 1000), "קג": ("g", 1000), "ק''ג": ("g", 1000),
       'מ"ל': ("ml", 1), "מל": ("ml", 1), "מ'ל": ("ml", 1), "ליטר": ("ml", 1000), "ל'": ("ml", 1000),
       "יח'": ("units", 1), "יח": ("units", 1), "יחידה": ("units", 1), "יחידות": ("units", 1), "מטר": ("m", 1),
       "קילוגרם": ("g", 1000), "מיליליטר": ("ml", 1), "מטרים": ("m", 1)}
NAME_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ק\"ג|קג|גרם|גר'|גר|מ\"ל|מ'ל|מל|ליטר|ל')(?![\u0590-\u05ff])")
NAME_COUNT = re.compile(r"(\d+)\s*(?:יח'|יח|יחידות)")


def parse_uom(label):
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(.*?)\s*$", str(label or ""))
    if not m or m.group(2) not in UOM:
        return None
    unit, mult = UOM[m.group(2)]
    return float(m.group(1)) * mult, unit


def name_size(name):
    """First explicit size in the product name, in base units, or None."""
    best = None
    for num, lab in NAME_SIZE.findall(name or ""):
        unit, mult = UOM[lab.replace("גר'", "גר")]
        val = float(num.replace(",", ".")) * mult
        best = (val, unit) if best is None else best
    return best


def derive_pack(item):
    """Pack size from feed data. Returns dict(qty, unit, basis, flags) or None when not derivable.
    Primary source: the feed's own quantity + unit_qty fields (e.g. 700 / גרם). These are cross-checked
    against a size written in the product name. Disagreement means not derivable (never guessed).
    NOTE: unit_price is not used: in the Rami 039 sample inspected it equalled price/100 whatever the pack size."""
    flags = []
    if getattr(item, "is_weighted", False):
        uom = parse_uom(item.unit_of_measure)
        if uom and uom == (1000.0, "g"):
            return {"qty": 1000.0, "unit": "g", "basis": "sold loose by weight, price per kg", "flags": flags}
        return None
    uq = UOM.get(str(item.unit_qty or "").strip())
    q = dnum(item.quantity)
    structured = (q * uq[1], uq[0]) if uq and q and q > 0 else None
    nm = name_size(item.name)
    cnt = NAME_COUNT.search(item.name or "")
    if structured and structured[1] == "units" or (not structured and cnt):
        if cnt:
            return {"qty": float(cnt.group(1)), "unit": "units", "basis": "count in product name", "flags": flags}
        if structured:
            flags.append("count not stated, assumed %g unit(s)" % structured[0])
            return {"qty": structured[0], "unit": "units", "basis": "feed quantity", "flags": flags}
        return None
    if structured and nm and structured[1] == nm[1]:
        if abs(structured[0] - nm[0]) <= 0.01 * nm[0]:
            return {"qty": structured[0], "unit": structured[1], "basis": "feed quantity and product name agree", "flags": flags}
        flags.append("feed quantity %g%s disagrees with name size %g%s" % (structured[0], structured[1], nm[0], nm[1]))
        return None
    if structured and structured[1] in ("g", "ml"):
        flags.append("size from feed quantity only (not in name)")
        return {"qty": structured[0], "unit": structured[1], "basis": "feed quantity", "flags": flags}
    if nm:
        flags.append("size from product name only")
        return {"qty": nm[0], "unit": nm[1], "basis": "product name", "flags": flags}
    return None


def convert_recipe_qty(qty, r_unit, p_unit):
    r, p = str(r_unit).lower().strip(), str(p_unit).lower().strip()
    if r == p:
        return float(qty)
    w = {"g": 1, "gram": 1, "grams": 1, "kg": 1000}
    v = {"ml": 1, "l": 1000, "liter": 1000, "tbsp": 15, "tsp": 5, "cup": 240}
    c = {"unit", "units", "item", "items", "egg", "eggs", "clove", "cloves"}
    if r in w and p in w:
        return float(qty) * w[r] / w[p]
    if r in v and p in v:
        return float(qty) * v[r] / v[p]
    if r in c and p in c:
        return float(qty)
    return None


# ---------------------------------------------------------------- candidates

VARIANT_WORDS = {"קפוא": "frozen", "קפואה": "frozen", "קפואים": "frozen", "מעושן": "smoked", "משומר": "canned/preserved",
                 "מבושל": "cooked", "יבש": "dry", "אורגני": "organic", "ללא גלוטן": "gluten free", "פרימיום": "premium"}


def item_view(it):
    pk = derive_pack(it)
    flags = list(pk["flags"]) if pk else ["pack size not derivable from feed"]
    variants = sorted({v for k, v in VARIANT_WORDS.items() if k in (it.name or "")})
    return {
        "item_code": str(it.item_code), "gtin": getattr(it, "gtin", None) or None,
        "name_he": (it.name or "").strip(), "manufacturer": (it.manufacturer or "").strip() or None,
        "price": dnum(it.price), "unit_price": dnum(it.unit_price), "unit_of_measure": it.unit_of_measure,
        "is_weighted": bool(it.is_weighted),
        "pack_qty": pk["qty"] if pk else None, "pack_unit": pk["unit"] if pk else None,
        "pack_basis": pk["basis"] if pk else None, "variant_flags": variants, "flags": flags,
    }


def candidates_for(ing, items, per_ing=12):
    kws = HEBREW_SEARCH_KEYWORDS.get(ing.lower().strip())
    if not kws:
        return None  # no search terms: reported as "no search terms", never guessed
    scored = []
    for it in items:
        nm = it.name or ""
        for rank, kw in enumerate(kws):
            if kw in nm:
                scored.append((rank, 1 if not derive_pack(it) else 0, len(nm), it))
                break
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [item_view(t[3]) for t in scored[:per_ing]]


def build_candidates(feeds, ingredients):
    out = {"schema": "grocery-blueprint-candidates/1",
           "note": "Real products from the downloaded feeds. NOTHING here is pinned or priced. "
                   "To use one, copy its item_code and name_he into mappings.json with approved_by_user true.",
           "sources": {}, "ingredients": {}}
    for chain, f in feeds.items():
        out["sources"][chain] = {"source_file": f["ref"].name, "published_at": iso_with_tz(f["ref"].published_at),
                                 "retrieved_at": f["retrieved_at"], "sha256": f["sha256"], "item_count": len(f["items"])}
    for ing in ingredients:
        out["ingredients"][ing] = {}
        for chain, f in feeds.items():
            out["ingredients"][ing][chain] = candidates_for(ing, f["items"])
    return out


# ---------------------------------------------------------------- pricing

def load_mappings(path=MAPPINGS_FILE):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != "grocery-blueprint-mappings/1" or not isinstance(data.get("pins"), dict):
        raise ValueError("mappings.json must have schema 'grocery-blueprint-mappings/1' and a 'pins' object")
    for ing, per in data["pins"].items():
        for chain in per:
            if chain not in CHAINS:
                raise ValueError("unknown chain key %r in pin for %r (allowed: %s)" % (chain, ing, ", ".join(CHAINS)))
    return data["pins"]


def build_prices(feeds, pins):
    """feeds: {chain: {ref, items, sha256, retrieved_at}}. Returns (prices_dict, problems[])."""
    problems = []
    chains_meta = {}
    lookups = {}
    for chain, f in feeds.items():
        ref = f["ref"]
        chains_meta[chain] = {
            "store_id": CHAINS[chain]["store_id"], "store_name": CHAINS[chain]["store_name"],
            "source_file": ref.name, "published_at": iso_with_tz(ref.published_at),
            "published_at_assumed_tz": FEED_TZ, "retrieved_at": f["retrieved_at"],
            "sha256": f["sha256"], "item_count": len(f["items"]), "priced_count": 0}
        lk = {}
        for it in f["items"]:
            lk[str(it.item_code).strip()] = it
        lookups[chain] = lk
    ingredients = {}
    for ing, per in pins.items():
        for chain, pin in per.items():
            if chain not in feeds:
                continue
            approved = pin.get("approved_by_user") is True
            assistant = pin.get("selected_by") == "assistant"
            if not (approved or assistant):
                continue  # pins neither user-approved nor assistant-selected are ignored, never priced
            code = str(pin.get("item_code", "")).strip()
            it = lookups[chain].get(code)
            if it is None:
                problems.append("%s | %s: pinned code %s not in %s" % (chain, ing, code, feeds[chain]["ref"].name)); continue
            if norm_text(it.name) != norm_text(pin.get("pinned_name")):
                problems.append("%s | %s: name changed for code %s (pinned %r, feed %r) - re-review" % (chain, ing, code, pin.get("pinned_name"), it.name)); continue
            pk = derive_pack(it)
            price = dnum(it.price)
            if not pk or not price or price <= 0:
                problems.append("%s | %s: code %s has no derivable pack size or valid price" % (chain, ing, code)); continue
            ref = feeds[chain]["ref"]
            ingredients.setdefault(ing.lower().strip(), {"ingredient_name": ing})[chain] = {
                "item_code": code, "gtin": getattr(it, "gtin", None) or None,
                "nameHe": (it.name or "").strip(), "brand": (it.manufacturer or "").strip() or None,
                "packPrice": price, "packQty": pk["qty"], "packUnit": pk["unit"],
                "packBasis": pk["basis"], "isWeighted": bool(it.is_weighted),
                "selectionSource": "user" if (approved and pin.get("selected_by") != "assistant") else "assistant",
                "selectionNote": pin.get("approval_note") or None,
                "unitPriceNorm": round(price / pk["qty"], 5),
                "priceUpdateTime": it.price_update_time.isoformat() if it.price_update_time else None,
                "metadataSource": "%s (published %s, store %s): ItemCode=%s, price=%s, pack=%s %s" % (
                    ref.name, chains_meta[chain]["published_at"], CHAINS[chain]["store_id"], code, price, pk["qty"], pk["unit"])}
            chains_meta[chain]["priced_count"] += 1
    return ({"metadata": {"version": SCHEMA_VERSION, "chains": chains_meta}, "ingredients": ingredients}, problems)


def write_review_md(path, cands):
    """Human review sheet. Top candidates per ingredient and chain; frozen/variant flags are shown, never hidden."""
    L = ["# Product mapping review (generated from real feeds - review candidates; current pins live in mappings.json)", ""]
    for ch, s in cands["sources"].items():
        L.append("- %s: %s, published %s, %d items" % (ch, s["source_file"], s["published_at"], s["item_count"]))
    L += ["", "To approve a match, add it to mappings.json under pins -> ingredient -> chain with item_code, pinned_name (exact name_he) and \"approved_by_user\": true.", ""]
    for ing, per in cands["ingredients"].items():
        L.append("## " + ing)
        for ch, lst in per.items():
            if lst is None:
                L.append("- %s: no search terms defined for this ingredient (left unpriced)" % ch)
            elif not lst:
                L.append("- %s: no feed item matched the search terms (left unpriced)" % ch)
            else:
                L.append("- %s:" % ch)
                for x in lst[:6]:
                    size = ("%g %s" % (x["pack_qty"], x["pack_unit"])) if x["pack_qty"] else "size unknown"
                    extra = "; ".join(x["variant_flags"] + x["flags"])
                    L.append("  - `%s` %s | NIS %s | %s%s" % (x["item_code"], x["name_he"], x["price"], size, (" | " + extra) if extra else ""))
        L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def atomic_write(path, obj):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def run(chains, prices_path=PRICES_FILE, cand_path=CANDIDATES_FILE, mappings_path=MAPPINGS_FILE, fetch=fetch_chain):
    try:
        pins = load_mappings(mappings_path)
        with open(INGREDIENTS_FILE, encoding="utf-8") as fh:
            ingredients = json.load(fh)
    except Exception as e:
        print("FATAL inputs: %s" % e, file=sys.stderr); return 3
    feeds = {}
    try:
        for chain in chains:
            print("[*] %s store %s: listing + downloading newest PriceFull" % (chain, CHAINS[chain]["store_id"]))
            feeds[chain] = fetch(chain, CHAINS[chain]["store_id"])
            r = feeds[chain]["ref"]
            print("[+] %s -> %s published %s (%d items)" % (chain, r.name, iso_with_tz(r.published_at), len(feeds[chain]["items"])))
    except FeedError as e:
        print("FATAL download/provenance: %s\nprices.json left untouched." % e, file=sys.stderr); return 1
    cands = build_candidates(feeds, ingredients)
    atomic_write(cand_path, cands)
    write_review_md(os.path.join(os.path.dirname(cand_path), "MAPPING_REVIEW.md"), cands)
    prices, problems = build_prices(feeds, pins)
    if problems:
        print("FATAL pin validation (prices.json left untouched):", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 2
    atomic_write(prices_path, prices)
    for c, m in prices["metadata"]["chains"].items():
        print("[+] %s: %d ingredients priced from %s" % (c, m["priced_count"], m["source_file"]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", default=",".join(CHAINS), help="comma list; default both. A subset writes a partial prices.json (missing chain = estimates in app)")
    a = ap.parse_args()
    chains = [c.strip() for c in a.chains.split(",") if c.strip()]
    bad = [c for c in chains if c not in CHAINS]
    if bad:
        print("unknown chain(s): %s" % bad, file=sys.stderr); sys.exit(3)
    sys.exit(run(chains))


if __name__ == "__main__":
    main()
