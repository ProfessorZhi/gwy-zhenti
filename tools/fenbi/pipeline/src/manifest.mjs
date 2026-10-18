import { atomicWriteJson, nowIso } from './fsutil.mjs';
import { STAGES, STAGE_INDEX, SUCCESS, TERMINAL_BAD } from './constants.mjs';
import path from 'node:path';

/**
 * A read-only work manifest for parallel offline consumers. It contains identity, stage, range,
 * owner hint, queue-relative work paths and permission flags — never raw text, image bytes,
 * cookies, profile paths or practice URLs.
 */
export function buildStageManifest({ jobs, stage, config, now = Date.now, observedCatalog = null } = {}) {
  if (!STAGES.includes(stage)) throw Object.assign(new Error(`Unknown stage: ${stage}`), { code: 'INVALID_STAGE' });
  const index = STAGE_INDEX[stage];
  const tasks = [];
  for (const job of jobs) {
    const entry = job.stages?.[stage];
    if (!entry) continue;
    const listed = ['pending', 'leased', 'needs_review'].includes(entry.status) || TERMINAL_BAD.includes(entry.status);
    if (!listed) continue;
    const previousStage = index > 0 ? STAGES[index - 1] : null;
    const previous = previousStage ? job.stages?.[previousStage] : null;
    const previousReady = index === 0 || previous?.status === SUCCESS;
    const blocked = TERMINAL_BAD.includes(entry.status) || TERMINAL_BAD.includes(job.status) || (entry.status === 'pending' && !previousReady);
    const actionable = !blocked && ['pending', 'leased'].includes(entry.status);
    const requiresBrowserOwner = stage === 'capture_ready';
    tasks.push({
      jobId: job.jobId,
      paperSourceId: job.paperSourceId,
      version: job.version,
      title: job.title,
      subject: job.subject,
      area: job.area,
      year: job.year,
      variant: job.variant ?? null,
      stage,
      status: entry.status,
      owner: entry.lease?.owner ?? null,
      suggestedOwner: requiresBrowserOwner ? 'browser-owner' : `${stage}-${tasks.length + 1}`,
      requiresBrowserOwner,
      assignableToOfflineWorker: !requiresBrowserOwner,
      range: {
        questionNumbers: job.qaSummary?.questionNumbers ?? null,
        questionCount: job.qaSummary?.questionCount ?? job.expected?.questions ?? null,
        materialCount: job.qaSummary?.materialCount ?? job.expected?.materials ?? null,
      },
      workDir: path.posix.join('artifacts', job.jobId, stage),
      readOnlyInputs: (previous?.artifacts ?? []).map((artifact) => ({
        path: path.posix.join('artifacts', job.jobId, previousStage, artifact.path),
        sha256: artifact.sha256,
        bytes: artifact.bytes,
      })),
      unknownNumbers: job.qaSummary?.unknownNumbers ?? [],
      placeholderNumbers: job.qaSummary?.placeholderNumbers ?? [],
      blocked,
      actionable,
      blockedReason: blocked ? (entry.reason ?? (entry.status === 'pending' && !previousReady ? 'previous-stage-not-done' : job.status)) : null,
      leaseExpiresAt: entry.lease?.expiresAt ?? null,
      permissions: {
        readOnly: !requiresBrowserOwner,
        browserProfile: requiresBrowserOwner ? 'owner-only' : false,
        cookies: false,
        rawSiteText: false,
        imageBytes: false,
      },
    });
  }
  return {
    schemaVersion: 1,
    kind: 'gwy-zhenti-work-manifest',
    generatedAt: nowIso(now()),
    stage,
    dataDir: config.dataDir,
    leaseTtlMs: config.leaseTtlMs,
    requiresBrowserOwner: stage === 'capture_ready',
    permissions: {
      readOnly: stage !== 'capture_ready',
      browserProfile: stage === 'capture_ready' ? 'owner-only' : false,
      cookies: false, rawSiteText: false, imageBytes: false,
    },
    tasks,
    observedCatalog,
    note: 'Read-only metadata manifest. Consumers must not open a browser/profile or read the Owner raw directory; only the listed queue-relative inputs are in scope.',
  };
}

export async function writeStageManifest(filename, manifest) {
  await atomicWriteJson(filename, manifest);
  return filename;
}
