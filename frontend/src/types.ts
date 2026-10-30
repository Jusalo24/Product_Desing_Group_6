// Keep these in sync with backend/app/schemas.py

export interface Ingredient {
  id: number;
  name: string;
  amount: string;
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
}

export interface RecipeCreate {
  title: string;
  description: string;
  instructions: string;
  prep_minutes: number | null;
  servings: number | null;
  ingredients: { name: string; amount: string }[];
}
