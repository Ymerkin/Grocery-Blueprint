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
