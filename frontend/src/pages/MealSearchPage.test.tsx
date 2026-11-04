import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
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

function renderPage() {
  return render(
    <MemoryRouter>
      <MealSearchPage />
    </MemoryRouter>,
  );
}

describe("MealSearchPage", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse([meal]));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("searches meals and displays the returned recipe details", async () => {
    const user = userEvent.setup();
    renderPage();

    const searchInput = screen.getByRole("textbox", { name: "Hae reseptiä" });
    await user.clear(searchInput);
    await user.type(searchInput, "chicken & rice");
    await user.click(screen.getByRole("button", { name: "Hae" }));

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

    await userEvent.setup().click(screen.getByRole("button", { name: "Hae" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reseptejä ei löytynyt.",
    );
  });

  it("requires a non-blank query without making a request", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.clear(screen.getByRole("textbox", { name: "Hae reseptiä" }));
    await user.click(screen.getByRole("button", { name: "Hae" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Kirjoita ruokalajin nimi.",
    );
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

    await userEvent.setup().click(screen.getByRole("button", { name: "Hae" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reseptien haku epäonnistui: External recipe provider unavailable",
    );
  });

  it("rejects malformed meal data", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: "incomplete" }]));
    renderPage();

    await userEvent.setup().click(screen.getByRole("button", { name: "Hae" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "TheMealDB palautti odottamattoman vastauksen.",
    );
  });

  it("disables the search button while the request is pending", async () => {
    let resolveResponse!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      }),
    );
    renderPage();

    await userEvent.setup().click(screen.getByRole("button", { name: "Hae" }));

    expect(screen.getByRole("button", { name: "Haetaan..." })).toBeDisabled();
    resolveResponse(jsonResponse([]));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Hae" })).toBeEnabled();
    });
  });
});
