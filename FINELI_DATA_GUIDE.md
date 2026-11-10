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
| License | Creative Commons Attribution 4.0 (CC BY 4.0) | ✅ (stated in `descript.txt`) |
| Copyright holder | THL (Terveyden ja hyvinvoinnin laitos) | ✅ |
| Format | Plain text CSV files, `;` separated | ✅ |
| Liability | THL is not liable for errors or misinterpretation | ✅ |

### Why we use the downloaded package instead of the API

Fineli's web API has blocked requests from our backend in the current setup. The downloadable package provides the data needed by the app, so we import it into our database and query that by default. Local lookups avoid API availability and rate-limit issues and are deterministic in tests.

### Where Fineli data appears in the app

The imported dataset powers Fineli ingredient matching and recipe nutrition estimates.
The meal search page supports importing external recipes, and saved recipe details let
users confirm ingredient matches and view nutrition coverage and totals.

With the backend running, try a lookup in a browser or PowerShell:

```text
http://localhost:8000/api/ingredients/search?q=sugar
```

The response includes matching foods, nutrient values per 100 g, and Fineli/THL source
attribution. The same endpoint is listed in the interactive API docs at
`http://localhost:8000/docs` under **ingredients → GET `/api/ingredients/search`**.
Recipe details display Fineli matches and calculated nutrition after the user confirms
the suggested food.

### Attribution (required by CC BY 4.0)

Wherever we show Fineli-derived data, include the required attribution. The backend includes this text in Fineli food responses:

> Source: Fineli, Finnish Institute for Health and Welfare (THL), release 20.0, CC BY 4.0

Keep the attribution visible or readily accessible when changing the UI. The importer derives kcal from kJ, and the recipe endpoint calculates totals from per-100-g values; make those transformations clear in the product.

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

- `fuclass_*` could enrich food labels and improve ingredient search and ranking.
- `specdiet.csv` and `specdiet_*` could support special-diet labels or filters;
  these classifications should not be treated as allergen-safety guarantees.
- `foodname_SV.csv` and `foodname_TX.csv` could add Swedish and scientific-name
  search.
- `eufdname_*` and `cmpclass_*` could provide readable names and groupings if more
  nutrient fields are exposed.
- `contribfood.csv`, `acqtype_*`, `methtype_*`, `methind_*` and `publication.csv`
  could support future composite-food explanations or nutrient-value provenance,
  but require additional interpretation and validation.

The downloader stages the twelve CSVs required by the importer. The
`foodtype_EN.csv`, `process_EN.csv`, and `igclass_EN.csv` lookup files are used
to analyze the classification codes; the importer stores the original codes.

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

Other codes worth knowing: `NA` (sodium), `FAPU` (polyunsaturated fat), `FAMCIS` (monounsaturated cis fat), `FATRN` (trans fat), `XENERC` (energy calculated without fibre). The component list contains about 190 codes, mostly individual fatty acids (`F18D2CN6` and so on) and a few vitamins and minerals. Add more columns only when the UI needs them.

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
root, then stages the twelve required CSVs in `backend/data/fineli/`. The archive and
the `backend/data/` folder are gitignored. To use another staging directory, pass
`--output-dir`.

The script validates that the archive contains all twelve required CSVs before
staging them.

**Run the importer** (from `backend/`, with the database running):

```powershell
.\.venv\Scripts\python.exe -m app.scripts.import_fineli
# or from another folder:
.\.venv\Scripts\python.exe -m app.scripts.import_fineli --data-dir "C:\path\to\fineli"
```

**Update an existing database schema** (from `backend/`):

```powershell
.\.venv\Scripts\python.exe -m app.scripts.migrate_db
```

The migration is additive and idempotent. It creates missing tables and adds only
the nullable `food_type`, `process`, and `ingredient_class` columns to
`fineli_foods`; it does not delete or truncate data. Application startup performs
the same check automatically.

**Input:** these twelve files in `backend/data/fineli/` (gitignored, never committed):

