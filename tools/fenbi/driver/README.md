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

## Deployment (2026-10-21)

These files are now meant to be the **only** collector source: run the service from a checkout of
`main` (see `deploy/systemd/fenbi-pipeline.service.example` and
`docs/WORKFLOW-THINKING.md`). Set `FENBI_WORK_DIR` to the existing runtime directory so profiles and
caches stay where they are; every module honours it. The untracked `driver/` copy on the Dell host
should be retired once the new unit is running.

Changes versus the archived copy: `SERVICE_BATCH` default 10 (was 3; raise to 30 after a clean trial),
`SERVICE_INTERVAL` 10s (was 60s), `SERVICE_FOCUS_RESCAN` 7200s (was 1800s). Every child summary now goes
through `service-risk.mjs`: captcha, login lost, unauthorized, or three 403/429 hits within an hour write `STOP`
and exit 0; other failures back off (`SERVICE_BACKOFF`, 900s, interruptible by `STOP`) and write `ALERT` after
`SERVICE_ALERT_AFTER` consecutive backoffs; a crash exits non-zero for `Restart=on-failure`.
`capture-new-generic.mjs` waits for the target row and for the question count to settle (at least 6s), and
re-snapshots once when fewer questions rendered than the paper's chapter counters state.

- Browser authentication and the persistent profile must stay local.

## Shenlun catalog replay (offline, metadata only)

`shenlun-catalog-build.mjs` + `shenlun-catalog-core.mjs` turn already-saved list
snapshots into a deduplicated shenlun catalog and a candidate queue. They never
open a browser, a profile, a network socket, `papers/` or `catalog-live/`.
Mock-exam list rows (`type=2`) are kept for accounting but are never candidates.

```bash
node tools/fenbi/driver/shenlun-catalog-build.mjs \
  --national-dir "$FENBI_WORK_DIR/t2-20261019/shenlun-national-catalog" \
  --inventory "$FENBI_WORK_DIR/t2-20261019/shenlun-inventory-zhejiang.json" \
  --api-dir "$FENBI_WORK_DIR/t2-20261019" \
  --captured-dir "$FENBI_WORK_DIR/shenlun-capture" \
  --captured-dir "$FENBI_WORK_DIR/papers" \
  --now 2026-10-21T12:00:00Z \
  --out "$FENBI_WORK_DIR/shenlun-catalog-20261021.json"
```

Rules enforced by the core:

- **Identity.** `sourceId` is the only paper identity. One id seen under several
  regions is one paper; it is marked `crossRegion`, given `area=null`, and held
  out of the auto queue. Conflicting non-null years/variants become
  `identityConflict` and are also held out. Nothing guesses a region.
- **Fee.** Explicit `paid`/`lockStatus` wins over row markers. `paidFlag=false`
  is the discovery's `absent-defaulted-false`, **not** an explicit free claim.
  With no per-row field the row is `free-visible-unverified`. A member/lock
  marker that cannot be bound to a sourceId (e.g. batch4 四川 `memberRows=2`,
  known double-count) goes to `pendingFreeCheck`, not `free`.
- **Titles.** Normalised fingerprints (full/half-width, `网友回忆版`, A/B/C
  markers) detect same area/year/variant titles with different ids. Collisions
  are listed and blocked; ids are never merged by title. An explicit API or
  inventory variant outranks a title heuristic; a title-only disagreement is
  counted separately (`variantTitleDisagreements`).
- **Years.** Reuses `year-policy.mjs`: Zhejiang keeps every visible year, other
  regions 2016..current year. Future rows and unknown years are separated.
- **Coverage.** The area matrix counts appearances; `totals.realSourceIds` is
  the deduplicated real-paper total and mock papers are reported separately.
  Partial pages, unpaired `apiIds`, unknown years and unobserved region tabs are
  explicit fields, never silently treated as complete.

Output is written `0600` outside `tools/`; raw titles appear only with
`--include-titles` and that file must stay local. The `needsLiveCapture` array
lists fields the saved snapshots cannot supply (sourceId-bound titles, per-row
member/lock binding, batches 1–3 lock fields, raw Zhejiang titles).

Replaying the snapshots present on 2026-10-21 (11 national batches, Zhejiang
inventory/API, plus a 569-id captured scan) gives: **838 real sourceIds** (802
national + 36 Zhejiang), **674 policy-in-scope** (638 national 2016–2026 + 36
Zhejiang all-years; 11 of the 36 are pre-2016), 3 cross-region ids, 0 identity
conflicts, 595 candidates and 33 pending free checks. This is the visible content of these snapshots, **not** a claim of a
national shenlun total; Zhejiang 2022 has no row and the 4 non-region tabs
(推荐/小模考/选调生/公安) were not inventoried here.
