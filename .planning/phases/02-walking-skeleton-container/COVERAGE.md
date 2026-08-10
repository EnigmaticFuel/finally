# API Coverage — Phase 2 (Walking-Skeleton Container)

No external API integration: this phase packages the already-built Phase 1 FastAPI app into a Docker image and adds host lifecycle scripts — the only "API" terms in scope are this project's own first-party routes (`/api/health`, `/api/stream/prices`), which Phase 1 already built and this phase only exercises over HTTP.

The `api-coverage` detector fires on the surface nouns `api` / `rest`, the same false positive recorded against Phase 1 in `.planning/STATE.md`. Phase 6 (AI Chat Copilot, OpenRouter via LiteLLM) is the first phase with a genuine external-API surface and is where the matrix is owed.

No external SDK, service client, or third-party HTTP call is added, removed, or configured by any of `02-01-PLAN.md` … `02-04-PLAN.md`. `backend/pyproject.toml` and `backend/uv.lock` are unchanged (D-03 consumes the existing lockfile).
