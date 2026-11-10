import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import RecipeDetailPage from "./RecipeDetailPage";

const ingredient = {
  id: 9,
  name: "olive oil",
  amount: "1 tbsp",
  quantity: null,
  unit: null,
  fineli_id: null,
  fineli_name: null,
  conversion_status: "unmatched",
};

const recipe = {
  id: 3,
  title: "Test recipe",
  description: "",
  instructions: "",
  prep_minutes: null,
  servings: 2,
  created_at: "2026-01-01T00:00:00Z",
  ingredients: [ingredient],
};

const partialEstimate = {
  recipe_id: 3,
  values: {
    energy_kcal: 100,
    energy_kj: 418,
    protein_g: 10,
    carbohydrates_g: 20,
    fat_g: 5,
    fiber_g: null,
    salt_g: null,
    sugars_g: null,
    saturated_fat_g: null,
  },
  source: {
    provider: "Fineli",
    source_type: "dataset",
    external_id: "20.0",
    source_url: "https://fineli.fi/fineli/en/open-data",
    retrieved_at: "2026-01-01T00:00:00Z",
    attribution_text: "Source: Fineli",
  },
  status: "partial",
  calculation_run_id: 1,
  per_serving_values: { energy_kcal: 50 },
  detailed_totals: [
    { code: "ENERC", name: "Energy", unit: "kcal", value: 100, group: "Energy", per_serving: 50 },
    { code: "PROT", name: "Protein", unit: "g", value: 10, group: "Macronutrients", per_serving: 5 },
  ],
  coverage: { total_ingredients: 2, included_ingredients: 1, ratio: 0.5 },
  ingredient_results: [
    {
      ingredient_id: 9,
      ingredient_name: "olive oil",
      fineli_id: "100",
      fineli_name: "Olive oil",
      quantity_grams: 13.5,
      status: "included",
      reason: null,
      nutrients: [{ code: "ENERC", name: "Energy", unit: "kcal", value: 12, group: "Energy" }],
    },
    {
      ingredient_id: 10,
      ingredient_name: "salt",
      fineli_id: null,
      fineli_name: null,
      quantity_grams: null,
      status: "skipped",
      reason: "unmatched",
      nutrients: [],
    },
  ],
};

const noEstimate = {
  ...partialEstimate,
  status: "unavailable",
  detailed_totals: [],
  coverage: { total_ingredients: 1, included_ingredients: 0, ratio: 0 },
  ingredient_results: [
    { ...partialEstimate.ingredient_results[1], ingredient_id: 9, ingredient_name: "olive oil" },
  ],
  values: Object.fromEntries(Object.keys(partialEstimate.values).map((key) => [key, null])),
};

const candidate = {
  id: "100",
  name: "Olive oil",
  nutrients_per_100g: { energy_kcal: 884 },
  detailed_nutrients: [
    { code: "ENERC", name: "Energy, calculated", unit: "kJ", group: "Energy", value_per_100g: 3700 },
  ],
  units: [{ code: "TBSP", name: "tablespoon", grams: 13.5 }],
  source: {
    provider: "Fineli",
    source_type: "dataset",
    external_id: "100",
    source_url: "https://fineli.fi/fineli/fi/elintarvikkeet/100",
    retrieved_at: "2026-01-01T00:00:00Z",
    attribution_text: "Source: Fineli",
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : status === 404 ? "Not Found" : "Created",
    json: async () => body,
  } as Response;
}

describe("RecipeDetailPage ingredient matching", () => {
  const fetchMock = vi.fn<typeof fetch>();
  let nutritionForPage: typeof partialEstimate | null;

  beforeEach(() => {
    nutritionForPage = null;
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(recipe);
      if (url.pathname === "/api/recipes/3/nutrition") {
        return nutritionForPage
          ? jsonResponse(nutritionForPage)
          : jsonResponse({}, 404);
      }
      if (url.pathname === "/api/ingredients/suggestions") return jsonResponse([candidate]);
      if (url.pathname.endsWith("/nutrition-source")) {
        return jsonResponse({
          ...ingredient,
          fineli_id: candidate.id,
          fineli_name: candidate.name,
          conversion_status: "matched",
        });
      }
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("requires explicit confirmation of a Fineli candidate", async () => {
    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Find Fineli match" }));
    expect(await screen.findByRole("button", { name: "Use Olive oil" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Use Olive oil" }));

    expect(await screen.findByText("Fineli match: Olive oil")).toBeVisible();
    const matchCall = fetchMock.mock.calls.find(([input, init]) =>
      String(input).endsWith("/nutrition-source") && init?.method === "PUT",
    );
    expect(matchCall).toBeDefined();
    expect(JSON.parse(String(matchCall?.[1]?.body))).toEqual({ fineli_id: "100" });
  });

  it("shows partial nutrition, coverage, per-serving totals, and skipped reasons", async () => {
    nutritionForPage = partialEstimate;
    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Coverage: 1 of 2 ingredients (50%)")).toBeVisible();
    expect(
      screen.getByText(
        "Approximate nutrition estimate based on confirmed Fineli matches and supported quantities.",
      ),
    ).toBeVisible();
    expect(
      screen.getAllByRole("listitem").some((item) => item.textContent?.includes("100 kcal")),
    ).toBe(true);
    expect(
      screen.getAllByRole("listitem").some((item) => item.textContent?.includes("50 kcal")),
    ).toBe(true);
    expect(screen.getByText("Skipped: No Fineli food selected")).toBeVisible();
    expect(screen.getByText("Source: Fineli")).toBeVisible();
  });

  it("explains when none of the ingredients can contribute", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(recipe);
      if (url.pathname === "/api/recipes/3/nutrition/recalculate" && init?.method === "POST") {
        return jsonResponse(noEstimate);
      }
      if (url.pathname === "/api/recipes/3/nutrition") return jsonResponse({}, 404);
      return jsonResponse({}, 404);
    });
    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await userEvent.setup().click(await screen.findByRole("button", { name: "Calculate nutrition" }));

    expect(
      await screen.findByText(
        "No nutrition estimate is available because no ingredients contributed data.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Coverage: 0 of 1 ingredients (0%)")).toBeVisible();
    expect(screen.getByText("Skipped: No Fineli food selected")).toBeVisible();
  });
});
