# API Usage Guide

How we call external APIs in this project, with TypeScript examples for **TheMealDB** (recipes) and **Fineli** (Finnish food composition data).

Read this before adding or changing any code that talks to a third-party API. Reviewers will check PRs against this document and `REVIEW_GUIDELINES.md`.

> **Validation status (last checked 2026-10-29)**
> - **Code:** every TypeScript file in this document was extracted into a real project, type-checked in `strict` mode, and exercised by the tests in [section 10](#10-testing): 59 tests pass on both Zod 3.25 and Zod 4.6. The tests were also mutation-checked (re-introducing the bugs below makes them fail). All HTTP is mocked, so **no live calls to either API were made**.
> - **TheMealDB:** endpoints, access tiers, key placement, image sizes and attribution come from the official API guide and agent guide. A few response-shape details are only partly confirmed; they are listed in [Appendix A](#appendix-a-validation-log).
> - **Fineli:** endpoints and terms are confirmed from Fineli's own pages. **Response field names, units, nutrient keys and "not found" behavior have not been verified** (the Swagger spec was not reachable). Every dependency on them is marked `VERIFY`. Fix those first (see [7.2](#72-fineli-verify-before-use)).
> - **Fixed during validation:** pre-aborted requests were still sent; one user cancelling a request could cancel a shared in-flight request for other users; one unexpected extra field in a TheMealDB record rejected the whole response; category/area filters wrongly had spaces replaced with underscores; network failures were not wrapped (mapped to HTTP 500 instead of 502); and the original key-leak test used a faked HTTP layer, so it never exercised the real `HttpError` redaction path (the new tests do).

---

## Contents

1. [Ground rules](#1-ground-rules)
2. [Project layout](#2-project-layout)
3. [Configuration and secrets](#3-configuration-and-secrets)
4. [Shared HTTP layer](#4-shared-http-layer)
5. [Caching and concurrency helpers](#5-caching-and-concurrency-helpers)
6. [TheMealDB](#6-themealdb)
7. [Fineli](#7-fineli)
8. [Combining recipes and nutrition](#8-combining-recipes-and-nutrition)
9. [Exposing data to the frontend](#9-exposing-data-to-the-frontend)
10. [Testing](#10-testing)
11. [Common mistakes](#11-common-mistakes)
12. [Pre-merge checklist](#12-pre-merge-checklist)

[Appendix A: Validation log](#appendix-a-validation-log)

---

## 1. Ground rules

1. **Never call third-party APIs directly from components.** All access goes through a client module in `src/lib/api/`.
2. **Validate every response at runtime** with Zod. TypeScript types do not protect us from API changes or crowd-sourced data quirks.
3. **Map provider shapes to our own domain types** at the boundary. The rest of the app never sees `strIngredient7`.
4. **Every request has a timeout.** Retries only for safe (GET) requests, with backoff, and only for network errors, `429` and `5xx`.
5. **Missing data stays missing.** Use `undefined`, never `0` or `""`, for unknown quantities, nutrients, or measures.
6. **Never imply safety or certainty about allergens or diets.** Neither API is an allergen or dietary certification service.
7. **Secrets stay server-side** and never appear in logs, error messages, or client bundles.
8. **Cache aggressively, call sparingly.** Recipe and composition data changes rarely. Do not call APIs per keystroke, per render, or inside unbounded loops.
9. **Attribute sources** where data or images are shown (see each API section).
10. **Use official endpoints only.** Do not scrape either website.

---

## 2. Project layout

```
src/
  lib/
    config.ts                 # env loading and validation
    api/
      http.ts                 # fetchJson, error classes, redaction
      cache.ts                # TTL cache with in-flight de-duplication
      concurrency.ts          # mapLimit
      themealdb/
        schemas.ts            # Zod schemas for raw API responses
        types.ts              # our domain types (Recipe, etc.)
        client.ts             # MealDbClient
        mapper.ts             # raw -> domain
        instance.ts           # configured singleton used by routes
      fineli/
        schemas.ts
        types.ts
        client.ts
        mapper.ts
        instance.ts
    nutrition/
      estimate.ts             # combines recipes with Fineli data
  server/
    routes/                   # HTTP handlers that use the clients
tests/
  http.test.ts  cache.test.ts  themealdb.test.ts  fineli.test.ts
  estimate.test.ts  routes.test.ts  config.test.ts
  fixtures/fineli/            # real saved responses (see 7.2)
```

Dependencies used in examples: `zod` (tested on 3.25 and 4.6), Node 18+ (global `fetch`; `AbortSignal.throwIfAborted` needs 17.3+), `express` for the route example, `vitest` for tests.

---

## 3. Configuration and secrets

```ts
// src/lib/config.ts
import { z } from "zod";

const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  // TheMealDB: "1" is the public development key. Production needs a supporter key.
  MEALDB_API_KEY: z.string().min(1).default("1"),
  MEALDB_BASE_URL: z.string().url().default("https://www.themealdb.com/api/json/v1"),
  FINELI_BASE_URL: z.string().url().default("https://fineli.fi/fineli/api/v1"),
  HTTP_TIMEOUT_MS: z.coerce.number().int().positive().default(8000),
});

export type AppConfig = z.infer<typeof EnvSchema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const config = EnvSchema.parse(env);

  // The dev key is for development and education only. Fail fast in production
  // instead of quietly shipping on the test key.
  if (config.NODE_ENV === "production" && config.MEALDB_API_KEY === "1") {
    throw new Error(
      "MEALDB_API_KEY is the public test key. Production requires a supporter key.",
    );
  }
  return config;
}
```

Rules:
- Keys live in environment variables (`.env.local`, CI secrets). Never commit them.
- **TheMealDB puts the API key in the URL path** (`/api/json/v1/<KEY>/search.php`). That means a premium key is exposed if the browser calls TheMealDB directly, and it will show up in any logged URL. Call it from the server and redact URLs in logs (see `redactUrl` below).
- Add new env vars to `.env.example` in the same PR.

---

## 4. Shared HTTP layer

All outbound requests go through `fetchJson`. It adds a timeout, bounded retries with backoff, and typed errors.

```ts
// src/lib/api/http.ts

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly url: string, // already redacted
    message?: string,
  ) {
    super(message ?? `HTTP ${status} for ${url}`);
    this.name = "HttpError";
  }
}

export class TimeoutError extends Error {
  constructor(public readonly url: string, public readonly timeoutMs: number) {
    super(`Request timed out after ${timeoutMs}ms: ${url}`);
    this.name = "TimeoutError";
  }
}

/** DNS failure, connection refused/reset, TLS error, etc. */
export class NetworkError extends Error {
  constructor(public readonly url: string, options?: { cause?: unknown }) {
    super(`Network error calling ${url}`, options);
    this.name = "NetworkError";
  }
}

export class ResponseValidationError extends Error {
  constructor(public readonly url: string, public readonly issues: unknown) {
    super(`Response failed validation: ${url}`);
    this.name = "ResponseValidationError";
  }
}

export class NotFoundError extends Error {
  constructor(what: string) {
    super(`${what} not found`);
    this.name = "NotFoundError";
  }
}

export interface FetchJsonOptions {
  timeoutMs?: number;     // default 8000
  retries?: number;       // default 2 (so up to 3 attempts)
  retryDelayMs?: number;  // base delay for exponential backoff, default 300
  signal?: AbortSignal;   // caller cancellation (e.g. user navigated away)
  /** Returns a version of the URL that is safe to log. Use it to hide keys in paths. */
  redact?: (url: string) => string;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);
const MAX_RETRY_AFTER_MS = 10_000; // never stall a request on a huge Retry-After

function parseRetryAfterMs(header: string | null): number | undefined {
  if (!header) return undefined;
  const seconds = Number(header);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(header);
  return Number.isNaN(date) ? undefined : Math.max(0, date - Date.now());
}

export async function fetchJson(
  url: string,
  {
    timeoutMs = 8000,
    retries = 2,
    retryDelayMs = 300,
    signal,
    redact = (u) => u,
  }: FetchJsonOptions = {},
): Promise<unknown> {
  const safeUrl = redact(url);
  let lastError: unknown;

  for (let attempt = 0; attempt <= retries; attempt++) {
    signal?.throwIfAborted(); // do not start (or restart) work nobody wants

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const onCallerAbort = () => controller.abort();
    signal?.addEventListener("abort", onCallerAbort, { once: true });

    try {
      const res = await fetch(url, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = new HttpError(res.status, safeUrl);
        if (RETRYABLE_STATUS.has(res.status) && attempt < retries) {
          lastError = err;
          const retryAfter = parseRetryAfterMs(res.headers.get("retry-after"));
          await sleep(Math.min(retryAfter ?? retryDelayMs * 2 ** attempt, MAX_RETRY_AFTER_MS));
          continue;
        }
        throw err;
      }

      // Some endpoints may return an empty body on "no data".
      const text = await res.text();
      if (!text.trim()) return null;
      try {
        return JSON.parse(text);
      } catch {
        throw new HttpError(res.status, safeUrl, `Non-JSON response from ${safeUrl}`);
      }
    } catch (err) {
      if (signal?.aborted) throw err; // caller cancelled: do not retry

      const timedOut = err instanceof DOMException && err.name === "AbortError";
      const network = err instanceof TypeError; // fetch() reports network failures as TypeError
      const wrapped: unknown = timedOut
        ? new TimeoutError(safeUrl, timeoutMs)
        : network
          ? new NetworkError(safeUrl, { cause: err })
          : err;

      if ((timedOut || network) && attempt < retries) {
        lastError = wrapped;
        await sleep(retryDelayMs * 2 ** attempt);
        continue;
      }
      throw wrapped;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onCallerAbort);
    }
  }
  throw lastError;
}
```

Notes:
- Only `GET` is used here, so retries are safe. Do not copy this retry logic for non-idempotent requests.
- Retried: network failures, timeouts, `429`, `500`, `502`, `503`, `504`. Never retried: other `4xx` (a `404` or `400` will not fix itself) and anything the caller cancelled.
- `Retry-After` is honored but capped at 10 seconds so one upstream header cannot stall a request for minutes.
- If the caller's signal is already aborted, no request is sent.
- Failures surface as typed errors (`HttpError`, `TimeoutError`, `NetworkError`, `ResponseValidationError`, `NotFoundError`) so route handlers can map them to status codes without string matching.
- `redact` is how we keep keys out of logs and error messages. Each client supplies its own.

---

## 5. Caching and concurrency helpers

### TTL cache with in-flight de-duplication and safe cancellation

If five components ask for the same meal at once, we want one request, not five.

**Cancellation rule:** the loader function is shared by everyone asking for the same key, so it must never use one caller's `AbortSignal`. Otherwise, one user closing a tab would cancel the request that other users are waiting on. Pass the caller's signal to `getOrLoad` as the third argument instead: that caller stops waiting immediately, the shared request keeps going (still bounded by its timeout), and its result is cached for everyone else. The tests in section 10 cover this.

```ts
// src/lib/api/cache.ts

interface Entry<T> {
  value: T;
  expiresAt: number;
}

/** Lets one caller stop waiting without cancelling the shared work. */
function raceAbort<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
    if (signal.aborted) return onAbort();
    signal.addEventListener("abort", onAbort, { once: true });
    promise
      .then(resolve, reject)
      .finally(() => signal.removeEventListener("abort", onAbort));
  });
}

export class TtlCache<T> {
  private store = new Map<string, Entry<T>>();
  private inflight = new Map<string, Promise<T>>();

  constructor(private readonly ttlMs: number, private readonly maxEntries = 500) {}

  /**
   * `load` is shared by every caller asking for the same key, so it must NOT use
   * any single caller's AbortSignal. Pass the caller's signal as the third argument
   * instead: that caller stops waiting, and the shared request keeps going so its
   * result is cached for everyone else. (The request is still bounded by its timeout.)
   */
  async getOrLoad(key: string, load: () => Promise<T>, signal?: AbortSignal): Promise<T> {
    signal?.throwIfAborted();

    const hit = this.store.get(key);
    if (hit && hit.expiresAt > Date.now()) return hit.value;

    let pending = this.inflight.get(key);
    if (!pending) {
      pending = load()
        .then((value) => {
          this.set(key, value);
          return value;
        })
        .finally(() => this.inflight.delete(key)); // failures are not cached
      this.inflight.set(key, pending);
    }
    return signal ? raceAbort(pending, signal) : pending;
  }

  private set(key: string, value: T) {
    if (this.store.size >= this.maxEntries) {
      // Map keeps insertion order: drop the oldest entry.
      const oldest = this.store.keys().next().value;
      if (oldest !== undefined) this.store.delete(oldest);
    }
    this.store.set(key, { value, expiresAt: Date.now() + this.ttlMs });
  }
}
```

Suggested TTLs (tune with real usage):

| Data | TTL |
|---|---|
| Category / area / ingredient lists | 24 hours |
| Meal by ID (lookup) | 24 hours |
| Search and filter results | 1 hour |
| Random meal | **Do not cache** (the point is variety) |
| Fineli food by ID, component list | 24 hours or longer (composition data changes rarely) |

In-memory caches reset on every deploy and are per-instance. For multi-instance production, use a shared cache (Redis, edge cache) behind the same interface.

### Bounded concurrency

```ts
// src/lib/api/concurrency.ts

export async function mapLimit<T, R>(
  items: readonly T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;

  async function worker() {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      results[i] = await fn(items[i], i);
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, worker),
  );
  return results;
}
```

Use it whenever you fan out (for example, looking up 20 meals after a filter). The default limit is **4** unless a provider documents otherwise.

---

## 6. TheMealDB

Docs: `https://www.themealdb.com/documentation` · Agent guide: `https://themealdb.com/AGENTS.md` · OpenAPI: `https://themealdb.com/api/spec/openapi-v1.yaml`

### 6.1 Access tiers

| | Free (V1) | Supporter / Premium (V2) |
|---|---|---|
| Base URL | `https://www.themealdb.com/api/json/v1/{KEY}/` | `https://www.themealdb.com/api/json/v2/{KEY}/` |
| Key | `1` (development and education) | Your supporter key |
| Extras | | Multi-ingredient filter, random 10, latest 10, larger limits |
| Public / production app | Not intended | Required |

We use **V1** for the endpoints below. V2-only features are noted where relevant.

### 6.2 Endpoint reference (V1)

All paths are appended to `{base}/{KEY}/`.

| Purpose | Request | Returns |
|---|---|---|
| Search by name | `search.php?s=Arrabiata` | Full meals |
| List by first letter | `search.php?f=a` | Full meals |
| Lookup by ID | `lookup.php?i=52772` | Full meal |
| Random meal | `random.php` | One full meal |
| Filter by ingredient | `filter.php?i=chicken_breast` | **Summaries only** |
| Filter by category | `filter.php?c=Seafood` | **Summaries only** |
| Filter by area | `filter.php?a=Canadian` | **Summaries only** |
| Category details | `categories.php` | `{ categories: [...] }` |
| List categories | `list.php?c=list` | Names |
| List areas | `list.php?a=list` | Names |
| List ingredients | `list.php?i=list` | Names and descriptions |

**Key behaviors to design around:**

1. **Filters return summaries** (`idMeal`, `strMeal`, `strMealThumb`). To show ingredients, measures, or instructions you must call `lookup.php` for each meal you intend to display. Never claim a filter result "has everything you need" without a lookup.
2. **Ingredients are flat fields.** `strIngredient1`..`strIngredient20` pair with `strMeasure1`..`strMeasure20` by number. Slots can be `null`, `""`, or whitespace. A measure can be blank while the ingredient is present.
3. **No-data results.** The official agent guide says searches and lookups can return an empty or no-data result but does not state the exact value. `{ "meals": null }` is what third-party examples assume. Our schema treats **any** non-array `meals` value as "no results", so it works whichever form the API uses. Confirm with a nonsense query (`search.php?s=zzzzqq`) and save the response as a fixture.
4. **Optional fields** (`strYoutube`, `strSource`, `strTags`, `strCreativeCommonsConfirmed`) may be missing, `null`, or empty.
5. **Preserve the recipe as written.** Do not invent missing quantities or silently substitute ingredients.

### 6.3 Schemas (raw API shapes)

```ts
// src/lib/api/themealdb/schemas.ts
import { z } from "zod";

const nullableString = z.string().nullish();

// Full meal record. Ingredient/measure slots (and any other extra fields the API
// adds later) fall into the catchall. It is `unknown` on purpose: one unexpected
// extra field must not make us reject an otherwise good recipe. The mapper only
// reads values it understands.
export const RawMealSchema = z
  .object({
    idMeal: z.string().min(1),
    strMeal: z.string().min(1),
    strCategory: nullableString,
    strArea: nullableString,
    strInstructions: nullableString,
    strMealThumb: nullableString,
    strTags: nullableString,
    strYoutube: nullableString,
    strSource: nullableString,
    strCreativeCommonsConfirmed: nullableString,
  })
  .catchall(z.unknown());

export type RawMeal = z.infer<typeof RawMealSchema>;

// Any non-array "meals" value (null, "no data" placeholder) becomes [].
const mealsOf = <T extends z.ZodTypeAny>(item: T) =>
  z.preprocess((v) => (Array.isArray(v) ? v : []), z.array(item));

export const MealsResponseSchema = z.object({ meals: mealsOf(RawMealSchema) });

export const RawMealSummarySchema = z.object({
  idMeal: z.string().min(1),
  strMeal: z.string().min(1),
  strMealThumb: nullableString,
});
export type RawMealSummary = z.infer<typeof RawMealSummarySchema>;

export const FilterResponseSchema = z.object({ meals: mealsOf(RawMealSummarySchema) });

export const CategoriesResponseSchema = z.object({
  categories: z.array(
    z.object({
      idCategory: z.string(),
      strCategory: z.string(),
      strCategoryThumb: nullableString,
      strCategoryDescription: nullableString,
    }),
  ),
});

export const CategoryListSchema = z.object({
  meals: mealsOf(z.object({ strCategory: z.string() })),
});
export const AreaListSchema = z.object({
  meals: mealsOf(z.object({ strArea: z.string() })),
});
export const IngredientListSchema = z.object({
  meals: mealsOf(
    z.object({
      idIngredient: z.string().nullish(),
      strIngredient: z.string(),
      strDescription: nullableString,
      strType: nullableString,
    }),
  ),
});
```

### 6.4 Domain types and mapping

```ts
// src/lib/api/themealdb/types.ts
export interface RecipeIngredient {
  name: string;
  /** As written by the source, e.g. "1 tbsp", "200g". Undefined if blank. */
  measure?: string;
}

export interface Recipe {
  id: string;
  name: string;
  category?: string;
  area?: string;
  instructions?: string;
  imageUrl?: string;
  tags: string[];
  youtubeUrl?: string;
  sourceUrl?: string;
  ingredients: RecipeIngredient[];
  /** Link to the canonical TheMealDB page (for attribution). */
  pageUrl: string;
}

export interface RecipeSummary {
  id: string;
  name: string;
  imageUrl?: string;
  pageUrl: string;
}

export const MEALDB_ATTRIBUTION =
  "Recipe data and imagery: TheMealDB (https://www.themealdb.com/)";
```

```ts
// src/lib/api/themealdb/mapper.ts
import type { RawMeal, RawMealSummary } from "./schemas";
import type { Recipe, RecipeSummary } from "./types";

const MAX_SLOTS = 20;

/** Trimmed non-empty string, or undefined for null/blank/non-string values. */
const clean = (v: unknown): string | undefined => {
  if (typeof v !== "string") return undefined;
  const t = v.trim();
  return t ? t : undefined;
};

export const mealPageUrl = (id: string) => `https://www.themealdb.com/meal/${id}`;

export function mapIngredients(raw: RawMeal) {
  const out: Recipe["ingredients"] = [];
  for (let n = 1; n <= MAX_SLOTS; n++) {
    const name = clean(raw[`strIngredient${n}`]);
    if (!name) continue; // empty slot
    out.push({ name, measure: clean(raw[`strMeasure${n}`]) });
  }
  return out;
}

export function mapMeal(raw: RawMeal): Recipe {
  return {
    id: raw.idMeal,
    name: raw.strMeal,
    category: clean(raw.strCategory),
    area: clean(raw.strArea),
    instructions: clean(raw.strInstructions),
    imageUrl: clean(raw.strMealThumb),
    tags: (clean(raw.strTags) ?? "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    youtubeUrl: clean(raw.strYoutube),
    sourceUrl: clean(raw.strSource),
    ingredients: mapIngredients(raw),
    pageUrl: mealPageUrl(raw.idMeal),
  };
}

export function mapSummary(raw: RawMealSummary): RecipeSummary {
  return {
    id: raw.idMeal,
    name: raw.strMeal,
    imageUrl: clean(raw.strMealThumb),
    pageUrl: mealPageUrl(raw.idMeal),
  };
}

export type ImageSize = "small" | "medium" | "large"; // ~200, 350, 500 px square

/** Meal image variants are made by appending the size to the image URL. */
export const sizedImage = (url: string | undefined, size: ImageSize) =>
  url ? `${url}/${size}` : undefined;
```

### 6.5 Client

```ts
// src/lib/api/themealdb/client.ts
import type { z } from "zod";
import { fetchJson, ResponseValidationError, NotFoundError } from "../http";
import { TtlCache } from "../cache";
import { mapLimit } from "../concurrency";
import {
  AreaListSchema,
  CategoriesResponseSchema,
  CategoryListSchema,
  FilterResponseSchema,
  IngredientListSchema,
  MealsResponseSchema,
} from "./schemas";
import { mapMeal, mapSummary } from "./mapper";
import type { Recipe, RecipeSummary } from "./types";

const HOUR = 60 * 60 * 1000;

export interface MealDbClientOptions {
  baseUrl: string;       // e.g. https://www.themealdb.com/api/json/v1
  apiKey: string;
  timeoutMs?: number;
  /** Injectable for tests. */
  fetchJson?: typeof fetchJson;
}

export class MealDbClient {
  private readonly fetchJson: typeof fetchJson;
  private readonly baseUrl: string;
  private readonly lookupCache = new TtlCache<Recipe | null>(24 * HOUR);
  private readonly searchCache = new TtlCache<Recipe[]>(1 * HOUR);
  private readonly filterCache = new TtlCache<RecipeSummary[]>(1 * HOUR);
  private readonly listCache = new TtlCache<string[]>(24 * HOUR);

  constructor(private readonly opts: MealDbClientOptions) {
    this.fetchJson = opts.fetchJson ?? fetchJson;
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
  }

  // ---------- internals ----------

  /**
   * The API key is a path segment. Build the real URL and a log-safe twin together,
   * so redaction never depends on string-searching for the key.
   */
  private build(path: string, params: Record<string, string>) {
    const qs = new URLSearchParams(params).toString(); // handles URL encoding
    const tail = qs ? `${path}?${qs}` : path;
    return {
      url: `${this.baseUrl}/${encodeURIComponent(this.opts.apiKey)}/${tail}`,
      safeUrl: `${this.baseUrl}/<redacted-key>/${tail}`,
    };
  }

  /** Validated GET. Pass `signal` only for uncached calls (see TtlCache.getOrLoad). */
  private async get<S extends z.ZodTypeAny>(
    path: string,
    params: Record<string, string>,
    schema: S,
    signal?: AbortSignal,
  ): Promise<z.infer<S>> {
    const { url, safeUrl } = this.build(path, params);
    const json = await this.fetchJson(url, {
      timeoutMs: this.opts.timeoutMs,
      redact: () => safeUrl,
      signal,
    });
    const parsed = schema.safeParse(json);
    if (!parsed.success) throw new ResponseValidationError(safeUrl, parsed.error.issues);
    return parsed.data;
  }

  // ---------- meals ----------

  async searchByName(name: string, signal?: AbortSignal): Promise<Recipe[]> {
    const q = name.trim();
    if (!q) return [];
    return this.searchCache.getOrLoad(
      `s:${q.toLowerCase()}`,
      async () => (await this.get("search.php", { s: q }, MealsResponseSchema)).meals.map(mapMeal),
      signal,
    );
  }

  async searchByFirstLetter(letter: string, signal?: AbortSignal): Promise<Recipe[]> {
    if (!/^[a-z]$/i.test(letter)) throw new RangeError("letter must be a single A-Z character");
    const f = letter.toLowerCase();
    return this.searchCache.getOrLoad(
      `f:${f}`,
      async () => (await this.get("search.php", { f }, MealsResponseSchema)).meals.map(mapMeal),
      signal,
    );
  }

  /** Returns null when the ID does not exist. */
  async lookup(id: string, signal?: AbortSignal): Promise<Recipe | null> {
    if (!/^\d+$/.test(id)) throw new RangeError("meal id must be numeric");
    return this.lookupCache.getOrLoad(
      `i:${id}`,
      async () => {
        const res = await this.get("lookup.php", { i: id }, MealsResponseSchema);
        return res.meals[0] ? mapMeal(res.meals[0]) : null;
      },
      signal,
    );
  }

  async lookupOrThrow(id: string, signal?: AbortSignal): Promise<Recipe> {
    const r = await this.lookup(id, signal);
    if (!r) throw new NotFoundError(`Meal ${id}`);
    return r;
  }

  /** Not cached on purpose, so the signal goes straight to the request. */
  async random(signal?: AbortSignal): Promise<Recipe | null> {
    const res = await this.get("random.php", {}, MealsResponseSchema, signal);
    return res.meals[0] ? mapMeal(res.meals[0]) : null;
  }

  // ---------- filters (summaries only) ----------

  filterByIngredient(ingredient: string, signal?: AbortSignal) {
    // The documented form uses underscores for spaces (chicken_breast).
    return this.filter("i", ingredient.trim().replace(/\s+/g, "_"), signal);
  }
  /** Use a value returned by listCategories(). */
  filterByCategory(category: string, signal?: AbortSignal) {
    return this.filter("c", category.trim(), signal);
  }
  /** Use a value returned by listAreas(). */
  filterByArea(area: string, signal?: AbortSignal) {
    return this.filter("a", area.trim(), signal);
  }

  private async filter(
    kind: "i" | "c" | "a",
    value: string,
    signal?: AbortSignal,
  ): Promise<RecipeSummary[]> {
    if (!value) return [];
    return this.filterCache.getOrLoad(
      `filter:${kind}:${value.toLowerCase()}`,
      async () =>
        (await this.get("filter.php", { [kind]: value }, FilterResponseSchema)).meals.map(mapSummary),
      signal,
    );
  }

  /**
   * Filter, then look up full details for the first `limit` results.
   * This is the correct pattern for "show recipes with ingredient X".
   */
  async findRecipesByIngredient(
    ingredient: string,
    { limit = 12, concurrency = 4 }: { limit?: number; concurrency?: number } = {},
    signal?: AbortSignal,
  ): Promise<Recipe[]> {
    const summaries = (await this.filterByIngredient(ingredient, signal)).slice(0, limit);
    const full = await mapLimit(summaries, concurrency, (s) => this.lookup(s.id, signal));
    return full.filter((r): r is Recipe => r !== null);
  }

  // ---------- lists ----------

  async listCategories(signal?: AbortSignal): Promise<string[]> {
    return this.listCache.getOrLoad(
      "categories",
      async () =>
        (await this.get("list.php", { c: "list" }, CategoryListSchema)).meals.map((m) => m.strCategory),
      signal,
    );
  }

  async listAreas(signal?: AbortSignal): Promise<string[]> {
    return this.listCache.getOrLoad(
      "areas",
      async () => (await this.get("list.php", { a: "list" }, AreaListSchema)).meals.map((m) => m.strArea),
      signal,
    );
  }

  async listIngredients(signal?: AbortSignal): Promise<string[]> {
    return this.listCache.getOrLoad(
      "ingredients",
      async () =>
        (await this.get("list.php", { i: "list" }, IngredientListSchema)).meals.map((m) => m.strIngredient),
      signal,
    );
  }

  async categoryDetails(signal?: AbortSignal) {
    const res = await this.get("categories.php", {}, CategoriesResponseSchema, signal);
    return res.categories;
  }
}
```

Design notes:
- **Cancellation:** cached methods pass the caller's `signal` to the cache (so only that caller stops waiting). Uncached calls (`random`, `categoryDetails`) pass it straight to the request.
- **Redaction:** the real URL and a log-safe URL are built together, so the key is never found by string search. The test suite checks this, including with key `1`.
- **Filter values:** only the ingredient filter replaces spaces with underscores (the documented form, `chicken_breast`). For category and area, use values returned by `listCategories()` and `listAreas()`; the client sends them as given, URL-encoded.
- **Base URL:** trailing slashes are stripped.

### 6.6 Usage examples

The configured client is created once and imported where needed. `loadConfig()` runs at import time, so a bad environment (including the test key in production) fails at startup, not on the first request.

```ts
// src/lib/api/themealdb/instance.ts
import { loadConfig } from "../../config";
import { MealDbClient } from "./client";

const config = loadConfig(); // throws on bad env (and on the test key in production)

export const mealDb = new MealDbClient({
  baseUrl: config.MEALDB_BASE_URL,
  apiKey: config.MEALDB_API_KEY,
  timeoutMs: config.HTTP_TIMEOUT_MS,
});
```

```ts
import { mealDb } from "@/lib/api/themealdb/instance";

// 1. Search by name
const results = await mealDb.searchByName("arrabiata");
if (results.length === 0) {
  // Show an empty state. Do not fabricate a recipe.
}

// 2. Full recipe for a detail page
const recipe = await mealDb.lookupOrThrow("52772");
console.log(recipe.name, recipe.ingredients); // [{ name: "...", measure: "..." }, ...]

// 3. "What can I make with chicken?" (filter, then lookup)
const recipes = await mealDb.findRecipesByIngredient("chicken breast", { limit: 8 });

// 4. Browse a category using a value from the API's own list
const [firstCategory] = await mealDb.listCategories();
const summaries = await mealDb.filterByCategory(firstCategory);

// 5. Cancellable request (e.g. search-as-you-type). Aborting stops THIS caller
//    waiting; other callers sharing the same request are unaffected.
const controller = new AbortController();
const p = mealDb.searchByName("pasta", controller.signal);
controller.abort(); // user typed again: p rejects with AbortError
```

### 6.7 Rendering recipes correctly

- Display **ingredients paired with measures** exactly as given. If `measure` is `undefined`, show just the ingredient name.
- Link the meal title to `recipe.pageUrl` and show `MEALDB_ATTRIBUTION` somewhere visible where recipes or images appear (footer is acceptable for a site-wide credit; add it to detail pages as well).
- Use `sizedImage(recipe.imageUrl, "medium")` for cards and `"large"` for detail pages. Add `loading="lazy"`, explicit `width`/`height`, and a fallback for broken images.
- If `sourceUrl` or Creative Commons metadata is present, keep it visible. Do not strip source or licensing information.
- **Never** show badges such as "vegan", "gluten-free", or "allergy-safe" based on `category`, `area`, `tags`, or a name. See [section 8](#8-combining-recipes-and-nutrition).

### 6.8 TheMealDB pitfalls

| Pitfall | Do this instead |
|---|---|
| Treating `filter.php` results as full recipes | Look up each ID before displaying ingredients/instructions |
| Assuming `meals` is always an array | Use the `mealsOf` preprocess (non-array becomes `[]`) |
| Indexing `strIngredient1..20` by hand in components | Use `mapIngredients` |
| Using `0`/`""` for blank measures | Keep `undefined` |
| Replacing spaces with underscores for category/area filters | Only ingredient filters are documented that way; use values from `listCategories()` / `listAreas()` |
| Rejecting a whole recipe because of one odd extra field | Keep the schema's catchall as `z.unknown()`; read only what you understand |
| Calling on every keystroke | Debounce (300 ms+), cancel stale requests, cache |
| Looping over `lookup` for hundreds of IDs | Limit results, use `mapLimit`, rely on the 24 h cache |
| Calling from the browser with a premium key | Proxy through the server |
| Shipping with key `1` | `loadConfig` fails in production |

---

## 7. Fineli

Fineli is the Finnish national food composition database maintained by THL (the Finnish Institute for Health and Welfare). Open data page: `https://fineli.fi/fineli/en/avoin-data` · Swagger spec: `https://fineli.fi/fineli/v2/api-docs`

### 7.1 What is documented

| Purpose | Request |
|---|---|
| List nutrient components | `GET https://fineli.fi/fineli/api/v1/components/` |
| Search foods by keyword | `GET https://fineli.fi/fineli/api/v1/foods?q=omena` |
| Food by ID | `GET https://fineli.fi/fineli/api/v1/foods/11060` |

- The three endpoints come from Fineli's own help/open-data pages (the `foods?q=` search form appears on the Finnish pages and is used by third-party apps). The Swagger spec is linked from those pages.
- No API key or authentication is mentioned in the documentation.
- No rate limits are documented. Assume they exist and cache accordingly.
- The service is JSON and has Finnish, Swedish, and English content.
- A bulk **CSV open data package** is also available (about 4,200 foods; food names in Finnish, Swedish and English; household measures and portion sizes). For high-traffic or latency-sensitive features, prefer loading this into our own datastore over calling the live API.

### 7.2 Fineli: verify before use

Do this once, then delete the `VERIFY` comments you resolved:

1. Open the Swagger spec (`https://fineli.fi/fineli/v2/api-docs`) and note the response models for `/foods`, `/foods/{id}`, and `/components`.
2. Run these and save real responses as test fixtures in `tests/fixtures/fineli/`:
   ```bash
   curl -s "https://fineli.fi/fineli/api/v1/foods?q=omena"   | jq . > tests/fixtures/fineli/search-omena.json
   curl -s "https://fineli.fi/fineli/api/v1/foods/11060"      | jq . > tests/fixtures/fineli/food-11060.json
   curl -s "https://fineli.fi/fineli/api/v1/components/"      | jq . > tests/fixtures/fineli/components.json
   ```
3. Confirm: ID type, name structure (per-language?), whether nutrients are per 100 g, nutrient field names and units, how missing values appear, and whether English search terms work.
4. Update `schemas.ts` to match, and make the tests in `tests/fineli.test.ts` use the fixtures.
5. Test from your deployed server environment. Automated requests to the Fineli site may be blocked by bot detection in some environments.

### 7.3 Schemas (provisional)

The schemas below are deliberately permissive (`passthrough`) so unknown fields do not break us, but they **must be tightened after step 7.2**.

```ts
// src/lib/api/fineli/schemas.ts
import { z } from "zod";

// VERIFY: names may be { fi, sv, en } or a different structure.
export const LocalizedNameSchema = z
  .object({
    fi: z.string().nullish(),
    sv: z.string().nullish(),
    en: z.string().nullish(),
  })
  .passthrough();

// VERIFY: id type and all other field names.
export const FineliFoodSchema = z
  .object({
    id: z.coerce.number().int(),
    name: LocalizedNameSchema,
  })
  .passthrough();
export type RawFineliFood = z.infer<typeof FineliFoodSchema>;

// VERIFY: the search endpoint may return a bare array or a wrapper object.
export const FineliSearchResponseSchema = z.array(FineliFoodSchema);

// VERIFY: component shape (code, names, unit).
export const FineliComponentSchema = z
  .object({ id: z.union([z.string(), z.number()]).optional() })
  .passthrough();
export const FineliComponentsResponseSchema = z.array(FineliComponentSchema);
```

### 7.4 Domain types and mapping

We expose a small, stable domain type. Nutrient values are keyed by a **provider key** and carry their unit and basis explicitly, so a nutrient without a value or unit cannot masquerade as zero.

```ts
// src/lib/api/fineli/types.ts
export type Lang = "fi" | "sv" | "en";

export interface NutrientValue {
  /** Undefined means unknown/not reported. It never means zero. */
  amount?: number;
  /** VERIFY: unit as defined by Fineli (e.g. g, mg, µg, kcal). */
  unit?: string;
}

export interface Food {
  id: number;
  names: Partial<Record<Lang, string>>;
  /** VERIFY: confirm this basis from the spec before displaying values. */
  basis: "per100g";
  nutrients: Record<string, NutrientValue>;
}

export const FINELI_ATTRIBUTION =
  "Nutrition data: Fineli, Finnish Institute for Health and Welfare (THL). " +
  "This site is not produced or endorsed by THL.";
```

```ts
// src/lib/api/fineli/mapper.ts
import type { RawFineliFood } from "./schemas";
import type { Food, Lang, NutrientValue } from "./types";

const finiteNumber = (v: unknown): number | undefined =>
  typeof v === "number" && Number.isFinite(v) ? v : undefined;

/**
 * VERIFY: replace this with explicit field mapping after reading the spec.
 * Until then we only copy top-level numeric fields and never invent values.
 */
function extractNutrients(raw: RawFineliFood): Record<string, NutrientValue> {
  const out: Record<string, NutrientValue> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (key === "id" || key === "name") continue;
    const amount = finiteNumber(value);
    if (amount !== undefined) out[key] = { amount };
  }
  return out;
}

export function mapFood(raw: RawFineliFood): Food {
  const names: Food["names"] = {};
  for (const lang of ["fi", "sv", "en"] as const) {
    const n = raw.name[lang]?.trim();
    if (n) names[lang] = n;
  }
  return { id: raw.id, names, basis: "per100g", nutrients: extractNutrients(raw) };
}

/** Prefer the requested language, then English, Finnish, Swedish. */
export function displayName(food: Food, lang: Lang = "en"): string {
  return (
    food.names[lang] ?? food.names.en ?? food.names.fi ?? food.names.sv ?? `Food #${food.id}`
  );
}
```

### 7.5 Client

```ts
// src/lib/api/fineli/client.ts
import type { z } from "zod";
import { fetchJson, HttpError, ResponseValidationError } from "../http";
import { TtlCache } from "../cache";
import {
  FineliComponentsResponseSchema,
  FineliFoodSchema,
  FineliSearchResponseSchema,
} from "./schemas";
import { mapFood } from "./mapper";
import type { Food } from "./types";

const HOUR = 60 * 60 * 1000;

export interface FineliClientOptions {
  baseUrl: string; // https://fineli.fi/fineli/api/v1
  timeoutMs?: number;
  fetchJson?: typeof fetchJson;
}

export class FineliClient {
  private readonly fetchJson: typeof fetchJson;
  private readonly baseUrl: string;
  private readonly foodCache = new TtlCache<Food | null>(24 * HOUR);
  private readonly searchCache = new TtlCache<Food[]>(6 * HOUR);
  private readonly componentCache = new TtlCache<unknown[]>(24 * HOUR);

  constructor(private readonly opts: FineliClientOptions) {
    this.fetchJson = opts.fetchJson ?? fetchJson;
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
  }

  /** Validated GET. Pass `signal` only for uncached calls (see TtlCache.getOrLoad). */
  private async get<S extends z.ZodTypeAny>(
    path: string,
    params: Record<string, string>,
    schema: S,
    signal?: AbortSignal,
  ): Promise<z.infer<S>> {
    const qs = new URLSearchParams(params).toString();
    const url = `${this.baseUrl}/${path}${qs ? `?${qs}` : ""}`;
    const json = await this.fetchJson(url, { timeoutMs: this.opts.timeoutMs, signal });
    const parsed = schema.safeParse(json);
    if (!parsed.success) throw new ResponseValidationError(url, parsed.error.issues);
    return parsed.data;
  }

  async searchFoods(query: string, signal?: AbortSignal): Promise<Food[]> {
    const q = query.trim();
    if (q.length < 2) return []; // avoid pointless broad queries
    return this.searchCache.getOrLoad(
      `q:${q.toLowerCase()}`,
      async () => (await this.get("foods", { q }, FineliSearchResponseSchema)).map(mapFood),
      signal,
    );
  }

  /** Returns null when the food does not exist. */
  async getFood(id: number, signal?: AbortSignal): Promise<Food | null> {
    if (!Number.isInteger(id) || id <= 0) throw new RangeError("invalid food id");
    return this.foodCache.getOrLoad(
      `id:${id}`,
      async () => {
        try {
          return mapFood(await this.get(`foods/${id}`, {}, FineliFoodSchema));
        } catch (err) {
          // VERIFY: confirm how Fineli reports an unknown ID (404 is assumed).
          if (err instanceof HttpError && err.status === 404) return null;
          throw err;
        }
      },
      signal,
    );
  }

  async listComponents(signal?: AbortSignal) {
    return this.componentCache.getOrLoad(
      "components",
      async () => this.get("components/", {}, FineliComponentsResponseSchema),
      signal,
    );
  }
}
```

### 7.6 Usage examples

```ts
// src/lib/api/fineli/instance.ts
import { loadConfig } from "../../config";
import { FineliClient } from "./client";

const config = loadConfig();

export const fineli = new FineliClient({
  baseUrl: config.FINELI_BASE_URL,
  timeoutMs: config.HTTP_TIMEOUT_MS,
});
```

```ts
import { fineli } from "@/lib/api/fineli/instance";
import { displayName } from "@/lib/api/fineli/mapper";

// Search (Finnish example from the docs; test English terms too)
const apples = await fineli.searchFoods("omena");
console.log(apples.map((f) => displayName(f, "fi")));

// By ID
const food = await fineli.getFood(11060);
if (!food) {
  // Show "not found"
}
```

### 7.7 Displaying Fineli data correctly

- Show **units and basis** next to every number (for example "per 100 g"). Do not display a bare number.
- If a nutrient is not present, show "not available", **never 0**.
- Values are **averages for foods typical in Finland**, not guarantees for a specific product or brand. Say so wherever values appear.
- Show `FINELI_ATTRIBUTION`. Fineli is a registered trademark of THL. Do not name, style, or word the site in a way that suggests THL produced it, recommends it, or that it is part of the Fineli service.
- Check the open data page for the current licence/attribution wording before launch, and update `FINELI_ATTRIBUTION` if it says something different.

### 7.8 Fineli pitfalls

| Pitfall | Do this instead |
|---|---|
| Hand-writing types from memory | Generate or write schemas from the Swagger spec and real fixtures |
| Treating a missing nutrient as `0` | `undefined`, display "not available" |
| Displaying values without basis/unit | Always show "per 100 g" (or whatever the spec says) and the unit |
| Searching on every keystroke | Debounce, minimum 2 characters, cancel stale requests |
| Hammering the live API for bulk work | Use the CSV open data package and load it into our datastore |
| Assuming search works in every language | Test Finnish, Swedish and English queries; fall back gracefully |
| Branding that suggests THL involvement | Use the attribution text; get legal/product review if unsure |

---

## 8. Combining recipes and nutrition

TheMealDB ingredients are free-text English strings with free-text measures ("1 tbsp", "a pinch", "200g"). Fineli foods are Finnish database entries with composition per 100 g. Connecting them is **approximate**, and the UI must reflect that.

### 8.1 Rules

1. **Nutrition from recipes is an estimate.** Label it "approximate" and show how much of the recipe it covers.
2. **Only count what we can convert.** If a measure cannot be turned into grams with confidence, exclude that ingredient and record it as unmatched. Do not guess "1 cup of flour = X g".
3. **Report coverage.** Show "based on 5 of 9 ingredients" or similar so users are not misled.
4. **Matching ingredient names to Fineli IDs is a curated step.** Maintain an explicit mapping file (`ingredient-map.json`: `{"chicken breast": 12345}`) reviewed by the team. Do not auto-pick the first search hit.
5. **Allergens and diets are out of scope for inference.** Neither source certifies them (see 8.3).

### 8.2 Example: coverage-aware estimate

```ts
// src/lib/nutrition/estimate.ts
import type { Recipe } from "@/lib/api/themealdb/types";
import type { Food } from "@/lib/api/fineli/types";

/** Only parses plain gram/kilogram measures. Everything else is unknown. */
export function parseGrams(measure: string | undefined): number | undefined {
  if (!measure) return undefined;
  const m = measure.trim().toLowerCase().match(/^(\d+(?:[.,]\d+)?)\s*(g|gr|grams?|kg|kilograms?)$/);
  if (!m) return undefined;
  const value = Number(m[1].replace(",", "."));
  if (!Number.isFinite(value)) return undefined;
  return m[2].startsWith("k") ? value * 1000 : value;
}

export interface NutrientEstimate {
  /** Total across matched ingredients. Undefined if nothing could be counted. */
  total?: number;
  /** Ingredients that contributed to the total. */
  counted: string[];
  /** Ingredients we could not include (no match, no gram weight, or nutrient missing). */
  skipped: { name: string; reason: "no-match" | "no-grams" | "no-nutrient" }[];
  /** counted / total ingredients, 0..1 */
  coverage: number;
}

export function estimateNutrient(
  recipe: Recipe,
  nutrientKey: string, // VERIFY against Fineli nutrient keys
  foodFor: (ingredientName: string) => Food | undefined, // from the curated map
): NutrientEstimate {
  const counted: string[] = [];
  const skipped: NutrientEstimate["skipped"] = [];
  let total = 0;

  for (const ing of recipe.ingredients) {
    const food = foodFor(ing.name);
    if (!food) { skipped.push({ name: ing.name, reason: "no-match" }); continue; }

    const grams = parseGrams(ing.measure);
    if (grams === undefined) { skipped.push({ name: ing.name, reason: "no-grams" }); continue; }

    const per100 = food.nutrients[nutrientKey]?.amount;
    if (per100 === undefined) { skipped.push({ name: ing.name, reason: "no-nutrient" }); continue; }

    total += (per100 * grams) / 100; // values are per 100 g (VERIFY)
    counted.push(ing.name);
  }

  return {
    total: counted.length ? total : undefined,
    counted,
    skipped,
    coverage: recipe.ingredients.length ? counted.length / recipe.ingredients.length : 0,
  };
}
```

UI guidance: if `coverage < 0.5`, do not show a headline number. Show "not enough data to estimate".

### 8.3 Allergens and dietary claims

- Do not label a recipe as vegan, vegetarian, gluten-free, dairy-free, halal, kosher, or "allergy-friendly" based on category, area, tags, name, or an ingredient scan.
- If we show ingredient-based hints (for example "contains: milk" because an ingredient string includes it), label them as **"Ingredients mention..."**, never as a complete list, and add: *"Always check ingredient labels and cross-contamination risks."*
- A recipe's absence of an allergen in its ingredient list is **not** evidence that the recipe is safe.

---

## 9. Exposing data to the frontend

The browser talks to **our** API, not to TheMealDB or Fineli. This hides keys, lets us cache centrally, and gives us one place to validate input.

Framework-neutral example with Express (adapt to your framework):

```ts
// src/server/routes/recipes.ts
import { Router, type ErrorRequestHandler } from "express";
import { z } from "zod";
import { mealDb } from "@/lib/api/themealdb/instance";
import {
  HttpError, NetworkError, NotFoundError, ResponseValidationError, TimeoutError,
} from "@/lib/api/http";
import { MEALDB_ATTRIBUTION } from "@/lib/api/themealdb/types";

export const recipesRouter = Router();

const SearchQuery = z.object({ q: z.string().trim().min(1).max(100) });
const IdParam = z.object({ id: z.string().regex(/^\d{1,10}$/) });

recipesRouter.get("/search", async (req, res, next) => {
  const parsed = SearchQuery.safeParse(req.query);
  if (!parsed.success) return res.status(400).json({ error: "Invalid query" });

  const controller = new AbortController();
  res.on("close", () => controller.abort()); // client went away: stop upstream work

  try {
    const recipes = await mealDb.searchByName(parsed.data.q, controller.signal);
    res.set("Cache-Control", "public, max-age=300");
    res.json({ recipes, attribution: MEALDB_ATTRIBUTION });
  } catch (err) {
    next(err);
  }
});

recipesRouter.get("/:id", async (req, res, next) => {
  const parsed = IdParam.safeParse(req.params);
  if (!parsed.success) return res.status(400).json({ error: "Invalid id" });
  try {
    const recipe = await mealDb.lookupOrThrow(parsed.data.id);
    res.set("Cache-Control", "public, max-age=3600");
    res.json({ recipe, attribution: MEALDB_ATTRIBUTION });
  } catch (err) {
    next(err);
  }
});

// Central error mapping: never leak upstream URLs, keys, or raw upstream bodies.
export const apiErrorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
  // The client disconnected and we cancelled on purpose: nobody is listening.
  if (err instanceof DOMException && err.name === "AbortError") return;
  if (res.headersSent) return;

  if (err instanceof NotFoundError) return void res.status(404).json({ error: "Not found" });
  if (err instanceof TimeoutError) return void res.status(504).json({ error: "Upstream timed out" });
  if (err instanceof HttpError && err.status === 429) {
    return void res.status(503).json({ error: "Service busy, try again shortly" });
  }
  if (
    err instanceof HttpError ||
    err instanceof NetworkError ||
    err instanceof ResponseValidationError
  ) {
    console.error("[upstream]", err.name, err.message); // message is already redacted
    return void res.status(502).json({ error: "Upstream service problem" });
  }
  console.error("[unhandled]", err);
  res.status(500).json({ error: "Internal error" });
};
```

Notes on the route code:
- `res.on("close")` aborts the work for **this** request only. Because the cache separates "stop waiting" from "stop the shared request", a user disconnecting cannot break anyone else's identical search.
- The error handler is typed as `ErrorRequestHandler`, ignores client aborts, and never writes after headers were sent.
- Upstream `429` becomes our `503`, not a `429`: from the browser's point of view, we are the one that is temporarily unavailable.

Frontend rules:
- **Debounce** search inputs (300 ms or more) and cancel in-flight requests with `AbortController` (or your data-fetching library's equivalent).
- Model request state as a discriminated union:

```ts
type Remote<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "empty" }
  | { status: "error"; message: string };
```

- Every list needs distinct loading, empty, and error states.
- Server error messages shown to users are generic. Details go to logs only.

---

## 10. Testing

Do not call real third-party APIs in tests. The clients accept an injected `fetchJson`, and `fetchJson` itself is tested by stubbing the global `fetch`.

The suite below is the one that was run to validate this document (59 tests, passing on Zod 3.25 and 4.6, type-checked with `strict`). To run it, add this `vitest.config.ts` and a matching `paths` entry in `tsconfig.json`:

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
});
```

```json
{ "compilerOptions": { "paths": { "@/*": ["./src/*"] } } }
```

### HTTP layer and secret handling

```ts
// tests/http.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJson, HttpError, NetworkError, TimeoutError } from "@/lib/api/http";
import { MealDbClient } from "@/lib/api/themealdb/client";

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const status = (code: number, headers: Record<string, string> = {}) =>
  new Response("", { status: code, headers });

afterEach(() => vi.unstubAllGlobals());

describe("fetchJson", () => {
  it("retries a 503 and then succeeds", async () => {
    const f = vi.fn().mockResolvedValueOnce(status(503)).mockResolvedValueOnce(ok({ a: 1 }));
    vi.stubGlobal("fetch", f);
    expect(await fetchJson("https://x.test/a", { retryDelayMs: 1 })).toEqual({ a: 1 });
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("does not retry a 404", async () => {
    const f = vi.fn().mockResolvedValue(status(404));
    vi.stubGlobal("fetch", f);
    await expect(fetchJson("https://x.test/a", { retryDelayMs: 1 })).rejects.toBeInstanceOf(HttpError);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("gives up after the configured retries", async () => {
    const f = vi.fn().mockResolvedValue(status(500));
    vi.stubGlobal("fetch", f);
    await expect(fetchJson("https://x.test/a", { retries: 2, retryDelayMs: 1 })).rejects.toBeInstanceOf(HttpError);
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("honors Retry-After on 429", async () => {
    const f = vi.fn().mockResolvedValueOnce(status(429, { "retry-after": "0" })).mockResolvedValueOnce(ok({}));
    vi.stubGlobal("fetch", f);
    await fetchJson("https://x.test/a");
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("turns a hung request into a TimeoutError", async () => {
    vi.stubGlobal("fetch", (_u: string, init: RequestInit) =>
      new Promise((_res, rej) =>
        init.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))),
      ),
    );
    await expect(fetchJson("https://x.test/a", { timeoutMs: 20, retries: 0 })).rejects.toBeInstanceOf(TimeoutError);
  });

  it("wraps network failures in NetworkError (and retries them)", async () => {
    const f = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    vi.stubGlobal("fetch", f);
    await expect(fetchJson("https://x.test/a", { retries: 1, retryDelayMs: 1 })).rejects.toBeInstanceOf(NetworkError);
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("returns null for an empty body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 200 })));
    expect(await fetchJson("https://x.test/a")).toBeNull();
  });

  it("does not send a request when the caller signal is already aborted", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    const c = new AbortController();
    c.abort();
    await expect(fetchJson("https://x.test/a", { signal: c.signal })).rejects.toBeDefined();
    expect(f).not.toHaveBeenCalled();
  });

  it("does not retry after the caller aborts", async () => {
    const c = new AbortController();
    const f = vi.fn((_u: string, init: RequestInit) =>
      new Promise((_res, rej) => {
        init.signal!.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
        setTimeout(() => c.abort(), 5);
      }),
    );
    vi.stubGlobal("fetch", f);
    await expect(fetchJson("https://x.test/a", { signal: c.signal, retryDelayMs: 1 })).rejects.toBeDefined();
    expect(f).toHaveBeenCalledTimes(1);
  });
});

describe("secret handling", () => {
  it("never leaks the API key through HttpError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(400)));
    const client = new MealDbClient({ baseUrl: "https://x.test/v1", apiKey: "SECRETKEY" });
    const err = await client.lookup("1").catch((e) => e);
    expect(err).toBeInstanceOf(HttpError);
    expect(JSON.stringify({ m: err.message, u: err.url, s: err.stack })).not.toContain("SECRETKEY");
  });

  it("redacts correctly even when the key is '1'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(400)));
    const client = new MealDbClient({ baseUrl: "https://x.test/1/v1", apiKey: "1" });
    const err = await client.lookup("1").catch((e) => e);
    expect(err.url).toBe("https://x.test/1/v1/<redacted-key>/lookup.php?i=1");
  });
});
```

### Cache, cancellation and concurrency

```ts
// tests/cache.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { TtlCache } from "@/lib/api/cache";
import { mapLimit } from "@/lib/api/concurrency";
import { MealDbClient } from "@/lib/api/themealdb/client";

afterEach(() => vi.unstubAllGlobals());

describe("TtlCache", () => {
  it("does not cache failures", async () => {
    const c = new TtlCache<number>(1000);
    await expect(c.getOrLoad("k", async () => { throw new Error("boom"); })).rejects.toThrow("boom");
    expect(await c.getOrLoad("k", async () => 5)).toBe(5);
  });

  it("de-duplicates concurrent loads", async () => {
    const c = new TtlCache<number>(1000);
    const load = vi.fn(async () => 1);
    await Promise.all([c.getOrLoad("k", load), c.getOrLoad("k", load), c.getOrLoad("k", load)]);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("expires entries after the TTL", async () => {
    vi.useFakeTimers();
    const c = new TtlCache<number>(1000);
    const load = vi.fn(async () => 1);
    await c.getOrLoad("k", load);
    vi.advanceTimersByTime(1001);
    await c.getOrLoad("k", load);
    expect(load).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("evicts the oldest entry beyond maxEntries", async () => {
    const c = new TtlCache<number>(1000, 2);
    const load = vi.fn(async () => 1);
    await c.getOrLoad("a", load);
    await c.getOrLoad("b", load);
    await c.getOrLoad("c", load); // evicts "a"
    await c.getOrLoad("a", load);
    expect(load).toHaveBeenCalledTimes(4);
  });

  it("lets one caller abort without breaking others sharing the request", async () => {
    const c = new TtlCache<string>(1000);
    const load = vi.fn(() => new Promise<string>((res) => setTimeout(() => res("done"), 30)));
    const a = new AbortController();
    const pa = c.getOrLoad("k", load, a.signal).catch((e) => e);
    const pb = c.getOrLoad("k", load);
    a.abort();
    expect((await pa).name).toBe("AbortError");
    await expect(pb).resolves.toBe("done");
    expect(load).toHaveBeenCalledTimes(1);
    expect(await c.getOrLoad("k", load)).toBe("done"); // cached for later callers
    expect(load).toHaveBeenCalledTimes(1);
  });
});

describe("MealDbClient with shared requests", () => {
  it("one user cancelling a search does not fail another user's identical search", async () => {
    const f = vi.fn(() =>
      new Promise((res) => setTimeout(() => res(new Response(JSON.stringify({ meals: null }))), 30)),
    );
    vi.stubGlobal("fetch", f);
    const client = new MealDbClient({ baseUrl: "https://x.test/v1", apiKey: "1" });
    const a = new AbortController();
    const pa = client.searchByName("pasta", a.signal).catch((e) => e);
    const pb = client.searchByName("pasta");
    a.abort();
    expect((await pa).name).toBe("AbortError");
    await expect(pb).resolves.toEqual([]);
    expect(f).toHaveBeenCalledTimes(1);
  });
});

describe("mapLimit", () => {
  it("preserves order and respects the concurrency limit", async () => {
    let running = 0;
    let max = 0;
    const out = await mapLimit([1, 2, 3, 4, 5, 6, 7, 8], 3, async (n) => {
      running++;
      max = Math.max(max, running);
      await new Promise((r) => setTimeout(r, 5));
      running--;
      return n * 2;
    });
    expect(out).toEqual([2, 4, 6, 8, 10, 12, 14, 16]);
    expect(max).toBeLessThanOrEqual(3);
  });
});
```

### TheMealDB

```ts
// tests/themealdb.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { MealDbClient } from "@/lib/api/themealdb/client";
import { mapIngredients, mapMeal, sizedImage } from "@/lib/api/themealdb/mapper";
import { RawMealSchema } from "@/lib/api/themealdb/schemas";
import { NotFoundError, ResponseValidationError } from "@/lib/api/http";

afterEach(() => vi.unstubAllGlobals());

const rawMeal = {
  idMeal: "52771",
  strMeal: "Spicy Arrabiata Penne",
  strDrinkAlternate: null,
  strCategory: "Vegetarian",
  strArea: "Italian",
  strInstructions: "Cook.",
  strMealThumb: "https://www.themealdb.com/images/media/meals/x.jpg",
  strTags: "Pasta, Curry",
  strIngredient1: "penne rigate",
  strMeasure1: "1 pound",
  strIngredient2: "olive oil",
  strMeasure2: "1/4 cup",
  strIngredient3: "",
  strMeasure3: " ",
  strIngredient4: null,
  strMeasure4: null,
  dateModified: null,
};

/** A client whose HTTP layer returns `response` and records the URLs it was called with. */
function clientWith(response: unknown) {
  const urls: string[] = [];
  const fake = vi.fn(async (url: string) => {
    urls.push(url);
    return response;
  });
  const client = new MealDbClient({
    baseUrl: "https://example.test/v1",
    apiKey: "k",
    fetchJson: fake as never,
  });
  return { client, fake, urls };
}

describe("mapping", () => {
  it("maps ingredients and skips empty slots", () => {
    expect(mapIngredients(RawMealSchema.parse(rawMeal))).toEqual([
      { name: "penne rigate", measure: "1 pound" },
      { name: "olive oil", measure: "1/4 cup" },
    ]);
  });

  it("reads slot 20 and keeps a blank measure as undefined", () => {
    const raw = RawMealSchema.parse({ idMeal: "1", strMeal: "x", strIngredient20: "  salt ", strMeasure20: " " });
    expect(mapMeal(raw).ingredients).toEqual([{ name: "salt", measure: undefined }]);
  });

  it("splits tags and builds the canonical page URL", () => {
    const r = mapMeal(RawMealSchema.parse(rawMeal));
    expect(r.tags).toEqual(["Pasta", "Curry"]);
    expect(r.pageUrl).toBe("https://www.themealdb.com/meal/52771");
  });

  it("tolerates unexpected extra fields of any type", () => {
    const parsed = RawMealSchema.safeParse({ ...rawMeal, weird: 5, nested: { a: 1 } });
    expect(parsed.success).toBe(true);
  });

  it("builds sized image URLs", () => {
    expect(sizedImage("https://img/x.jpg", "medium")).toBe("https://img/x.jpg/medium");
    expect(sizedImage(undefined, "small")).toBeUndefined();
  });
});

describe("MealDbClient", () => {
  it("treats meals: null as an empty result", async () => {
    const { client } = clientWith({ meals: null });
    expect(await client.searchByName("zzzz")).toEqual([]);
  });

  it("treats a non-array placeholder as an empty result", async () => {
    const { client } = clientWith({ meals: "no data found" });
    expect(await client.searchByName("zzzz")).toEqual([]);
  });

  it("returns null for an unknown id, and lookupOrThrow throws NotFoundError", async () => {
    const { client } = clientWith({ meals: null });
    expect(await client.lookup("999999")).toBeNull();
    await expect(client.lookupOrThrow("999998")).rejects.toBeInstanceOf(NotFoundError);
  });

  it("rejects malformed responses with ResponseValidationError", async () => {
    const { client } = clientWith({ meals: [{ nope: true }] });
    await expect(client.searchByName("x")).rejects.toBeInstanceOf(ResponseValidationError);
  });

  it("caches repeated lookups", async () => {
    const { client, fake } = clientWith({ meals: [rawMeal] });
    await client.lookup("52771");
    await client.lookup("52771");
    expect(fake).toHaveBeenCalledTimes(1);
  });

  it("does not call the API for blank searches or invalid ids", async () => {
    const { client, fake } = clientWith({ meals: null });
    expect(await client.searchByName("   ")).toEqual([]);
    await expect(client.lookup("abc")).rejects.toBeInstanceOf(RangeError);
    expect(fake).not.toHaveBeenCalled();
  });

  it("builds correct URLs (underscores only for ingredients, encoding for the rest)", async () => {
    const { client, urls } = clientWith({ meals: null });
    await client.filterByIngredient("chicken breast");
    await client.filterByArea("Saudi Arabian");
    await client.searchByName("mac & cheese");
    expect(urls).toEqual([
      "https://example.test/v1/k/filter.php?i=chicken_breast",
      "https://example.test/v1/k/filter.php?a=Saudi+Arabian",
      "https://example.test/v1/k/search.php?s=mac+%26+cheese",
    ]);
  });

  it("findRecipesByIngredient filters, then looks up each result", async () => {
    const fake = vi.fn(async (url: string) =>
      url.includes("filter.php")
        ? { meals: [{ idMeal: "1", strMeal: "A" }, { idMeal: "2", strMeal: "B" }] }
        : { meals: [{ idMeal: new URL(url).searchParams.get("i"), strMeal: "full" }] },
    );
    const client = new MealDbClient({ baseUrl: "https://example.test/v1", apiKey: "k", fetchJson: fake as never });
    const recipes = await client.findRecipesByIngredient("egg", { limit: 5 });
    expect(recipes.map((r) => r.id)).toEqual(["1", "2"]);
    expect(fake).toHaveBeenCalledTimes(3); // 1 filter + 2 lookups
  });
});
```

### Nutrition estimates

```ts
// tests/estimate.test.ts
import { describe, expect, it } from "vitest";
import { estimateNutrient, parseGrams } from "@/lib/nutrition/estimate";
import type { Recipe } from "@/lib/api/themealdb/types";
import type { Food } from "@/lib/api/fineli/types";

describe("parseGrams", () => {
  it.each([
    ["200g", 200],
    ["1.5 kg", 1500],
    ["250 grams", 250],
    ["1,5kg", 1500],
  ])("parses %s", (input, grams) => expect(parseGrams(input)).toBe(grams));

  it.each(["1 tbsp", "1/2 cup", "a pinch", "", undefined])("does not guess for %s", (input) =>
    expect(parseGrams(input)).toBeUndefined(),
  );
});

describe("estimateNutrient", () => {
  const recipe = {
    ingredients: [
      { name: "a", measure: "100g" },
      { name: "b", measure: "100g" },
      { name: "c", measure: "1 cup" },
      { name: "d", measure: "50g" },
    ],
  } as Recipe;
  const foods: Record<string, Food> = {
    a: { id: 1, names: {}, basis: "per100g", nutrients: { protein: { amount: 10 } } },
    b: { id: 2, names: {}, basis: "per100g", nutrients: {} },
    c: { id: 3, names: {}, basis: "per100g", nutrients: { protein: { amount: 1 } } },
  };

  it("never counts a missing nutrient as zero, and reports coverage", () => {
    const r = estimateNutrient(recipe, "protein", (n) => foods[n]);
    expect(r.total).toBe(10);
    expect(r.counted).toEqual(["a"]);
    expect(r.skipped.map((s) => s.reason)).toEqual(["no-nutrient", "no-grams", "no-match"]);
    expect(r.coverage).toBe(0.25);
  });

  it("returns an undefined total when nothing could be counted", () => {
    const r = estimateNutrient(recipe, "protein", () => undefined);
    expect(r.total).toBeUndefined();
    expect(r.coverage).toBe(0);
  });
});
```

### Fineli (replace inline data with real fixtures after 7.2)

```ts
// tests/fineli.test.ts
// VERIFY: replace the inline objects with real fixtures saved in step 7.2.
import { describe, expect, it, vi } from "vitest";
import { FineliClient } from "@/lib/api/fineli/client";
import { displayName, mapFood } from "@/lib/api/fineli/mapper";
import { HttpError } from "@/lib/api/http";

const apple = { id: 11060, name: { fi: "Omena", en: "Apple" }, energyKcal: 52, protein: 0.3 };

const make = (impl: (url: string) => Promise<unknown>) => {
  const fake = vi.fn(impl);
  return { fake, client: new FineliClient({ baseUrl: "https://example.test/api/v1/", fetchJson: fake as never }) };
};

describe("Fineli mapping", () => {
  it("keeps missing nutrients missing and picks a display name", () => {
    const food = mapFood({ id: 1, name: { fi: "Omena" } } as never);
    expect(food.nutrients).toEqual({});
    expect(displayName(food, "en")).toBe("Omena"); // falls back to Finnish
  });
});

describe("FineliClient", () => {
  it("skips the call for very short queries", async () => {
    const { client, fake } = make(async () => []);
    expect(await client.searchFoods("a")).toEqual([]);
    expect(fake).not.toHaveBeenCalled();
  });

  it("normalizes the base URL and encodes the query", async () => {
    const { client, fake } = make(async () => [apple]);
    await client.searchFoods("omena pie");
    expect(fake.mock.calls[0][0]).toBe("https://example.test/api/v1/foods?q=omena+pie");
  });

  it("returns null on 404 and rethrows other HTTP errors", async () => {
    const a = make(async (u) => { throw new HttpError(404, u); });
    expect(await a.client.getFood(1)).toBeNull();
    const b = make(async (u) => { throw new HttpError(500, u); });
    await expect(b.client.getFood(2)).rejects.toBeInstanceOf(HttpError);
  });

  it("rejects invalid ids without calling the API", async () => {
    const { client, fake } = make(async () => apple);
    await expect(client.getFood(-1)).rejects.toBeInstanceOf(RangeError);
    expect(fake).not.toHaveBeenCalled();
  });
});
```

### Routes and config

```ts
// tests/routes.test.ts
import { describe, expect, it, vi } from "vitest";
import { apiErrorHandler } from "@/server/routes/recipes";
import { HttpError, NetworkError, NotFoundError, TimeoutError } from "@/lib/api/http";

function run(err: unknown, headersSent = false) {
  const res: any = { headersSent, status: vi.fn().mockReturnThis(), json: vi.fn().mockReturnThis() };
  vi.spyOn(console, "error").mockImplementation(() => {});
  apiErrorHandler(err, {} as never, res, vi.fn());
  return res;
}

describe("apiErrorHandler", () => {
  it.each([
    [new NotFoundError("x"), 404],
    [new TimeoutError("u", 1), 504],
    [new HttpError(429, "u"), 503],
    [new HttpError(500, "u"), 502],
    [new NetworkError("u"), 502],
    [new Error("boom"), 500],
  ])("maps %o to %i", (err, code) => {
    expect(run(err).status).toHaveBeenCalledWith(code);
  });

  it("never exposes upstream details", () => {
    const res = run(new HttpError(500, "https://x.test/v1/<redacted-key>/a"));
    expect(JSON.stringify(res.json.mock.calls)).not.toContain("x.test");
  });

  it("stays silent for client aborts and already-sent responses", () => {
    expect(run(new DOMException("a", "AbortError")).status).not.toHaveBeenCalled();
    expect(run(new Error("late"), true).status).not.toHaveBeenCalled();
  });
});
```

```ts
// tests/config.test.ts
import { describe, expect, it } from "vitest";
import { loadConfig } from "@/lib/config";

describe("loadConfig", () => {
  it("allows the test key in development", () => {
    expect(loadConfig({ NODE_ENV: "development" } as never).MEALDB_API_KEY).toBe("1");
  });
  it("refuses the test key in production", () => {
    expect(() => loadConfig({ NODE_ENV: "production" } as never)).toThrow(/test key/);
  });
  it("accepts a real key in production", () => {
    expect(loadConfig({ NODE_ENV: "production", MEALDB_API_KEY: "abc123" } as never).MEALDB_API_KEY).toBe("abc123");
  });
  it("rejects a malformed URL", () => {
    expect(() => loadConfig({ MEALDB_BASE_URL: "not a url" } as never)).toThrow();
  });
});
```

**What these tests protect against** (each was verified by re-introducing the bug and watching a test fail):
- sending a request after the caller already cancelled;
- one caller's cancellation breaking other callers sharing a request;
- the API key appearing in error messages or URLs, including when the key is `1`;
- one unexpected extra field rejecting a whole recipe;
- missing nutrients or unparseable measures being counted as zero.

**Still not covered, add when you build these features:** real fixtures for Fineli; a recorded real TheMealDB response for each endpoint (save the live JSON once, then test against the file); component tests for loading, empty and error states; an end-to-end test through the real Express app.

---

## 11. Common mistakes

| Mistake | Why it matters |
|---|---|
| `fetch` inside a React component | Bypasses validation, caching, timeouts, and key protection |
| `as MealResponse` on `await res.json()` | Types lie when the API changes or data is partial |
| Using `0` when a nutrient or measure is missing | Presents unknown as fact |
| Logging full request URLs for TheMealDB | Leaks the API key (it is in the path) |
| Unbounded `Promise.all` over many lookups | Burns quota and can trigger throttling |
| No `AbortSignal` on search-as-you-type | Stale responses overwrite newer ones |
| Retrying on every error | Hides bugs and multiplies load during outages |
| Showing diet/allergen badges from tags or categories | Risk of real harm; neither API certifies this |
| Hotlinking images with no fallback | Broken images when URLs change |
| Treating the TheMealDB dev key as production-ready | Not permitted for publicly released apps |
| Copying Fineli field names from a blog post | Use the Swagger spec and fixtures |
| Passing one caller's `AbortSignal` into a shared (cached) loader | Pass it to `getOrLoad`'s third argument so only that caller stops waiting |
| Testing key redaction with a faked HTTP layer | The fake bypasses the code that does the redacting. Stub the global `fetch` instead and assert on the error's `message`, `url` and `stack` |

---

## 12. Pre-merge checklist

For any PR that touches an external API:

- [ ] Calls go through a client in `src/lib/api/`, not from components.
- [ ] Responses are validated with Zod and mapped to domain types.
- [ ] `null`/empty/no-data responses are handled and tested.
- [ ] Timeout set; retries limited to safe cases; caller cancellation supported and never shared across cached callers.
- [ ] Caching and de-duplication considered; no unbounded fan-out.
- [ ] No secrets in code, logs, error messages, or client bundles.
- [ ] Missing values are `undefined`, never `0` or `""`.
- [ ] Units and basis shown with nutrition values.
- [ ] Attribution present (TheMealDB credit, Fineli/THL credit and no implied endorsement).
- [ ] No allergen or dietary claims inferred from tags, names, or categories.
- [ ] Tests use mocks or fixtures, not live APIs.
- [ ] New env vars documented in `.env.example`.
- [ ] Any `VERIFY` comment you touched is resolved or still clearly marked.

---

## References

- TheMealDB API guide: https://www.themealdb.com/documentation
- TheMealDB agent guide (attribution, responsible use): https://themealdb.com/AGENTS.md
- TheMealDB OpenAPI (V1): https://themealdb.com/api/spec/openapi-v1.yaml
- TheMealDB terms of use: https://themealdb.com/terms_of_use.php
- Fineli open data: https://fineli.fi/fineli/en/avoin-data
- Fineli open data (Finnish, lists the `foods?q=` search): https://fineli.fi/fineli/fi/avoin-data
- Fineli service description and trademark terms: https://www.suomi.fi/services/finnish-food-composition-database-fineli-the-national-institute-for-health-and-welfare-thl/cbc1b926-a496-42b9-8a66-5e3e9ef638e4
- Fineli API Swagger docs: https://fineli.fi/fineli/v2/api-docs

---

## Appendix A: Validation log

Result of checking this document's claims on 2026-10-29. "Verified" means confirmed in an official source or by running the code. "Partial" and "Unverified" items are either handled defensively in code or marked `VERIFY`.

### TheMealDB

| Claim | Status | Basis |
|---|---|---|
| V1 base URL, API key as a path segment, free test key `1` | Verified | Official API guide |
| Public/production apps need a supporter key; £10 lifetime upgrade; V2 adds multi-ingredient filter, random 10, latest 10, larger limits | Verified | Official API guide (prices and tiers can change; re-check before launch) |
| Paths for search, first-letter, lookup, random, filter (i/c/a), categories, list (c/a/i) | Verified | Official API guide |
| Filters return summaries only (`idMeal`, `strMeal`, `strMealThumb`); full data needs `lookup.php` | Verified | Official agent guide; third-party code shows the same three fields |
| Ingredients/measures are `strIngredient1..20` / `strMeasure1..20`; measures can be blank | Verified | Official agent guide |
| Image sizes `/small` `/medium` `/large` = 200, 350, 500 px | Verified | Official agent guide |
| Suggested attribution wording; do not scrape; do not resell | Verified | Official agent guide |
| Ingredient filter uses underscores for spaces | Verified | Official examples (`chicken_breast`) and agent guide |
| Category/area filter values with spaces accept underscores | Unverified | Not documented. Code no longer assumes it |
| `list.php?c=list` / `a=list` return `meals[].strCategory` / `strArea` | Verified | Third-party code and connector docs |
| `list.php?i=list` returns `idIngredient`, `strIngredient`, `strDescription`, `strType` | Unverified | From memory. Schema requires only `strIngredient` |
| `categories.php` returns `categories[]` with `idCategory`, `strCategory`, `strCategoryThumb`, `strCategoryDescription` | Partial | `categories[].strCategory` confirmed; other field names from memory |
| No-match responses use `meals: null` | Partial | Docs say "empty or no-data result". Code accepts any non-array |
| Real records contain extra fields (e.g. `strDrinkAlternate`, `dateModified`) | Verified | Third-party examples and connector schema; the schema tolerates them |
| Rate limits | Not documented | No limits are stated in the official guide; treat as unknown |

### Fineli

| Claim | Status | Basis |
|---|---|---|
| Endpoints `components/`, `foods?q=`, `foods/{id}`; JSON | Verified | Fineli help and open data pages; third-party app using the search endpoint |
| Swagger spec at `/fineli/v2/api-docs` | Verified (link) | Listed on Fineli pages. **Not opened**, so response models are unconfirmed |
| Open data CSV packages: 4,232 foods with 55 or 74 components; ingredients package 1,370 foods / 40 components; names in fi/sv/en | Verified | Fineli open data page |
| Service is free; Finnish, Swedish, English | Verified | Suomi.fi service description |
| Must not imply THL produced or endorses the service; Fineli is a THL trademark | Verified | Suomi.fi service description |
| No API key required | Partial | Not mentioned in docs; one user report in a third-party issue |
| Rate limits | Not documented | Treat as unknown |
| Response field names, id type, name structure, nutrient keys, units, "per 100 g" basis | **Unverified** | Marked `VERIFY` in code. Save real responses as fixtures (7.2) |
| Unknown ID returns HTTP 404 | **Unverified** | Marked `VERIFY` |
| English search terms work | **Unverified** | Test before relying on it |
| Automated requests may be blocked by bot detection | Observed | Requests from the research tooling were blocked; may not apply to your server |
| Data licence/attribution wording | Not found | Check the open data page before launch |

### Code

| Claim | Status | Basis |
|---|---|---|
| All TypeScript compiles under `strict` | Verified | `tsc --noEmit` on extracted files |
| Works with Zod 3.25 and 4.6 | Verified | Type-check and 59 tests on both |
| Retry, timeout, cancellation, redaction, caching, de-duplication, concurrency limit behave as documented | Verified | Tests in section 10, mutation-checked |
| Behavior against the live APIs | **Not tested** | Test environment could not reach either API; all HTTP is mocked |
| Express route example end to end | **Not tested** | Only the error handler is unit-tested |

