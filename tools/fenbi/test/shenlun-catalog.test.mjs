// Offline tests for the shenlun catalog discover/candidate builder.
// Every fixture here is synthetic (9xxxxx ids); no real title, answer or URL is used.

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {
  buildShenlunCatalog, classifyFee, normalizeTitle, variantFromTitle,
} from '../driver/shenlun-catalog-core.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(here, 'fixtures', 'shenlun-catalog');
const CLI = path.join(here, '..', 'driver', 'shenlun-catalog-build.mjs');
const NOW = new Date('2026-10-21T12:00:00Z');

const read = (name) => JSON.parse(fs.readFileSync(path.join(FIX, name), 'utf8'));
const snapshot = (kind, name, extra = {}) => ({ kind, file: name, json: read(name), ...extra });
const baseSnapshots = () => [
  snapshot('national', 'national-catalog-batch1.json'),
  snapshot('national', 'national-catalog-batch2.json'),
  snapshot('inventory', 'inventory-zhejiang.json'),
  snapshot('api', 'api-zhejiang.json'),
  snapshot('catalog-live', 'catalog-live-zhejiang.json'),
];
const build = (snapshots = baseSnapshots(), options = {}) => buildShenlunCatalog({ snapshots, now: NOW, ...options });
const byId = (out, id) => out.papers.find((paper) => paper.sourceId === id);
const hasCandidate = (out, id) => out.candidates.some((candidate) => candidate.sourceId === id);

test('one sourceId across several regions is one paper, isolated from the queue', () => {
  const out = build();
  assert.equal(out.offline, true);
  assert.equal(out.rightsStatus, 'unverified');
  assert.equal(out.totals.uniqueSourceIds, 22);
  assert.equal(out.totals.realSourceIds, 21);
  assert.equal(out.totals.mockSourceIds, 1);

  const paper = byId(out, '900004');
  assert.deepEqual(paper.areas, ['国考', '江苏', '甘肃']);
  assert.equal(paper.area, null);
  assert.equal(paper.flags.crossRegion, true);
  assert.equal(out.totals.crossRegion, 1);
  assert.deepEqual(out.ambiguities.crossRegion.map((item) => item.sourceId), ['900004']);
  assert.equal(hasCandidate(out, '900004'), false);

  // The area matrix counts appearances; only the global total dedupes by sourceId.
  const appearances = out.coverage.byArea.reduce((sum, area) => sum + area.sourceIds, 0);
  assert.equal(appearances - out.totals.uniqueSourceIds, 2);

  // Every paper is classified exactly once: queue, pending, or one exclusion bucket.
  const accounted = out.candidates.length + out.pendingFreeCheck.length
    + Object.values(out.excluded).reduce((sum, count) => sum + count, 0);
  assert.equal(accounted, out.totals.uniqueSourceIds);
});

test('year policy: Zhejiang keeps every visible year, other regions stay 2016..now', () => {
  const out = build();
  assert.equal(out.policy.defaultMinYear, 2016);
  assert.equal(out.policy.zhejiangAllYears, true);
  assert.equal(out.policy.maxYear, 2026);

  assert.equal(hasCandidate(out, '910001'), true); // Zhejiang 2008
  assert.equal(hasCandidate(out, '920003'), true); // Zhejiang 2012
  assert.equal(hasCandidate(out, '900003'), false); // Jiangsu 2015
  assert.equal(out.excluded.outOfYear, 1);
  assert.equal(out.totals.future, 0); // the synthetic 2027 row is a mock, not a real paper

  const zhejiang = out.coverage.byArea.find((area) => area.area === '浙江');
  assert.equal(zhejiang.pre2016, 3);
  assert.equal(zhejiang.outOfScope, 0);
});

test('fee states are fail-closed: absence of a marker is not "free"', () => {
  const out = build();
  assert.equal(byId(out, '900001').fee, 'free-visible-unverified'); // paidFlag=false only
  assert.equal(byId(out, '910001').fee, 'free'); // lockStatus=0
  assert.equal(byId(out, '910004').fee, 'locked'); // lockStatus=1
  assert.equal(byId(out, '900006').fee, 'free-visible-unverified'); // member row unbound
  assert.equal(byId(out, '900006').flags.memberSignal, true);
  assert.ok(byId(out, '900006').feeConflicts.includes('row-marker-contradicts-lock-field'));

  assert.equal(classifyFee({ explicitLock: 'free' }).fee, 'free');
  assert.equal(classifyFee({ explicitLock: 'free', memberRows: 1 }).fee, 'free-visible-unverified');
  assert.equal(classifyFee({ explicitPaid: 'member', explicitLock: 'free' }).fee, 'unknown');
  assert.equal(classifyFee({ explicitLock: 'mixed' }).fee, 'unknown');
  assert.equal(classifyFee({}).fee, 'free-visible-unverified');
});