`food.csv`, `foodname_EN.csv`, `component.csv`, `eufdname_EN.csv`,
`cmpclass_EN.csv`, `compunit_EN.csv`,
`component_value.csv`, `foodaddunit.csv`, `foodunit_EN.csv`,
`foodtype_EN.csv`, `process_EN.csv`, `igclass_EN.csv`

**Steps:**

1. Check that all twelve files exist, otherwise stop and name the missing ones.
2. Read each normalized nutrient's unit from `component.csv` and `compunit_EN.csv`. Stop on unknown units.
3. Read `component_value.csv`, retain the normalized nutrients used by the app and every detailed numeric component value per 100 g, parse decimal commas, convert normalized values, and treat blank or non-numeric values as missing. Detailed values retain Fineli's source unit.
4. Read `FOODTYPE`, `PROCESS`, and `IGCLASS` directly from `food.csv`. Blank values become NULL; unknown codes are preserved.
5. Build one record per food: Finnish name (from `food.csv`), English name (from `foodname_EN.csv`), classification codes, nutrients, and derived kcal.
6. Build unit conversions from `foodaddunit.csv`, with readable names from `foodunit_EN.csv`. Rows for unknown foods or with unreadable mass are skipped.
7. Replace the normalized foods, unit conversions, component definitions, and detailed nutrient values in a database transaction. **Re-running is safe**; each successful run replaces the previous imported dataset.

The importer prints a classification analysis after a successful import. For
each field it reports the number of distinct codes, missing values, English
descriptions found by `THSCODE` plus `LANG=EN`, and codes without a description.
The repository does not contain the downloadable Fineli archive, so the exact
Rel20 counts and descriptions must be generated from the staged release; no
unverified values are listed here as confirmed facts.

**Output tables:**

| Table | Columns | Rows (roughly) |
| --- | --- | --- |
| `fineli_foods` | `id` (FOODID, text), `name_fi`, `name_en`, `food_type`, `process`, `ingredient_class`, nutrient columns (nullable floats) | a few thousand ⚠️ |
| `fineli_food_units` | `food_id`, `unit_code`, `unit_name`, `grams` | tens of thousands ⚠️ |
| `fineli_components` | component code, English name, source unit, group label | all component definitions in the release |
| `fineli_food_nutrients` | food ID, component code, numeric value per 100 g in the component's Fineli unit | numeric food/component pairs |

**How the backend reads it:**

- `LocalFineliClient` (`app/integrations/fineli/local_client.py`) has the same `search_foods` and `get_food` methods as the old HTTP client.
- `get_fineli_client(db)` (`factory.py`) always returns the local dataset client. Ingredient search and nutrition recalculation do not call Fineli's HTTP API.
- Search is a case-insensitive "contains" match on English and Finnish names. Results are ranked exact match first, then prefix match, then shorter names first, and limited to 20.
- Fineli search and single-food responses also include nullable `food_type`,
  `process`, and `ingredient_class` code fields.
- Detailed nutrients and food-specific unit weights are loaded locally with each food.
- `/api/ingredients/suggestions?q=...` returns up to five normalized/alias-ranked candidates; alias mapping never confirms a match automatically.
- An unknown food id gives **404** from `/api/ingredients/{id}`. During nutrition recalculation it is reported as a skipped ingredient (`food_not_found`); it does not fail the whole recipe.

When Fineli publishes a new release, update the `FINELI_RELEASE` constant in `local_client.py` so the attribution text stays correct.

---

## 6. Refining the data

The current implementation imports the nutrient fields and household-unit rows described above. The items below are product and data-quality improvements, not claims about existing behavior; section 6.1 and the search notes in 6.6 describe the current search behavior where relevant.

### 6.1 Make ingredient matching work (highest impact)

TheMealDB gives ingredient names like `Chicken Breasts`, `Plain Flour`, `Olive Oil`. Fineli names follow their own conventions. A naive "contains" search finds too much or nothing.

