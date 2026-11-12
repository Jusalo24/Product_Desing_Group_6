import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

type Meal = {
  id: string;
  name: string;
  category: string | null;
  area: string | null;
  instructions: string | null;
  imageUrl: string | null;
  tags: string[];
  youtubeUrl: string | null;
  sourceUrl: string | null;
  creativeCommonsConfirmed: string | null;
  ingredients: RecipeIngredient[];
};

type RecipeIngredient = {
  name: string;
  measure: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOptionalText(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isMeal(value: unknown): value is Meal {
  if (!isRecord(value)) return false;

  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    isOptionalText(value.category) &&
    isOptionalText(value.area) &&
    isOptionalText(value.instructions) &&
    isOptionalText(value.imageUrl) &&
    isOptionalText(value.sourceUrl) &&
    isOptionalText(value.youtubeUrl) &&
    isOptionalText(value.creativeCommonsConfirmed) &&
    Array.isArray(value.tags) &&
    value.tags.every((tag) => typeof tag === "string") &&
    Array.isArray(value.ingredients) &&
    value.ingredients.every(
      (ingredient) =>
        isRecord(ingredient) &&
        typeof ingredient.name === "string" &&
        isOptionalText(ingredient.measure),
    )
  );
}

function getErrorMessage(body: unknown, status: number): string {
  if (!isRecord(body)) return `HTTP ${status}`;
  if (typeof body.detail === "string") return body.detail;
  if (isRecord(body.detail) && typeof body.detail.message === "string") {
    return body.detail.message;
  }
  return `HTTP ${status}`;
}

// Example recipes shown on the homepage before the user searches.
// Clicking one runs a TheMealDB search for `query`.
const FEATURED_RECIPES = [
  {
    title: "Spicy Arrabiata Penne",
    query: "Arrabiata",
    emoji: "🍝",
    background: "linear-gradient(135deg, #f6d5c3, #e8a07c)",
  },
  {
    title: "Teriyaki Chicken",
    query: "Teriyaki",
    emoji: "🍗",
    background: "linear-gradient(135deg, #f3e3b5, #d9b25f)",
  },
  {
    title: "Hearty Homemade Soup",
    query: "soup",
    emoji: "🍲",
    background: "linear-gradient(135deg, #d8e8c8, #9cbf7d)",
  },
];

export default function MealSearchPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const query = (params.get("q") ?? "").trim();
  const [meals, setMeals] = useState<Meal[]>([]);
  const [selectedMeal, setSelectedMeal] = useState<Meal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [savingMealId, setSavingMealId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState("");

  async function saveSelectedMeal() {
    if (!selectedMeal) return;
    setSavingMealId(selectedMeal.id);
    setSaveError("");
    try {
      const recipe = await api.importExternalRecipe(selectedMeal.id);
      navigate(`/recipes/${recipe.id}`);
    } catch (err) {
      setSaveError(
        err instanceof Error
          ? `Could not save recipe: ${err.message}`
          : "Could not save recipe.",
      );
    } finally {
      setSavingMealId(null);
    }
  }

  useEffect(() => {
    if (!query) {
      setMeals([]);
      setSelectedMeal(null);
      setError("");
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function searchMeals(searchTerm: string) {
      setLoading(true);
      setError("");
      setMeals([]);
      setSelectedMeal(null);

      try {
        const url = new URL("/api/meals/search", window.location.origin);
        url.searchParams.set("q", searchTerm);
        const response = await fetch(url);

        if (!response.ok) {
          const body: unknown = await response.json().catch(() => null);
          throw new Error(getErrorMessage(body, response.status));
        }

        const body: unknown = await response.json();
        if (!Array.isArray(body) || !body.every(isMeal)) {
          throw new Error("TheMealDB palautti odottamattoman vastauksen.");
        }
        if (cancelled) return;

        setMeals(body);
        if (body.length === 0) {
          setError("Reseptejä ei löytynyt. Kokeile toista hakusanaa.");
        }
      } catch (err) {
        if (cancelled) return;
        console.error("TheMealDB search failed:", err);
        setError(
          err instanceof Error
            ? `Reseptien haku epäonnistui: ${err.message}`
            : "Reseptien haku epäonnistui tuntemattomasta syystä.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void searchMeals(query);
    return () => {
      cancelled = true;
    };
  }, [query]);

  if (!query) {
    return (
      <section>
        <h1 className="section-title">
          <span>Dinner tonight</span>
        </h1>
        <div className="feature-grid">
          {FEATURED_RECIPES.map((recipe) => (
            <Link
              key={recipe.query}
              to={`/?q=${encodeURIComponent(recipe.query)}`}
              className="feature-card"
            >
              <div
                className="feature-card__image"
                style={{ background: recipe.background }}
              >
                <span aria-hidden="true">{recipe.emoji}</span>
              </div>
              <h2 className="feature-card__title">{recipe.title}</h2>
            </Link>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section>
      <h1 className="section-title">
        <span>Results for “{query}”</span>
      </h1>

      {loading && <p role="status">Haetaan...</p>}
      {error && <p role="alert">{error}</p>}

      <section aria-label="Hakutulokset" className="feature-grid">
        {meals.map((meal) => (
          <article key={meal.id} className="feature-card">
            {meal.imageUrl ? (
              <img
                src={meal.imageUrl}
                alt=""
                loading="lazy"
                className="feature-card__image"
              />
            ) : (
              <div className="feature-card__image feature-card__image--empty">
                <span aria-hidden="true">🍽️</span>
              </div>
            )}
            <h2 className="feature-card__title">{meal.name}</h2>
            <p className="feature-card__meta">
              {[meal.category, meal.area].filter(Boolean).join(" · ")}
            </p>
            <button
              type="button"
              className="button secondary"
              onClick={() => setSelectedMeal(meal)}
            >
              Näytä resepti
            </button>
          </article>
        ))}
      </section>

      {selectedMeal && (
        <section
          aria-labelledby="selected-meal-title"
          className="panel selected-meal"
        >
          <p className="eyebrow">Selected recipe</p>
          <h2 id="selected-meal-title">{selectedMeal.name}</h2>
          <p className="muted-copy">
            {[selectedMeal.category, selectedMeal.area]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p>
            <a
              href={`https://www.themealdb.com/meal/${encodeURIComponent(selectedMeal.id)}`}
              target="_blank"
              rel="noreferrer"
            >
              Avaa resepti TheMealDB:ssä
            </a>
          </p>

          <h3>Ainekset</h3>
          {selectedMeal.ingredients.length > 0 ? (
            <ul>
              {selectedMeal.ingredients.map((ingredient, index) => (
                <li key={`${ingredient.name}-${index}`}>
                  {ingredient.measure ? `${ingredient.measure} ` : ""}
                  {ingredient.name}
                </li>
              ))}
            </ul>
          ) : (
            <p>Ainesosia ei ole ilmoitettu.</p>
          )}

          <h3>Valmistusohje</h3>
          {selectedMeal.instructions ? (
            <p className="instructions">
              {selectedMeal.instructions}
            </p>
          ) : (
            <p>Valmistusohjetta ei ole ilmoitettu.</p>
          )}

          {selectedMeal.sourceUrl && (
            <p>
              <a href={selectedMeal.sourceUrl} target="_blank" rel="noreferrer">
                Alkuperäinen lähde
              </a>
            </p>
          )}
          {selectedMeal.youtubeUrl && (
            <p>
              <a href={selectedMeal.youtubeUrl} target="_blank" rel="noreferrer">
                Katso video-ohje
              </a>
            </p>
          )}

          <button
            type="button"
            className="button"
            onClick={saveSelectedMeal}
            disabled={savingMealId === selectedMeal.id}
          >
            {savingMealId === selectedMeal.id
              ? "Saving recipe…"
              : "Save recipe for nutrition"}
          </button>
          {saveError && <p role="alert">{saveError}</p>}
        </section>
      )}

      <footer className="source-note">
        Recipe data and imagery:{" "}
        <a href="https://www.themealdb.com/" target="_blank" rel="noreferrer">
          TheMealDB
        </a>
        .
      </footer>
    </section>
  );
}
