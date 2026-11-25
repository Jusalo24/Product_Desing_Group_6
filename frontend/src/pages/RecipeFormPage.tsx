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
  rowKey: number;
  name: string;
  amount: string;
  quantity: string;
  unit: "g" | "kg";
  fineliId: string | null;
}

function hasFineliId(
  ingredient: IngredientRow,
): ingredient is IngredientRow & { fineliId: string } {
  return ingredient.name.trim() !== "" && ingredient.fineliId !== null;
}

export default function RecipeFormPage() {
  const navigate = useNavigate();
  const nextRowKey = useRef(2);
  const [title, setTitle] = useState("New recipe");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [prepMinutes, setPrepMinutes] = useState("");
  const [servings, setServings] = useState("");
  const [ingredients, setIngredients] = useState<IngredientRow[]>([
    { rowKey: 1, name: "", amount: "", quantity: "", unit: "g", fineliId: null },
  ]);
  const [suggestions, setSuggestions] = useState<Record<number, FineliFood[]>>({});
  const [activeSuggestion, setActiveSuggestion] = useState<Record<number, number>>({});
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

  function updateIngredient(rowKey: number, patch: Partial<IngredientRow>) {
    setIngredients((rows) =>
      rows.map((r) => (r.rowKey === rowKey ? { ...r, ...patch } : r)),
    );
  }

  const searchSignature = ingredients
    .filter((row) => row.name.trim() && !row.fineliId)
    .map((row) => `${row.rowKey}:${row.name.trim()}`)
    .join("|");

  useEffect(() => {
    const queryRows = searchSignature
      ? searchSignature.split("|").map((entry) => {
          const splitAt = entry.indexOf(":");
          return {
            rowKey: Number(entry.slice(0, splitAt)),
            query: entry.slice(splitAt + 1),
          };
        })
      : [];

    if (queryRows.length === 0) {
      setSuggestions({});
      setSearching({});
      return;
    }

    const sequence = ++searchSequence.current;
    const timeout = window.setTimeout(async () => {
      setSearching(Object.fromEntries(queryRows.map(({ rowKey }) => [rowKey, true])));
      setSearchError(null);
      try {
        const results = await Promise.all(
          queryRows.map(
            async ({ rowKey, query }) =>
              [rowKey, await api.searchIngredients(query)] as const,
          ),
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
  }, [searchSignature]);

  function selectIngredient(rowKey: number, food: FineliFood) {
    updateIngredient(rowKey, { name: food.name, fineliId: food.id });
    setSuggestions((current) => ({ ...current, [rowKey]: [] }));
    setActiveSuggestion((current) => ({ ...current, [rowKey]: -1 }));
  }

  function changeIngredientName(rowKey: number, name: string) {
    searchSequence.current += 1;
    updateIngredient(rowKey, { name, fineliId: null });
    setSuggestions((current) => ({ ...current, [rowKey]: [] }));
    setActiveSuggestion((current) => ({ ...current, [rowKey]: -1 }));
  }

  function handleIngredientKeyDown(
    rowKey: number,
    event: KeyboardEvent<HTMLInputElement>,
  ) {
    const options = suggestions[rowKey] ?? [];
    if (event.key === "Escape") {
      event.preventDefault();
      setSuggestions((current) => ({ ...current, [rowKey]: [] }));
      setActiveSuggestion((current) => ({ ...current, [rowKey]: -1 }));
      return;
    }

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (options.length === 0) {
        return;
      }
      event.preventDefault();
      const currentIndex = activeSuggestion[rowKey] ?? -1;
      const nextIndex =
        event.key === "ArrowDown"
          ? (currentIndex + 1) % options.length
          : (currentIndex - 1 + options.length) % options.length;
      setActiveSuggestion((current) => ({ ...current, [rowKey]: nextIndex }));
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      const selectedIndex = activeSuggestion[rowKey] ?? 0;
      const selectedSuggestion = options[selectedIndex] ?? options[0];
      if (selectedSuggestion) {
        selectIngredient(rowKey, selectedSuggestion);
      }
    }
  }

  function removeIngredient(rowKey: number) {
    setIngredients((rows) => rows.filter((row) => row.rowKey !== rowKey));
    setSuggestions((current) => {
      const next = { ...current };
      delete next[rowKey];
      return next;
    });
    setActiveSuggestion((current) => {
      const next = { ...current };
      delete next[rowKey];
      return next;
    });
    setSearching((current) => {
      const next = { ...current };
      delete next[rowKey];
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
            amount: ingredient.quantity ? `${ingredient.quantity} ${ingredient.unit}` : ingredient.amount,
            quantity: ingredient.quantity ? Number(ingredient.quantity) : null,
            unit: ingredient.quantity ? ingredient.unit : null,
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
            <div className="ingredient-row" key={row.rowKey}>
              <label className="recipe-field amount-field">
                <span className="sr-only">Amount for ingredient {i + 1}</span>
                <input
                  type="number"
                  min={0}
                  step="any"
                  placeholder="Amount"
                  value={row.quantity}
                  onChange={(e) =>
                    updateIngredient(row.rowKey, {
                      quantity: e.target.value,
                      amount: e.target.value,
                    })
                  }
                  aria-label={`Amount for ingredient ${i + 1}`}
                />
              </label>
              <label className="recipe-field unit-field">
                <span className="sr-only">Unit for ingredient {i + 1}</span>
                <select
                  className="unit-select"
                  value={row.unit}
                  onChange={(e) =>
                    updateIngredient(row.rowKey, { unit: e.target.value as "g" | "kg" })
                  }
                  aria-label={`Unit for ingredient ${i + 1}`}
                >
                  <option value="g">g</option>
                  <option value="kg">kg</option>
                </select>
              </label>
              <label className="recipe-field ingredient-field">
                <span className="sr-only">Ingredient {i + 1}</span>
                <input
                  placeholder="Search Fineli ingredients"
                  value={row.name}
                  onChange={(e) => changeIngredientName(row.rowKey, e.target.value)}
                  onKeyDown={(e) => handleIngredientKeyDown(row.rowKey, e)}
                  role="combobox"
                  aria-autocomplete="list"
                  aria-controls={`ingredient-suggestions-${row.rowKey}`}
                  aria-expanded={(suggestions[row.rowKey]?.length ?? 0) > 0}
                  aria-activedescendant={
                    activeSuggestion[row.rowKey] >= 0
                      ? `ingredient-suggestion-${row.rowKey}-${activeSuggestion[row.rowKey]}`
                      : undefined
                  }
                  aria-label={`Ingredient ${i + 1}`}
                />
                {searching[row.rowKey] && <small className="field-hint">Searching Fineli…</small>}
                {!!suggestions[row.rowKey]?.length && (
                  <ul
                    id={`ingredient-suggestions-${row.rowKey}`}
                    className="ingredient-suggestions"
                    role="listbox"
                  >
                    {suggestions[row.rowKey].map((food, suggestionIndex) => (
                      <li
                        key={food.id}
                        id={`ingredient-suggestion-${row.rowKey}-${suggestionIndex}`}
                        role="option"
                        aria-selected={activeSuggestion[row.rowKey] === suggestionIndex}
                        className={
                          activeSuggestion[row.rowKey] === suggestionIndex
                            ? "suggestion-active"
                            : undefined
                        }
                      >
                        <button type="button" onClick={() => selectIngredient(row.rowKey, food)}>
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
                onClick={() => removeIngredient(row.rowKey)}
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
            setIngredients((rows) => [
              ...rows,
              {
                rowKey: nextRowKey.current++,
                name: "",
                amount: "",
                quantity: "",
                unit: "g",
                fineliId: null,
              },
            ])
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