The implemented suggestion endpoint normalizes ingredient names and applies the
curated aliases in `backend/app/data/fineli-ingredient-aliases.json` before
searching both the alias and original phrase. The alias file covers common
English/US/UK terms, spelling variants, pasta shapes, produce names, pantry
ingredients, and broad meat/dairy terms. Targets are based on names present in
the imported Fineli release.

Aliases only broaden the candidate search; they do not assert that two foods
have identical nutrient profiles or automatically save a match. The user must
confirm a specific Fineli food. For example, `penne rigate` can suggest the
closest available general pasta records, but this release has no exact penne
entry. Review the alias file against new recipe inputs and Fineli releases, and
avoid aliases that imply a false equivalence.

### 6.2 Prefer basic foods over composite dishes

⚠️ `food.csv` has `FOODTYPE` and `PROCESS` columns (the sample rows show `FOOD` and `IND`). Fineli also contains composite foods and dishes built from recipe rows (`contribfood.csv`). When a user types "potato", they almost certainly mean the raw ingredient, not a prepared dish.

The importer now preserves the source codes and prints the distinct values and
their lookup descriptions. Before filtering, **inspect those results** for the
exact release and read their meanings in `foodtype_EN.csv`, `process_EN.csv`
and `igclass_EN.csv`. Then:

- Import `FOODTYPE`, `PROCESS` and `IGCLASS` into `fineli_foods`.
- Rank basic foods above dishes in search, or filter dishes out of ingredient search.
- Consider showing the processing state ("raw", "cooked", "boiled") next to the name. The difference between raw and cooked rice is large, and users need to see which one they picked.

### 6.3 Quantities: from "2 tbsp" to grams

Our nutrition calculation currently accepts only `g` and `kg`, because Fineli values are per 100 g. TheMealDB measures are strings (`1 tbsp`, `2 cloves`, `200g`, `1/2 cup`). The `fineli_food_units` table is the bridge.

Plan:

1. **Parse** the measure string into a quantity and a unit. Handle fractions (`1/2`), ranges, and "a pinch".
2. **Direct metric units:** `g`, `kg` need no lookup. `ml` and `l` need a density, see below.
3. **Household units:** map the parsed unit (tbsp, tsp, cup, clove, slice, piece) to a Fineli unit code, then look up grams in `fineli_food_units` for the chosen food. ⚠️ Codes seen so far include `KG`, `DL`, `L`, `PORTM`, `PORTL`, `KPL_S`. Read `foodunit_EN.csv` in full to build the mapping; do not guess what each code means.
4. **No conversion available?** Do not silently guess. Mark the ingredient with a status. The `IngredientRead` schema already has a `conversion_status` field for this. For example `exact`, `estimated`, `unknown`. Show totals as "partial" when anything is unknown.
5. **Volume to weight** (when only `foodaddunit` has `DL` for the food): `DL` gives grams per decilitre, so `1 dl = mass_g`, and `1 tbsp` is 0.15 dl (15 ml), `1 tsp` is 0.05 dl, `1 cup` is about 2.4 dl. This is an approximation; label it "estimated".

### 6.4 Handle missing nutrient values deliberately

The nutrition endpoint preserves available nutrient values and reports calculation coverage
alongside each ingredient's included/skipped status and reason. Missing values are not
silently treated as zero. The estimate is approximate and must not be used to determine
allergen or dietary safety.

Fix this at the source too: after the first import, count how many foods have missing required fields (section 8.3). If a significant share of common foods is affected, check whether the missing values have a documented alternative code (for example a food that has `CHOCDF` but no `CHOAVL`).

### 6.5 Edible portion

⚠️ `food.csv` has an `EDPORT` column (edible portion, percent). For foods with waste (bananas with peel, fish with bones) it tells how much of the *whole item* you can eat. We do **not** apply it. We treat nutrient values as per 100 g as given. This is right when the recipe quantity is the edible amount ("200 g peeled banana") and wrong when it is the as-purchased amount ("2 whole bananas"). Confirm the exact meaning in Fineli's documentation before using `EDPORT` in calculations.

### 6.6 Search quality