test('normalised title collisions block auto-queue but never merge ids', () => {
  assert.equal(variantFromTitle('2026年浙江省公考《申论》题（Ａ卷）'), 'a');
  assert.equal(
    normalizeTitle('2026年浙江省公考《申论》题（A卷）网友回忆版').titleKey,
    normalizeTitle('2026年浙江省公考《申论》题（Ａ卷）网友回忆版').titleKey,
  );

  const out = build();
  const group = out.ambiguities.titleCollisions.find((item) => item.area === '浙江' && item.year === 2024);
  assert.deepEqual(group.sourceIds, ['930001', '930002']);
  for (const id of group.sourceIds) {
    assert.equal(byId(out, id).flags.titleCollision, true);
    assert.equal(hasCandidate(out, id), false);
  }
  assert.equal(hasCandidate(out, '930003'), true); // B卷 is a different paper
});

test('same id with two different years is an identity conflict, not a guess', () => {
  const national = {
    categoriesSeen: [],
    categories: [{
      category: '江苏', observed: true, pagesRead: 1, totalPagesObserved: 1, partialPages: false,
      memberRows: 0, lockStyledRows: 0,
      pages: [{ page: 1, rowCount: 1, apiIds: ['950001'], apiItems: [{ id: '950001', year: 2024, variant: 'unknown' }] }],
    }],
  };
  const api = {
    body: {
      pageInfo: { currentPage: 0, totalPage: 1, totalItem: 1 },
      list: [{ id: 950001, name: '2025年江苏省公考《申论》题', type: 1, lockStatus: 0 }],
    },
  };
  const out = build([
    { kind: 'national', file: 'n.json', json: national },
    { kind: 'api', file: 'a.json', area: '江苏', json: api },
  ]);
  const paper = byId(out, '950001');
  assert.deepEqual(paper.years, [2024, 2025]);
  assert.equal(paper.year, null);
  assert.equal(paper.flags.identityConflict, true);
  assert.deepEqual(paper.flags.identityConflicts, ['year']);
  assert.equal(out.excluded.identityConflict, 1);
  assert.equal(out.candidates.length, 0);
});

test('an explicit variant outranks a title heuristic', () => {
  const national = {
    categoriesSeen: [],
    categories: [{
      category: '江苏', observed: true, pagesRead: 1, totalPagesObserved: 1, partialPages: false,
      memberRows: 0, lockStyledRows: 0,
      pages: [{ page: 1, rowCount: 1, apiIds: ['980001'], apiItems: [{ id: '980001', year: 2024, variant: 'a' }] }],
    }],
  };
  const api = {
    body: {
      pageInfo: { currentPage: 0, totalPage: 1, totalItem: 1 },
      list: [{ id: 980001, name: '2024年江苏省公务员联考《申论》题', type: 1, lockStatus: 0 }],
    },
  };
  const out = build([
    { kind: 'national', file: 'n.json', json: national },
    { kind: 'api', file: 'a.json', area: '江苏', json: api },
  ]);
  const paper = byId(out, '980001');
  assert.equal(paper.variant, 'a');
  assert.equal(paper.flags.identityConflict, false);
  assert.equal(paper.flags.variantTitleDisagreement, true);
  assert.equal(out.totals.variantTitleDisagreements, 1);
});

test('a mock list page cannot make a real-paper area look partial', () => {
  const national = {
    categoriesSeen: ['国考'],
    categories: [{
      category: '国考', observed: true, pagesRead: 1, totalPagesObserved: 1, partialPages: false,
      memberRows: 0, lockStyledRows: 0,
      pages: [{ page: 1, rowCount: 1, apiIds: ['990001'], apiItems: [{ id: '990001', year: 2026, variant: 'unknown' }] }],
    }],
  };
  const mock = {
    body: {
      pageInfo: { currentPage: 0, totalPage: 15, totalItem: 100 },
      list: [{ id: 990002, name: '2027国考行测申论联合模考大赛《申论》（副省卷）', type: 2, lockStatus: 0 }],
    },
  };
  const out = build([
    { kind: 'national', file: 'n.json', json: national },
    { kind: 'api', file: 'm.json', json: mock },
  ]);
  const guokao = out.coverage.byArea.find((area) => area.area === '国考');
  assert.equal(guokao.coverage, 'full');
  assert.equal(out.totals.partialCoverage, 0);
});

test('same id with two different titles is a title conflict and is held back', () => {
  const make = (name) => ({
    body: {
      pageInfo: { currentPage: 0, totalPage: 1, totalItem: 1 },
      list: [{ id: 960001, name, type: 1, lockStatus: 0 }],
    },
  });
  const out = build([
    { kind: 'api', file: 'a1.json', area: '浙江', json: make('2024年浙江省公考《申论》题（A卷）市级') },
    { kind: 'api', file: 'a2.json', area: '浙江', json: make('2024年浙江省公考《申论》题（A卷）县级') },
  ]);
  const paper = byId(out, '960001');
  assert.equal(paper.flags.titleConflict, true);
  assert.equal(paper.flags.identityConflict, false);
  assert.equal(out.excluded.titleConflict, 1);
  assert.equal(hasCandidate(out, '960001'), false);
});

