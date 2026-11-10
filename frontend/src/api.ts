import type {
  FineliFood,
  Ingredient,
  NutritionResponse,
  Recipe,
  RecipeCreate,
  RecipeIngredientsUpdate,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  searchIngredients: (query: string) =>
    request<FineliFood[]>(`/ingredients/search?q=${encodeURIComponent(query)}`),
  suggestIngredients: (query: string) => {
    const params = new URLSearchParams({ q: query });
    return request<FineliFood[]>(`/ingredients/suggestions?${params.toString()}`);
  },
  importExternalRecipe: (externalId: string) =>
    request<Recipe>(`/external-recipes/id/${encodeURIComponent(externalId)}/import`, {
      method: "POST",
    }),
  listRecipes: () => request<Recipe[]>("/recipes"),
  getRecipe: (id: number) => request<Recipe>(`/recipes/${id}`),
  createRecipe: (data: RecipeCreate) =>
    request<Recipe>("/recipes", { method: "POST", body: JSON.stringify(data) }),
  updateIngredients: (id: number, data: RecipeIngredientsUpdate) =>
    request<Recipe>(`/recipes/${id}/ingredients`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  matchIngredient: (recipeId: number, ingredientId: number, fineliId: string) =>
    request<Ingredient>(
      `/recipes/${recipeId}/ingredients/${ingredientId}/nutrition-source`,
      { method: "PUT", body: JSON.stringify({ fineli_id: fineliId }) },
    ),
  getNutrition: (id: number) => request<NutritionResponse>(`/recipes/${id}/nutrition`),
  recalculateNutrition: (id: number) =>
    request<NutritionResponse>(`/recipes/${id}/nutrition/recalculate`, { method: "POST" }),
  deleteRecipe: (id: number) => request<void>(`/recipes/${id}`, { method: "DELETE" }),
};