- **Language:** search currently covers both English and Finnish names. Matching is case-insensitive, but neither language is preferred over the other.
- **Synonyms and spelling variants:** the curated alias table maps common variants such as `eggplant`/`aubergine`, `courgette`/`zucchini`, `cilantro`/`coriander`, and `penne rigate` to available broader pasta candidates. These mappings are suggestions only.
- **Performance:** a few thousand rows searched with `LIKE` is instant. Only add `pg_trgm` or full-text search for fuzzy matching, not for speed.

---

## 7. Updating to a new Fineli release

1. Confirm the archive URL and release you intend to use. For a new release, inspect its `descript.txt` and schema before importing; the downloader does not retain the ZIP or stage `descript.txt`.
2. Download the package in your browser, place `Fineli_Rel20__74_ravintotekij__.zip` in the repository root, and run `python -m app.scripts.download_fineli` from `backend/`.
3. With the database running, run `python -m app.scripts.import_fineli` from `backend/`. It replaces the existing imported Fineli rows.
4. Update `FINELI_RELEASE` in `app/integrations/fineli/local_client.py` to match the release you imported.
5. Run the backend test suite (`python -m pytest -q`).
6. **Check for orphaned ids.** Food ids can disappear or change between releases. Such
ingredients are reported as skipped (`food_not_found`) during recalculation. Find them:

```sql
SELECT i.id, i.name, i.fineli_id
FROM ingredients i
LEFT JOIN fineli_foods f ON f.id = i.fineli_id
WHERE i.fineli_id IS NOT NULL AND f.id IS NULL;
```

7. Spot-check several foods you know well (for example milk, rice, or olive oil) against the Fineli website.

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
- search in English and Finnish, ranking, and that `100%` is treated as literal text
- unknown food id gives 404 on the ingredient route and is reported as skipped during recalculation
- a complete recalculation with correct totals, and rejection when a required nutrient is missing
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
| Ingredient skipped: `food_not_found` | The id is not in the imported data (typo, or removed in a new release) | Re-match the ingredient (section 7 step 7) |
| Incomplete nutrition coverage | The ingredient is unmatched, has an unsupported quantity, or lacks usable data | Review the ingredient results and match or update quantities |
| Names look like `H�D` in the terminal | Terminal display only | Section 8.2. The database is fine if the importer decoded the file as Latin-1 |
| Names look like `HÃ„D` in the database | File decoded as the wrong encoding | The file is Latin-1; check that the importer fell back from UTF-8 correctly |
| Import is slow or memory use is high | `component_value.csv` is large; the current importer reads it into memory | Allow the import to finish; if this becomes a recurring issue, optimize the importer to stream rows |
| Connection refused during import | Database not running | `docker compose up -d` from the repo root |

---

## 11. Open questions to resolve

These are the unverified items collected from this document. Settle them once, then update the guide.

1. Does the current release define non-numeric `BESTLOC` markers beyond blanks? (section 8.1)
2. Which units do `NACL` and the other nutrients use in `compunit_EN.csv`? The importer reads them, but note the results.
3. Which exact `FOODTYPE`, `PROCESS` and `IGCLASS` values occur in the staged release, and how do we separate basic foods from dishes? Run the importer analysis; no filter is implemented yet. (section 6.2)
4. What does each household unit code mean (`PORTM`, `PORTL`, `KPL_S`, ...)? Read `foodunit_EN.csv`. (section 6.3)
5. How should `EDPORT` be used, if at all? (section 6.5)
6. How many foods lack English names or any of the four required nutrients? (section 8.3)

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
| Import command | `python -m app.scripts.import_fineli` (from `backend/`) |
| Download command | `python -m app.scripts.download_fineli` (from `backend/`) |
| Data folder (gitignored) | `backend/data/fineli/` |
| Fineli lookup source | Imported local dataset; online API is not used |
| Tables | `fineli_foods`, `fineli_food_units` |
| Key code | `app/scripts/import_fineli.py`, `app/integrations/fineli/local_client.py`, `factory.py` |
