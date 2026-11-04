# Grocery Blueprint v10 - what changed, tested how, what is still open

v10 is built from the exact v9 package (Grocery-Blueprint-v9.zip, sha256 7ab858c9...). v9 is unchanged and kept for comparison. Nothing here was deployed or pushed.
Selections of products are assistant picks (selected_by: assistant, approved_by_user: false). The files in the package that say a user approved or delegated something are v9 text and are not evidence of approval.

## Fixes
1. Pantry matching (index.html, matchIngredientToPantryStapleId). v9 used substring matches. Now whole-word matches plus exclusions. Fixed: Red Bell Peppers and Bell Peppers matched "pepper"; Feta matched "Salty" -> salt; Flour Tortilla Wraps matched "flour"; Matzo Meal matched Hebrew "flour"; Brown Rice Cakes matched "brown rice"; Red Lentil Protein Pasta matched pasta; "Soy Sauce & Ginger" and "Honey & Garlic" matched the plain sauce and honey; sugar snap peas matched sugar (found by the new tests). Effect over the same 100 simulated weeks: at least one wrongly-owned item in 75 weeks (v9) -> 0 (v10). Deliberate v9 merges (all rice types -> one staple, garlic and onions -> one staple) are unchanged and listed in UNVERIFIED_ITEMS.md section G.
2. Carrefour estimate (getAggregatedGroceryList). v9 added up per-recipe estimates, each rounded up to whole packs. Now computed once on the combined quantity, like the real chains. Carrefour was the highest card in 100 of 100 weeks, now 80 of 100. Week 99 Carrefour 755.49 -> 633.75.
3. Cart screen. Items with no verified product at a real chain now show "Not priced at this chain: <reason>", a muted "est." price and "not in total". Carrefour lines say "estimate (avg of priced chains)". v9 showed an unlabeled normal price and never showed the reason.
4. Wrong products removed. 43 pins listed in quarantine.json with reason and evidence (candy for pickles, cookies for oats, sauces for garlic, bourekas for potatoes, almond cookies for almonds, dried garlic granules for garlic, and others), plus pins with unresolved evidence or product weight conflicts. The refresh script never re-adds a quarantined code.
5. Replacement pins from the stores' own files: 17 (Osher 5, Yohananof 6, Victory 6). See UNVERIFIED_ITEMS.md section B for exactly what is verified and what is assumed.
6. Refresh script (scripts/fetch_prices.py), found broken while testing against the real 4 Nov feeds:
   - It rejected the Victory pins in mappings.json (unknown chain), so the nightly run would have stopped before doing anything.
   - It could not derive pack sizes for 91 of 112 Osher pins (the Osher feed labels quantities differently), so the run would have aborted at pin validation.
   - One renamed product (a promotion prefix "*מבצע*" or a longer name) aborted the whole refresh. A bad pin is now dropped on its own and reported in prices.json metadata.pin_warnings.
   After the fix, running the script's own build against the real 4 Nov Osher, Yohananof and Rami files reproduces every v9 pin except 2 (listed in UNVERIFIED_ITEMS.md section E).

