# prices.json schema 3

Written by `scripts/sync_stores.py`, read by the app. Legacy 2.1 remains accepted during migration; new writes use 3.

```json
{
  "metadata": {
    "version": "3",
    "chains": {
      "shufersal::413": {
        "chain": "shufersal", "store_id": "413", "store_name": "...", "kind": "online",
        "source_file": "PriceFull...", "source_url": "...", "published_at": "...",
        "published_at_assumed_tz": "Asia/Jerusalem", "retrieved_at": "...", "sha256": "...",
        "item_count": 1, "priced_count": 1
      }
    },
    "sync_attempted_at": "..."
  },
  "ingredients": {
    "ingredient name": {
      "ingredient_name": "Ingredient Name",
      "shufersal::413": {
        "item_code": "...", "gtin": "...", "nameHe": "...", "brand": "...",
        "packPrice": 1, "packQty": 1000, "packUnit": "g", "packBasis": "...", "isWeighted": false,
        "selectionSource": "assistant", "selectionNote": null,
        "matchMethod": "chain-local-pin", "metadataSource": "...", "priceUpdateTime": "..."
      }
    }
  },
  "conversions": {},
  "promotions": {},
  "sync_status": {}
}
```

`metadata.chains` retains its old name to minimize migration risk, but its keys now identify specific stores. Store ID and retailer must agree with the key and downloaded file. Store keys are generated centrally as `slug::store_id` with at least three digits. Duplicate store IDs within a chain's directory are omitted until sub-chain identity can be resolved; no merge by guess.

## Price and identity safety

- Actual prices require the store's own dated source and at least one valid match. Older than 48h or over 1h in the future is not current. The app rechecks age at pricing time, including already-open sessions.
- Source file/URL, original publication date and SHA identify the bytes parsed. Download time is never a freshness replacement. Failed refreshes preserve original timestamps and are recorded in `sync_status`.
- Positive finite numeric `packPrice`/`packQty`; units g/ml/units. Invalid product metadata rejects the file rather than silently pricing it.
- Existing approved/assistant-selected pins require name and pack validation. Quarantine applies to both fresh and preserved entries. Assistant choices retain their status.
- Cross-store matching requires a checksum-valid normalized GTIN, a single unambiguous target, compatible name and same pack capacity. Restricted-distribution (20-29 prefix) and weighted codes do not cross-match. No fuzzy equivalent-product substitutions.
- `matchMethod: exact-gtin` also carries `matchedFromChain`. The source entry must already exist from a validated pin. A pin is not copied as a new user approval.
- Existing `pack_override` rules remain: quantity/unit changes need their recorded evidence; no new cross-chain override is invented. Drained foods require their source-verified drained record for the exact product, with gross capacity preserved separately.
- Own-brand, weighted and internal item codes remain chain-local manual selections. Product availability is not inferred from being present in a price file.

## Promotions

`promotions[storeKey]` contains status, source_file, source_url, published_at, retrieved_at, sha256 and offers. Only dated, store-specific PromoFull sources are accepted. Retailer/store identities must agree. The parser serializes validity times with explicit Israel timezone offsets. Missing validity bounds do not produce an active offer.

Offers retain published eligibility, coupon, quantities, minimum spend, reward/discount fields, remarks and restrictions. Only item records for mapped products are retained to bound payload size; `offer_group_item_count` records full group size. This is a relevant-offer view, not a complete retailer offer database. UI additionally filters by selected branch, basket products, price-source freshness, promo-source freshness and current validity. Offers are informational; totals never deduct an unproven promotion.

## Directory and refresh configuration

`stores.json` version 1 has `checked_at`, `stores` and per-chain connection status. Records have key, chain, chain_name, chain_name_he, store_id, name, kind, address, city and directory_source. Numeric municipality codes are not mislabeled as city names. Unknown address text is not treated as a location.

`store_config.json.refresh_stores` is the refresh shortlist. Browser selections are local preferences only, never backend job registrations. Directory-only stores cannot claim actual prices. `data/directories` caches source directory records for safe retention; `data/stores` holds local worker snapshots and is not needed by the client. `data/matching_reference.json` preserves old validated source entries privately for barcode identity seeding, not current prices or freshness. `default_compare_stores` copies the configured release shortlist into the directory for client defaults; the current shortlist is both online stores plus five Givat Shmuel records (including Be pharmacy separately labeled).

Legacy aliases (`rami_levy`, `shufersal`, `osher_ad`, `yohananof`, `victory`) map to their original default snapshots. Saved meal/pantry/custom state remains compatible. If a selected branch was removed, the app safely falls back rather than crashing.
