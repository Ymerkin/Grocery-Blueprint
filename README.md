# v10 notice

This package is v10. Read CHANGES_v10.md (what changed and how it was tested) and UNVERIFIED_ITEMS.md (everything still open) first. quarantine.json lists pins removed as wrong or unresolved.

# Grocery Blueprint

Single-page meal plan to grocery list app (`index.html`) with optional real prices from the Israeli price-transparency feeds
(Shufersal online store 413, Rami Levy online store 039).

## State of the price data in this package
- `prices.json` here was produced by `scripts/fetch_prices.py` from real downloads (see `metadata.chains` for the exact files and times).
- **Most products are currently assistant-selected** (`"selected_by": "assistant"` in mappings.json) under the user's delegation and show in the app as "assistant pick - unconfirmed". Pins the user confirmed carry `"approved_by_user": true`.
- `MAPPING_REVIEW.md` / `mapping_candidates.json` list real products from those feeds for each ingredient. Review them, then pin the ones you accept.

## How cart totals are computed
- Published online feeds (Shufersal online 413, Rami Levy online 039): purchase cost from the published price-transparency files.
- Published branch files (Osher Ad 032 Kiryat Ono, Yohananof 035 Tel Aviv Nachalat Yitzhak): same law-published files, for a physical branch (Osher Ad has no online store). Branch prices may differ from other branches.
- Victory Online: live victoryonline.co.il catalog snapshot (their official price-file portal is geo-blocked outside Israel, so the nightly workflow cannot refresh it; it is preserved from the last harvest and the app shows it as stale after 48h).
- In every real-price chain, packaged goods round up to whole packages and loose by-weight goods are charged at actual weight (no whole-kilo rounding). Items with no verified match in a chain are excluded from that chain's total - check the per-chain coverage badge. New-chain matches are assistant-selected and marked unconfirmed in the app until reviewed in MAPPING_REVIEW.md.
- Carrefour (no reachable feed or shop API): estimated per item as the average of the real-price chains for the same quantity - never a hand-set multiplier - and tagged "Estimate (from published avg)".

## Pin products (the review step)
1. Open `MAPPING_REVIEW.md`. Pick the right product per ingredient and chain (watch the frozen / variant flags and pack size).
2. Add it to `mappings.json`:
```
{"schema": "grocery-blueprint-mappings/1",
 "pins": {"Fresh Chicken Breast": {"rami-levy": {"item_code": "<code>", "pinned_name": "<exact name_he>", "approved_by_user": true}}}}
```
3. Run the script (below). It fails on a missing code, a changed name, or a pack size it cannot derive.
Ingredients with no pin stay estimates. Candidates are keyword matches, so check each one.

## Run locally
```
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tests/test_script_contract.py                    # no network
python scripts/fetch_prices.py                          # downloads both feeds, writes prices.json (Shufersal listing can take minutes)
python -m http.server 8000                              # open http://localhost:8000
```
`--chains rami-levy` runs one chain only (the other shows as estimates). Exit codes: 1 download/provenance, 2 pin validation, 3 bad inputs. A failed run never overwrites `prices.json`.

## Publish with GitHub Pages and the nightly refresh (existing repo)
Based on GitHub's docs for custom Pages workflows (docs.github.com, "Using custom workflows with GitHub Pages").
1. Copy these files into the repo root, keeping paths: `index.html`, `prices.json`, `mappings.json`, `all_unique_ingredients.json`, `rami_branches.json`, `mapping_candidates.json`, `MAPPING_REVIEW.md`, `requirements.txt`, `DATA_CONTRACT.md`, `scripts/`, `tests/`, `.github/workflows/prices.yml`. Commit and push to the default branch.
2. Repo **Settings > Pages > Build and deployment > Source: GitHub Actions**.
3. Repo **Settings > Actions > General > Workflow permissions**: allow read and write (the job commits refreshed data).
4. **Actions** tab > "Sync supermarket prices and deploy Pages" > **Run workflow**. Open the run and confirm the steps pass.
5. Open https://ymerkin.github.io/Grocery-Blueprint/ and hard-refresh. With no approved pins the badge says prices are estimates; after you approve pins it says published prices with each chain's file date.
The workflow runs nightly at 03:00 UTC. If a download fails the run fails, nothing is deployed, and the app drops to estimates once the file is older than 48 hours.
This workflow has not been run on GitHub; first run is step 4.

## Tests
- `tests/test_script_contract.py`: script logic with synthetic fixtures (source selection, provenance, pins, pack sizes, failure handling).
- `tests/test_regen_and_render.py`: 40 plan regenerations with cart invariants plus desktop/390px screenshots.
- `tests/test_app_contract.py`: loads the app in headless Chrome against fresh, stale, wrong-version, wrong-key, empty, partial and missing price files (`pip install playwright`; needs Chrome installed; the GitHub workflow runs only the script tests, not these; create the fixture first with `GB_FIXTURE_OUT=/tmp/fixture_v21.json python tests/test_script_contract.py`).
Fixtures are synthetic and their file names say so.

## Complete-cart semantics (v10e)
Totals are full-basket. Actual store prices are never altered; only missing lines are estimated, each labelled (estimate-chains / estimate-baseline / user-entered). Method: average of other fresh chains for the same quantity; no price-level index. Post-deploy checklist: run the workflow manually once, confirm prices.json commit scope (prices.json, mapping_candidates.json only), open the page, check actual/estimate counts per card, confirm Victory freshness (preserved, not refreshed by CI), verify no console errors. Not verified in production.