## Tests
- tests/test_v10_fixes.py (new): quarantine consistency, pack derivation, 35 pantry cases, and whole-cart invariants over 100 simulated weeks x 6 chains (about 29,600 checks): aggregated quantities equal the sum of recipe quantities; chain totals equal the sum of the line costs; each Carrefour line equals the average of the real chains on the combined quantity; combined cost never above the sum of per-recipe costs; pantry items never in totals. The whole-cart part runs only while each chain's file is under 48 hours old (the app's own rule).
- The four v9 test files still pass: test_pricing_regression, test_script_contract, test_app_contract, test_regen_and_render.
- Before/after (same plans, seed 20261104, 100 weeks; v9 = archived 3 Nov data and v9 mappings; v10 = refreshed Osher, Yochananof, Rami files of 4 Nov, Shufersal 3 Nov, Victory 3 Nov plus 4 Nov pins): median 6-card spread 217.7 -> 183.7. Max 387.9 -> 355.4. Median 5-chain spread (real chains only) 119.5 -> 140.9, max 244.7 -> 314.7 (this rises because wrong cheap items are no longer counted at some chains). Carrefour highest card 100/100 weeks -> 76/100. Median same-basket spread (identical items at all five real chains) 93.5 -> 80.9. Week 99 shown totals v9 -> v10: Shufersal 610.41 -> 615.17, Rami 590.21 -> 598.41, Osher 528.12 -> 505.66, Yochananof 367.59 -> 369.26, Victory 381.36 -> 358.46, Carrefour 755.49 -> 633.39. The effect of data refresh and the effect of the fixes are not separated in these figures.
- Coverage fell a little because wrong products were removed instead of kept (mean share of cart items priced, v9 -> v10: Shufersal 77.2% -> 74.3%, Rami 77.2% -> 76.0%, Osher 68.2% -> 65.3%, Yochananof 65.6% -> 64.6%, Victory 62.1% -> 58.0%). Totals of the real chains still sum only the items each chain prices, so the large gaps that remain are mostly coverage differences. Use the same-basket line to compare prices.
- Single-item arithmetic (3,160 checks): only the legitimate "buy a whole pack for a small quantity" cases show up.

## Fixed after the first v10 checkpoint
- Refresh script: running a subset of chains erased the others (found when 9 pricing tests failed after a partial refresh). Unrequested and failed chains now keep their entries and their own publish dates. Regression test added.
- More wrong pins found by cross-chain form and price audits: Yochananof frozen broccoli (was fresh baby broccoli), soy sauce (was sweet soy), olive oil (500 ml promo pack, now 750 ml), sweet corn (promo triple pack), ginger at Victory (sushi ginger) and Yochananof (low-sugar ginger).
- Replacements from 4 Nov store files and the Victory catalog for 5 further quarantined pins; each has a SOURCE or INFERRED status in AUDIT_LIST_FOR_USER.md.

## Not fixed (see UNVERIFIED_ITEMS.md for the complete list)
Unit gaps (64 ingredient-and-unit combinations), 26 quarantined pins without a replacement, Shufersal not checked on 4 Nov, Victory cannot be refreshed by the workflow, pantry merge design, and the freshness window. v10 does not claim all mappings are correct.

## User-approved recipe working estimates (2026-11-04 11:21 IST)
Applied, 4 portions, each row tagged qtyEstimate in index.html: champignons 300 g (Creamy Garlic & Mushroom Penne), cucumbers 300 g (Mujadara), basil 40 g (Creamy Tomato & Basil Penne), yellow onion 110 g (Kofta, White Bean Stew; 110 g is a US USDA medium-onion weight, an estimate, not an Israeli market weight), carrots 150 g (Bolognese), tahini 2 tbsp (3 recipes), paprika 1 tbsp (2 recipes), olive oil 2 tbsp (3 recipes). These are recipe estimates; shopping cost still uses store pack size or weighed quantity. NOT approved or applied: container targets (canned goods, tomatoes, tuna, cream, loaf).

## User-approved product rules (2026-11-04 11:38 IST)
Glatt turkey not required (Shufersal pin marked glatt); plain cream cheese 16-18% accepted; granola nuts or fruit accepted, not chocolate; pistachios must be shelled, roasted and unsalted (no feed line states all three, so all chain pins were removed and pistachios are unpriced); no red-for-yellow onion substitution (Victory yellow-onion pin removed; Yochananof on dry onion 620, inferred yellow). Quarantine: 57 entries, 29 replaced, 28 without replacement.

## User-approved produce weights (2026-11-04 11:49 IST)
Recipe rows written in "units" converted to grams, each tagged qtyEstimate (US reference weights, working estimates): onion 110 g (yellow and red; 5 rows), carrot 61 g (2 rows), banana 118 g (1), lemon 58 g (1), red bell pepper 119 g (2), cucumber 201 g (4). 14 rows. Rows already in grams were not changed. Celery stalk 40 g: no recipe row uses a stalk unit, so nothing to convert. tests/test_app_contract.py was adjusted: cucumbers are now one g line and the coverage denominator is 13 lines, not 14.

