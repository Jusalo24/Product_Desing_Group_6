// Keep these in sync with backend/app/schemas.py

export interface Ingredient {
  id: number;
  name: string;
  amount: string;
  quantity: number | null;
  unit: "g" | "kg" | null;
  fineli_id: string | null;
  fineli_name: string | null;
  conversion_status: string;
}

export interface Recipe {
  id: number;
  title: string;
  description: string;
  instructions: string;
  prep_minutes: number | null;
  servings: number | null;
  created_at: string;
  ingredients: Ingredient[];
  source?: RecipeSource | null;
}

export interface RecipeSource {
  provider: string;
  external_id: string;
  provider_url: string | null;
  source_url: string | null;
  image_url: string | null;
  attribution_text: string;
  extra_data: Record<string, unknown>;
  retrieved_at: string;
}

export interface FineliNutrient {
  code: string;
  name: string;
  unit: string;
  group: string | null;
  value_per_100g: number;
}

export interface FineliFood {
  id: string;
  name: string;
  nutrients_per_100g: Record<string, number | null>;
  detailed_nutrients: FineliNutrient[];
  units: { code: string; name: string; grams: number }[];
  source: {
    provider: string;
    source_type: string;
    external_id: string;
    source_url: string | null;
    retrieved_at: string;
    attribution_text: string;
  };
}

export interface NutritionSource {
  provider: string;
  source_type: string;
  external_id: string;
  source_url: string | null;
  retrieved_at: string;
  attribution_text: string;
}

export interface DetailedNutrientTotal {
  code: string;
  name: string;
  unit: string;
  group: string | null;
  value: number;
  per_serving: number | null;
}

export interface NutritionIngredientResult {
  ingredient_id: number;
  ingredient_name: string;
  fineli_id: string | null;
  fineli_name: string | null;
  quantity_grams: number | null;
  status: "included" | "skipped";
  reason: string | null;
  nutrients: DetailedNutrientTotal[];
}

export interface NutritionEstimate {
  recipe_id: number;
  values: Record<string, number | null>;
  per_serving_values: Record<string, number | null> | null;
  detailed_totals: DetailedNutrientTotal[];
  coverage: {
    total_ingredients: number;
    included_ingredients: number;
    ratio: number;
  };
  ingredient_results: NutritionIngredientResult[];
  source: NutritionSource;
  status: string;
  calculation_run_id: number | null;
}

export interface RecipeCreate {
  title: string;
  description: string;
  instructions: string;
  prep_minutes: number | null;
  servings: number | null;
  ingredients: { name: string; amount: string }[];
}
