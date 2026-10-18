/**
 * Offline consumer for Owner fast10 metadata shards.
 *
 * It reads only the shard JSON already attached to capture_ready (categories, numbers, image
 * SHA-256, optionHash, answerStatus). It never reads question text, image bytes, a profile or a
 * site. Exact content/answer verification is not claimed.
 */
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

function sha256(buffer) { return crypto.createHash('sha256').update(buffer).digest('hex'); }

async function readShard(job, config) {
  const artifact = (job.stages?.capture_ready?.artifacts ?? []).find((item) => item.kind === 'question_index');
  if (!artifact) throw Object.assign(new Error('fast10 worker: no question_index artifact'), { code: 'FAST10_ARTIFACT_MISSING' });
  const filename = path.join(config.dataDir, 'artifacts', job.jobId, 'capture_ready', artifact.path);
  const bytes = await fs.readFile(filename);
  if (artifact.sha256 && sha256(bytes) !== artifact.sha256) throw Object.assign(new Error('fast10 worker: shard hash mismatch'), { code: 'FAST10_HASH_MISMATCH' });
  const shard = JSON.parse(bytes.toString('utf8'));
  if (shard.containsQuestionText !== false || shard.containsImageBytes !== false) throw Object.assign(new Error('fast10 worker: shard declares content bytes'), { code: 'FAST10_CONTENT_FORBIDDEN' });
  return { shard, filename };
}

function categoryCounts(shard) {
  const counts = {};
  for (const question of shard.questions ?? []) counts[question.category] = (counts[question.category] ?? 0) + 1;
  return counts;
}

function answerCounts(shard) {
  const counts = {};
  for (const question of shard.questions ?? []) counts[question.answerStatus ?? 'unknown'] = (counts[question.answerStatus ?? 'unknown'] ?? 0) + 1;
  return counts;
}

async function writeTemp(filename, value) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'fast10-worker-'));
  const file = path.join(directory, filename);
  await fs.writeFile(file, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  return file;
}

export const adapter = {
  async process(job, { stage, config }) {
    const { shard } = await readShard(job, config);
    const categories = categoryCounts(shard);
    const answers = answerCounts(shard);
    const imageProblems = (categories.image_unknown ?? 0) + (categories.image_chunking_not_comparable ?? 0);
    if (stage === 'normalized') {
      const file = await writeTemp('normalized-metadata.json', {
        schemaVersion: 1, kind: 'gwy-zhenti-fast10-normalized-summary',
        jobId: job.jobId, sourceId: shard.sourceId, label: shard.label,
        questionCount: shard.questions?.length ?? 0, categories, answerStatus: answers,
        imageCount: (job.images ?? []).length, officialVerification: false, metadataOnly: true,
      });
      return {
        outcome: 'done',
        artifacts: [{ source: file, name: 'normalized-metadata.json', kind: 'metadata' }],
        declarations: { metadataOnly: true, contentUnknown: false },
      };
    }
    if (stage === 'aligned') {
      const file = await writeTemp('alignment-metadata.json', {
        schemaVersion: 1, kind: 'gwy-zhenti-fast10-alignment-summary',
        jobId: job.jobId, sourceId: shard.sourceId,
        questions: (shard.questions ?? []).map((question) => ({
          sourceNumber: question.sourceNumber, repositoryNumber: question.repositoryNumber,
          category: question.category, score: question.score ?? null,
        })),
        categories, officialVerification: false, metadataOnly: true,
      });
      return {
        outcome: 'done',
        artifacts: [{ source: file, name: 'alignment-metadata.json', kind: 'metadata' }],
        declarations: { metadataOnly: true },
      };
    }
    if (stage === 'assets_qa') {
      if (imageProblems > 0) {
        return { outcome: 'needs_review', reason: `fast10 image evidence incomplete: image_unknown=${categories.image_unknown ?? 0}, chunking=${categories.image_chunking_not_comparable ?? 0}` };
      }
      if (!(job.images ?? []).length) {
        const file = await writeTemp('assets-metadata.json', { schemaVersion: 1, kind: 'gwy-zhenti-fast10-assets-summary', jobId: job.jobId, images: 0, categories, officialVerification: false, metadataOnly: true });
        return { outcome: 'done', artifacts: [{ source: file, name: 'assets-metadata.json', kind: 'metadata' }], declarations: { metadataOnly: true } };
      }
      const manifestFile = await writeTemp('image-manifest.json', {
        schemaVersion: 1,
        images: job.images.map((image) => ({ ref: image.ref, sha256: image.sha256, ...(image.bytes ? { bytes: image.bytes } : {}) })),
        note: 'Owner fast10 source image SHA-256; no image bytes were read.',
      });
      const summaryFile = await writeTemp('assets-metadata.json', {
        schemaVersion: 1, kind: 'gwy-zhenti-fast10-assets-summary',
        jobId: job.jobId, images: job.images.length, categories,
        officialVerification: false, metadataOnly: true,
      });
      return {
        outcome: 'done',
        artifacts: [
          { source: manifestFile, name: 'image-manifest.json', kind: 'image_manifest' },
          { source: summaryFile, name: 'assets-metadata.json', kind: 'metadata' },
        ],
        declarations: { metadataOnly: true, imageContentOnly: false },
      };
    }
    if (stage === 'answer_explanation_qa') {
      return { outcome: 'needs_review', reason: 'fast10 answerStatus is unverified; no source-observed or human-authored answer provenance' };
    }
    return { outcome: 'needs_review', reason: `fast10 worker has no processor for stage ${stage}` };
  },
};

export default adapter;
