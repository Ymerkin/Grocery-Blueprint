# Remaining store connection limits

This file supplements the older ingredient-specific UNVERIFIED_ITEMS.md.

## Directory unavailable

- Carrefour Israel: https://prices.carrefour.co.il (no new verified directory connection).
- Hatzi Hinam: https://shop.hazi-hinam.co.il/Prices (no new verified directory connection).
- Victory: https://laibcatalog.co.il/victory/index.html (no new verified directory connection).
- Mahsanei HaShuk: https://laibcatalog.co.il/mshuk/index.html (no new verified directory connection).
- Het Cohen: https://laibcatalog.co.il/hcohen/index.html (no new verified directory connection).

## Store selection

- Only the seven keys in store_config.json have a refreshed price and promotion snapshot.
- The Givat Shmuel shortlist is the user-requested city scope. Five local records were found in connected directories; blocked chains could have additional branches, so exhaustive city retail coverage is not claimed.
- Directory-only stores show estimates and do not automatically gain a refresh job.
- Be pharmacy has only one mapped ingredient and zero mapped active deals; it is a verified connection with low grocery coverage, not a full supermarket basket.
- Duplicate chain/store identifiers were excluded; sub-chain routing needs further work before those can be offered safely.

## Deals and online shopping

- Deal conditions are displayed, not used to compute automatic discount/stacking savings.
- Existing retailer website/copy/search handoff is not automatic retailer-cart insertion.
- No retailer account, basket or checkout was tested. Rami Levy storefront returned 403 to an unauthenticated request while its public feeds worked.
- Victory is not in the active shortlist and has no claimed fresh connection.

## Production

- No GitHub push, workflow run or deploy occurred. Four-per-day production schedule remains unverified until approved deployment and a real run.
- No paid hosting/backend/runner changes are included.
