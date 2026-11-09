import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { FineliFood } from "../types";
import "../styles/RecipeFormPage.css";

interface IngredientRow {
  name: string;
  amount: string;
  fineliId: string | null;
}

function hasFineliId(
  ingredient: IngredientRow,
): ingredient is IngredientRow & { fineliId: string } {
  return ingredient.name.trim() !== "" && ingredient.fineliId !== null;
}

export default function RecipeFormPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("New recipe");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [prepMinutes, setPrepMinutes] = useState("");
  const [servings, setServings] = useState("");
  const [ingredients, setIngredients] = useState<IngredientRow[]>([
    { name: "", amount: "", fineliId: null },
  ]);
  const [suggestions, setSuggestions] = useState<Record<number, FineliFood[]>>({});
  const [searching, setSearching] = useState<Record<number, boolean>>({});
  const [searchError, setSearchError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchSequence = useRef(0);
  const ingredientListRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function closeSuggestions(event: MouseEvent) {
      if (!ingredientListRef.current?.contains(event.target as Node)) {
        setSuggestions({});
      }
    }

    document.addEventListener("mousedown", closeSuggestions);
    return () => document.removeEventListener("mousedown", closeSuggestions);
  }, []);

  function updateIngredient(index: number, patch: Partial<IngredientRow>) {
    setIngredients((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  useEffect(() => {
    const queryRows = ingredients
      .map((row, index) => ({ row, index }))
      .filter(({ row }) => row.name.trim() && !row.fineliId);

    if (queryRows.length === 0) {
      setSuggestions({});
      setSearching({});
      return;
    }

    const sequence = ++searchSequence.current;
    const timeout = window.setTimeout(async () => {
      setSearching(Object.fromEntries(queryRows.map(({ index }) => [index, true])));
      setSearchError(null);
      try {
        const results = await Promise.all(
          queryRows.map(async ({ row, index }) => [index, await api.searchIngredients(row.name)] as const),
        );
        if (sequence === searchSequence.current) {
          setSuggestions(Object.fromEntries(results));
        }
      } catch {
        if (sequence === searchSequence.current) {
          setSearchError("Ingredient search failed. Try again.");
          setSuggestions({});
        }
      } finally {
        if (sequence === searchSequence.current) {
          setSearching({});
        }
      }
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [ingredients]);

  function selectIngredient(index: number, food: FineliFood) {
    updateIngredient(index, { name: food.name, fineliId: food.id });
    setSuggestions((current) => ({ ...current, [index]: [] }));
  }

  function changeIngredientName(index: number, name: string) {
    searchSequence.current += 1;
    updateIngredient(index, { name, fineliId: null });
    setSuggestions((current) => ({ ...current, [index]: [] }));
  }

  function handleIngredientKeyDown(
    index: number,
    event: KeyboardEvent<HTMLInputElement>,
  ) {
    if (event.key !== "Enter") {
      return;
    }

    event.preventDefault();
    const firstSuggestion = suggestions[index]?.[0];
    if (firstSuggestion) {
      selectIngredient(index, firstSuggestion);
    }
  }

  function removeIngredient(index: number) {
    setIngredients((rows) => rows.filter((_, rowIndex) => rowIndex !== index));
    setSuggestions((current) => {
      const next = { ...current };
      delete next[index];
      return next;
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const incompleteIngredient = ingredients.some(
      (ingredient) => ingredient.name.trim() !== "" && !ingredient.fineliId,
    );
    if (incompleteIngredient) {
      setError("Select each ingredient from the Fineli suggestions.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await api.createRecipe({
        title,
        description,
        instructions,
        prep_minutes: prepMinutes ? Number(prepMinutes) : null,
        servings: servings ? Number(servings) : null,
        ingredients: ingredients
          .filter(hasFineliId)
          .map((ingredient) => ({
            name: ingredient.name,
            amount: ingredient.amount,
            fineli_id: ingredient.fineliId,
          })),
      });
      navigate(`/recipes/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form recipe-form">
      <div className="recipe-header">
        <h1 className="recipe-title-heading" aria-label={title}>
          <input
            className="recipe-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label="Recipe title"
            required
          />
        </h1>
        <p className="recipe-subtitle">Create something delicious</p>
      </div>

      <section className="recipe-card" aria-labelledby="details-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Start with the basics</p>
            <h2 id="details-heading">Recipe details</h2>
          </div>
        </div>

        <label className="recipe-field">
          <span>Description</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What makes this recipe special?"
            rows={3}
          />
        </label>

        <div className="recipe-meta">
          <label className="recipe-field">
            <span>Prep time</span>
            <div className="input-with-suffix">
              <input
                type="number"
                min={0}
                value={prepMinutes}
                onChange={(e) => setPrepMinutes(e.target.value)}
                placeholder="30"
              />
              <span>min</span>
            </div>
          </label>
          <label className="recipe-field">
            <span>Servings</span>
            <input
              type="number"
              min={1}
              value={servings}
              onChange={(e) => setServings(e.target.value)}
              placeholder="4"
            />
          </label>
        </div>
      </section>

      <section className="recipe-card" aria-labelledby="ingredients-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Build your recipe</p>
            <h2 id="ingredients-heading">Ingredients</h2>
          </div>
          <span className="section-count">{ingredients.length}</span>
        </div>

        <div className="ingredient-list" ref={ingredientListRef}>
          {ingredients.map((row, i) => (
            <div className="ingredient-row" key={i}>
              <label className="recipe-field amount-field">
                <span className="sr-only">Amount for ingredient {i + 1}</span>
                <input
                  placeholder="Amount"
                  value={row.amount}
                  onChange={(e) => updateIngredient(i, { amount: e.target.value })}
                  aria-label={`Amount for ingredient ${i + 1}`}
                />
              </label>
              <label className="recipe-field ingredient-field">
                <span className="sr-only">Ingredient {i + 1}</span>
                <input
                  placeholder="Search Fineli ingredients"
                  value={row.name}
                  onChange={(e) => changeIngredientName(i, e.target.value)}
                  onKeyDown={(e) => handleIngredientKeyDown(i, e)}
                  role="combobox"
                  aria-autocomplete="list"
                  aria-controls={`ingredient-suggestions-${i}`}
                  aria-expanded={(suggestions[i]?.length ?? 0) > 0}
                  aria-label={`Ingredient ${i + 1}`}
                />
                {searching[i] && <small className="field-hint">Searching Fineli…</small>}
                {!!suggestions[i]?.length && (
                  <ul
                    id={`ingredient-suggestions-${i}`}
                    className="ingredient-suggestions"
                    role="listbox"
                  >
                    {suggestions[i].map((food) => (
                      <li key={food.id} role="option">
                        <button type="button" onClick={() => selectIngredient(i, food)}>
                          {food.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </label>
              <button
                type="button"
                className="remove-ingredient"
                onClick={() => removeIngredient(i)}
                aria-label={`Remove ingredient ${i + 1}`}
                disabled={ingredients.length === 1}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          className="button secondary add-ingredient"
          onClick={() =>
            setIngredients((rows) => [...rows, { name: "", amount: "", fineliId: null }])
          }
        >
          <span aria-hidden="true">+</span> Add ingredient
        </button>
      </section>

      {searchError && <p className="error">{searchError}</p>}

      <section className="recipe-card" aria-labelledby="instructions-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">One step at a time</p>
            <h2 id="instructions-heading">Instructions</h2>
          </div>
        </div>
        <label className="recipe-field">
          <span className="sr-only">Instructions</span>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="Write the steps for making your recipe..."
            rows={7}
          />
        </label>
      </section>

      {error && <p className="error">{error}</p>}

      <div className="recipe-actions">
        <button type="submit" className="button save-recipe" disabled={saving}>
          {saving ? "Saving…" : "Save recipe"}
        </button>
      </div>
    </form>
  );
}
