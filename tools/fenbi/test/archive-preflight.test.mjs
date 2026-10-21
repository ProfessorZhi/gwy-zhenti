import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile, readFile, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { scanArchive, TECHNICAL, PUBLICATION } from '../src/archive-preflight.mjs';

// 全部使用合成文本与合成 PNG 头；不含任何真实题目、材料、答案或图片字节。
const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const SECRET = 'SYNTHETIC_ANSWER_TEXT_MUST_NOT_APPEAR_IN_REPORT';

function png(width, height, salt = 0) {
  const buffer = Buffer.alloc(34);
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(buffer, 0);
  buffer.writeUInt32BE(13, 8);
  buffer.write('IHDR', 12, 'ascii');
  buffer.writeUInt32BE(width, 16);
  buffer.writeUInt32BE(height, 20);
  buffer[33] = salt;
  return buffer;
}

function volume({ id = '1001', area = '浙江', year = 2026, variant = 'a', tabs = 1, images = 1, questionCount = 1 } = {}) {
  const imageList = Array.from({ length: images }, (_, index) => {
    const bytes = png(700, 300 + index, index);
    return { bytes, sha256: sha256(bytes), file: `assets/${sha256(bytes)}.png`, width: 700, height: 300 + index };
  });
  const materials = Array.from({ length: tabs }, (_, index) => ({
    position: index,
    tabNumbers: [index + 1],
    markdown: `合成材料 ${index + 1}\n\n${imageList[index] ? `![合成图](${imageList[index].file})` : ''}`,
  }));
  const questions = Array.from({ length: questionCount }, (_, index) => ({
    number: index + 1,
    materialRefs: [{ tabNumber: Math.min(index + 1, tabs), stored: true, htmlSha: 'a'.repeat(64) }],
    promptMarkdown: `合成题干 ${index + 1}`,
    requirementsMarkdown: '要求：不超过300字。',
    answerMarkdown: `${SECRET} 合成作答 ${index + 1}`,
    explanationMarkdown: '',
    analysisStatus: 'video-only',
    answerSource: 'referenceAnswer',
  }));
  const paperMd = [
    `# 合成卷 ${id}`,
    '',
    ...materials.map((material) => material.markdown),
    ...questions.map((question) => `## 第${question.number}题\n\n${question.promptMarkdown}\n\n${question.requirementsMarkdown}\n\n${question.answerMarkdown}`),
    '',
  ].join('\n');
  const analysis = { textual: 0, imageOnly: 0, videoOnly: questionCount, absent: 0 };
  const structure = {
    questionsComplete: true,
    materialsComplete: true,
    answersComplete: true,
    assetsComplete: images > 0,
    questionCount,
    answersPresent: questionCount,
    materialPanesStored: tabs,
    materialTabsDeclared: tabs,
    materialCountEvidence: 'material-tab-strip',
    unresolvedMaterialReferences: 0,
    validatorStatus: 'partial',
    issueCodes: ['explanation-empty'],
  };
  const rights = {
    rightsStatus: 'unverified',
    cloudStorageBlocked: true,
    copyrightLicense: 'not-established',
    githubPublicationAllowed: false,
  };
  const documentBytes = Buffer.from(`{"synthetic":"document-${id}"}\n`);
  const documentSha = sha256(documentBytes);
  const paper = {
    schemaVersion: 1,
    kind: 'shenlun-local-archive-paper',
    generatedAt: '2026-10-21T00:00:00.000Z',
    sourceId: id,
    area,
    year,
    variant,
    titleHash: sha256(`synthetic-title-${id}`).slice(0, 16),
    titleLen: 8,
    titleVerified: null,
    cohort: 'other',
    archiveStatus: 'PARTIAL',
    gaps: ['合成 gap'],
    structure,
    analysis,
    rights,
    materials,
    questions,
    assets: imageList.map((image) => ({
      sha256: image.sha256, bytes: image.bytes.length, file: image.file, width: image.width, height: image.height,
    })),
    missingImages: [],
    imageMapping: 'order+dimensions',
    imageMappingSource: 'document-assets-order',
    capture: { lane: 'synthetic', documentSha, capturedAt: '2026-10-21T00:00:00.000Z', binding: null },
  };
  const receipt = {
    schemaVersion: 1,
    kind: 'shenlun-local-archive-receipt',
    generatedAt: paper.generatedAt,
    sourceId: id,
    paperId: id,
    area,
    year,
    variant,
    subject: 'shenlun',
    questionCount,
    questionNumbers: Array.from({ length: questionCount }, (_, index) => index + 1),
    expectedQuestions: questionCount,
    missingQuestionNumbers: [],
    materialPanesStored: tabs,
    materialTabsDeclared: tabs,
    unresolvedMaterialReferences: [],
    analysis,
    sectionTitles: {},
    answersPresent: questionCount,
    explanationsPresent: 0,
    rightsStatus: 'unverified',
    cloudStorageBlocked: true,
    validation: { status: 'partial', issueCodes: ['explanation-empty'] },
    titleHash: paper.titleHash,
    titleLen: paper.titleLen,
    titleVerified: null,
    cohort: paper.cohort,
    archiveStatus: paper.archiveStatus,
    gaps: paper.gaps,
    structure,
    imageRefs: images,
    imageBytesStored: images,
    imagesMissing: 0,
    imageMapping: paper.imageMapping,
    imageMappingSource: paper.imageMappingSource,
    materialTabNumbersStored: Array.from({ length: tabs }, (_, index) => index + 1),
    rights: { thirdPartyCopyrightLicense: { status: 'not-established' }, githubCloudStorage: { status: 'blocked' } },
    capture: paper.capture,
  };
  const index = {
    sourceId: id,
    area,
    year,
    variant,
    titleHash: paper.titleHash,
    cohort: paper.cohort,
    pilotScope: false,
    archiveStatus: paper.archiveStatus,
    questions: questionCount,
    answersPresent: questionCount,
    materialPanesStored: tabs,
    materialTabsDeclared: tabs,
    imageRefs: images,
    imageBytesStored: images,
    imagesMissing: 0,
    textualAnalysis: 0,
    videoOnlyAnalysis: questionCount,
    absentAnalysis: 0,
    validatorStatus: 'partial',
    rightsStatus: 'unverified',
    cloudStorageBlocked: true,
    path: `papers/${id}/`,
  };
  return { paper, receipt, index, paperMd, imageList, documentBytes, documentSha };
}

