import type {
  FineliFood,
  Ingredient,
  NutritionEstimate,
  Recipe,
  RecipeCreate,
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
  listRecipes: () => request<Recipe[]>("/recipes"),
  getRecipe: (id: number) => request<Recipe>(`/recipes/${id}`),
  getNutrition: (id: number) => request<NutritionEstimate>(`/recipes/${id}/nutrition`),
  recalculateNutrition: (id: number) =>
    request<NutritionEstimate>(`/recipes/${id}/nutrition/recalculate`, { method: "POST" }),
  createRecipe: (data: RecipeCreate) =>
    request<Recipe>("/recipes", { method: "POST", body: JSON.stringify(data) }),
  importExternalRecipe: (externalId: string) =>
    request<Recipe>(`/external-recipes/id/${encodeURIComponent(externalId)}/import`, {
      method: "POST",
    }),
  suggestIngredients: (query: string) => {
    const params = new URLSearchParams({ q: query });
    return request<FineliFood[]>(`/ingredients/suggestions?${params.toString()}`);
  },
  matchIngredient: (recipeId: number, ingredientId: number, fineliId: string) =>
    request<Ingredient>(
      `/recipes/${recipeId}/ingredients/${ingredientId}/nutrition-source`,
      { method: "PUT", body: JSON.stringify({ fineli_id: fineliId }) },
    ),
  deleteRecipe: (id: number) => request<void>(`/recipes/${id}`, { method: "DELETE" }),
};
