import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import MealSearchPage from "./MealSearchPage";

const meal = {
  id: "52771",
  name: "Spicy Arrabiata Penne",
  category: "Vegetarian",
  area: "Italian",
  instructions: "Boil the pasta.\nPrepare the sauce.",
  imageUrl: "https://www.themealdb.com/images/media/meals/example.jpg",
  tags: ["Pasta"],
  sourceUrl: "https://example.com/recipe",
  youtubeUrl: "https://youtube.com/watch?v=example",
  creativeCommonsConfirmed: null,
  ingredients: [
    { name: "penne rigate", measure: "1 pound" },
    { name: "olive oil", measure: null },
  ],
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function renderPage(path = "/?q=Arrabiata") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MealSearchPage />
    </MemoryRouter>,
  );
}

describe("MealSearchPage", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse([meal]));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("searches meals and displays the returned recipe details", async () => {
    const user = userEvent.setup();
    renderPage(`/?q=${encodeURIComponent("chicken & rice")}`);

    expect(await screen.findByRole("heading", { name: meal.name })).toBeVisible();
    const [requestedUrl] = fetchMock.mock.calls[0];
    expect(new URL(String(requestedUrl)).pathname).toBe("/api/meals/search");
    expect(new URL(String(requestedUrl)).searchParams.get("q")).toBe(
      "chicken & rice",
    );

    await user.click(screen.getByRole("button", { name: "Näytä resepti" }));

    expect(screen.getByText("1 pound penne rigate")).toBeVisible();
    expect(screen.getByText("olive oil")).toBeVisible();
    expect(screen.getByText(/Boil the pasta\./)).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Avaa resepti TheMealDB:ssä" }),
    ).toHaveAttribute("href", "https://www.themealdb.com/meal/52771");
    expect(screen.getByRole("link", { name: "Alkuperäinen lähde" })).toHaveAttribute(
      "href",
      "https://example.com/recipe",
    );
    expect(screen.getByRole("link", { name: "Katso video-ohje" })).toHaveAttribute(
      "href",
      meal.youtubeUrl,
    );
  });

  it("shows a no-results message when the API returns no meals", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reseptejä ei löytynyt.",
    );
  });

  it("saves the selected meal and navigates to its recipe", async () => {
    const savedRecipe = { id: 17 };
    fetchMock
      .mockResolvedValueOnce(jsonResponse([meal]))
      .mockResolvedValueOnce(jsonResponse(savedRecipe, 201));
    render(
      <MemoryRouter initialEntries={["/?q=Arrabiata"]}>
        <Routes>
          <Route path="/" element={<MealSearchPage />} />
          <Route path="/recipes/:id" element={<p>Saved recipe page</p>} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Näytä resepti" }));
    await user.click(screen.getByRole("button", { name: "Save recipe for nutrition" }));

    expect(await screen.findByText("Saved recipe page")).toBeVisible();
    expect(String(fetchMock.mock.calls[1][0])).toBe(
      "/api/external-recipes/id/52771/import",
    );
  });

  it("shows example recipes without making a request when there is no query", () => {
    renderPage("/");

    expect(screen.getByRole("heading", { name: "Dinner tonight" })).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Spicy Arrabiata Penne" }),
    ).toHaveAttribute("href", "/?q=Arrabiata");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a useful error when the backend rejects the search", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          detail: {
            code: "external_provider_unavailable",
            message: "External recipe provider unavailable",
          },
        },
        502,
      ),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reseptien haku epäonnistui: External recipe provider unavailable",
    );
  });

  it("rejects malformed meal data", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: "incomplete" }]));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "TheMealDB palautti odottamattoman vastauksen.",
    );
  });

  it("shows a loading message while the request is pending", async () => {
    let resolveResponse!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      }),
    );
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent("Haetaan...");
    resolveResponse(jsonResponse([]));
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
