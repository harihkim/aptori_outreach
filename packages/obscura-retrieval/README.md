# Obscura retrieval adapters

This package implements the two project-owned variants authorized by ADR-012:

- `ObscuraDuckDuckGoLiteDiscoverySource`
- `ObscuraRedditThreadFetcher`

It deliberately exposes no generic Obscura command runner. Runtime configuration rejects stealth, proxies, persistent browser profiles, non-WSL execution, and binary/runtime drift. Each call targets one allowlisted public surface, emits a typed outcome, and saves raw evidence before normalization.

## Runtime

The committed provider configs pin Obscura, Node.js, Playwright Core, access mode, timeouts, concurrency, and extraction settings. The binary path recorded in the configs is the reference machine's stable location (`/home/hari/.local/bin/obscura`); `OBSCURA_BIN` relocates it and its SHA-256 is always verified against the committed config. Do not reference ephemeral tool-scratch locations in committed configs.

`verifyRuntime` enforces the exact Node v20.18.0 pinned by the configs, so live retrieval and the smoke gate need that toolchain (via your version manager, or `OBSCURA_NODE_DIR` for the daily canary). The offline tests below run on any current Node:

```bash
npm ci
npm test
```

Run one frozen input (requires the pinned Node runtime):

```bash
node bin/retrieval-cli.js discover \
  --config ../../retrieval-eval/prototype-smoke/provider-configs/obscura-duckduckgo-lite.json \
  --input ../../retrieval-eval/prototype-smoke/queries-2026-08.json \
  --id q01-api-security-broad \
  --output-root ../../retrieval-eval/prototype-smoke/results/manual
```

Generated evidence under `retrieval-eval/prototype-smoke/results/` is local and ignored. The frozen protocol/configuration commit must exist before a scored run.
