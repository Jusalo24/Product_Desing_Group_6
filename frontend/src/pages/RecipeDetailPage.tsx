import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { Recipe } from "../types";

export default function RecipeDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getRecipe(Number(id))
      .then(setRecipe)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  async function handleDelete() {
    if (!recipe || !window.confirm("Delete this recipe?")) return;
    await api.deleteRecipe(recipe.id);
    navigate("/");
  }

  if (error) return <p className="error">Could not load recipe: {error}</p>;
  if (!recipe) return <p>Loading…</p>;

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
          </li>
        ))}
      </ul>

      <h2>Instructions</h2>
      <p className="instructions">{recipe.instructions}</p>

      <button className="button danger" onClick={handleDelete}>
        Delete
      </button>
    </article>
  );
}