## Final state (4 Nov 2026, 12:20 IST)
Supersedes the counts above (64 unit gaps, 26 quarantined without replacement): 59 quarantine entries, 29 with a replacement pin, 30 without; 37 remaining unit-gap combinations after the approved estimates.
User-approved on 4 Nov: container amounts (loaf 750 g, cooking cream 250 ml, pesto 180 g, crushed tomatoes 800 g, hummus 500 g, pepper/cherry tomato/strawberry pack 500 g, ptitim 500 g, garlic clove 3 g) and the garlic data fix (300 g -> 12 g). All converted rows carry qtyEstimate. Tuna, canned beans/corn, tortilla and cheese-slice amounts are NOT set.
Same plans, seed 20261104, v9 vs final: median 6-card spread 217.7 -> 177.1 (max 387.9 -> 355.8); 5-chain real spread median 119.5 -> 148.9 (max 244.7 -> 276.8); Carrefour highest 100 -> 78 of 100 weeks; same-basket median 93.5 -> 76.8; week 99 Shufersal 610.41 -> 620.62, Rami 590.21 -> 601.36, Osher 528.12 -> 484.01, Yochananof 367.59 -> 343.81, Victory 381.36 -> 363.91, Carrefour 755.49 -> 621.77; mean coverage Shufersal 77.2 -> 81.0%, Rami 77.2 -> 84.2%, Osher 68.2 -> 71.6%, Yochananof 65.6 -> 72.0%, Victory 62.1 -> 64.8%. The refresh effect, fix effect and approved-estimate effect are not separated; coverage rose mainly because approved weights and amounts let more rows price.

### Gap trace (4 Nov 12:20), largest gaps in the final sim
Week 99 (largest 5-chain real spread 276.8: Shufersal 620.6 vs Yochananof 343.8, which prices 14 of 17 rows, as does Shufersal). Main contributors: smoked turkey slices 1,700 g (Shufersal and Rami 10 x 180 g = 279-284 vs Osher 5 x 400 g = 159.5, Yochananof 155.4; whole packs, 1,700 g is the recipe quantity), ground beef 1,550 g (Osher 500 g packs x 4 = 179.6 vs loose by weight 92.9-114.6 at Rami and Shufersal; packaged items round up to whole packs, loose weighted items are priced by weight), hummus 1,200 g (Victory 3 x 500 g at 19.9 = 59.7 vs 2 x 1 kg at 27.8-34.4; Victory hummus type unverified), feta 100 g (priced by weight at 3.5-3.9 at Shufersal and Yochananof vs a whole 250-400 g pack at Rami and Osher). Week 83 (largest 6-card spread 355.8, Carrefour full-cart estimate 559.3 vs Victory 203.9 priced 10 of 18 rows). In week 83 Rami's salmon is a whole fillet (81.4/kg) vs Yochananof portions (149.9/kg): form differs, unverified.
The trace found two wrong-tier Osher pins (gluten-free-marked bourekas, truncated-name buns at under half price). Both were quarantined. Other matches in the two weeks looked like the same kind of product by name; names are not label verification.
After this fix: 59 quarantine entries; Osher priced_count 115.


