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

  let content;
  if (loading) {
    content = <p className="empty-state">Loading…</p>;
  } else if (error) {
    content = <p className="error">Could not load recipes: {error}</p>;
  } else if (recipes.length === 0) {
    content = (
      <p className="empty-state">
        No recipes yet. <Link to="/new">Add the first one!</Link>
      </p>
    );
  } else {
    content = (
      <div className="grid">
        {recipes.map((r) => (
          <Link key={r.id} to={`/recipes/${r.id}`} className="card">
            <h2>{r.title}</h2>
            {r.description && <p>{r.description}</p>}
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

  return (
    <section>
      <h1 className="section-title">
        <span>My recipes</span>
      </h1>
      {content}
    </section>
  );
}
