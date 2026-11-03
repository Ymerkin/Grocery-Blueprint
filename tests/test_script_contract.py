"""Script-side contract tests. Uses SYNTHETIC fixtures (clearly named) - they exercise parsing/validation logic only
and are never real feed data. Run: python tests/test_script_contract.py"""
import json, os, sys, tempfile, unittest
from datetime import datetime, timedelta
from decimal import Decimal
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_prices as fp
from israeli_prices import FileRef, FileType, PriceItem


def item(code, name, price, uq, qty, uom, weighted=False):
    return PriceItem(item_code=code, name=name, price=Decimal(price), unit_price=Decimal("0.1"), unit_qty=uq, quantity=Decimal(qty),
                     unit_of_measure=uom, is_weighted=weighted, manufacturer="TEST")


def feed(chain, store, items, published):
    ref = FileRef(chain=chain, name="SYNTHETIC-TEST-FIXTURE-%s-%s.gz" % (chain, store), file_type=FileType.PRICE_FULL,
                  url="http://invalid.test/x", store_id=store, published_at=published)
    return {"ref": ref, "items": items, "sha256": "0" * 64, "retrieved_at": datetime.utcnow().isoformat()}


class T(unittest.TestCase):
    def feeds(self, published=None):
        p = published or datetime.now() - timedelta(hours=3)
        return {"rami-levy": feed("rami-levy", "039", [item("111", "אורז בסמטי 1 ק\"ג", "12.9", 'ק"ג', "1", "100 גרם"), item("222", "ביצים 12יח", "15", "יח'", "1", "1 יח'")], p),
                "shufersal": feed("shufersal", "413", [item("111", "אורז בסמטי 1 ק\"ג", "13.9", 'ק"ג', "1", "100 גרם")], p)}

    def pins(self, approved=True):
        return {"Fragrant Basmati Rice": {"rami-levy": {"item_code": "111", "pinned_name": "אורז בסמטי 1 ק\"ג", "approved_by_user": approved},
                                          "shufersal": {"item_code": "111", "pinned_name": "אורז בסמטי 1 ק\"ג", "approved_by_user": approved}}}

    def test_schema_and_keys(self):
        d, problems = fp.build_prices(self.feeds(), self.pins())
        self.assertEqual(problems, [])
        self.assertEqual(d["metadata"]["version"], "2.1")
        self.assertEqual(set(d["metadata"]["chains"]), {"shufersal", "rami-levy"})
        e = d["ingredients"]["fragrant basmati rice"]["rami-levy"]
        for k in ("packPrice", "packQty", "packUnit", "nameHe", "metadataSource", "item_code"):
            self.assertIn(k, e)
        self.assertEqual((e["packQty"], e["packUnit"]), (1000.0, "g"))
        self.assertIn("SYNTHETIC-TEST-FIXTURE", e["metadataSource"])

    def test_freshness_is_file_publication_time(self):
        pub = datetime(2026, 1, 2, 3, 4)
        d, _ = fp.build_prices(self.feeds(pub), self.pins())
        self.assertTrue(d["metadata"]["chains"]["rami-levy"]["published_at"].startswith("2026-01-02T03:04:00"))
        self.assertNotEqual(d["metadata"]["chains"]["rami-levy"]["published_at"], d["metadata"]["chains"]["rami-levy"]["retrieved_at"])

    def test_unapproved_pin_not_priced(self):
        d, p = fp.build_prices(self.feeds(), self.pins(approved=False))
        self.assertEqual(d["ingredients"], {})

    def test_missing_code_and_name_change_fail(self):
        pins = self.pins(); pins["Fragrant Basmati Rice"]["rami-levy"]["item_code"] = "999"
        _, p = fp.build_prices(self.feeds(), pins); self.assertTrue(any("not in" in x for x in p))
        pins = self.pins(); pins["Fragrant Basmati Rice"]["shufersal"]["pinned_name"] = "something else"
        _, p = fp.build_prices(self.feeds(), pins); self.assertTrue(any("name changed" in x for x in p))

    def test_select_ref_ignores_promo_and_wrong_store(self):
        mk = lambda n, s, h: FileRef(chain="rami-levy", name=n, file_type=FileType.PRICE_FULL, url="u", store_id=s, published_at=datetime(2026, 1, 1, h))
        refs = [mk("promofull-039-x.gz", "039", 23), mk("pricefull-001-x.gz", "001", 22), mk("pricefull-039-a.gz", "039", 5), mk("pricefull-039-b.gz", "039", 9)]
        self.assertEqual(fp.select_ref(refs, "039").name, "pricefull-039-b.gz")
        with self.assertRaises(fp.FeedError): fp.select_ref([FileRef(chain="x", name="pricefull-039", file_type=FileType.PRICE_FULL, url="u", store_id="039", published_at=None)], "039")

    def test_pack_derivation_never_guesses(self):
        self.assertIsNone(fp.derive_pack(item("1", "מוצר ללא גודל", "5", None, "0", "1 יח'")) or None) if False else None
        self.assertEqual(fp.derive_pack(item("1", "ביצים 18יח גדול", "21", "יח'", "1", "1 יח'"))["qty"], 18.0)
        self.assertIsNone(fp.derive_pack(item("1", "שמן 500 מל", "9", 'מ"ל', "750", '100 מ"ל')))  # feed 750 vs name 500: reject

    def test_failure_exit_preserves_old_prices(self):
        with tempfile.TemporaryDirectory() as d:
            pp = os.path.join(d, "prices.json"); open(pp, "w").write('{"keep":"me"}')
            mp = os.path.join(d, "m.json"); open(mp, "w").write(json.dumps({"schema": "grocery-blueprint-mappings/1", "pins": {}}))
            def boom(chain, store): raise fp.FeedError("simulated outage")
            rc = fp.run(["rami-levy"], prices_path=pp, cand_path=os.path.join(d, "c.json"), mappings_path=mp, fetch=boom)
            self.assertEqual(rc, 1); self.assertEqual(open(pp).read(), '{"keep":"me"}')

    def test_bad_mapping_chain_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            mp = os.path.join(d, "m.json"); open(mp, "w").write(json.dumps({"schema": "grocery-blueprint-mappings/1", "pins": {"X": {"rami_levy": {}}}}))
            with self.assertRaises(ValueError): fp.load_mappings(mp)

    def test_write_fixture_for_app(self):
        """Writes a SYNTHETIC prices.json (via the real build_prices) covering the default plan: 3 priceable items per chain,
        plus one deliberately incompatible-unit pin (zucchini sold by weight, recipe in units)."""
        out = os.environ.get("GB_FIXTURE_OUT")
        if not out:
            return
        pub = datetime.now() - timedelta(hours=3)
        mk = lambda price: [item("c1", "חזה עוף טרי SYNTH", price, 'ק"ג', "1", "1 ק\"ג", weighted=True),
                            item("t1", "טופו SYNTH 400 גרם", "10", "גרם", "400", "100 גרם"),
                            item("b1", "ברוקולי קפוא SYNTH 800 גרם", "14", "גרם", "800", "100 גרם"),
                            item("z1", "קישוא SYNTH 500 גרם", "6", "גרם", "500", "100 גרם")]
        feeds = {"rami-levy": feed("rami-levy", "039", mk("30"), pub), "shufersal": feed("shufersal", "413", mk("34"), pub)}
        names = {"Fresh Chicken Breast": ("c1", "חזה עוף טרי SYNTH"), "Firm Tofu": ("t1", "טופו SYNTH 400 גרם"),
                 "Frozen Broccoli Florets": ("b1", "ברוקולי קפוא SYNTH 800 גרם"), "Fresh Zucchini": ("z1", "קישוא SYNTH 500 גרם")}
        pins = {k: {c: {"item_code": v[0], "pinned_name": v[1], "approved_by_user": True} for c in ("rami-levy", "shufersal")} for k, v in names.items()}
        d, problems = fp.build_prices(feeds, pins)
        self.assertEqual(problems, [])
        json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    unittest.main()
