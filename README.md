# Grocery Blueprint

Single-page meal plan to grocery list app (`index.html`) with optional real prices from the Israeli price-transparency feeds
(Shufersal online store 413, Rami Levy online store 039).

## State of the price data in this package
- `prices.json` here was produced by `scripts/fetch_prices.py` from real downloads (see `metadata.chains` for the exact files and times).
- **Most products are currently assistant-selected** (`"selected_by": "assistant"` in mappings.json) under the user's delegation and show in the app as "assistant pick - unconfirmed". Pins the user confirmed carry `"approved_by_user": true`.
- `MAPPING_REVIEW.md` / `mapping_candidates.json` list real products from those feeds for each ingredient. Review them, then pin the ones you accept.

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
