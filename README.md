# Grocery Blueprint

Static meal-plan and grocery-list app. This package is the **stores + barcode review build**. Read `REVIEW_STORES.md` for verified coverage, tests and remaining limits. Not deployed.

## Local preview

```sh
pip install -r requirements.txt
python -m http.server 8000
# http://localhost:8000/
```

## Data refresh

- `stores.json`: branch directory and connection status. Directory data does not imply connected prices.
- `prices.json`: schema 3, separate store keys (`chain::store_id`), dated price provenance, mapped products, promotions and sync status.
- `store_config.json`: user-requested Givat Shmuel branches plus the two online stores actually refreshed. Selecting another branch in the browser does not edit this file or start a new data job.
- `scripts/sync_stores.py --catalog`: refresh directory records. Per-chain child processes have a 75-second timeout; failures keep older records with an unavailable connection status.
- `scripts/sync_stores.py`: refresh configured branches, preserving original source dates when a branch fails. Per-store child processes have a configured timeout. If every branch fails, exits nonzero and the workflow does not deploy.
- `scripts/fetch_prices.py`: legacy 2.1 source/pack validation library and standalone legacy sync. Use `sync_stores.py` for this build's schema-3 refresh.
- `mappings.json` and `quarantine.json`: existing selected products and rejected/unresolved choices. Exact barcode matching reuses validated selections, not fuzzy product-name guesses. Unconfirmed assistant selections stay unconfirmed.

```sh
python scripts/sync_stores.py --catalog
python scripts/sync_stores.py
# Optional explicit subset (does not edit the scheduled shortlist):
python scripts/sync_stores.py --stores shufersal::413,rami-levy::039
```

`data/matching_reference.json` privately preserves pre-upgrade validated source entries so cross-store matching does not depend on keeping unused test branches in the client price payload. It is not published by Pages.

A brand-new pin must first produce a validated entry in its source branch; that entry can seed other branches on the following refresh. Conflicting existing brand choices remain exact-product alternatives in deterministic order. Store-local pins take precedence for their own chain. A new chain's weights/own-brand matches are not invented.

## Totals

Whole packages round up; loose by-weight items use actual weight. Only fresh source files with valid product/pack metadata provide actual prices. Missing/incompatible/stale items use explicit estimates from other connected store snapshots or the recipe baseline. User-entered custom prices remain separate. Deals are shown with their terms but not deducted without proving qualification. No delivery fees or assumed club/coupon savings are included.

Online shopping is the existing copy/search/website handoff, not an automated retailer-cart API. Physical branches cannot launch it.

## Tests

Install `playwright` and provide Chrome for browser tests; no retailer login is used.

```sh
python tests/test_store_sync.py
GB_FIXTURE_OUT=/tmp/fixture_v21.json python tests/test_script_contract.py
python tests/test_stores_ui.py
python tests/test_complete_cart.py
python tests/test_app_contract.py
python tests/test_features.py
python tests/test_typeahead.py
python tests/test_pricing_regression.py
python tests/test_v10_fixes.py
python tests/test_v10_overrides.py
python tests/test_regen_and_render.py
```

Synthetic fixtures never go into the published price file. Tests age or manipulate local copies where needed to exercise freshness and error behavior.

## Deployment gate and schedule

No deployment is authorized by this package. Obtain review approval before pushing. The proposed existing Pages workflow polls the configured shortlist four times/day (`17 0,6,12,18 * * *`, UTC) and publishes only `index.html`, `prices.json`, `stores.json`. It does not publish mappings, directories or raw snapshots. GitHub scheduling is best-effort; verify the first run after approved deployment. Do not enable any billable service.
