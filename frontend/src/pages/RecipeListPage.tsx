import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Recipe } from "../types";

export default function RecipeListPage() {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRecipes()
      .then(setRecipes)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading…</p>;
  if (error) return <p className="error">Could not load recipes: {error}</p>;
  if (recipes.length === 0) {
    return (
      <p>
        No recipes yet. <Link to="/new">Add the first one!</Link>
      </p>
    );
  }

  return (
    <div className="grid">
      {recipes.map((r) => (
        <Link key={r.id} to={`/recipes/${r.id}`} className="card">
          <h2>{r.title}</h2>
          <p>{r.description}</p>
          <small>
            {r.prep_minutes != null && `${r.prep_minutes} min`}
            {r.prep_minutes != null && r.servings != null && " · "}
            {r.servings != null && `${r.servings} servings`}
          </small>
        </Link>
      ))}
    </div>
  );
}