async function makeArchive({ volumes = [volume()], rights = {} } = {}) {
  const root = await mkdtemp(path.join(tmpdir(), 'shenlun-preflight-'));
  await mkdir(path.join(root, 'catalog'), { recursive: true });
  await mkdir(path.join(root, 'papers'), { recursive: true });
  await writeFile(path.join(root, 'rights-provenance.json'), JSON.stringify({
    schemaVersion: 1,
    fields: {
      thirdPartyCopyrightLicense: { status: 'not-established' },
      githubCloudStorage: { status: 'blocked', publishableVolumes: 0 },
      ...rights,
    },
  }));
  const indexLines = [];
  let questions = 0;
  let answers = 0;
  let panes = 0;
  let imageRefs = 0;
  let imageBytes = 0;
  for (const item of volumes) {
    const dir = path.join(root, 'papers', item.index.sourceId);
    await mkdir(path.join(dir, 'assets'), { recursive: true });
    await writeFile(path.join(dir, 'paper.json'), JSON.stringify(item.paper));
    await writeFile(path.join(dir, 'receipt.json'), JSON.stringify(item.receipt));
    await writeFile(path.join(dir, 'paper.md'), item.paperMd);
    for (const image of item.imageList) await writeFile(path.join(dir, image.file), image.bytes);
    indexLines.push(JSON.stringify(item.index));
    questions += item.paper.questions.length;
    answers += item.receipt.answersPresent;
    panes += item.paper.materials.length;
    imageRefs += item.receipt.imageRefs;
    imageBytes += item.receipt.imageBytesStored;
  }
  await writeFile(path.join(root, 'catalog', 'index.jsonl'), `${indexLines.join('\n')}\n`);
  await writeFile(path.join(root, 'catalog', 'archive-manifest.json'), JSON.stringify({
    schemaVersion: 1,
    generatedAt: '2026-10-21T00:00:00.000Z',
    totals: {
      volumes: volumes.length,
      questions,
      answers,
      materialPanes: panes,
      imageRefs,
      imageBytesStored: imageBytes,
      volumesWithMissingImages: 0,
      textualAnalysisQuestions: 0,
      videoOnlyAnalysisQuestions: questions,
      absentAnalysisQuestions: 0,
      archiveComplete: 0,
      archivePartial: volumes.length,
      cohortZhejiang20: 0,
      cohortNational8: 0,
      otherVolumes: volumes.length,
      githubPublished: 0,
    },
  }));
  const inventory = {
    captures: volumes.map((item) => ({
      sourceId: item.index.sourceId,
      dir: path.join(root, 'captures', item.index.sourceId),
      documentSha: item.documentSha,
    })),
  };
  for (const item of volumes) {
    const dir = path.join(root, 'captures', item.index.sourceId);
    await mkdir(dir, { recursive: true });
    await writeFile(path.join(dir, 'document.json'), item.documentBytes);
  }
  const inventoryPath = path.join(root, 'inventory.json');
  await writeFile(inventoryPath, JSON.stringify(inventory));
  return { root, inventoryPath };
}