## Update 4 Nov 13:25 (continuation, not yet reported before this entry)
- Whole-pin name screen of about 600 legacy pins: 12 more quarantine entries, 71 in total. Osher: hot paprika, cinnamon 250 g, quinoa 1.2 kg, breadcrumbs 550 g, tahini 3 kg and almond flour removed or repinned; beef stew pinned to goulash (weighted, inferred); Yochananof paprika in oil, ginger, Liguori spaghetti repinned; Victory blueberries (dessert), sliced almonds and two paprika-with-oil pins removed (priced_count -4). All new pins approved_by_user false, selected_by assistant.
- Osher, Yochananof and Rami regenerated from the live feeds (Osher 11:05, Yochananof 00:40, Rami 05:20). Diff against the previous prices.json showed only the intended pin changes, so regeneration reproduces. Shufersal (3 Nov 03:40) and Victory remain preserved snapshots.
- New `pack_override` (unit relabel only, same quantity, status and evidence required, rejected otherwise): Osher labneh 500 ml -> 500 g (source-verified), Osher tofu 300 ml -> 300 g (source-verified by same barcode at two chains), Osher rice vermicelli 454 ml -> 454 g (inferred).
- New `conversions` (g<->ml density, only entries with applied:true, source-derived from USDA SR Legacy): milk, cooking cream, coconut cream/milk, olive oil. Unit-gap rows 37 -> 30. The 30 left all need quantities the user has not approved: see APPROVAL_BATCH_UNIT_WEIGHTS.md.
- Same plans, seed 20261104, 100 weeks: median 6-card spread 168.2 (max 355.8); 5-chain median 140.3 (max 276.8); Carrefour highest in 76 of 100 weeks; week 99 Osher 484.01, Carrefour 621.77.
- Tests: tests/test_v10_overrides.py added. Rebuilt 5 earlier suites passed before the zip was rebuilt; see the final run below.
- Still open: Rami raw almonds code 522 is missing from the feed; Victory jasmine rice 5 kg; unequal brand tiers (Liguori pasta, butter); Osher garlic, strawberries, pitted kalamata, fettuccine and green beans have no feed replacement; Shufersal portal unreachable from this sandbox; Victory cannot refresh in CI; workflow never run on GitHub.


## Correction 4 Nov 13:30 (after review)
- Size-only quarantines reversed: Osher ground cinnamon 250 g, white quinoa 1.2 kg and raw tahini 3 kg are restored as the original pins (a large pack is a legitimate purchase). Quarantine total 68 (35 with replacement). Kept as evidence-based: Osher hot paprika (wrong product), almond flour for whole almonds (wrong form), panko vs golden seasoned crumbs (form), Yochananof paprika in oil (paste), Liguori spaghetti (brand tier; flagged, not a size case), Victory dessert blueberries, sliced almonds, paprika-with-oil.
- Coconut cream/milk density no longer applied (cream and milk differ). Applied bridges: milk 1.0313 g/ml (USDA 171265: cup 244 g), cooking cream 1.0144 (170857: light cream cup 240 g), olive oil 0.9129 (171413: cup 216 g). All in mappings.json `conversions`; they need scoped approval if treated as an assumption.
- Same plans: median 6-card spread 168.3 (max 355.8); 5-chain median 139.9 (max 276.8); Carrefour highest 77/100; week 99 Osher 484.01, Carrefour 621.77. Unit gaps 31.
- The Drive file was updated at 13:26 with this WIP build; the next build will be delivered as a clearly new file.


## Update 4 Nov 13:35
- Osher goulash pin removed (cut not stated on the label 'גולש בקר טרי ישראלי'; fresh beef but unconfirmed as a stew cut), Osher beef stew now unpriced pending confirmation.
- Legacy GTIN metric: 209 of 638 pins sit on a barcode that another chain pins for the same ingredient (exact same product, cross-checked by barcode). The other 429 are distinct local products matched by name/size and rest on the name screen only; they are not individually verified.
- Workflow: YAML parses (jobs sync, deploy; nightly 03:00 UTC cron plus manual run); added a no-network step running tests/test_v10_overrides.py before the fetch. Dependency israeli-prices==0.2.0 downloads from PyPI. The workflow has never run on GitHub, and it cannot refresh Victory (preserved snapshot).
- Victory jasmine rice 5 kg (retailer brand, 49.9) is a legitimate pack, left as is (large pack is not an error).


