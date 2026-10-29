# Review Guidelines

Guidelines for reviewing pull requests in this repo: a TypeScript website that integrates with food-related APIs (recipes, nutrition, restaurants, etc.).

These apply to **human reviewers and AI reviewers alike**. If you are an AI reviewer, follow the "AI reviewer instructions" section at the bottom.

---

## 1. Principles

- **Review the change, not the author.** Be specific, kind, and concrete.
- **Prioritize.** Spend attention on correctness, security, and data integrity before style.
- **Don't duplicate tooling.** Anything ESLint, Prettier, `tsc`, or CI already enforces should not be raised in review.
- **Explain why.** Every blocking comment should say what could go wrong, not just what to change.
- **Small PRs get fast reviews.** If a PR is hard to review, say so and suggest how to split it.

## 2. Severity labels

Prefix every comment with one of these so the author knows what's required.

| Label | Meaning | Blocks merge? |
|---|---|---|
| `blocker:` | Bug, security issue, data loss, broken contract, missing required test | Yes |
| `suggestion:` | Would improve the code, but the current version works | No |
| `question:` | Reviewer needs context to understand the change | Until answered |
| `nit:` | Minor preference (naming, wording). Use sparingly | No |
| `praise:` | Something done well | No |

## 3. What to check, in priority order

### 3.1 Correctness
- Does the code do what the PR description says? Are edge cases handled (empty results, null fields, zero quantities, very large lists)?
- Are async flows correct: no missing `await`, no unhandled promise rejections, no race conditions between concurrent requests or stale responses overwriting newer ones?
- Are loading, error, and empty states all handled in the UI?

### 3.2 Security
- **No secrets in code, logs, or client bundles.** API keys must come from environment variables and stay server-side unless the provider explicitly supports public client keys.
- Third-party API calls that need a secret key go through our backend or server routes, never directly from the browser.
- User input is validated and sanitized before use in queries, URLs, or rendered HTML. No `dangerouslySetInnerHTML` (or equivalent) with API content unless sanitized.
- Error messages and logs do not leak keys, tokens, or internal URLs.
- New dependencies: is it maintained, necessary, and reasonably sized?

### 3.3 External API integration
This is the highest-risk area of the codebase, so review it carefully.

- **Validate responses at runtime.** Types alone don't protect us from API changes. Responses should be parsed with a schema validator (e.g. Zod) at the boundary, and the rest of the app should use the validated types.
- **Handle failure explicitly.** Check for timeouts, non-2xx responses, malformed bodies, and partial data. The UI must degrade gracefully, not crash or show blank content.
- **Timeouts and retries.** Every outbound request has a timeout. Retries use backoff and only apply to safe/idempotent requests.
- **Rate limits and quotas.** Is the new call going to burn quota? Look for calls inside loops, calls on every keystroke (needs debounce), and duplicate requests for the same data.
- **Caching.** Is the data cacheable? Is the cache duration reasonable for how often the data changes (nutrition facts rarely, restaurant hours often)? Are cache keys correct?
- **Isolate the integration.** API-specific logic lives in a dedicated client/service module. Components do not call `fetch` for third-party APIs directly, and provider-specific response shapes are mapped to our own domain types.
- **Provider terms.** Check that required attribution, branding, and usage rules for the API are followed, and that we aren't storing data the provider's terms prohibit storing.

### 3.4 Food-domain data accuracy
Mistakes here can mislead users, so be extra careful.

- **Units are explicit.** Quantities carry a unit (g, ml, cups, servings). Conversions are tested and don't silently mix metric and imperial.
- **Nutrition values** are labeled per serving vs. per 100g correctly, and rounding doesn't change meaning.
- **Allergens and dietary tags** (vegan, gluten-free, etc.) are never inferred loosely. If the source data is missing or uncertain, the UI says "unknown" instead of implying safe. Flag any change that could make an unverified claim look like a guarantee.
- **Missing data** is represented as missing (`undefined`/`null`), not `0` or empty string.
- Localization concerns (decimal separators, ingredient names, units by region) are handled or noted.

### 3.5 TypeScript quality
- No `any` without a comment explaining why. Prefer `unknown` plus narrowing.
- No non-null assertions (`!`) or type assertions (`as`) that bypass real checks, especially on API data.
- Types model the domain: use unions and discriminated unions for states (e.g. `loading | error | success`) instead of several loose booleans or optionals.
- Public functions and exported types have clear names and, where non-obvious, short doc comments.
- No unused exports, dead code, or leftover `console.log`.

### 3.6 Performance
- No unnecessary re-renders or expensive work in render paths; memoization is used where measured or clearly warranted, not by default.
- Lists from APIs are paginated or virtualized if they can be large.
- Images (food photos) are sized, lazy-loaded, and have fallbacks when URLs break.
- No sequential requests that could run in parallel, and no parallel requests that should be sequential for rate limit reasons.

### 3.7 Accessibility and UX
- Interactive elements are keyboard accessible and have accessible names.
- Images have meaningful `alt` text (or empty `alt` if decorative).
- Dietary and allergen information is not communicated by color alone.
- Errors are understandable to users, with a next step where possible.

### 3.8 Testing
- New logic has tests. Bug fixes include a test that fails without the fix.
- API integration is tested with mocked responses covering: success, empty result, malformed data, timeout, and rate limit (429).
- Tests don't hit real third-party APIs.
- Unit conversion and nutrition calculation logic has direct unit tests.

### 3.9 Maintainability
- Functions do one thing; files stay a reasonable size.
- Names describe intent. Comments explain *why*, not *what*.
- Config values (base URLs, limits, TTLs) are constants or env config, not magic numbers or strings scattered around.

## 4. What not to comment on

- Formatting, import order, or anything auto-fixed by Prettier/ESLint.
- Personal style preferences that aren't in this document. Use `nit:` at most once, or skip it.
- Rewrites of unchanged code unrelated to the PR (open a separate issue instead).
- Speculative future requirements.

## 5. Pull request expectations (for authors)

A PR description should include:

1. **What and why** in a few sentences.
2. **How to test** (steps, or which tests cover it).
3. **Screenshots** for UI changes.
4. **API impact**: new endpoints used, new env vars, expected change in request volume.
5. **Risks or follow-ups**, if any.

Keep PRs focused on one concern. Prefer under roughly 400 changed lines where possible.

## 6. Team process

- At least **one approval** is required to merge; **two** for changes to the API client layer, auth, or anything touching secrets/env config.
- Authors respond to every `blocker:` and `question:` comment before re-requesting review.
- Reviewers aim to respond within **one working day**.
- Disagreements: discuss in the thread; if unresolved after one round, ask a third teammate to weigh in.
- Don't merge with failing CI.

## 7. AI reviewer instructions

If you are an automated reviewer applying this document:

1. **Start with a short summary** of what the PR changes (2 to 4 sentences) and a list of files grouped by purpose.
2. **Only comment when you are reasonably confident** there is a real issue. Prefer fewer, higher-quality comments over exhaustive ones.
3. **Use the severity labels** from section 2 on every comment.
4. **Show the fix.** For each `blocker:` or `suggestion:`, include a concrete code snippet or clear change.
5. **Prioritize sections 3.1 to 3.4** (correctness, security, API integration, food data accuracy). Pay particular attention to unvalidated API responses, exposed secrets, missing timeouts, and any change that could misstate allergen or nutrition information.
6. **Skip everything in section 4.**
7. **Say what you couldn't verify** (for example, behavior that depends on code outside the diff) rather than guessing.
8. **End with an overall assessment:** approve, approve with suggestions, or request changes, plus the one or two most important items.
