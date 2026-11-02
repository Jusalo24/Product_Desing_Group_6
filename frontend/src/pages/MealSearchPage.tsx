import { useState, type FormEvent } from "react";

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

export default function MealSearchPage() {
  const [query, setQuery] = useState("Arrabiata");
  const [meals, setMeals] = useState<Meal[]>([]);
  const [selectedMeal, setSelectedMeal] = useState<Meal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function searchMeals(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const searchTerm = query.trim();

    if (!searchTerm) {
      setError("Kirjoita ruokalajin nimi.");
      return;
    }

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

      setMeals(body);
      if (body.length === 0) {
        setError("Reseptejä ei löytynyt. Kokeile toista hakusanaa.");
      }
    } catch (err) {
      console.error("TheMealDB search failed:", err);
      setError(
        err instanceof Error
          ? `Reseptien haku epäonnistui: ${err.message}`
          : "Reseptien haku epäonnistui tuntemattomasta syystä.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h1>Reseptihaku</h1>
      <p>Etsi ruokia ja reseptejä TheMealDB:n tietokannasta.</p>

      <form
        onSubmit={searchMeals}
        style={{ display: "flex", gap: 8, marginBottom: 20 }}
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Esim. Arrabiata tai chicken"
          aria-label="Hae reseptiä"
          style={{ flex: 1, minWidth: 0, padding: 12, fontSize: 16 }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{ padding: "12px 18px", cursor: "pointer" }}
        >
          {loading ? "Haetaan..." : "Hae"}
        </button>
      </form>

      {error && <p role="alert">{error}</p>}

      <section
        aria-label="Hakutulokset"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 16,
        }}
      >
        {meals.map((meal) => (
          <article
            key={meal.id}
            style={{
              overflow: "hidden",
              border: "1px solid #ddd",
              borderRadius: 10,
            }}
          >
            {meal.imageUrl && (
              <img
                src={meal.imageUrl}
                alt=""
                loading="lazy"
                style={{
                  display: "block",
                  width: "100%",
                  aspectRatio: "4 / 3",
                  objectFit: "cover",
                }}
              />
            )}
            <div style={{ padding: 14 }}>
              <h2 style={{ margin: "0 0 8px", fontSize: 18 }}>{meal.name}</h2>
              <p style={{ color: "#666", fontSize: 14 }}>
                {[meal.category, meal.area].filter(Boolean).join(" · ")}
              </p>
              <button type="button" onClick={() => setSelectedMeal(meal)}>
                Näytä resepti
              </button>
            </div>
          </article>
        ))}
      </section>

      {selectedMeal && (
        <section
          aria-labelledby="selected-meal-title"
          style={{
            marginTop: 28,
            padding: 20,
            border: "2px solid #888",
            borderRadius: 12,
          }}
        >
          <h2 id="selected-meal-title">{selectedMeal.name}</h2>
          <p style={{ color: "#666" }}>
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
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
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
        </section>
      )}

      <footer style={{ marginTop: 32, color: "#666", fontSize: 12 }}>
        Recipe data and imagery:{" "}
        <a href="https://www.themealdb.com/" target="_blank" rel="noreferrer">
          TheMealDB
        </a>
        .
      </footer>
    </section>
  );
}
