import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { NutritionResponse, Recipe } from "../types";
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
    api
      .getRecipe(Number(id))
      .then(setRecipe)
      .catch((e: Error) => setError(e.message));
    api.getNutrition(Number(id)).then(setNutrition).catch(() => undefined);
  }, [id]);

  async function calculateNutrition() {
    if (!recipe) return;
    setNutritionLoading(true);
    setNutritionError(null);
    try {
      setNutrition(await api.recalculateNutrition(recipe.id));
    } catch (e) {
      setNutritionError((e as Error).message);
    } finally {
      setNutritionLoading(false);
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
                  <span>{i.name}</span>
                  <strong>{i.amount}</strong>
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
          {nutrition ? (
            <dl className="nutrition-grid">
              <NutritionValue label="Energy" value={nutrition.values.energy_kcal} unit="kcal" />
              <NutritionValue label="Protein" value={nutrition.values.protein_g} unit="g" />
              <NutritionValue label="Carbohydrates" value={nutrition.values.carbohydrates_g} unit="g" />
              <NutritionValue label="Fat" value={nutrition.values.fat_g} unit="g" />
              <NutritionValue label="Fiber" value={nutrition.values.fiber_g} unit="g" />
              <NutritionValue label="Salt" value={nutrition.values.salt_g} unit="g" />
            </dl>
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