async function cleanup(root) { await rm(root, { recursive: true, force: true }); }

test('clean synthetic volume: technical PASS, publication BLOCKED, no content leaked', async () => {
  const fx = await makeArchive();
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.PASS, 1);
    assert.equal(report.gates.technical.FAIL, 0);
    assert.equal(report.gates.publication.BLOCKED, 1);
    assert.equal(report.volumes[0].assets.verified, 1);
    assert.equal(report.volumes[0].documentSha.status, 'verified');
    const serialized = JSON.stringify(report);
    assert.equal(serialized.includes(SECRET), false, 'report must not contain answer text');
    assert.equal(serialized.includes('合成材料'), false, 'report must not contain material text');
    assert.equal(serialized.includes('合成题干'), false, 'report must not contain prompt text');
    assert.equal(report.archive.snapshotStable, true);
  } finally { await cleanup(fx.root); }
});

test('asset SHA mismatch fails technical gate', async () => {
  const item = volume();
  const fx = await makeArchive({ volumes: [item] });
  try {
    await writeFile(path.join(fx.root, 'papers', '1001', item.imageList[0].file), png(700, 999, 7));
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.FAIL, 1);
    assert.ok(report.volumes[0].checks.some((issue) => issue.code === 'asset-sha-mismatch'));
  } finally { await cleanup(fx.root); }
});

test('missing asset and missing image bytes fail technical gate', async () => {
  const item = volume();
  const fx = await makeArchive({ volumes: [item] });
  try {
    await rm(path.join(fx.root, 'papers', '1001', item.imageList[0].file));
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.FAIL, 1);
    assert.ok(report.volumes[0].checks.some((issue) => issue.code === 'asset-missing'));
  } finally { await cleanup(fx.root); }
});

test('material pane gap and unresolved reference fail technical gate', async () => {
  const item = volume({ tabs: 1, questionCount: 1 });
  item.paper.structure.materialTabsDeclared = 2;
  item.receipt.materialTabsDeclared = 2;
  item.index.materialTabsDeclared = 2;
  item.paper.questions[0].materialRefs[0].stored = false;
  item.paper.structure.unresolvedMaterialReferences = 1;
  item.receipt.unresolvedMaterialReferences = [{ questionNumber: 1, textLen: 1, htmlSha: 'b'.repeat(64) }];
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.FAIL, 1);
    const codes = report.volumes[0].checks.map((issue) => issue.code);
    assert.ok(codes.includes('material-pane-gap'));
    assert.ok(codes.includes('material-ref-unresolved'));
  } finally { await cleanup(fx.root); }
});

test('index identity mismatch fails technical gate', async () => {
  const item = volume();
  item.index.year = 2025;
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.FAIL, 1);
    assert.ok(report.volumes[0].checks.some((issue) => issue.code === 'identity-mismatch'));
  } finally { await cleanup(fx.root); }
});

test('rights flipped to cleared is a publication policy violation, never auto-accepted', async () => {
  const item = volume();
  item.paper.rights.rightsStatus = 'cleared';
  item.paper.rights.cloudStorageBlocked = false;
  item.paper.rights.githubPublicationAllowed = true;
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.publication.ELIGIBLE, 0);
    assert.equal(report.gates.publication.POLICY_VIOLATION, 1);
    assert.ok(report.volumes[0].checks.some((issue) => issue.code === 'rights-policy-violation'));
  } finally { await cleanup(fx.root); }
});

test('markdown image order mismatch is detected', async () => {
  const item = volume({ tabs: 2, images: 2, questionCount: 1 });
  const [first, second] = item.imageList;
  const index = item.paperMd.indexOf(first.file);
  item.paperMd = item.paperMd.replace(first.file, '__TMP__').replace(second.file, first.file).replace('__TMP__', second.file);
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.FAIL, 1);
    const codes = report.volumes[0].checks.map((issue) => issue.code);
    assert.ok(codes.includes('paper-md-ref-mismatch') || codes.includes('asset-ref-order-mismatch'));
    assert.ok(index >= 0);
  } finally { await cleanup(fx.root); }
});

test('document SHA mismatch is fatal', async () => {
  const item = volume();
  const fx = await makeArchive({ volumes: [item] });
  try {
    await writeFile(path.join(fx.root, 'captures', '1001', 'document.json'), '{"synthetic":"tampered"}');
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.gates.technical.FAIL, 1);
    assert.ok(report.volumes[0].checks.some((issue) => issue.code === 'document-sha-mismatch'));
  } finally { await cleanup(fx.root); }
});

