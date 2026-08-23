# aptori frontend

SvelteKit 2 + Svelte 5 application for the social intelligence and engagement copilot, styled with Tailwind 4 and shadcn-svelte components. The shell reports backend health at `/`; `/campaigns` manages Campaigns (create, edit, lifecycle) over the backend REST API.

## Requirements

- Node.js >= 20.19 (22.x recommended)
- pnpm 11.22.0 (see `packageManager` in `package.json`)
- A running backend; see [`../backend/README.md`](../backend/README.md)

## Setup

```bash
cd frontend
pnpm install
```

## Development

```bash
pnpm dev          # http://localhost:5173
```

The app loads health state from `http://127.0.0.1:8000` by default. Point it at another backend base URL:

```bash
PUBLIC_API_BASE_URL=http://localhost:8000 pnpm dev
```

`PUBLIC_API_BASE_URL` is read via `$env/dynamic/public` in both `src/routes/+page.server.ts` and `src/routes/campaigns/+page.server.ts`; any `PUBLIC_`-prefixed env var must be set before `pnpm dev` or `pnpm build`. Copy `.env.example` to the git-ignored `frontend/.env` for local development.

## Checks and build

```bash
pnpm check        # svelte-check against tsconfig.json
pnpm check:watch  # watch mode
pnpm build        # vite build
pnpm preview      # preview the production build
```

## Backend contract

`+page.server.ts` fetches `GET {PUBLIC_API_BASE_URL}/health` with a 3-second timeout and classifies it as `apiReachable`, `database` (`ok` | `unavailable` | `unknown`), and `degraded`. The page reports `operational` only for the complete healthy contract — HTTP 200 with `status: "ok"`, `api: "reachable"`, and `database: "ok"`; anything else is shown as degraded.

`/campaigns` follows the same pattern: the load fetches a bounded `GET /campaigns?limit=50&cursor=…` page through the pure contract parser in `src/lib/campaigns.ts`, and the page exposes newest/older navigation using the backend's opaque cursor. SvelteKit form actions (`?/create`, `?/update`, `?/transition`) proxy `POST`/`PATCH /campaigns*` server-side, translating the backend's stable error codes into operator guidance. Writes carry the backend's bearer token from the private `API_TOKEN` env var and a server-issued `Idempotency-Key` scoped to each logical form submission; a failed submission keeps its own key for a safe retry without sharing it with other forms, unless the operator explicitly starts a new attempt. Configure `API_TOKEN` and `PUBLIC_API_BASE_URL` in the server environment.
