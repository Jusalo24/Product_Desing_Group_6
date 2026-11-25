import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import RecipeDetailPage from "./RecipeDetailPage";
import type { NutritionResponse } from "../types";

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
  coverage: { total_ingredients: 2, included_ingredients: 1, negligible_ingredients: 0, ratio: 0.5 },
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
    fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(recipe);
      if (url.pathname === "/api/recipes/3/nutrition") {
        return nutritionForPage
          ? jsonResponse(nutritionForPage)
          : jsonResponse({}, 404);
      }
      if (url.pathname === "/api/recipes/3/nutrition/recalculate" && init?.method === "POST") {
        return jsonResponse(partialEstimate);
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
    expect(screen.queryByText("No matching Fineli foods found.")).not.toBeInTheDocument();
    expect(await screen.findByText("Coverage: 1 of 2 ingredients (50%)")).toBeVisible();
    const matchCall = fetchMock.mock.calls.find(([input, init]) =>
      String(input).endsWith("/nutrition-source") && init?.method === "PUT",
    );
    expect(matchCall).toBeDefined();
    expect(JSON.parse(String(matchCall?.[1]?.body))).toEqual({ fineli_id: "100" });
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          String(input).endsWith("/nutrition/recalculate") && init?.method === "POST",
      ),
    ).toHaveLength(1);
    const matchCallIndex = fetchMock.mock.calls.findIndex(
      ([input, init]) =>
        String(input).endsWith("/nutrition-source") && init?.method === "PUT",
    );
    const recalculateCallIndex = fetchMock.mock.calls.findIndex(
      ([input, init]) =>
        String(input).endsWith("/nutrition/recalculate") && init?.method === "POST",
    );
    expect(recalculateCallIndex).toBeGreaterThan(matchCallIndex);
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

  it("supports auto-matching unmatched ingredients and shows negligible reason", async () => {
    const autoMatchedRecipe = {
      ...recipe,
      ingredients: [
        {
          ...ingredient,
          fineli_id: "100",
          fineli_name: "Olive oil",
          quantity: 13.5,
          unit: "g" as const,
          conversion_status: "estimated",
        },
      ],
    };
    fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(recipe);
      if (url.pathname === "/api/recipes/3/ingredients/auto-match" && init?.method === "POST") {
        return jsonResponse(autoMatchedRecipe);
      }
      if (url.pathname === "/api/recipes/3/nutrition/recalculate" && init?.method === "POST") {
        return jsonResponse(partialEstimate);
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

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Auto-match ingredients" }));

    expect(
      await within(screen.getByRole("region", { name: "Ingredients" })).findByText(
        /Fineli match: Olive oil/,
      ),
    ).toBeVisible();
    expect(screen.getByText(/13\.5 g \(estimated\)/)).toBeVisible();
    const calls = fetchMock.mock.calls.map(([input, init]) => ({
      path: String(input),
      method: init?.method,
    }));
    const autoMatchCallIndex = calls.findIndex(
      (call) => call.path.endsWith("/auto-match") && call.method === "POST",
    );
    const recalculateCallIndices = calls.flatMap((call, index) =>
      call.path.endsWith("/nutrition/recalculate") && call.method === "POST" ? [index] : [],
    );
    expect(recalculateCallIndices).toHaveLength(1);
    expect(recalculateCallIndices[0]).toBeGreaterThan(autoMatchCallIndex);
  });

  it("supports custom Fineli search query and closing the match panel", async () => {
    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Find Fineli match" }));
    const searchInput = await screen.findByRole("searchbox", {
      name: "Search Fineli for olive oil",
    });
    await user.clear(searchInput);
    await user.type(searchInput, "extra virgin");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/api/ingredients/suggestions?q=extra+virgin"),
      ),
    ).toBe(true);

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(
      screen.queryByRole("searchbox", { name: "Search Fineli for olive oil" }),
    ).not.toBeInTheDocument();
  });

  it("shows Auto-match for matched ingredients with unknown quantity and shows negligible coverage", async () => {
    const unknownQtyRecipe = {
      ...recipe,
      ingredients: [
        {
          ...ingredient,
          fineli_id: "100",
          fineli_name: "Olive oil",
          quantity: null,
          unit: null,
          conversion_status: "unknown",
        },
      ],
    };
    nutritionForPage = {
      ...partialEstimate,
      coverage: {
        total_ingredients: 2,
        included_ingredients: 1,
        negligible_ingredients: 1,
        ratio: 1,
      },
    };
    fetchMock.mockImplementation(async (input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(unknownQtyRecipe);
      if (url.pathname === "/api/recipes/3/nutrition") return jsonResponse(nutritionForPage);
      return jsonResponse({}, 404);
    });

    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("button", { name: "Auto-match ingredients" }),
    ).toBeVisible();
    expect(
      await screen.findByText("Coverage: 1 of 2 ingredients (100%) · 1 negligible"),
    ).toBeVisible();
  });

  it("shows an error alert when deleting a recipe fails", async () => {
    vi.stubGlobal("confirm", () => true);
    fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3" && init?.method === "DELETE") {
        return jsonResponse({}, 500);
      }
      if (url.pathname === "/api/recipes/3") return jsonResponse(recipe);
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

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not delete recipe",
    );
  });

  it("renders summary facts, collapsible vitamins & minerals, and compact ingredient macros", async () => {
    const richEstimate: NutritionResponse = {
      ...partialEstimate,
      values: {
        ...partialEstimate.values,
        saturated_fat_g: 1.2,
        sugars_g: 3.4,
        fiber_g: 2.5,
        salt_g: 0.5,
      },
      detailed_totals: [
        ...partialEstimate.detailed_totals,
        { code: "VITC", name: "Vitamin C", unit: "mg", value: 15, group: "Water soluble vitamins", per_serving: 7.5 },
        { code: "FE", name: "Iron", unit: "mg", value: 2.2, group: "Trace elements", per_serving: 1.1 },
      ],
      ingredient_results: [
        {
          ingredient_id: 9,
          ingredient_name: "olive oil",
          fineli_id: "100",
          fineli_name: "Olive oil",
          quantity_grams: 13.5,
          status: "included",
          reason: null,
          nutrients: [
            { code: "ENERC", name: "Energy", unit: "kJ", value: 502.08, group: "Energy", per_serving: null },
            { code: "PROT", name: "Protein", unit: "g", value: 0, group: "Macro", per_serving: null },
            { code: "CHOAVL", name: "Carbohydrate", unit: "g", value: 0, group: "Macro", per_serving: null },
            { code: "FAT", name: "Fat", unit: "g", value: 13.5, group: "Macro", per_serving: null },
            { code: "VITC", name: "Vitamin C", unit: "mg", value: 15, group: "Vitamins", per_serving: null },
          ],
        },
      ],
    };
    nutritionForPage = richEstimate as unknown as typeof partialEstimate;

    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const summary = await screen.findByRole("list", { name: "Nutrition summary" });
    expect(within(summary).getByText("Energy")).toBeVisible();
    expect(within(summary).getByText("of which saturates")).toBeVisible();
    expect(within(summary).getByText("of which sugars")).toBeVisible();
    expect(within(summary).getByText("Fibre")).toBeVisible();
    expect(within(summary).getByText("Salt")).toBeVisible();

    // Collapsible vitamins & minerals starts closed and opens on click
    const toggle = screen.getByText("Vitamins & minerals (2)");
    const details = toggle.closest("details");
    expect(details).not.toHaveAttribute("open");
    await userEvent.setup().click(toggle);
    expect(details).toHaveAttribute("open");
    expect(screen.getByText("Vitamin C")).toBeVisible();
    expect(screen.getByText("Iron")).toBeVisible();

    // Compact 1-line ingredient macro summary (kcal converted from kJ)
    const contributions = screen.getByRole("list", { name: "Ingredient nutrition results" });
    expect(
      within(contributions).getByText("120 kcal · Protein 0 g · Carbs 0 g · Fat 13.5 g"),
    ).toBeVisible();
  });

  it("converts kilojoule ingredient unit to kcal and prioritizes macro previews on suggestions", async () => {
    const richCandidate = {
      ...candidate,
      detailed_nutrients: [
        { code: "ALC", name: "Alcohol", unit: "gram", group: "Alcohol", value_per_100g: 0 },
        { code: "ASH", name: "Ash", unit: "gram", group: "Ash", value_per_100g: 0 },
        { code: "CA", name: "Calcium", unit: "milligram", group: "Minerals", value_per_100g: 1 },
        { code: "ENERC", name: "Energy,calculated", unit: "kilojoule", group: "Energy", value_per_100g: 3700 },
        { code: "FAT", name: "Fat, total", unit: "gram", group: "Fat", value_per_100g: 100 },
        { code: "PROT", name: "Protein, total", unit: "gram", group: "Protein", value_per_100g: 0 },
      ],
    };
    const kjEstimate = {
      ...partialEstimate,
      ingredient_results: [
        {
          ingredient_id: 9,
          ingredient_name: "olive oil",
          fineli_id: "100",
          fineli_name: "Olive oil",
          quantity_grams: 100,
          status: "included" as const,
          reason: null,
          nutrients: [
            { code: "ENERC", name: "Energy,calculated", unit: "kilojoule", value: 418.4, group: "Energy", per_serving: null },
          ],
        },
      ],
    };
    fetchMock.mockImplementation(async (input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(recipe);
      if (url.pathname === "/api/recipes/3/nutrition") return jsonResponse(kjEstimate);
      if (url.pathname === "/api/ingredients/suggestions") return jsonResponse([richCandidate]);
      return jsonResponse({}, 404);
    });

    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const contributions = await screen.findByRole("list", {
      name: "Ingredient nutrition results",
    });
    expect(within(contributions).getByText("100 kcal")).toBeVisible();

    await userEvent.setup().click(screen.getByRole("button", { name: "Find Fineli match" }));
    const suggestionList = await screen.findByRole("list", {
      name: "Fineli suggestions for olive oil",
    });
    expect(within(suggestionList).getByText(/Energy,calculated: 3700 kilojoule\/100 g/)).toBeVisible();
    expect(within(suggestionList).queryByText(/Alcohol:/)).not.toBeInTheDocument();
  });

  it("disables Calculate nutrition when a recipe has no ingredients", async () => {
    const emptyRecipe = { ...recipe, ingredients: [] };
    fetchMock.mockImplementation(async (input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/recipes/3") return jsonResponse(emptyRecipe);
      return jsonResponse({}, 404);
    });

    render(
      <MemoryRouter initialEntries={["/recipes/3"]}>
        <Routes>
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Add ingredients before calculating nutrition."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Calculate nutrition" })).toBeDisabled();
  });
});
