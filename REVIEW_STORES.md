# Grocery Blueprint: stores + barcode review build

Review build, November 14, 2026. Not deployed.

## What changed

- Searchable online/physical branch directory, filtered by chain and branch name/address. Branch choices and comparison cards survive reloads. Added branches can be removed from the comparison.
- 1,143 selectable branch identities: 1,142 unambiguous records from 20 connected supermarket directories, plus the established Victory online entry. Ambiguous duplicate store IDs are omitted rather than mixed across sub-chains.
- Exact branch prices, source timestamps and actual/estimated splits. A directory entry is not advertised as a price connection. Selecting one without a snapshot shows estimates, not another branch's prices.
- Seven configured stores fetched successfully at least twice, with real PriceFull and PromoFull files. Local chain snapshots include Fresh Market/Haviv and Super Bareket.
- Exact validated GTIN matching from an existing selected product, with name/size checks, preserves selection status. Invalid/weighted/restricted-distribution barcodes do not cross-match. Existing chain-local pins remain available for produce and own-label/manual choices. Quarantine and drained-weight checks still apply.
- Deals relevant to mapped products and the basket, with eligibility, validity, quantities, coupons, minimum spend and feed citations. Large eligibility lists can be expanded. Deals are informational, never silently deducted from totals.
- Shopping-list/copy/search handoff appears only for an online store with an existing supported launch URL. Physical branches have neither the cart-launch controls nor per-item online buttons. The existing handoff is not automatic insertion into a retailer account/cart.
- Workflow draft: four refresh attempts daily, at 00:17, 06:17, 12:17 and 18:17 UTC. This is not a timing guarantee. The open app rechecks its static snapshot hourly and when returning after an hour; it never polls retailer portals from the browser.
- Schema 3 store keys; legacy 2.1 still accepted. Old default store IDs resolve to their exact existing branches. No changes to meal plans, servings, recipes or pantry preferences are required.

## Connected price/promotion shortlist: Givat Shmuel

Jonathan requested Givat Shmuel on November 14. These are all five unambiguous city-681 records in the connected supermarket-chain directories, plus both established online stores. Every one fetched price and promo files successfully at least twice. The test-pick branches were removed from the published price payload and default comparison.

| Store | Branch | Matched products | Current mapped offers |
|---|---|---:|---:|
| Shufersal | Online 413 | 129 | 42 |
| Rami Levy | Online warehouse 039 | 137 | 5 |
| Rami Levy | Menachem Begin 23, Givat Shmuel 712 | 33 | 7 |
| Haviv / Fresh Market | Yoni Netanyahu 21, Givat Shmuel 047 | 30 | 15 |
| Super Bareket | HaZeitim 96, Givat Shmuel 009 | 23 | 5 |
| Super Bareket City | Ben Gurion 11, Givat Shmuel 065 | 19 | 5 |
| Be pharmacy (Shufersal feed) | Givat Shmuel 645 | 1 | 0 |

Be is explicitly labeled as a pharmacy, not claimed to have supermarket basket coverage. Zero current mapped offers is a successful promo-feed check, not a connection failure.

Counts are ingredient matches and offers that touch mapped products, not total inventory or guaranteed availability. The release candidate has 73 exact-GTIN links in addition to chain-local pins. Products not matched at a store remain clearly marked estimates. Existing assistant-selected mappings remain unconfirmed; this build does not turn them into user-approved choices.

## Tested

- 105 end-to-end store-flow assertions in local desktop Chrome (1280px), 390px and 320px mobile layouts: directory/filter/search, exact branch choice, physical/online gating, item buttons, modal destinations, reload persistence, malformed data rejection, freshness expiry, promo validity, totals unaffected by informational deals, no JS errors and no unintended viewport overflow.
- 31 synthetic sync tests: valid/invalid GTINs, restricted and weighed codes, duplicate matches, renamed products, sizes, quarantine, branch isolation, drained weights, eligibility and promo validity, wrong store/retailer, missing dates, timeout preservation and nonfinite numbers.
- 100 random-week complete-cart pass: 56,210 assertions. Additional pantry/quantity regression stress: 56,210 assertions. These are test assertions, not simulated real purchases.
- 80 further plan regenerations, real-snapshot and synthetic-fixture runs.
- Existing legacy app-contract, pricing regression, override/drained-weight, typeahead and feature tests. Feature checks cover macros, custom items, zero/no-price handling, exports, print toggle and three viewport widths.
- Actual screenshots inspected: branch search at 390px and 320px; offer conditions at 390px; expanded comparison cards on desktop. Cards were widened after a visual check found dense/clipped comparison text.
- JavaScript syntax and Python compilation checked. Both HTML entry points are identical. Historical product-capacity tests use the privately retained pre-upgrade matching reference; current store, UI and total tests use the release-candidate snapshots.

No GitHub workflow was executed, no repository changes were pushed, no deploy was made, no money was spent and no retailer cart was changed.

## Open before deployment

1. **City scope is connected, not nationwide.** Givat Shmuel selection is resolved as above. Other directory branches do not automatically register a server-side refresh when selected. Connecting all directory branches needs a larger data job/backend and its capacity/cost review; it is not silently enabled here. The five city records are all that could be verified in the connected directories, not proof that no other chain has a store in the city.
2. **Five directories unavailable.** Hatzi Hinam returned HTTP 403. Carrefour, Victory, Mahsanei Hashuk and Het Cohen failed TLS/network access during this run. They are recorded as unavailable. Victory is not in the active Givat Shmuel/online shortlist; no fresh Victory feed or promos are claimed.
3. **Online cart handoff, not retailer-cart insertion.** Local UI and destinations tested. No signed-in retailer basket/checkout was exercised. An unauthenticated Rami Levy storefront link check returned HTTP 403, although its price and promo feeds worked twice. No claim that all storefront sessions work from every network.
4. **Deal calculation.** Offers are displayed with their conditions but not applied automatically to the basket. Full promotion stacking/group/reward logic is not implemented. Treat basket totals as regular published prices plus labeled estimates, excluding delivery/member/coupon discounts.
5. **Production verification remains.** Four daily scheduled runs and the Pages packaging are drafted and statically checked, not run on GitHub. First approved deployment still needs a real workflow run and live-site smoke test. Scheduled jobs may be delayed; source publication times, not download times, determine freshness.
6. **Scope of barcode matching.** This matches the same selected product by exact identity; it does not declare different brands/pack sizes equivalent. New chains therefore have lower coverage. Additional choices need product review rather than fuzzy automatic substitution.

## Preview locally

```sh
python -m http.server 8000
# Open http://localhost:8000/
```

Do not open index.html with file://: fetching the separate data files requires an HTTP server. The review ZIP contains code, configuration, snapshots and tests. Deployment requires separate approval.
