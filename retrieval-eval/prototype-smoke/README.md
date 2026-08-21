# ADR-012 prototype smoke

This directory freezes the smaller Internal Product retrieval gate authorized by ADR-012. It is not Retrieval Gate R0 and cannot graduate a provider or authorize external use.

The protocol commit precedes scored results. The runner refuses a dirty worktree, records the clean Git commit SHA and hashes every frozen input/config file. Generated raw evidence and reports live under ignored `results/` directories so result publication can be a separate reviewed decision.

From the package directory in WSL:

```bash
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH npm ci
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH npm test
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH npm run smoke
```

The runner executes discovery once and the known-thread corpus twice. Every attempt has its own immutable directory containing `observation.json` and, when received, the raw page or structured response.