## Update 4 Nov 13:40 (user approved reference sizes at 13:31)
- User approval (WhatsApp reply 13:31:08, message id wamid.HBgMOTcyNTMzOTI3MDI5FQIAEhgUM0FFNDYzNDEwOUZBM0U3RTM4MDcA: "all good in general standard US reference sizes can be used without my input"; main relayed it): seven reference weights, g/ml reference densities for milk, cooking cream, olive oil, and standard US reference sizes in general. Not approved: invented sizes, product labels, treating a reference weight as a store pack size. Coconut cream/milk stays unapplied.
- Applied `conversions` with gramsPerUnit (recipe count/head to feed grams only; USDA SR Legacy portion, ESTIMATE): eggplant 548 g unpeeled (169228), zucchini 196 medium (169291), sweet potato 130 5" (168482), romaine 626 head (169247), cauliflower 588 medium head (169986), pita 60 large (172816). Bagel 99 is not applied: the gap is recipe grams vs a feed 'unit', and a feed unit has no known weight or pack count (same for pita grams, celery 40 g, cauliflower/romaine grams, herbs, spinach, mushrooms, sourdough, lettuce hearts).
- The app never converts recipe grams into feed 'units'. Rows using a reference weight return referenceWeightEstimate.
- Unit gaps 25. Osher goulash pin removed pending a confirmed stew cut.
- Same plans: median 6-card spread 175.7 (max 348.7); 5-chain 144.5 (max 276.8); Carrefour highest 70/100; week 99 Osher 484.01, Carrefour 621.77.
- The 25 left: 12 are recipe grams against a feed 'unit' with unknown weight (no source-backed fill), 6 are can/pack/slice rows needing the user's can/pack choice (tuna, black beans, chickpeas, cannellini, corn, tortilla pack, cheese slice), asparagus/parsley bunch (recipe bunch vs feed units or g without a bunch weight), coconut cream/milk (g vs ml, density unapplied).

## Update 4 Nov 13:40 (option c research, not delivered)
- Verified: downloaded Drive copy of the 13:34 upload equals the local zip (830,547 bytes, sha256 abd1a7e5…15f35f5). Earlier "830,427" was a stale ls from a superseded build.
- Two feed-unit rows resolved by exact evidence (pack_override with allow_qty_change, source-verified): Shufersal baby spinach barcode 7290003996742 '1 unit' = 200 g (Rami lists the same barcode as 200 g); Shufersal basil 7290000001050 '1 unit' = 50 g (the feed name states 50 g). Overrides also apply to preserved chains.
- Unit gaps 24. Same plans: median 6-card spread 178.3 (max 350.5); 5-chain 157.2 (max 323.8, week 99 Shufersal 665.32 vs Yochananof 343.81); Carrefour highest 58/100. The spread rose because Shufersal now prices spinach and basil.
- Not found / source-blocked (individually): herb and celery 'unit' items (parsley, dill, chives, celery, lettuce hearts, mushrooms tray, sourdough, bagel packs): search of savemycart/cheapersal/compee returned barcode pages without pack weights; the only lead is a Wolt Shufersal item 'פטרוזיליה 20 גרם' with no barcode on the page (lead, not applied). Cheese slices, tortilla pack, cans: no weight in feeds; need the user.

