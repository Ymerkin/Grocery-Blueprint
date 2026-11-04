# prices.json contract (schema 2.1)

One schema, written by `scripts/fetch_prices.py`, read by `index.html`. The app rejects any other version
and any chain key other than `shufersal` and `rami-levy` (it falls back to labelled estimates and shows why).

```
{
  "metadata": {
    "version": "2.1",
    "chains": {
      "shufersal" | "rami-levy": {
        "store_id": "413" | "039", "store_name": "...",
        "source_file":  exact filename of the PriceFull FileRef that was downloaded and parsed,
        "published_at": that file's publication time from the portal listing (ISO, Asia/Jerusalem assumed for the naive portal time),
        "published_at_assumed_tz": "Asia/Jerusalem",
        "retrieved_at": when the script downloaded it (UTC; never used for freshness),
        "sha256": hash of the downloaded bytes, "item_count": n, "priced_count": n
      }
    }
  },
  "ingredients": {
    "<ingredient name, lower case>": {
      "ingredient_name": "...",
      "shufersal" | "rami-levy": {
        "item_code", "gtin", "nameHe", "brand",
        "packPrice", "packQty", "packUnit" (g | ml | units), "packBasis", "isWeighted",
        "unitPriceNorm", "priceUpdateTime", "metadataSource"
      }
    }
  }
}
```

Rules
- Freshness is per chain, from `published_at` of that chain's source file only. Older than 48 hours = estimates.
- A chain is labelled "Published online prices" only when its file is fresh AND at least one approved product is priced from it.
- Pins in `mappings.json` are priced when `"approved_by_user": true` (user-confirmed) or `"selected_by": "assistant"` (assistant-selected under the user's explicit delegation). Nothing is ever pinned automatically. Priced entries carry `selectionSource`: `"user"` or `"assistant"`; the app labels assistant-selected matches as unconfirmed picks.
- Recipe quantity vs pack unit must be convertible (g/kg, ml/l, tbsp/tsp/cup to ml, counts). Otherwise the item is excluded from published totals and shown with a reason.
- Savings are shown only on items priced in both chains.

`mappings.json`: `{"schema": "grocery-blueprint-mappings/1", "pins": {"Ingredient": {"rami-levy": {"item_code", "pinned_name", "approved_by_user": true}, "shufersal": {...}}}}`. Assistant-delegated selections use `"selected_by": "assistant"` instead of `approved_by_user` and show in the app as unconfirmed picks until the user confirms them.

Limits: pack size is only as good as the feed's quantity and unit fields plus the product name; multipacks, 'by weight' items and odd unit labels may be missed or flagged, and a human still has to confirm each product is the right one. Pack size comes from the feed's own `quantity` + `unit_qty` fields, cross-checked against a size in the product name.
If they disagree, or neither exists, the product cannot be pinned (the script fails the run for an approved pin like that).
`unit_price` is not used. In the Rami 039 sample inspected it equalled price/100 even for 700 g and 750 ml packs, so it could not be trusted there; Shufersal's looked like a real per-measure price, but one rule is used for both chains.

## Chain sources (v9, 2026-11-03)
- shufersal (413), rami-levy (039), osher-ad (032), yochananof (035): official price-transparency PriceFull files via israeli-prices; metadataSource cites file + published_at + item code.
- victory: live victoryonline.co.il catalog (stor.ai retailer 1470, online branch 2331). The official portal (laibcatalog.co.il) is geo-blocked outside Israel, so scripts/fetch_prices.py preserves the last victory entries instead of refreshing them; freshness follows the stored published_at like every chain.
- carrefour: no prices.json entries (portal + shop unreachable); the app estimates it as the average of the real-price chains.


## v10 additions
- quarantine.json (schema grocery-blueprint-quarantine/1): pins that must not be priced. The refresh script drops a pin whose (ingredient, chain, item_code) is listed there.
- prices.json metadata.pin_warnings (optional list of strings): pins dropped by the last refresh and why. metadata.package_revision is informational. metadata.version stays 2.1 because the app requires it.
- Victory entries are preserved from the previous prices.json (its portal is not reachable from CI).

## pack_override and conversions (v10 update)
- `pack_override` on a pin {qty, unit, status, evidence}: relabels the feed unit only (ml to g). qty must equal the feed's derived quantity or the pin is dropped. Shipped in prices.json as `packOverride`. This is assistant-selected, not user-approved.
- `conversions` in mappings.json is copied to prices.json. The app uses an entry only when `applied` is true; gPerMl bridges g and ml. Proposed (unapplied) entries are ignored.

## capacity_basis and drained (v10, 4 Nov)
- `mappings.json -> capacity_basis.ingredients`: ingredients whose recipe amounts are drained food amounts. For these, a pin needs `drained: {per_unit_g, units, gross_per_unit_g, status: "source-verified", evidence}` for its exact item_code, or it is unpriced.
- prices.json entry then has packQty = per_unit_g x units (g), grossPackQty/grossPackUnit (feed quantity), `drained` metadata, and packBasis "drained weight ...". metadata.drained_unpriced lists dropped pins.
- `pack_override.allow_qty_change` (source-verified only) lets a feed '1 unit' item take a weight from the same barcode in another chain (`same_barcode_chain`), a Rami label photo for the barcode, or a weight in the product name.