test('main manifest match is exact for a unique variant and flags prior answer overlap', async () => {
  const item = volume({ id: '2001', area: '广东', year: 2026, variant: 'xingzheng', tabs: 1, images: 1, questionCount: 1 });
  const fx = await makeArchive({ volumes: [item] });
  try {
    const manifestPath = path.join(fx.root, 'main-manifest.jsonl');
    await writeFile(manifestPath, [
      JSON.stringify({ subject: '申论', area: '广东', year: 2026, paper_type: '行政执法', path: '省考/广东/2026/申论-行政执法.md', declared_questions: 1, sha256: 'c'.repeat(64) }),
      JSON.stringify({ subject: '申论', area: '广东', year: 2026, paper_type: '统考', path: '省考/广东/2026/申论-统考.md', declared_questions: 12, sha256: 'd'.repeat(64) }),
    ].join('\n'));
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath, mainManifestPath: manifestPath });
    assert.equal(report.volumes[0].mainCatalog.match, 'exact');
    assert.equal(report.volumes[0].mainCatalog.exactPath, '省考/广东/2026/申论-行政执法.md');
    assert.equal(report.volumes[0].mainCatalog.priorAnswerOverlap, true);
  } finally { await cleanup(fx.root); }
});

test('groups and totals are stable', async () => {
  const fx = await makeArchive({
    volumes: [
      volume({ id: '3001', area: '浙江', year: 2025, variant: 'a' }),
      volume({ id: '3002', area: '浙江', year: 2025, variant: 'b' }),
      volume({ id: '3003', area: '国考', year: 2026, variant: 'unknown' }),
    ],
  });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.totals.volumes, 3);
    assert.equal(report.groups.byArea['浙江'].total, 2);
    assert.equal(report.groups.byArea['国考'].total, 1);
    assert.equal(report.groups.byYear['2025'].total, 2);
    assert.equal(report.archiveManifest.drift.length, 0);
  } finally { await cleanup(fx.root); }
});

test('unreadable volume is skipped, not silently passed', async () => {
  const fx = await makeArchive();
  try {
    await writeFile(path.join(fx.root, 'catalog', 'index.jsonl'), `${JSON.stringify({ sourceId: '9999', area: '浙江', year: 2026 })}\n`);
    const report = scanArchive({ archiveRoot: fx.root });
    const missing = report.volumes.find((volume) => volume.sourceId === '9999');
    assert.equal(missing.technicalStatus, TECHNICAL.SKIP);
    assert.ok(missing.checks.some((issue) => issue.code === 'volume-missing'));
    assert.equal(report.gates.publication.ELIGIBLE, 0);
  } finally { await cleanup(fx.root); }
});

test('expectedQuestions=0 is unknown, not a zero-question expectation', async () => {
  const item = volume();
  item.receipt.expectedQuestions = 0;
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.volumes[0].technicalStatus, TECHNICAL.PASS);
    assert.equal(report.volumes[0].checks.some((issue) => issue.code === 'question-count-mismatch'), false);
  } finally { await cleanup(fx.root); }
});

test('null variant and empty-string variant are the same identity', async () => {
  const item = volume({ variant: null });
  item.receipt.variant = '';
  item.index.variant = null;
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.volumes[0].checks.some((issue) => issue.code === 'identity-mismatch'), false);
  } finally { await cleanup(fx.root); }
});

test('failing volume without an alternate capture is marked recapture-required', async () => {
  const item = volume();
  item.paper.structure.materialTabsDeclared = 3;
  item.receipt.materialTabsDeclared = 3;
  item.index.materialTabsDeclared = 3;
  const fx = await makeArchive({ volumes: [item] });
  try {
    const report = scanArchive({ archiveRoot: fx.root, inventoryPath: fx.inventoryPath });
    assert.equal(report.volumes[0].recovery.status, 'recapture-required');
    assert.equal(report.volumes[0].recovery.alternateCompleteCaptures, 0);
  } finally { await cleanup(fx.root); }
});

test('cleared flags without rights provenance never become ELIGIBLE', async () => {
  const item = volume();
  item.paper.rights.rightsStatus = 'cleared';
  item.paper.rights.cloudStorageBlocked = false;
  const fx = await makeArchive({ volumes: [item] });
  try {
    await rm(path.join(fx.root, 'rights-provenance.json'));
    const report = scanArchive({ archiveRoot: fx.root });
    assert.equal(report.gates.publication.ELIGIBLE, 0);
    assert.notEqual(report.volumes[0].publicationStatus, PUBLICATION.ELIGIBLE);
  } finally { await cleanup(fx.root); }
});
