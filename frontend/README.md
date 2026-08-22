# aptori frontend

SvelteKit 2 + Svelte 5 application shell for the social intelligence and engagement copilot, styled with Tailwind 4 and shadcn-svelte components. V2 delivers the shell wired to backend health; Campaign screens land in V3.

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

`PUBLIC_API_BASE_URL` is read via `$env/dynamic/public` in `src/routes/+page.server.ts`; any `PUBLIC_`-prefixed env var must be set before `pnpm dev` or `pnpm build`.

## Checks and build

```bash
pnpm check        # svelte-check against tsconfig.json
pnpm check:watch  # watch mode
pnpm build        # vite build
pnpm preview      # preview the production build
```

## Backend contract

`+page.server.ts` fetches `GET {PUBLIC_API_BASE_URL}/health` with a 3-second timeout and classifies it as `apiReachable`, `database` (`ok` | `unavailable` | `unknown`), and `degraded`. The page reports `operational` only for the complete healthy contract — HTTP 200 with `status: "ok"`, `api: "reachable"`, and `database: "ok"`; anything else is shown as degraded.
