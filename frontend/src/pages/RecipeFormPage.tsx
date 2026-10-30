import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

interface IngredientRow {
  name: string;
  amount: string;
}

export default function RecipeFormPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [prepMinutes, setPrepMinutes] = useState("");
  const [servings, setServings] = useState("");
  const [ingredients, setIngredients] = useState<IngredientRow[]>([{ name: "", amount: "" }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateIngredient(index: number, patch: Partial<IngredientRow>) {
    setIngredients((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await api.createRecipe({
        title,
        description,
        instructions,
        prep_minutes: prepMinutes ? Number(prepMinutes) : null,
        servings: servings ? Number(servings) : null,
        ingredients: ingredients.filter((i) => i.name.trim() !== ""),
      });
      navigate(`/recipes/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="form">
      <h1>New recipe</h1>

      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>

      <label>
        Description
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
      </label>

      <div className="row">
        <label>
          Prep time (min)
          <input
            type="number"
            min={0}
            value={prepMinutes}
            onChange={(e) => setPrepMinutes(e.target.value)}
          />
        </label>
        <label>
          Servings
          <input
            type="number"
            min={1}
            value={servings}
            onChange={(e) => setServings(e.target.value)}
          />
        </label>
      </div>

      <fieldset>
        <legend>Ingredients</legend>
        {ingredients.map((row, i) => (
          <div className="row" key={i}>
            <input
              placeholder="Amount (e.g. 2 dl)"
              value={row.amount}
              onChange={(e) => updateIngredient(i, { amount: e.target.value })}
            />
            <input
              placeholder="Ingredient"
              value={row.name}
              onChange={(e) => updateIngredient(i, { name: e.target.value })}
            />
          </div>
        ))}
        <button
          type="button"
          className="button secondary"
          onClick={() => setIngredients((rows) => [...rows, { name: "", amount: "" }])}
        >
          + Add ingredient
        </button>
      </fieldset>

      <label>
        Instructions
        <textarea
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          rows={6}
        />
      </label>

      {error && <p className="error">Could not save: {error}</p>}

      <button type="submit" className="button" disabled={saving}>
        {saving ? "Saving…" : "Save recipe"}
      </button>
    </form>
  );
}