test('unpaired page ids stay visible as unknown-year records', () => {
  const out = build([{
    kind: 'national', file: 'n.json', json: {
      categoriesSeen: [],
      categories: [{
        category: '江苏', observed: true, pagesRead: 1, totalPagesObserved: 1, partialPages: false,
        memberRows: 0, lockStyledRows: 0,
        pages: [{ page: 1, rowCount: 1, apiIds: ['970001'] }],
      }],
    },
  }]);
  const paper = byId(out, '970001');
  assert.equal(paper.year, null);
  assert.equal(paper.flags.unpaired, true);
  assert.equal(out.totals.unknownYear, 1);
  assert.equal(out.excluded.missingYear, 1);
});

test('already captured sourceIds are excluded by exact id', () => {
  const out = build(baseSnapshots(), { capturedIds: new Set(['900001', '910001']) });
  assert.equal(out.excluded.captured, 2);
  assert.equal(hasCandidate(out, '900001'), false);
  assert.equal(hasCandidate(out, '910001'), false);
});

test('coverage records partial regions and the unknown range', () => {
  const out = build();
  assert.deepEqual(out.coverage.partialAreas, ['广东']);
  assert.equal(out.coverage.observedAreas, 6);
  assert.equal(out.coverage.categoriesSeen, 10);
  assert.deepEqual(out.coverage.unobservedRegions, []);
  assert.deepEqual(out.coverage.nonRegionTabs.sort(), ['公安招警和公检法', '推荐', '小模考', '选调生'].sort());
  assert.equal(out.totals.partialCoverage, 2);

  const guokao = out.coverage.byArea.find((area) => area.area === '国考');
  assert.equal(guokao.sourceIds, 4); // 3 real + 1 mock
  assert.equal(guokao.realSourceIds, 3);
  assert.equal(guokao.mock, 1);
  assert.equal(guokao.inScope, 2);
  assert.deepEqual(guokao.fee, { 'free-visible-unverified': 3 });

  const onlyNational = build(baseSnapshots().filter((item) => item.kind === 'national'));
  assert.deepEqual(onlyNational.coverage.unobservedRegions, ['浙江']);

  assert.equal(out.needsLiveCapture.length, 4);
  assert.ok(out.needsLiveCapture.some((field) => /四川/u.test(field.why)));
});

test('mock papers are excluded unless explicitly requested', () => {
  const out = build();
  assert.equal(out.excluded.mock, 1);
  assert.equal(hasCandidate(out, '920004'), false);
  const withMock = build(baseSnapshots(), { includeMock: true });
  assert.equal(withMock.excluded.mock, 0);
});

test('output is deterministic and hides raw titles by default', () => {
  assert.equal(JSON.stringify(build()), JSON.stringify(build()));
  assert.equal(build().papers.every((paper) => !('title' in paper)), true);

  const titled = build(baseSnapshots(), { includeTitles: true });
  assert.match(byId(titled, '930001').title, /2024年/u);
});

test('CLI replays the fixtures offline and writes a 0600 receipt', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'shenlun-catalog-'));
  const outFile = path.join(tmp, 'catalog.json');
  try {
    const stdout = execFileSync(process.execPath, [
      CLI,
      '--national-dir', FIX,
      '--inventory', path.join(FIX, 'inventory-zhejiang.json'),
      '--api-snapshot', path.join(FIX, 'api-zhejiang.json'),
      '--catalog-live-dir', FIX,
      '--now', '2026-10-21T12:00:00Z',
      '--out', outFile,
    ], { encoding: 'utf8' });
    const summary = JSON.parse(stdout.trim().split('\n').pop());
    assert.equal(summary.ok, true);
    assert.equal(summary.offline, true);
    assert.equal(summary.uniqueSourceIds, 22);

    const catalog = JSON.parse(fs.readFileSync(outFile, 'utf8'));
    assert.equal(catalog.sources.length, 5);
    for (const source of catalog.sources) assert.match(source.sha256, /^[0-9a-f]{64}$/u);
    assert.equal(fs.statSync(outFile).mode & 0o777, 0o600);
    assert.equal(catalog.papers.every((paper) => !('title' in paper)), true);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('discover/queue code has no browser, network or profile dependency', () => {
  for (const file of [CLI, path.join(here, '..', 'driver', 'shenlun-catalog-core.mjs')]) {
    const source = fs.readFileSync(file, 'utf8');
    assert.doesNotMatch(source, /playwright|chromium\.launch|from ['"]node:http|from ['"]node:https|fetch\(/u, path.basename(file));
    if (file === CLI) {
      assert.match(source, /const B = path\.resolve\(process\.env\.FENBI_BASE/u);
      assert.match(source, /const WORK = path\.resolve\(process\.env\.FENBI_WORK_DIR/u);
    }
  }
});
