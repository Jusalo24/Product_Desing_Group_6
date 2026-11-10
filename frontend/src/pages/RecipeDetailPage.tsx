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
  const [matchingIngredientId, setMatchingIngredientId] = useState<number | null>(null);
  const [matchErrors, setMatchErrors] = useState<Record<number, string>>({});
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

  async function calculateNutrition() {
    if (!recipe) return;
    setNutritionLoading(true);
    setNutritionError(null);
    try {
      setNutrition(await api.recalculateNutrition(recipe.id));
    } catch (e) {
      setNutritionError(
        e instanceof Error ? e.message : "Could not calculate nutrition.",
      );
    } finally {
      setNutritionLoading(false);
    }
  }

  async function findFineliMatches(ingredientId: number, name: string) {
    setMatchingIngredientId(ingredientId);
    setMatchErrors((errors) => ({ ...errors, [ingredientId]: "" }));
    try {
      const candidates = await api.suggestIngredients(name);
      setSuggestions((current) => ({ ...current, [ingredientId]: candidates }));
    } catch (err) {
      setMatchErrors((errors) => ({
        ...errors,
        [ingredientId]: err instanceof Error ? err.message : "Could not search Fineli foods.",
      }));
    } finally {
      setMatchingIngredientId(null);
    }
  }

  async function confirmFineliMatch(ingredientId: number, food: FineliFood) {
    if (!recipe) return;
    setMatchingIngredientId(ingredientId);
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
      setSuggestions((current) => ({ ...current, [ingredientId]: [] }));
    } catch (err) {
      setMatchErrors((errors) => ({
        ...errors,
        [ingredientId]: err instanceof Error ? err.message : "Could not save Fineli match.",
      }));
    } finally {
      setMatchingIngredientId(null);
    }
  }

  async function handleDelete() {
    if (!recipe || !window.confirm("Delete this recipe?")) return;
    await api.deleteRecipe(recipe.id);
    navigate("/my-recipes");
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
    if (draftIngredients.some((ingredient) => !ingredient.quantity || Number(ingredient.quantity) <= 0)) {
      setIngredientError("Add a valid amount for every ingredient.");
      return;
    }

    setSavingIngredients(true);
    setIngredientError(null);
    try {
      const updated = await api.updateIngredients(recipe.id, {
        ingredients: draftIngredients.map((ingredient) => ({
          name: ingredient.name,
          amount: `${ingredient.quantity} ${ingredient.unit}`,
          quantity: Number(ingredient.quantity),
          unit: ingredient.unit,
          fineli_id: ingredient.fineli_id,
        })),
      });
      setRecipe(updated);
      setNutrition(null);
      setEditingIngredients(false);
    } catch (e) {
      setIngredientError((e as Error).message);
    } finally {
      setSavingIngredients(false);
    }
  }

  if (error) return <p className="error">Could not load recipe: {error}</p>;
  if (!recipe) return <p>Loading…</p>;

  const detailedGroups = groupNutrients(nutrition?.detailed_totals ?? []);
  const legacyNutrients = Object.entries(nutrition?.values ?? {})
    .filter((entry): entry is [string, number] => entry[1] !== null)
    .map(([key, value]) => ({
      name: legacyNutrientNames[key] ?? key,
      unit: legacyNutrientUnits[key] ?? "",
      value,
      perServing: nutrition?.per_serving_values?.[key] ?? null,
    }));

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
                    aria-label={`Amount for ${ingredient.name}`}
                    onChange={(event) =>
                      setDraftIngredients((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, quantity: event.target.value, amount: event.target.value }
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
                            ? { ...item, unit: event.target.value as "g" | "kg" }
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
                  </p>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => findFineliMatches(i.id, i.name)}
                    disabled={matchingIngredientId === i.id}
                  >
                    {matchingIngredientId === i.id
                      ? "Searching Fineli…"
                      : i.fineli_id
                        ? "Change Fineli match"
                        : "Find Fineli match"}
                  </button>
                  {matchErrors[i.id] && <p className="error">{matchErrors[i.id]}</p>}
                  {suggestions[i.id]?.length ? (
                    <ul aria-label={`Fineli suggestions for ${i.name}`}>
                      {suggestions[i.id].map((food) => (
                        <li key={food.id}>
                          <strong>{food.name}</strong>
                          {food.detailed_nutrients.slice(0, 3).length > 0 && (
                            <p>
                              {food.detailed_nutrients
                                .slice(0, 3)
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
                            disabled={matchingIngredientId === i.id}
                          >
                            Use {food.name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : suggestions[i.id] ? (
                    <p className="muted-copy">No matching Fineli foods found.</p>
                  ) : null}
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
              </p>
              {nutrition.coverage.included_ingredients === 0 ? (
                <p className="muted-copy">
                  No nutrition estimate is available because no ingredients contributed data.
                </p>
              ) : (
                <>
                  {detailedGroups.size > 0 ? (
                    Array.from(detailedGroups.entries()).map(([group, nutrients]) => (
                      <section key={group}>
                        <h3>{group}</h3>
                        <ul>
                          {nutrients.map((nutrient) => (
                            <li key={`${nutrient.code}-${nutrient.unit}`}>
                              <strong>{nutrient.name}:</strong>{" "}
                              {formatNutrient(nutrient.value, nutrient.unit)}
                              {nutrient.per_serving != null &&
                                ` (per serving: ${formatNutrient(nutrient.per_serving, nutrient.unit)})`}
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))
                  ) : (
                    <dl className="nutrition-grid">
                      {legacyNutrients.map((nutrient) => (
                        <NutritionValue
                          key={nutrient.name}
                          label={nutrient.name}
                          value={nutrient.value}
                          unit={nutrient.unit}
                        />
                      ))}
                    </dl>
                  )}
                </>
              )}
              <h3>Ingredient contributions</h3>
              <ul aria-label="Ingredient nutrition results">
                {nutrition.ingredient_results.map((result) => (
                  <li key={result.ingredient_id}>
                    <strong>{result.ingredient_name}</strong>
                    {result.status === "included" ? (
                      <>
                        <p>
                          Fineli match: {result.fineli_name ?? result.fineli_id}
                          {result.quantity_grams != null &&
                            ` · ${formatNutrient(result.quantity_grams, "g")}`}
                        </p>
                        {result.nutrients.length > 0 && (
                          <ul>
                            {result.nutrients.map((nutrient) => (
                              <li key={`${nutrient.code}-${nutrient.unit}`}>
                                {nutrient.name}: {formatNutrient(nutrient.value, nutrient.unit)}
                              </li>
                            ))}
                          </ul>
                        )}
                      </>
                    ) : (
                      <p>Skipped: {skippedReason(result)}</p>
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted-copy">Calculate nutrition from the selected Fineli ingredients.</p>
          )}
          {nutritionError && <p className="error">{nutritionError}</p>}
          <button className="button nutrition-button" onClick={calculateNutrition} disabled={nutritionLoading}>
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

      <button className="button danger detail-delete" onClick={handleDelete}>
        Delete
      </button>
    </article>
  );
}

function NutritionValue({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value == null ? "—" : `${value.toFixed(1)} ${unit}`}</dd>
    </div>
  );
}

const legacyNutrientNames: Record<string, string> = {
  energy_kcal: "Energy",
  energy_kj: "Energy",
  protein_g: "Protein",
  carbohydrates_g: "Carbohydrates",
  fat_g: "Fat",
  fiber_g: "Fiber",
  salt_g: "Salt",
  sugars_g: "Sugars",
  saturated_fat_g: "Saturated fat",
};

const legacyNutrientUnits: Record<string, string> = {
  energy_kcal: "kcal",
  energy_kj: "kJ",
  protein_g: "g",
  carbohydrates_g: "g",
  fat_g: "g",
  fiber_g: "g",
  salt_g: "g",
  sugars_g: "g",
  saturated_fat_g: "g",
};

const skippedReasons: Record<string, string> = {
  unmatched: "No Fineli food selected",
  unknown_quantity: "The ingredient quantity could not be converted",
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
