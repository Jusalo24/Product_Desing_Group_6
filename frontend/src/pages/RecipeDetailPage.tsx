import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type {
  DetailedNutrientTotal,
  FineliFood,
  NutritionIngredientResult,
  NutritionResponse,
  Recipe,
} from "../types";
import "../styles/RecipeDetailPage.css";

type EditableIngredient = {
  name: string;
  amount: string;
  quantity: string;
  unit: "g" | "kg";
  fineli_id: string | null;
  conversion_status?: string;
  dirty: boolean;
};

export default function RecipeDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [nutrition, setNutrition] = useState<NutritionResponse | null>(null);
  const [nutritionLoading, setNutritionLoading] = useState(false);
  const [nutritionError, setNutritionError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editingIngredients, setEditingIngredients] = useState(false);
  const [draftIngredients, setDraftIngredients] = useState<EditableIngredient[]>([]);
  const [savingIngredients, setSavingIngredients] = useState(false);
  const [ingredientError, setIngredientError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, FineliFood[]>>({});
  const [openMatchPanels, setOpenMatchPanels] = useState<Record<number, boolean>>({});
  const [matchQueries, setMatchQueries] = useState<Record<number, string>>({});
  const [busyIngredientIds, setBusyIngredientIds] = useState<Record<number, boolean>>({});
  const [autoMatching, setAutoMatching] = useState(false);
  const [matchErrors, setMatchErrors] = useState<Record<number, string>>({});
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function closeMenu(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function closeMenuWithEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", closeMenu);
    document.addEventListener("keydown", closeMenuWithEscape);
    return () => {
      document.removeEventListener("mousedown", closeMenu);
      document.removeEventListener("keydown", closeMenuWithEscape);
    };
  }, []);

  useEffect(() => {
    let active = true;
    api
      .getRecipe(Number(id))
      .then((loadedRecipe) => {
        if (active) setRecipe(loadedRecipe);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    api
      .getNutrition(Number(id))
      .then((estimate) => {
        if (active) setNutrition(estimate);
      })
      .catch((e: Error) => {
        if (active && !e.message.startsWith("404 ")) setNutritionError(e.message);
      });
    return () => {
      active = false;
    };
  }, [id]);

  async function refreshNutrition(recipeId: number) {
    setNutritionLoading(true);
    setNutritionError(null);
    try {
      setNutrition(await api.recalculateNutrition(recipeId));
    } catch (e) {
      setNutritionError(
        e instanceof Error ? e.message : "Could not calculate nutrition.",
      );
    } finally {
      setNutritionLoading(false);
    }
  }

  async function calculateNutrition() {
    if (!recipe) return;
    await refreshNutrition(recipe.id);
  }

  async function findFineliMatches(ingredientId: number, query: string) {
    const trimmed = query.trim();
    setOpenMatchPanels((current) => ({ ...current, [ingredientId]: true }));
    setMatchQueries((current) => ({ ...current, [ingredientId]: query }));
    if (!trimmed) {
      setMatchErrors((errors) => ({
        ...errors,
        [ingredientId]: "Enter a search term for Fineli.",
      }));
      return;
    }
    setBusyIngredientIds((current) => ({ ...current, [ingredientId]: true }));
    setMatchErrors((errors) => ({ ...errors, [ingredientId]: "" }));
    try {
      const candidates = await api.suggestIngredients(trimmed);
      setSuggestions((current) => ({ ...current, [ingredientId]: candidates }));
    } catch (err) {
      setMatchErrors((errors) => ({
        ...errors,
        [ingredientId]: err instanceof Error ? err.message : "Could not search Fineli foods.",
      }));
    } finally {
      setBusyIngredientIds((current) => ({ ...current, [ingredientId]: false }));
    }
  }

  function closeMatchPanel(ingredientId: number) {
    setOpenMatchPanels((current) => ({ ...current, [ingredientId]: false }));
    setMatchErrors((errors) => ({ ...errors, [ingredientId]: "" }));
  }

  async function confirmFineliMatch(ingredientId: number, food: FineliFood) {
    if (!recipe) return;
    setBusyIngredientIds((current) => ({ ...current, [ingredientId]: true }));
    setMatchErrors((errors) => ({ ...errors, [ingredientId]: "" }));
    try {
      const matched = await api.matchIngredient(recipe.id, ingredientId, food.id);
      setRecipe((current) =>
        current
          ? {
              ...current,
              ingredients: current.ingredients.map((item) =>
                item.id === ingredientId ? matched : item,
              ),
            }
          : current,
      );
      setNutrition(null);
      setSuggestions((current) => {
        const next = { ...current };
        delete next[ingredientId];
        return next;
      });
      setOpenMatchPanels((current) => ({ ...current, [ingredientId]: false }));
      setBusyIngredientIds((current) => ({ ...current, [ingredientId]: false }));
      await refreshNutrition(recipe.id);
    } catch (err) {
      setMatchErrors((errors) => ({
        ...errors,
        [ingredientId]: err instanceof Error ? err.message : "Could not save Fineli match.",
      }));
    } finally {
      setBusyIngredientIds((current) => ({ ...current, [ingredientId]: false }));
    }
  }

  async function autoMatchAll() {
    if (!recipe) return;
    setAutoMatching(true);
    setIngredientError(null);
    try {
      const updated = await api.autoMatchIngredients(recipe.id);
      setRecipe(updated);
      setNutrition(null);
      await refreshNutrition(updated.id);
    } catch (err) {
      setIngredientError(
        err instanceof Error ? err.message : "Could not auto-match ingredients.",
      );
    } finally {
      setAutoMatching(false);
    }
  }

  async function handleDelete() {
    if (!recipe || !window.confirm("Delete this recipe?")) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteRecipe(recipe.id);
      navigate("/my-recipes");
    } catch (e) {
      setDeleteError(
        e instanceof Error
          ? `Could not delete recipe: ${e.message}`
          : "Could not delete recipe.",
      );
    } finally {
      setDeleting(false);
    }
  }

  function startEditingIngredients() {
    setMenuOpen(false);
    setIngredientError(null);
    setDraftIngredients(
      recipe?.ingredients.map((ingredient) => ({
        name: ingredient.name,
        amount: ingredient.amount,
        quantity: ingredient.quantity?.toString() ?? "",
        unit: ingredient.unit === "kg" ? "kg" : "g",
        fineli_id: ingredient.fineli_id ?? null,
        conversion_status: ingredient.conversion_status,
        dirty: false,
      })) ?? [],
    );
    setEditingIngredients(true);
  }

  function cancelEditingIngredients() {
    setEditingIngredients(false);
    setIngredientError(null);
  }

  async function saveIngredients() {
    if (!recipe) return;
    const hasInvalidQuantity = draftIngredients.some((ingredient) => {
      const trimmed = ingredient.quantity.trim();
      if (!trimmed) {
        return false;
      }
      const parsed = Number(trimmed);
      return !Number.isFinite(parsed) || parsed <= 0;
    });
    if (hasInvalidQuantity) {
      setIngredientError("Amounts must be positive numbers.");
      return;
    }

    setSavingIngredients(true);
    setIngredientError(null);
    try {
      const updated = await api.updateIngredients(recipe.id, {
        ingredients: draftIngredients.map((ingredient) => {
          const trimmed = ingredient.quantity.trim();
          const hasQty = trimmed !== "";
          const qtyValue = hasQty ? Number(trimmed) : null;
          return {
            name: ingredient.name,
            amount:
              ingredient.dirty && hasQty
                ? `${trimmed} ${ingredient.unit}`
                : ingredient.amount,
            quantity: qtyValue,
            unit: hasQty ? ingredient.unit : null,
            fineli_id: ingredient.fineli_id,
          };
        }),
      });
      setRecipe(updated);
      setNutrition(null);
      setEditingIngredients(false);
      await refreshNutrition(updated.id);
    } catch (e) {
      setIngredientError((e as Error).message);
    } finally {
      setSavingIngredients(false);
    }
  }

  if (error) return <p className="error">Could not load recipe: {error}</p>;
  if (!recipe) return <p>Loading…</p>;

  const coreNutrients = buildCoreNutrients(
    nutrition?.values,
    nutrition?.per_serving_values,
  );
  const micronutrients = (nutrition?.detailed_totals ?? []).filter(
    (nutrient) => !MACRO_COMPONENT_CODES.has(nutrient.code),
  );
  const micronutrientGroups = groupNutrients(micronutrients);

  return (
    <article className="recipe-detail">
      <header className="detail-hero">
        <div className="detail-hero-topline">
          <div>
            <p className="eyebrow">Saved recipe</p>
            <h1>{recipe.title}</h1>
          </div>
          <div className="recipe-actions" ref={menuRef}>
            <button
              className="recipe-actions-trigger"
              type="button"
              aria-label="Recipe actions"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span aria-hidden="true">⋯</span>
            </button>
            {menuOpen && (
              <div className="recipe-actions-menu" role="menu">
                <button type="button" role="menuitem" onClick={startEditingIngredients}>
                  Edit ingredients
                </button>
                <button type="button" role="menuitem" className="menu-delete" onClick={handleDelete}>
                  Delete recipe
                </button>
              </div>
            )}
          </div>
        </div>
        {recipe.description && <p className="detail-description">{recipe.description}</p>}
        <div className="detail-meta">
          {recipe.prep_minutes != null && <span>⏱ {recipe.prep_minutes} min</span>}
          {recipe.servings != null && <span>🍽 {recipe.servings} servings</span>}
        </div>
      </header>

      <div className="detail-grid">
        <section className="detail-card" aria-labelledby="detail-ingredients">
          <div className="detail-section-heading">
            <div>
              <p className="eyebrow">What you need</p>
              <h2 id="detail-ingredients" tabIndex={-1}>Ingredients</h2>
            </div>
            <span className="section-count">{recipe.ingredients.length}</span>
          </div>
          {!editingIngredients &&
            recipe.ingredients.some(
              (item) =>
                !item.fineli_id ||
                (item.quantity == null && item.conversion_status !== "negligible"),
            ) && (
              <div className="ingredient-edit-actions">
                <button
                  type="button"
                  className="button secondary"
                  onClick={autoMatchAll}
                  disabled={autoMatching}
                >
                  {autoMatching ? "Auto-matching…" : "Auto-match ingredients"}
                </button>
              </div>
            )}
          {editingIngredients ? (
            <div className="ingredient-edit-list">
              {draftIngredients.map((ingredient, index) => (
                <div className="ingredient-edit-row" key={`${ingredient.name}-${index}`}>
                  <span>{ingredient.name}</span>
                  <input
                    type="number"
                    min="0.001"
                    step="any"
                    value={ingredient.quantity}
                    placeholder={ingredient.amount || "g"}
                    aria-label={`Amount for ${ingredient.name}`}
                    onChange={(event) =>
                      setDraftIngredients((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, quantity: event.target.value, dirty: true }
                            : item,
                        ),
                      )
                    }
                  />
                  <select
                    className="detail-unit-select"
                    value={ingredient.unit}
                    aria-label={`Unit for ${ingredient.name}`}
                    onChange={(event) =>
                      setDraftIngredients((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, unit: event.target.value as "g" | "kg", dirty: true }
                            : item,
                        ),
                      )
                    }
                  >
                    <option value="g">g</option>
                    <option value="kg">kg</option>
                  </select>
                </div>
              ))}
              {ingredientError && <p className="error">{ingredientError}</p>}
              <div className="ingredient-edit-actions">
                <button type="button" className="button secondary" onClick={cancelEditingIngredients}>
                  Cancel
                </button>
                <button type="button" className="button" onClick={saveIngredients} disabled={savingIngredients}>
                  {savingIngredients ? "Saving…" : "Save ingredients"}
                </button>
              </div>
            </div>
          ) : (
            <ul className="ingredient-list-detail">
              {recipe.ingredients.map((i) => (
                <li key={i.id}>
                  <div className="ingredient-detail-row">
                    <span>{i.name}</span>
                    <strong>{i.amount}</strong>
                  </div>
                  <p className="muted-copy">
                    {i.fineli_id
                      ? `Fineli match: ${i.fineli_name ?? i.fineli_id}`
                      : "No Fineli food selected"}
                    {i.quantity != null
                      ? ` · ${formatNutrient(i.quantity, i.unit ?? "g")} (${i.conversion_status ?? "estimated"})`
                      : i.conversion_status === "negligible"
                        ? " · negligible amount"
                        : i.conversion_status === "unknown"
                          ? " · unknown quantity"
                          : ""}
                  </p>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => findFineliMatches(i.id, i.name)}
                    disabled={!!busyIngredientIds[i.id]}
                  >
                    {busyIngredientIds[i.id]
                      ? "Searching Fineli…"
                      : i.fineli_id
                        ? "Change Fineli match"
                        : "Find Fineli match"}
                  </button>
                  {openMatchPanels[i.id] && (
                    <div className="fineli-match-panel">
                      <form
                        className="fineli-match-search"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void findFineliMatches(i.id, matchQueries[i.id] ?? i.name);
                        }}
                      >
                        <input
                          type="search"
                          value={matchQueries[i.id] ?? i.name}
                          onChange={(event) =>
                            setMatchQueries((current) => ({
                              ...current,
                              [i.id]: event.target.value,
                            }))
                          }
                          aria-label={`Search Fineli for ${i.name}`}
                          placeholder="Search Fineli foods"
                        />
                        <button
                          type="submit"
                          className="button secondary"
                          disabled={!!busyIngredientIds[i.id]}
                        >
                          Search
                        </button>
                        <button
                          type="button"
                          className="button secondary"
                          onClick={() => closeMatchPanel(i.id)}
                        >
                          Close
                        </button>
                      </form>
                      {matchErrors[i.id] && <p className="error">{matchErrors[i.id]}</p>}
                      {suggestions[i.id]?.length ? (
                        <ul className="fineli-suggestions" aria-label={`Fineli suggestions for ${i.name}`}>
                          {suggestions[i.id].map((food) => (
                            <li key={food.id}>
                              <strong>{food.name}</strong>
                              {(food.food_type || food.process) && (
                                <p className="muted-copy">
                                  {[food.food_type, food.process].filter(Boolean).join(" · ")}
                                </p>
                              )}
                              {previewSuggestionNutrients(food.detailed_nutrients).length > 0 && (
                                <p>
                                  {previewSuggestionNutrients(food.detailed_nutrients)
                                    .map(
                                      (nutrient) =>
                                        `${nutrient.name}: ${nutrient.value_per_100g} ${nutrient.unit}/100 g`,
                                    )
                                    .join(" · ")}
                                </p>
                              )}
                              <button
                                type="button"
                                className="button secondary"
                                onClick={() => confirmFineliMatch(i.id, food)}
                                disabled={!!busyIngredientIds[i.id]}
                              >
                                Use {food.name}
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : suggestions[i.id] && !busyIngredientIds[i.id] ? (
                        <p className="muted-copy">No matching Fineli foods found.</p>
                      ) : null}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="detail-card nutrition-card" aria-labelledby="nutrition-heading">
          <div className="detail-section-heading">
            <div>
              <p className="eyebrow">Powered by Fineli</p>
              <h2 id="nutrition-heading">Nutrition</h2>
            </div>
          </div>
          <p>
            Approximate nutrition estimate based on confirmed Fineli matches and supported
            quantities.
          </p>
          <p>This estimate does not determine allergen or dietary safety.</p>
          {nutrition ? (
            <>
              <p>
                Coverage: {nutrition.coverage.included_ingredients} of{" "}
                {nutrition.coverage.total_ingredients} ingredients (
                {Math.round(nutrition.coverage.ratio * 100)}%)
                {(nutrition.coverage.negligible_ingredients ?? 0) > 0 &&
                  ` · ${nutrition.coverage.negligible_ingredients} negligible`}
              </p>
              {nutrition.coverage.included_ingredients === 0 ? (
                <p className="muted-copy">
                  No nutrition estimate is available because no ingredients contributed data.
                </p>
              ) : (
                <>
                  <ul className="nutrition-facts" aria-label="Nutrition summary">
                    {coreNutrients.map((row) => (
                      <li
                        key={row.key}
                        className={row.indented ? "nutrition-fact-sub" : "nutrition-fact"}
                      >
                        <span className="nutrition-fact-label">{row.label}</span>
                        <span className="nutrition-fact-values">
                          <strong>{row.totalText}</strong>
                          {row.perServingText && (
                            <span className="muted-copy">
                              per serving: {row.perServingText}
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {micronutrientGroups.size > 0 && (
                    <details className="nutrition-details">
                      <summary>Vitamins &amp; minerals ({micronutrients.length})</summary>
                      <div className="nutrition-details-body">
                        {Array.from(micronutrientGroups.entries()).map(([group, nutrients]) => (
                          <section key={group}>
                            <h3>{group}</h3>
                            <ul className="nutrition-micronutrient-list">
                              {nutrients.map((nutrient) => (
                                <li key={`${nutrient.code}-${nutrient.unit}`}>
                                  <span>{nutrient.name}</span>
                                  <span>
                                    {formatNutrient(nutrient.value, nutrient.unit)}
                                    {nutrient.per_serving != null &&
                                      ` (per serving: ${formatNutrient(nutrient.per_serving, nutrient.unit)})`}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </section>
                        ))}
                      </div>
                    </details>
                  )}
                </>
              )}
              <h3>Ingredient contributions</h3>
              <ul className="ingredient-contributions" aria-label="Ingredient nutrition results">
                {nutrition.ingredient_results.map((result) => {
                  const macroSummary =
                    result.status === "included"
                      ? summarizeIngredientMacros(result.nutrients)
                      : null;
                  return (
                    <li key={result.ingredient_id}>
                      <strong>{result.ingredient_name}</strong>
                      {result.status === "included" ? (
                        <>
                          <p>
                            Fineli match: {result.fineli_name ?? result.fineli_id}
                            {result.quantity_grams != null &&
                              ` · ${formatNutrient(result.quantity_grams, "g")}`}
                          </p>
                          {macroSummary && <p className="muted-copy">{macroSummary}</p>}
                        </>
                      ) : (
                        <p>Skipped: {skippedReason(result)}</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </>
          ) : (
            <p className="muted-copy">Calculate nutrition from the selected Fineli ingredients.</p>
          )}
          {nutritionError && <p className="error">{nutritionError}</p>}
          {recipe.ingredients.length === 0 && (
            <p className="muted-copy">Add ingredients before calculating nutrition.</p>
          )}
          <button
            className="button nutrition-button"
            onClick={calculateNutrition}
            disabled={nutritionLoading || recipe.ingredients.length === 0}
          >
            {nutritionLoading ? "Calculating…" : nutrition ? "Recalculate nutrition" : "Calculate nutrition"}
          </button>
          {nutrition && <small className="attribution">{nutrition.source.attribution_text}</small>}
        </section>
      </div>

      {recipe.source && (
        <p className="attribution">
          {recipe.source.attribution_text}{" "}
          {recipe.source.source_url && (
            <a href={recipe.source.source_url} target="_blank" rel="noreferrer">
              Recipe source
            </a>
          )}
        </p>
      )}

      <section className="detail-card instructions-card" aria-labelledby="instructions-heading">
        <p className="eyebrow">How to make it</p>
        <h2 id="instructions-heading">Instructions</h2>
        <p className="instructions">{recipe.instructions || "No instructions added yet."}</p>
      </section>

      {deleteError && (
        <p className="error" role="alert">
          {deleteError}
        </p>
      )}
      <button
        className="button danger detail-delete"
        onClick={handleDelete}
        disabled={deleting}
      >
        {deleting ? "Deleting…" : "Delete"}
      </button>
    </article>
  );
}

const MACRO_COMPONENT_CODES = new Set([
  "ENERC",
  "PROT",
  "CHOAVL",
  "CHOCDF",
  "FAT",
  "FIBC",
  "FIBT",
  "NACL",
  "SUGAR",
  "FASAT",
]);

const CORE_NUTRIENT_ROWS: {
  key: string;
  label: string;
  unit: string;
  indented?: boolean;
}[] = [
  { key: "fat_g", label: "Fat", unit: "g" },
  { key: "saturated_fat_g", label: "of which saturates", unit: "g", indented: true },
  { key: "carbohydrates_g", label: "Carbohydrates", unit: "g" },
  { key: "sugars_g", label: "of which sugars", unit: "g", indented: true },
  { key: "fiber_g", label: "Fibre", unit: "g" },
  { key: "protein_g", label: "Protein", unit: "g" },
  { key: "salt_g", label: "Salt", unit: "g" },
];

type CoreNutrientRow = {
  key: string;
  label: string;
  totalText: string;
  perServingText: string | null;
  indented?: boolean;
};

function buildCoreNutrients(
  values: Record<string, number | null> | undefined,
  perServing: Record<string, number | null> | undefined | null,
): CoreNutrientRow[] {
  if (!values) return [];
  const rows: CoreNutrientRow[] = [];

  const kcal = values.energy_kcal;
  const kj = values.energy_kj;
  if (kcal != null || kj != null) {
    const totalText =
      kcal != null && kj != null
        ? `${formatNutrient(kcal, "kcal")} (${formatNutrient(kj, "kJ")})`
        : kcal != null
          ? formatNutrient(kcal, "kcal")
          : formatNutrient(kj as number, "kJ");
    const psKcal = perServing?.energy_kcal;
    const psKj = perServing?.energy_kj;
    const perServingText =
      psKcal != null
        ? formatNutrient(psKcal, "kcal")
        : psKj != null
          ? formatNutrient(psKj, "kJ")
          : null;
    rows.push({ key: "energy", label: "Energy", totalText, perServingText });
  }

  for (const spec of CORE_NUTRIENT_ROWS) {
    const val = values[spec.key];
    if (val == null) continue;
    const ps = perServing?.[spec.key];
    rows.push({
      key: spec.key,
      label: spec.label,
      totalText: formatNutrient(val, spec.unit),
      perServingText: ps != null ? formatNutrient(ps, spec.unit) : null,
      indented: spec.indented,
    });
  }
  return rows;
}

function summarizeIngredientMacros(nutrients: DetailedNutrientTotal[]): string | null {
  const byCode = new Map(nutrients.map((n) => [n.code, n]));
  const parts: string[] = [];

  const enerc = byCode.get("ENERC");
  if (enerc) {
    const unit = enerc.unit.toLowerCase();
    const kcal =
      unit === "kcal"
        ? enerc.value
        : unit === "kj" || unit === "kilojoule"
          ? enerc.value / 4.184
          : null;
    if (kcal != null) {
      parts.push(formatNutrient(kcal, "kcal"));
    }
  }
  const prot = byCode.get("PROT");
  if (prot) parts.push(`Protein ${formatNutrient(prot.value, prot.unit)}`);
  const cho = byCode.get("CHOAVL");
  if (cho) parts.push(`Carbs ${formatNutrient(cho.value, cho.unit)}`);
  const fat = byCode.get("FAT");
  if (fat) parts.push(`Fat ${formatNutrient(fat.value, fat.unit)}`);

  return parts.length > 0 ? parts.join(" · ") : null;
}

const SUGGESTION_PREVIEW_CODES = ["ENERC", "PROT", "CHOAVL", "FAT"] as const;

function previewSuggestionNutrients(
  nutrients: FineliFood["detailed_nutrients"],
): FineliFood["detailed_nutrients"] {
  const byCode = new Map(nutrients.map((nutrient) => [nutrient.code, nutrient]));
  const preferred: FineliFood["detailed_nutrients"] = [];
  for (const code of SUGGESTION_PREVIEW_CODES) {
    const match = byCode.get(code);
    if (match) preferred.push(match);
  }
  if (preferred.length >= 3) {
    return preferred.slice(0, 3);
  }
  const seen = new Set(preferred.map((nutrient) => nutrient.code));
  for (const nutrient of nutrients) {
    if (!seen.has(nutrient.code)) {
      preferred.push(nutrient);
      if (preferred.length >= 3) break;
    }
  }
  return preferred;
}

const skippedReasons: Record<string, string> = {
  unmatched: "No Fineli food selected",
  unknown_quantity: "The ingredient quantity could not be converted",
  negligible_measure: "Negligible amount (e.g. pinch or to taste)",
  food_not_found: "The selected Fineli food is no longer available",
  missing_nutrients: "Fineli has no usable nutrient values for this food",
};

function groupNutrients(
  nutrients: DetailedNutrientTotal[],
): Map<string, DetailedNutrientTotal[]> {
  return nutrients.reduce((groups, nutrient) => {
    const group = nutrient.group || "Other nutrients";
    groups.set(group, [...(groups.get(group) ?? []), nutrient]);
    return groups;
  }, new Map<string, DetailedNutrientTotal[]>());
}

function formatNutrient(value: number, unit: string): string {
  const formatted = Number(value.toFixed(2)).toString();
  return unit ? `${formatted} ${unit}` : formatted;
}

function skippedReason(result: NutritionIngredientResult): string {
  return result.reason
    ? skippedReasons[result.reason] ?? "Nutrition could not be calculated"
    : "Nutrition could not be calculated";
}
