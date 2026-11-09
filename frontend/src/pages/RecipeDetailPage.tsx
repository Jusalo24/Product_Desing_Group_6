import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type {
  DetailedNutrientTotal,
  FineliFood,
  NutritionEstimate,
  NutritionIngredientResult,
  Recipe,
} from "../types";

export default function RecipeDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [nutrition, setNutrition] = useState<NutritionEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nutritionError, setNutritionError] = useState<string | null>(null);
  const [calculatingNutrition, setCalculatingNutrition] = useState(false);
  const [suggestions, setSuggestions] = useState<Record<number, FineliFood[]>>({});
  const [matchingIngredientId, setMatchingIngredientId] = useState<number | null>(null);
  const [matchErrors, setMatchErrors] = useState<Record<number, string>>({});

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

  async function handleDelete() {
    if (!recipe || !window.confirm("Delete this recipe?")) return;
    await api.deleteRecipe(recipe.id);
    navigate("/my-recipes");
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

  async function calculateNutrition() {
    setCalculatingNutrition(true);
    setNutritionError(null);
    try {
      setNutrition(await api.recalculateNutrition(Number(id)));
    } catch (err) {
      setNutritionError(
        err instanceof Error ? err.message : "Could not calculate nutrition.",
      );
    } finally {
      setCalculatingNutrition(false);
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
    <article>
      <h1>{recipe.title}</h1>
      <p>{recipe.description}</p>
      <p>
        {recipe.prep_minutes != null && <span>⏱ {recipe.prep_minutes} min </span>}
        {recipe.servings != null && <span>🍽 {recipe.servings} servings</span>}
      </p>

      <h2>Ingredients</h2>
      <ul>
        {recipe.ingredients.map((i) => (
          <li key={i.id}>
            {i.amount} {i.name}
            <div>
              {i.fineli_id ? (
                <p>Fineli match: {i.fineli_name ?? i.fineli_id}</p>
              ) : (
                <p>No Fineli food selected</p>
              )}
              <button
                type="button"
                onClick={() => findFineliMatches(i.id, i.name)}
                disabled={matchingIngredientId === i.id}
              >
                {matchingIngredientId === i.id
                  ? "Searching Fineli…"
                  : i.fineli_id
                    ? "Change Fineli match"
                    : "Find Fineli match"}
              </button>
              {matchErrors[i.id] && <p role="alert">{matchErrors[i.id]}</p>}
              {suggestions[i.id]?.length ? (
                <ul aria-label={`Fineli suggestions for ${i.name}`}>
                  {suggestions[i.id].map((food) => (
                    <li key={food.id}>
                      <strong>{food.name}</strong>
                      <p>
                        {food.detailed_nutrients
                          .slice(0, 3)
                          .map(
                            (nutrient) =>
                              `${nutrient.name}: ${nutrient.value_per_100g} ${nutrient.unit}/100 g`,
                          )
                          .join(" · ")}
                      </p>
                      <button
                        type="button"
                        onClick={() => confirmFineliMatch(i.id, food)}
                        disabled={matchingIngredientId === i.id}
                      >
                        Use {food.name}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : suggestions[i.id] ? (
                <p>No matching Fineli foods found.</p>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      <h2>Instructions</h2>
      <p className="instructions">{recipe.instructions}</p>

      {recipe.source && (
        <p>
          {recipe.source.attribution_text}{" "}
          {recipe.source.source_url && (
            <a href={recipe.source.source_url} target="_blank" rel="noreferrer">
              Recipe source
            </a>
          )}
        </p>
      )}

      <section aria-labelledby="nutrition-heading">
        <h2 id="nutrition-heading">Nutrition estimate</h2>
        <p>Approximate nutrition estimate based on confirmed Fineli matches and supported quantities.</p>
        <p>This estimate does not determine allergen or dietary safety.</p>
        <button type="button" onClick={calculateNutrition} disabled={calculatingNutrition}>
          {calculatingNutrition
            ? "Calculating nutrition…"
            : nutrition
              ? "Recalculate nutrition"
              : "Calculate nutrition"}
        </button>
        {nutritionError && <p role="alert">Could not load nutrition estimate: {nutritionError}</p>}
        {nutrition && (
          <div>
            <p>
              <strong>
                Coverage: {nutrition.coverage.included_ingredients} of{" "}
                {nutrition.coverage.total_ingredients} ingredients (
                {Math.round(nutrition.coverage.ratio * 100)}%)
              </strong>
            </p>
            <p>{nutrition.source.attribution_text}</p>
            {nutrition.coverage.included_ingredients === 0 ? (
              <p>
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
                            {nutrient.per_serving != null && (
                              <span>
                                {" "}
                                (per serving: {formatNutrient(nutrient.per_serving, nutrient.unit)})
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))
                ) : (
                  <ul aria-label="Common nutrient totals">
                    {legacyNutrients.map((nutrient) => (
                      <li key={nutrient.name}>
                        <strong>{nutrient.name}:</strong>{" "}
                        {formatNutrient(nutrient.value, nutrient.unit)}
                        {nutrient.perServing != null && (
                          <span>
                            {" "}
                            (per serving: {formatNutrient(nutrient.perServing, nutrient.unit)})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
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
                      {result.nutrients.length ? (
                        <ul>
                          {result.nutrients.map((nutrient) => (
                            <li key={`${nutrient.code}-${nutrient.unit}`}>
                              {nutrient.name}: {formatNutrient(nutrient.value, nutrient.unit)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p>No detailed nutrient values are available for this ingredient.</p>
                      )}
                    </>
                  ) : (
                    <p>Skipped: {skippedReason(result)}</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <button className="button danger" onClick={handleDelete}>
        Delete
      </button>
    </article>
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
