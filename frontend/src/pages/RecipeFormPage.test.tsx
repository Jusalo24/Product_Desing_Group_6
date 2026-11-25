import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import RecipeFormPage from "./RecipeFormPage";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Created",
    json: async () => body,
  } as Response;
}

const sampleFoods = [
  {
    id: "1",
    name: "Sugar",
    nutrients_per_100g: { energy_kcal: 400 },
    detailed_nutrients: [],
    units: [],
    source: {
      provider: "Fineli",
      source_type: "dataset",
      external_id: "1",
      source_url: "https://fineli.fi/fineli/fi/elintarvikkeet/1",
      retrieved_at: "2026-01-01T00:00:00Z",
      attribution_text: "Source: Fineli",
    },
  },
  {
    id: "2",
    name: "Brown sugar",
    nutrients_per_100g: { energy_kcal: 380 },
    detailed_nutrients: [],
    units: [],
    source: {
      provider: "Fineli",
      source_type: "dataset",
      external_id: "2",
      source_url: "https://fineli.fi/fineli/fi/elintarvikkeet/2",
      retrieved_at: "2026-01-01T00:00:00Z",
      attribution_text: "Source: Fineli",
    },
  },
];

describe("RecipeFormPage", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows empty search feedback when Fineli returns no matches", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    render(
      <MemoryRouter initialEntries={["/new"]}>
        <Routes>
          <Route path="/new" element={<RecipeFormPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const user = userEvent.setup();
    await user.type(screen.getByRole("combobox", { name: "Ingredient 1" }), "zzzznothing");

    expect(
      await screen.findByText("No matching Fineli foods found."),
    ).toBeVisible();
  });

  it("selects a Fineli suggestion with ArrowDown and Enter without submitting", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(sampleFoods))
      .mockResolvedValueOnce(jsonResponse({ id: 42 }, 201));
    render(
      <MemoryRouter initialEntries={["/new"]}>
        <Routes>
          <Route path="/new" element={<RecipeFormPage />} />
          <Route path="/recipes/:id" element={<p>Recipe detail</p>} />
        </Routes>
      </MemoryRouter>,
    );

    const user = userEvent.setup();
    const input = screen.getByRole("combobox", { name: "Ingredient 1" });
    await user.type(input, "sugar");
    await screen.findByRole("option", { name: "Brown sugar" });

    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    // Even if a browser/CDP dispatches a follow-up keypress or submit event, it must not submit
    const form = input.closest("form");
    expect(form).not.toBeNull();
    const keypressEvent = new KeyboardEvent("keypress", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
    });
    input.dispatchEvent(keypressEvent);
    expect(keypressEvent.defaultPrevented).toBe(true);
    form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(input).toHaveValue("Brown sugar");
    expect(screen.queryByText("Recipe detail")).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);

    // Explicit Save recipe click immediately afterwards still submits normally
    await user.click(screen.getByRole("button", { name: "Save recipe" }));
    expect(await screen.findByText("Recipe detail")).toBeVisible();
  });

  it("rejects zero or negative ingredient amounts before calling the API", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(sampleFoods));
    render(
      <MemoryRouter initialEntries={["/new"]}>
        <Routes>
          <Route path="/new" element={<RecipeFormPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const user = userEvent.setup();
    await user.type(screen.getByRole("spinbutton", { name: "Amount for ingredient 1" }), "0");
    await user.type(screen.getByRole("combobox", { name: "Ingredient 1" }), "sugar");
    await user.click(await screen.findByRole("button", { name: "Sugar" }));
    await user.click(screen.getByRole("button", { name: "Save recipe" }));

    expect(await screen.findByText("Amounts must be positive numbers.")).toBeVisible();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
      ).toBe(false);
    });
  });
});
