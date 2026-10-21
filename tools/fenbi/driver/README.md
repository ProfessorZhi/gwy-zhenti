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

## Deployment (2026-10-21)

These files are now meant to be the **only** collector source: run the service from a checkout of
`main` (see `tools/fenbi/deploy/systemd/fenbi-collector.service.example` and
`docs/WORKFLOW-THINKING.md`). Set `FENBI_WORK_DIR` to the existing runtime directory so profiles and
caches stay where they are; every module honours it. The untracked `driver/` copy on the Dell host
should be retired once the new unit is running.

Changes versus the archived copy: `SERVICE_BATCH` default 30 (was 3), `SERVICE_INTERVAL` 10s (was 60s),
`SERVICE_FOCUS_RESCAN` 7200s (was 1800s); non-risk failures back off (`SERVICE_BACKOFF`, 900s) instead of
writing `STOP`, and a failed round no longer ends the service; fixed waits in `capture-new-generic.mjs`
became element waits with timeouts no shorter than before. Risk signals (captcha, login lost, 403/429)
still write `STOP`.

- Browser authentication and the persistent profile must stay local.
