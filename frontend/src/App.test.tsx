import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("App routes", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse([]));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("opens the homepage with example recipes and a header search", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Dinner tonight" })).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Search recipes" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("searches from the header search box", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/my-recipes"]}>
        <App />
      </MemoryRouter>,
    );

    await user.type(
      screen.getByRole("searchbox", { name: "Search recipes" }),
      "chicken",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(
      await screen.findByRole("heading", { name: "Results for “chicken”" }),
    ).toBeVisible();
    const searchCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/meals/search"),
    );
    expect(new URL(String(searchCall?.[0])).searchParams.get("q")).toBe(
      "chicken",
    );
  });

  it("keeps saved recipes and recipe creation available", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/my-recipes"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("No recipes yet.")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "My recipes" }));
    expect(await screen.findByText("No recipes yet.")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "New recipe" }));

    expect(screen.getByRole("heading", { name: "New recipe" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Recipe App home" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("keeps the meal-search route available", () => {
    render(
      <MemoryRouter initialEntries={["/meals/search"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Dinner tonight" })).toBeVisible();
  });

  it("returns to saved recipes after deleting a recipe", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          id: 1,
          title: "Test recipe",
          description: "",
          instructions: "",
          prep_minutes: null,
          servings: null,
          created_at: "2026-01-01T00:00:00Z",
          ingredients: [],
        }),
      )
      .mockResolvedValueOnce(jsonResponse(null, 204))
      .mockResolvedValueOnce(jsonResponse([]));

    render(
      <MemoryRouter initialEntries={["/recipes/1"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Test recipe" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirm).toHaveBeenCalledWith("Delete this recipe?");
    expect(await screen.findByText("No recipes yet.")).toBeVisible();
  });
});
