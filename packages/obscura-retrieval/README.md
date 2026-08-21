# Obscura retrieval adapters

This package implements the two project-owned variants authorized by ADR-012:

- `ObscuraDuckDuckGoLiteDiscoverySource`
- `ObscuraRedditThreadFetcher`

It deliberately exposes no generic Obscura command runner. Runtime configuration rejects stealth, proxies, persistent browser profiles, non-WSL execution, and binary/runtime drift. Each call targets one allowlisted public surface, emits a typed outcome, and saves raw evidence before normalization.

## Runtime

The committed provider configs pin Obscura, Node.js, Playwright Core, access mode, timeouts, concurrency, and extraction settings. `OBSCURA_BIN` may relocate the binary only when its SHA-256 still matches the committed config.

```bash
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH npm ci
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH npm test
```

Run one frozen input:

```bash
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH node bin/retrieval-cli.js discover \
  --config ../../retrieval-eval/prototype-smoke/provider-configs/obscura-duckduckgo-lite.json \
  --input ../../retrieval-eval/prototype-smoke/queries-2026-08.json \
  --id q01-api-security-broad \
  --output-root ../../retrieval-eval/prototype-smoke/results/manual
```

Generated evidence under `retrieval-eval/prototype-smoke/results/` is local and ignored. The frozen protocol/configuration commit must exist before a scored run.