## Update 4 Nov 13:48
- Rami champignon tray: pack_override 250 g (Rami product photo with the barcode printed, https://img.rami-levy.co.il/product/7290003996209/large.jpg, label "250 גרם").
- Shufersal celery pin ("סלרי עלים") kept, flagged: the Harira recipe says only "celery" 300 g; leaf vs stalk not settled (form_flag in mappings). Not quarantined.
- Script: quarantined pins are not carried forward from preserved snapshots; preserved-chain priced_count recomputed.
- Coconut (proposal only, nothing applied): culinary light product exists in feeds: Master Chef "קרם קוקוס לייט" 400 ml 7290114604925 (half the fat of regular 18-19% per eati.co.il) and "נוזל קוקוס 5-7%" 400 ml 7290015603522 (Osher 5.9, Yochananof 6.9, Rami 5.8). Chia pudding recipe says "light coconut milk" -> 5-7% product; curry says "coconut milk" -> 17-19% can is sold as cooking coconut milk (ethnicfoods.gr Aroy-D 17-19% listing).

## Update 4 Nov 14:08 (user approval 14:02:51, reply "Yeah" to the 13:52:55 question)
- Approved common recipe targets applied: chickpeas and black beans 230 g drained per can (2 cans of cannellini = 460 g), tortilla pack 450 g, 3 tuna cans = 336 g drained. Each recipe row carries a qtyChange note.
- New rule `capacity_basis` (mappings.json) + `apply_capacity_basis` (scripts/fetch_prices.py): for black beans, chickpeas, cannellini and tuna a pack's capacity is the source-verified drained weight x tins of that exact item code, rounded up to whole packs (multipacks are priced as whole packs). A pin without a verified `drained` record is dropped to unpriced, never inferred from another brand or chain. Gross weight is kept as grossPackQty.
- Verified by label photo (Rami image of the same barcode): Strauss Teva Hateva black beans 7290110559014, white beans 7290112348142, chickpeas 7290112357113: net 380 g, drained 230 g. Starkist 4-pack 7290005287206: 160 g per tin, 112 g drained, 4 tins.
- Chickpeas re-pinned at Rami and Yochananof from Sugat 7290100704974 (drained weight unverified) to the Strauss tin 7290112357113 (present in both feeds). Assistant choice, not user-approved. The Rami cannellini net-380 override and the Sugat chickpea 240-to-400 override were removed (now 6 overrides).
- Unpriced by this rule: Shufersal black beans and chickpeas (400 g, other barcodes, no drained weight); tuna at Rami (own brand 670604), Osher (7290017617831), Yochananof (7290000551005), Victory (7290002551003): no label found. Starkist sold 160/140/120 g gross tins, so 112 g feed values and Osher "4x140" are not assumed to be drained weights. Tuna is priced at Shufersal only.
- Tortilla: whole-pack ceiling against feed net weights (Rami 450 verified by label; Yochananof 320, Shufersal 420, Osher 700 from the name 10x70, Victory 840 from the feed).
- Corn "1 can" and cheese "4 slices" were not part of the approval and stay unpriced. Found: Rami image for Yochananof's corn barcode 7290016370829 shows Kvuzat Yavne, net 430 g, drained 370 g, while Yochananof's feed says 550 (a size mismatch to resolve; not applied). Cheese pack photos (Shufersal 7290014760448 400 g, Osher 7290014763395 600 g) show no slice count.
- Results: unit gaps 22 -> 17. Same plans, seed 20261104, with Osher's 14:05 feed: median 6-card spread 174.8 (max 350.5), 5-chain median 156.3 (max 323.8), Carrefour highest 61/100, week 99 unchanged. All 6 suites and the invariants pass (tests/test_v10_overrides.py: 119 checks).

## 14:13-14:30 IST Nov 4 (v10e): cheese/pita, drained capacity, complete-cart estimates
- Cheese slice = 28 g (standard reference); Osher pita override 1000 g (Berman x10, label-verified); drained-weight capacity for beans/chickpeas/tuna.
- COMPLETE CART (user choice 14:17/14:18, item-level fill only): every chain prices the identical needed-basket after pantry. A line with a valid live match at a fresh chain keeps its actual price unchanged. Only a missing/unpriceable line gets an estimate: the plain average of the other fresh chains' whole-pack cost for the same exact quantity ("estimate-chains"); if no chain prices it, the recipe baseline ("estimate-baseline", no store/city/kosher multiplier while feeds are fresh). Custom items use the user's price as typed. Totals use integer cents: actual + estimated chains + estimated baseline + user-entered = cart. UI marks each estimated row and shows per-chain actual/estimated split and coverage. No chain price-level index is applied (disclosed simplification).
- A chain whose feed is >48 h old becomes all-estimate from the other chains.
- Tests: test_complete_cart.py (20 checks), whole_cart_invariants.js updated, others re-run green.

## 14:30-14:35 IST Nov 4 (v10f): review fixes on the complete cart
- Removed the legacy store/city/kosher multipliers from baseline estimates in ALL modes (previously applied when every feed was stale). With all feeds stale every chain now gets the identical recipe-baseline cart and city/kosher settings do not change it (tested).
- Detailed WhatsApp/text export, the export modal checklist and the online-cart modal now mark estimated lines "(est.)" / "est." (the earlier build marked them only in the summary line).
- Pantry-owned rows show a struck-through grey price "owned - not in total" instead of an estimate label; they were never in the total.
- Price cells no longer wrap ("≈" alone on a line on mobile).
- New tests: all-stale no multipliers, custom 0/NaN price, same ingredient in two recipes (baseline accumulates once), export markers.
- Gap trace (week 41, max spread 222): Shufersal 961.66 vs Rami 739.69. Differences are ACTUAL feed prices on pinned products, not estimates: smoked salmon 366.40 vs 318.40; cream cheese 89.50 (16% 200 g @17.9) vs 53.50 (@10.7); chicken thighs 46.90 (Landau 1 kg) vs 20.00; fresh salmon 71.94 vs 48.84; ground turkey 52.00 (glatt) vs 31.80 (red turkey); halloumi 99.60 vs 82.40; drumsticks 27.45 (Landau) vs 11.10. Shufersal's pins on chicken/turkey are premium-brand/glatt products, which the user said are not required; re-pinning is an OPEN assistant decision, not done.
- Victory refresh: the stor.ai catalog API (victoryonline.co.il/v2/retailers/1470/...) returned a Cloudflare 403 challenge to a plain HTTP request from this runtime (the earlier harvest used a real browser session). A plain-Python CI job cannot be assumed to refresh Victory; it stays in PRESERVE_CHAINS and goes stale 48 h after its 3 Nov 22:55 snapshot.

## 14:40 IST Nov 4 (v10g)
- Custom items: a typed price of 0 is a valid free item and is kept as entered (user-entered 0.00). Missing/NaN/negative price is invalid and never shown as the user's value (labelled baseline estimate 10). The add form now accepts 0-2000.
- New analytic fixtures: identical recipe twice = qty doubles and baseline doubles (5 -> 10); two different recipes keep their own cost contributions (5 + 7 = 12; other ingredient 3). Weighted actual lines asserted pro-rata on actual weight, packaged lines whole packs (all chains, whole plan).
- Shufersal like-for-like re-pin (Landau chicken, glatt turkey, 16% cream cheese): NOT done. prices.shufersal.co.il times out from this sandbox (israeli_prices adapter) and from the cloud browser, and the 3 Nov Shufersal file (15,837 items) is not stored locally; only the 142 pinned items exist in prices.json. No alternative Shufersal product can be verified (form, pack, unit) without that feed. The pins stay as real actual prices; the difference is disclosed, not corrected.

## 14:45 IST Nov 4 (v10h)
- Invalid custom input is rejected, not guessed: the form shows "Please enter a valid price between ₪0 and ₪2000" and adds nothing for negative/empty/over 2000/non-numeric (typed 0 is accepted as free). Older saved state with an invalid-priced custom item is dropped on load, and the cart builder skips any such item. No invented baseline item is created.
- Test: every ingredient in the app (unit gaps, Baharat, soba, composites) is an actual price only with a verified convertible pack; otherwise an explicit estimate-chains/estimate-baseline line.

## 14:48 IST Nov 4 (v10i)
- Mobile cart rows (<640 px) now stack: checkbox + title/description at full width, price/actions below. Desktop unchanged.
- Corn (430/370 vs feed 550), Yochananof pita (580 vs 880 stickers) and cauliflower (500 g floret tray, different form): NOT applied. Source/unit not verified or conflicting, so they remain explicit estimates.
