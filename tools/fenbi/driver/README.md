# Fenbi collector — archived source copy (S1 Dell)

Code-only record of the collector that currently runs on the S1 Dell host. It is
committed so the active pipeline can be reviewed and versioned; it is **not** the
deployment and has **never** been executed from this path.

## Provenance

- Live source: an untracked `driver/` directory outside any git worktree
  (`fenbi-pipeline.service`, `ExecStart` → `driver/fenbi-service.mjs`).
- This copy: same ten modules, copied verbatim except for **portable path
  refactor + secret sanitization** (absolute base path removed, repo-relative
  resolution via `import.meta.url`, `FENBI_BASE` / `FENBI_WORK_DIR` overrides).
  Capture behaviour, concurrency, throttling and DOM parsing rules are unchanged.
- Therefore the blob SHA256 here differs from the running file. The live files
  were not modified.

| Module | Role | Live SHA256 prefix | Ported SHA256 prefix |
|---|---|---|---|
| `fenbi-service.mjs` | service loop / scheduling | `c474a566ebe13c6f` | see PR body |
| `focus-schedule.mjs` | focus-region rotation | `b0674e72273cf53e` | unchanged |
| `p0-discover-regions.mjs` | catalog discovery | `d4d3ff8d1d4e9ae6` | see PR body |
| `build-candidates-live.mjs` | candidate queue | `6d693087430a5c01` | see PR body |
| `year-policy.mjs` | policy years | `e8831c08b4470df3` | unchanged |
| `t2-phaseb2.mjs` | batch capture driver | `fc58eb5b379a68c2` | see PR body |
| `capture-new-generic.mjs` | single-paper DOM capture | `6c3c029e05a246d9` | see PR body |
| `t2-collector.mjs` | persistent-browser collector | `00270958863a251b` | see PR body |
| `t2-backfill-json.mjs` | JSON backfill | `edb2661dd2d63d1e` | see PR body |
| `t2-asset-pass.mjs` | asset/image pass | `38501c5d2b2358be` | see PR body |

`focus-schedule.mjs` and `year-policy.mjs` had no absolute paths and are byte-identical.

## Layout and environment

```
FENBI_BASE     repo root (default: resolved from this file, ../../..)
FENBI_WORK_DIR runtime work dir (default: $FENBI_BASE/work/fenbi)
```

The collector coordinator and every child process resolve both overrides to
absolute paths. Use one shared `FENBI_WORK_DIR` for discovery, capture,
submission, backfill and assets; mixed work directories can split STOP files,
locks and caches. This is a **source-code contract**, not proof of successful
deployment on Dell.

Runtime layout under `FENBI_WORK_DIR`: `papers/<paper-key>/document.json`,
`catalog-live-<date>/`, `candidates-live.json`, `t2-<date>/{ledger,run-state,service.log}.json`,
`profiles/<profileName>/`, `STOP`, `config.json`.

Everything under `work/` is gitignored: profiles, cookies, tokens, captured
documents, images and service env files stay on the collector host.

## Capture cadence (read from the source constants, unchanged)

- `T2_TABS=3` max concurrent tabs; shared navigation gate `NAV_GAP_MS=2500`
- `DWELL_MS=30000` per paper; Playwright default timeout `45000`
- service batch `SERVICE_BATCH=3`, interval `60s`, focus pages `8`
- one persistent Chrome profile, single owner session; no paid/member content,
  no captcha or 403/429 bypass

## document.json handoff schema

Top level: `schemaVersion, identity, source, expected, materials, questions,
assets, evidence, conflicts, chapters`.

Question: `id, number, contentHtml, options, materialIds, answerHtml,
explanationHtml, requirementsHtml, materialIdsObserved`.

Asset: `url, status, localPath, sha256, bytes, width, height, decoded, decode`.
`assets[].sha256` is the content hash used downstream by the Publisher lane;
`source.url` is a private capture URL and must not be republished.

## Dependencies

Node 22 (`engines.node >= 22`) and `playwright-core 1.64.1` from
`tools/fenbi/package.json`. `node_modules/` is not committed; install with the
normal lockfile on the host. Other imports are Node builtins or the tracked
`tools/fenbi/src/*.mjs` modules.

## Not deployed / limitations

- This copy has not been run in production and is not wired to any service.
- The Publisher service runs from a separate worktree at a different commit
  than `main`; that is a deployment fact, not a grant of publication rights.
- Browser authentication and the persistent profile must stay local. The
  `deploy/systemd/*.example` units are templates only; see their README notes.
