# Fineli Data Guide

This guide covers the Fineli nutrient-data package used by the project: how to download and import it, how the backend uses the imported data, and what to consider when improving nutrition lookups.

**Status legend** used throughout this document:

- ✅ **Verified**: confirmed in the importer, application code, tests, or inspected package files.
- ⚠️ **To verify**: plausible, but not confirmed against the full current Fineli release. Check before relying on it.

---

## 1. What Fineli is

Fineli is the Finnish national food composition database, maintained by the Finnish Institute for Health and Welfare (THL). It lists foods and their nutrient content (energy, protein, fat, vitamins, minerals, fatty acids, and so on), with names in Finnish, Swedish and English.

| Fact | Value | Status |
| --- | --- | --- |
| Package we use | "Nutrient data package", release **20.0** | ✅ |
| License | Creative Commons Attribution 4.0 (CC BY 4.0) | ✅ (stated in the downloaded package's `descript.txt`; official current terms still need release-time confirmation) |
| Copyright holder | THL (Terveyden ja hyvinvoinnin laitos) | ✅ |
| Format | Plain text CSV files, `;` separated | ✅ |
| Liability | THL is not liable for errors or misinterpretation | ✅ |

### Why we use the downloaded package instead of the API

Fineli's web API has blocked requests from our backend in the current setup. The downloadable package provides the data needed by the app, so we import it into our database and query that by default. Local lookups avoid API availability and rate-limit issues and are deterministic in tests.

### Where Fineli data appears in the app

The imported dataset is available through the backend API and is used by the recipe
detail page to suggest Fineli foods, save user-confirmed ingredient matches, and show
approximate nutrition estimates with per-ingredient contributions and coverage.

With the backend running, try a lookup in a browser or PowerShell:

```text
http://localhost:8000/api/ingredients/search?q=sugar
```

The response includes matching foods, normalized nutrient values, detailed Fineli
component values and units per 100 g, food-specific household-unit weights, and
Fineli/THL source attribution. The same endpoint is listed in the interactive API docs at
`http://localhost:8000/docs` under **ingredients → GET `/api/ingredients/search`**.
The recipe detail page uses the bounded suggestions endpoint and displays the
confirmed match and resulting estimate.

### Attribution (required by CC BY 4.0)

Wherever we show Fineli-derived data, include the required attribution. The backend includes this text in Fineli food responses:

> Source: Fineli, Finnish Institute for Health and Welfare (THL), release 20.0, CC BY 4.0

Keep the attribution visible or readily accessible when changing the UI. The importer
derives kcal from kJ, and the estimate scales per-100-g values by confirmed ingredient
weights; the UI labels the result approximate and shows coverage and skipped reasons.
Fineli's official open-data/API pages returned HTTP 403 to the research request on
2026-11-09. Before public redistribution or release, verify the current license,
attribution and access conditions against the official source as well as the downloaded
release's `descript.txt`.

---

## 2. What is in the package

The package is a zip of about 45 CSV files plus `descript.txt` (the data description, in Finnish, Swedish and English). Files fall into four groups.

### 2.1 Core data files

| File | Contents | Used by us |
| --- | --- | --- |
| `food.csv` | One row per food: id, Finnish name, type, processing, edible portion, classes | ✅ yes |
| `component_value.csv` | One row per (food, nutrient): the actual nutrient value | ✅ yes |
| `component.csv` | One row per nutrient: its unit and group | ✅ yes |
| `foodaddunit.csv` | Grams per household unit for a food (tablespoon, piece, ...) | ✅ yes |
| `contribfood.csv` | Recipe rows: which foods make up a composite food | no |
| `publication.csv` | Source publications (citation, DOI) for values | no |

### 2.2 Name files

| File | Contents | Used by us |
| --- | --- | --- |
| `foodname_FI.csv` | Finnish food names | no (`food.csv` already has the Finnish name) |
| `foodname_EN.csv` | English food names | ✅ yes |
| `foodname_SV.csv` | Swedish food names | no |
| `foodname_TX.csv` | Scientific (Latin) names | no |

### 2.3 Classification files (lookup tables)

Each classification exists once per language, with suffix `_FI`, `_SV` or `_EN`. All have the same three columns: `THSCODE` (the code), `DESCRIPT` (the description), `LANG` (language).

| Files | Describes |
| --- | --- |
| `compunit_*` | Units of nutrients (g, mg, µg, kJ, ...) ✅ used |
| `foodunit_*` | Household units of foods (tbsp, piece, portion, ...) ✅ used |
| `eufdname_*` | Names of nutrient codes (`PROT` = "protein, total") |
| `foodtype_*` | Food type (the sample shows `FOOD`) |
| `process_*` | Processing method (the sample shows `IND`) |
| `igclass_*`, `fuclass_*` | Ingredient class and food-use class (hierarchies) |
| `cmpclass_*` | Nutrient group (fatty acids, vitamins, ...) |
| `acqtype_*`, `methtype_*`, `methind_*` | How a value was obtained: source, method type, analysis method |
| `specdiet_*` | Special diets (the file `specdiet.csv` links foods to them) |

### 2.4 How the files link together

```text
food.csv ──FOODID──┬── component_value.csv ──EUFDNAME──► component.csv ──COMPUNIT──► compunit_EN.csv
                   ├── foodname_EN.csv      (English name)
                   ├── foodaddunit.csv ──FOODUNIT──► foodunit_EN.csv
                   ├── contribfood.csv      (recipe rows, FOODID and CONFDID both point to food.csv)
                   └── specdiet.csv
```

Key points from `descript.txt` ✅:

- `FOODID` is the primary key of a food and the foreign key everywhere else.
- `EUFDNAME` is the nutrient code (for example `PROT`).
- Classification files hold **all languages in one file**. When joining, filter or join on `LANG` too.

### 2.5 Files to revisit in future work

The archive contains additional files that may be useful as the project grows, but
they are **not implemented or imported in the current project state**:

- `foodtype_*`, `process_*`, `igclass_*` and `fuclass_*` could enrich food labels
  and improve ingredient search and ranking.
- `specdiet.csv` and `specdiet_*` could support special-diet labels or filters;
  these classifications should not be treated as allergen-safety guarantees.
- `foodname_SV.csv` and `foodname_TX.csv` could add Swedish and scientific-name
  search.
- `eufdname_*` and `cmpclass_*` could provide readable names and groupings if more
  nutrient fields are exposed.
- `contribfood.csv`, `acqtype_*`, `methtype_*`, `methind_*` and `publication.csv`
  could support future composite-food explanations or nutrient-value provenance,
  but require additional interpretation and validation.

The current downloader stages only the seven CSVs required by the importer. These
other archive files are not part of the current application workflow.

---

## 3. File format and the traps in it

Everything below was seen in the real sample rows ✅ unless marked.

| Trap | What you see | What to do |
| --- | --- | --- |
| **Separator** | `;` instead of `,` | `csv` module with `delimiter=";"` |
| **Decimal comma** | `1698,30`, `99,900`, `4,00` | Replace `,` with `.` before converting to float |
| **Encoding** | Names such as `HEDELMÄSOKERI` contain non-ASCII characters; terminal output can show `�` | The importer decodes UTF-8 (including a BOM) first and falls back to Latin-1. Confirm the encoding if a future package fails to decode correctly |
| **Zero vs missing** | `1;FAT;0;...` is a genuine zero | Never turn missing into `0`. Blank or non-numeric means missing (`NULL`) |
| **Missing-value codes** | `descript.txt` mentions "codes for missing data" | ⚠️ The importer treats blank and non-numeric `BESTLOC` values as missing. Check the current release for documented markers before deciding whether any special handling is needed (section 8.1) |
| **Uppercase names** | `SOKERI`, `SUGAR`, `FRUCTOSE` | We apply `.capitalize()` at import. Search is case-insensitive |
| **Mixed units per nutrient** | Energy in kJ; some nutrients in g, others in mg or µg | Read the unit from `component.csv` and convert. Never assume. See section 4.2 |
| **Large value file** | `component_value.csv` has one row per food per nutrient and can be large | The importer keeps only the component codes it needs after reading the CSV. `read_rows` currently reads the file into memory; consider streaming if memory use becomes a problem. Keep the data out of git |
| **Printing in the terminal** | `ä` shows as `�` or `Ã¤` | This is only a display problem in PowerShell. Read the file with an explicit encoding (section 8.2) |

---

## 4. The nutrients we use

### 4.1 Mapping

Our API exposes nine nutrient fields, always **per 100 g** of food. Each maps to a Fineli component code:

| Our field | Fineli code | Meaning | Status |
| --- | --- | --- | --- |
| `energy_kj` | `ENERC` | energy, calculated (in kJ) | ✅ the sample value for sugar is `1698,30`, which only makes sense in kJ |
| `energy_kcal` | *(derived)* | `energy_kj / 4.184`, rounded to 1 decimal | ✅ sugar gives about 405.9 kcal |
| `protein_g` | `PROT` | protein, total | ✅ |
| `carbohydrates_g` | `CHOAVL` | carbohydrate, available | ✅ code exists. Alternatives: `CHOCDF` (by difference), `CHOAVLM` (monosaccharide equivalents) |
| `fat_g` | `FAT` | fat, total | ✅ |
| `fiber_g` | `FIBC`, fallback `FIBT` | fibre, total / total dietary | ✅ both exist. Fineli may use one or the other per food |
| `salt_g` | `NACL` | salt | ✅ code exists. ⚠️ unit probably mg, converted at import |
| `sugars_g` | `SUGAR` | sugars, total | ✅ |
| `saturated_fat_g` | `FASAT` | fatty acids, total saturated | ✅ |

Other codes worth knowing: `NA` (sodium), `FAPU` (polyunsaturated fat), `FAMCIS` (monounsaturated cis fat), `FATRN` (trans fat), `XENERC` (energy calculated without fibre). The inspected Rel20 package contains 74 component codes, including vitamins, minerals, and fatty-acid components. All numeric component values are imported with their code, English name, source unit, and group, rather than adding a database column for each nutrient.

### 4.2 Units

`component.csv` gives each nutrient a `COMPUNIT` code, and `compunit_EN.csv` explains it. The importer:

1. Looks up the unit description for every nutrient it needs.
2. Converts to **grams** (`mg` × 0.001, `µg` × 0.000001) or keeps **kJ** for energy.
3. **Stops with a clear error** if it meets a unit it does not know, instead of guessing.

If that error ever appears, add the unit to `UNIT_FACTORS` in `backend/app/scripts/import_fineli.py`.

### 4.3 The `ACQTYPE`, `METHTYPE`, `METHIND` columns

Every value in `component_value.csv` also records how it was obtained (for example `S`, `F`, `E` and a method code like `MI0107`). We ignore these today. They could later power a "data quality" indicator, for example flagging values that were estimated or imputed rather than measured. The meanings are in the `acqtype_EN.csv` and `methtype_EN.csv` files ⚠️.

---

## 5. How our importer works

**Where:** `backend/app/scripts/import_fineli.py`

**Download and stage the input files** (manual download, then stage from `backend/`):

```powershell
python -m app.scripts.download_fineli
```

First download the Fineli Rel20 nutrient-data ZIP in your browser and move it to the
repository root, keeping the filename `Fineli_Rel20__74_ravintotekij__.zip`. The
script does not download the archive; it looks for that exact file at the project
root, then stages the nine required CSVs in `backend/data/fineli/`. The archive and
the `backend/data/` folder are gitignored. To use another staging directory, pass
`--output-dir`.

The script validates that the archive contains all nine required CSVs before
staging them.

**Run the importer** (from `backend/`, with the database running):

```powershell
.\.venv\Scripts\python.exe -m app.scripts.import_fineli
# or from another folder:
.\.venv\Scripts\python.exe -m app.scripts.import_fineli --data-dir "C:\path\to\fineli"
```

**Input:** these nine files in `backend/data/fineli/` (gitignored, never committed):

`food.csv`, `foodname_EN.csv`, `component.csv`, `eufdname_EN.csv`, `cmpclass_EN.csv`, `compunit_EN.csv`, `component_value.csv`, `foodaddunit.csv`, `foodunit_EN.csv`

**Steps:**

1. Check that all nine files exist, otherwise stop and name the missing ones.
2. Read each normalized field's units from `component.csv` and `compunit_EN.csv`; stop on unsupported units. Detailed values retain Fineli's source unit.
3. Read every component definition with its English name (`eufdname_EN.csv`), display unit, and component group (`cmpclass_EN.csv`).
4. Read `component_value.csv`, parse decimal commas, retain every numeric component value per 100 g, and leave blank or non-numeric values missing. The current implementation reads the CSV into memory rather than streaming it.
5. Build one record per food: Finnish name (from `food.csv`), English name (from `foodname_EN.csv`), normalized fields, and derived kcal.
6. Build unit conversions from `foodaddunit.csv`, with readable names from `foodunit_EN.csv`. Rows for unknown foods or with unreadable mass are skipped.
7. Create the required tables if absent, then replace the Fineli catalog in a database transaction. **Re-running is safe**; each successful run replaces the previous imported dataset.

**Output tables:**

| Table | Columns | Rows (roughly) |
| --- | --- | --- |
| `fineli_foods` | `id` (FOODID, text), `name_fi`, `name_en`, `energy_kj`, `energy_kcal`, `protein_g`, `carbohydrates_g`, `fat_g`, `fiber_g`, `salt_g`, `sugars_g`, `saturated_fat_g` (nullable floats) | a few thousand ⚠️ |
| `fineli_components` | component code, English name, source unit, group label | all component definitions in the release |
| `fineli_food_nutrients` | food ID, component code, numeric value per 100 g in the component's Fineli unit | numeric food/component pairs |
| `fineli_food_units` | `food_id`, `unit_code`, `unit_name`, `grams` | tens of thousands ⚠️ |

**How the backend reads it:**

- `LocalFineliClient` (`app/integrations/fineli/local_client.py`) has the same `search_foods` and `get_food` methods as the old HTTP client.
- `get_fineli_client(db)` (`factory.py`) always returns the local dataset client. Ingredient search and nutrition recalculation do not call Fineli's HTTP API.
- Search is a case-insensitive "contains" match on English and Finnish names. Results are ranked exact match first, then prefix match, then shorter names first, and limited to 20.
- Detailed nutrients and food-specific unit weights are loaded locally with the food.
- `/api/ingredients/suggestions?q=...` returns up to five normalized/alias-ranked candidates; alias mapping never confirms a match automatically.
- An unknown food id gives **404** from `/api/ingredients/{id}`. During nutrition recalculation it is reported as a skipped ingredient (`food_not_found`); it does not fail the whole recipe.

When Fineli publishes a new release, update the `FINELI_RELEASE` constant in `local_client.py` so the attribution text stays correct.

---

## 6. Refining the data

Sections 6.1, 6.3, and 6.4 describe implemented behavior. Sections 6.2, 6.5,
and 6.6 identify data-quality improvements not currently applied to estimates.

### 6.1 Ingredient matching in the application

TheMealDB names such as `Chicken Breasts`, `Plain Flour`, and `Olive Oil` do not
always match Fineli naming. `GET /api/ingredients/suggestions?q=...` applies
deterministic text normalization, a small reviewed alias list in
`backend/app/data/fineli-ingredient-aliases.json`, and candidate ranking; it
returns at most five results. An alias only influences suggestions. The user
must choose a result explicitly before its Fineli ID/name is stored on the
ingredient. The source ingredient label and measure remain unchanged.

Maintain aliases as reviewed suggestions, not as nutritional equivalences.
Inspect the Fineli food description and processing state before confirming a
match. Fuzzy matching or silently confirming the first result is not enabled.

### 6.2 Future improvement: prefer basic foods over composite dishes

⚠️ `food.csv` has `FOODTYPE` and `PROCESS` columns (the sample rows show `FOOD` and `IND`). Fineli also contains composite foods and dishes built from recipe rows (`contribfood.csv`). When a user types "potato", they almost certainly mean the raw ingredient, not a prepared dish.

Before filtering, **inspect the distinct values** of `FOODTYPE`, `PROCESS`, `IGCLASS` and read their meanings in `foodtype_EN.csv`, `process_EN.csv` and `igclass_EN.csv`. Then:

- Import `FOODTYPE`, `PROCESS` and `IGCLASS` into `fineli_foods`.
- Rank basic foods above dishes in search, or filter dishes out of ingredient search.
- Consider showing the processing state ("raw", "cooked", "boiled") next to the name. The difference between raw and cooked rice is large, and users need to see which one they picked.

### 6.3 Quantities: from "2 tbsp" to grams

Nutrition values are per 100 g. The current measure parser in
`backend/app/integrations/fineli/measure.py` accepts positive metric grams and
kilograms, fractions/mixed fractions for supported expressions, and a reviewed
set of household-unit names/codes when the selected food has a corresponding
Fineli `foodaddunit` entry. Household conversions are marked `estimated`;
metric conversions are `exact`.

Ranges, qualitative measures, unsupported units, and volume units without a
food-specific Fineli conversion remain unknown. No generic density conversion
is used. The original TheMealDB measure is retained even after a conversion;
an unknown conversion has no grams and is shown as a skipped ingredient in the
estimate.

### 6.4 Handle missing nutrient values deliberately

The estimate includes a confirmed, weighted ingredient when it has at least one
known normalized or detailed nutrient. Missing individual nutrients remain
`null` in normalized totals and absent from detailed totals; they are never
replaced with zero. Ingredients without a match, usable grams, an available
Fineli ID, or usable nutrients get an explicit skipped reason in the response.
The response status is `completed`, `partial`, or `unavailable`, with coverage
over all recipe ingredients. The UI shows partial totals at every nonzero
coverage and states when nothing could contribute.

### 6.5 Edible portion

⚠️ `food.csv` has an `EDPORT` column (edible portion, percent). For foods with waste (bananas with peel, fish with bones) it tells how much of the *whole item* you can eat. We do **not** apply it. We treat nutrient values as per 100 g as given. This is right when the recipe quantity is the edible amount ("200 g peeled banana") and wrong when it is the as-purchased amount ("2 whole bananas"). Confirm the exact meaning in Fineli's documentation before using `EDPORT` in calculations.

### 6.6 Search quality

- **Language:** search currently covers both English and Finnish names. Matching is case-insensitive, but neither language is preferred over the other.
- **Synonyms and spelling variants:** `aubergine`/`eggplant`, `courgette`/`zucchini`, `coriander`/`cilantro`. These belong in the alias table (6.1).
- **Performance:** a few thousand rows searched with `LIKE` is instant. Only add `pg_trgm` or full-text search for fuzzy matching, not for speed.

---

## 7. Updating to a new Fineli release

1. Confirm the archive URL and release you intend to use. For a new release, inspect its `descript.txt` and schema before importing; the downloader does not retain the ZIP or stage `descript.txt`.
2. Download the package in your browser, place `Fineli_Rel20__74_ravintotekij__.zip` in the repository root, and run `python -m app.scripts.download_fineli` from `backend/`.
3. With the database running, run `python -m app.scripts.import_fineli` from `backend/`. It replaces the existing imported Fineli rows.
4. Update `FINELI_RELEASE` in `app/integrations/fineli/local_client.py` to match the release you imported.
5. Run the backend test suite (`python -m pytest -q`).
6. **Check for orphaned ids.** Food ids can disappear or change between releases. Nutrition recalculation reports an obsolete selected ID as `food_not_found` and excludes that ingredient without failing the rest of the recipe. Find them:

```sql
SELECT i.id, i.name, i.fineli_id
FROM ingredients i
LEFT JOIN fineli_foods f ON f.id = i.fineli_id
WHERE i.fineli_id IS NOT NULL AND f.id IS NULL;
```

7. Spot-check several foods you know well (for example milk, rice, or olive oil) against the Fineli website.
8. Recheck release metadata, attribution/license conditions and the downloaded `descript.txt`. Historical calculation runs retain ingredient-level nutrient contribution snapshots; new calculations use the currently imported release. Public release remains blocked until provider terms and redistribution conditions are verified.

---

## 8. Hands-on checks (PowerShell)

Run the CSV checks from `backend/data/fineli/` after downloading the files. Run database and API checks from `backend/` unless stated otherwise.

### 8.1 Find non-numeric values in `component_value.csv`

This reports non-numeric values in `BESTLOC` for review. It can take a while and uses memory proportional to the file size. The importer currently treats such values as missing; do not map a marker to zero without confirming its meaning in the release documentation.

```powershell
$latin1 = [System.Text.Encoding]::GetEncoding(28591)
$rows = [System.IO.File]::ReadAllLines("$PWD\component_value.csv", $latin1) | ConvertFrom-Csv -Delimiter ';'
$rows |
    Where-Object { $_.BESTLOC -and $_.BESTLOC -notmatch '^-?\d+(,\d+)?$' } |
    Group-Object BESTLOC | Sort-Object Count -Descending |
    Select-Object Name, Count -First 15
```

An empty result means every value is a plain number. Anything else is a marker to handle.

### 8.2 Read a file with the right encoding

PowerShell guesses the encoding, which is why `Ä` shows as `�`. Be explicit:

```powershell
$latin1 = [System.Text.Encoding]::GetEncoding(28591)
[System.IO.File]::ReadAllLines("$PWD\food.csv", $latin1) | Select-Object -First 5
```

If your terminal still shows odd characters, run `chcp 65001` first or use VS Code's file viewer, which is independent of the terminal.

### 8.3 How complete is the imported data?

Run from `backend/` after the import:

```powershell
@'
from sqlalchemy import func, select
from app.database import SessionLocal
from app.models import FineliFood as F

db = SessionLocal()
total = db.scalar(select(func.count()).select_from(F))
print("foods:", total)
for col in ["energy_kcal", "protein_g", "carbohydrates_g", "fat_g",
            "fiber_g", "salt_g", "sugars_g", "saturated_fat_g"]:
    missing = db.scalar(select(func.count()).select_from(F).where(getattr(F, col).is_(None)))
    print(f"{col:18} missing: {missing:5}  ({100 * missing / total:.0f}%)")
without_en = db.scalar(select(func.count()).select_from(F).where(F.name_en.is_(None)))
print("without English name:", without_en)
'@ | .\.venv\Scripts\python.exe -
```

Read the result like this:

- `without English name` high: matching TheMealDB ingredients will be harder, plan for the alias table.
- The four required fields (`energy_kcal`, `protein_g`, `carbohydrates_g`, `fat_g`) missing for many foods: see section 6.4.

### 8.4 Look at a few foods through the API

With the backend running (`uvicorn app.main:app --reload`):

```powershell
Invoke-RestMethod "http://localhost:8000/api/ingredients/search?q=milk" |
    Select-Object id, name, @{n='kcal'; e={$_.nutrients_per_100g.energy_kcal}}, @{n='protein'; e={$_.nutrients_per_100g.protein_g}}

Invoke-RestMethod "http://localhost:8000/api/ingredients/1" | ConvertTo-Json -Depth 5
```

---

## 9. Testing

`backend/tests/test_fineli_local.py` builds small fake Fineli files in the real format (Latin-1 bytes, `;` separators, decimal commas, and Finnish characters) and checks:

- decimal-comma parsing, blank means `None`, genuine `0` stays `0`
- unit conversion (mg to g) and the `FIBT` fallback for fibre
- detailed component labels, source units/groups, numeric values and food-specific unit weights
- search in English and Finnish, ranking, and that `100%` is treated as literal text
- unknown food id gives 404 on the ingredient route and a skipped outcome during recalculation
- complete and partial recalculations, per-serving totals, zero coverage, snapshots, and unknown-vs-zero nutrients
- exact metric conversion, food-specific household conversion, and unsupported measure handling
- a clear error when data files are missing

`backend/tests/test_fineli_downloader.py` checks that the downloader stages the required files from a nested ZIP and reports missing files.

Tests never touch the real Fineli data, so they run anywhere. Nutrition route tests mock the local client; separate integration-client tests only verify the legacy HTTP client's response mapping and do not make network requests.

---

## 10. Troubleshooting

| Problem | Likely cause | Fix |
| --- | --- | --- |
| `FileNotFoundError: Missing in ...: food.csv, ...` | The package has not been downloaded/staged, or a custom data directory is incomplete | Run `python -m app.scripts.download_fineli` from `backend/`, or provide the complete CSV set (section 5) |
| `ValueError: Unknown unit '...' ... for component ...` | A nutrient uses a unit we have not mapped | Add it to `UNIT_FACTORS` in `import_fineli.py` |
| Search returns nothing | Dataset has not been downloaded and imported, or query has no matches | Run the downloader and importer, then retry |
| An ingredient is skipped as `food_not_found` | The selected ID is not in the imported data (typo, or removed in a new release) | Re-match the ingredient (section 7) |
| An ingredient is skipped as `missing_nutrients` | Fineli has no usable nutrient values for that food | See section 6.4 |
| Coverage is partial or zero | Some matches, conversions, or nutrient values are missing | Review the per-ingredient skipped reasons; do not infer missing values |
| Names look like `H�D` in the terminal | Terminal display only | Section 8.2. The database is fine if the importer decoded the file as Latin-1 |
| Names look like `HÃ„D` in the database | File decoded as the wrong encoding | The file is Latin-1; check that the importer fell back from UTF-8 correctly |
| Import is slow or memory use is high | `component_value.csv` is large; the current importer reads it into memory | Allow the import to finish; if this becomes a recurring issue, optimize the importer to stream rows |
| Connection refused during import | Database not running | `docker compose up -d` from the repo root |

---

## 11. Release checks still required

1. Fineli's official open-data/API pages returned HTTP 403 during the 2026-11-09 research and verification attempts. The downloaded Rel20 `descript.txt` states CC BY 4.0 and names THL as copyright holder. Reconfirm current license, attribution, access, and redistribution terms from the official source before public release.
2. The importer validates known dataset component units and names but does not assess every nutrient's analytical quality or method. Preserve release metadata and avoid interpreting missing values as zero.
3. This application does not apply edible-portion adjustments or make diet/allergen safety conclusions.

---

## 12. Quick reference

| Item | Value |
| --- | --- |
| Data source | Fineli nutrient data package; release currently recorded as 20.0 in the app |
| License | CC BY 4.0, attribution required |
| File format | `;` separated, decimal comma; importer tries UTF-8 then Latin-1 |
| Key identifiers | `FOODID` (food), `EUFDNAME` (nutrient code), `THSCODE` (classification code) |
| Energy | `ENERC` is kJ; kcal = kJ / 4.184 |
| Values are | per 100 g |
| Detailed values | all imported numeric component values, each with source unit and group |
| Import command | `python -m app.scripts.import_fineli` (from `backend/`) |
| Download command | `python -m app.scripts.download_fineli` (from `backend/`) |
| Data folder (gitignored) | `backend/data/fineli/` |
| Fineli lookup source | Imported local dataset; online API is not used |
| Tables | `fineli_foods`, `fineli_components`, `fineli_food_nutrients`, `fineli_food_units` |
| Match policy | Ranked suggestions only; user confirmation required |
| Estimate policy | Partial totals with coverage and per-ingredient skipped reasons; missing remains unknown |
| Key code | `app/scripts/import_fineli.py`, `app/integrations/fineli/local_client.py`, `app/integrations/fineli/measure.py`, `app/routers/nutrition.py` |
