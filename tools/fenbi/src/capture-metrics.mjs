/**
 * Aggregate capture throughput without writing exercise URLs, source text or account state.
 * A successful function return is NOT necessarily a completed capture: partial checkpoints
 * and already-cached documents are counted separately.
 */
export function buildCaptureBatchMetrics(run, { startedAtMs, endedAtMs, planned, spacingMs }) {
  if (!run || !Array.isArray(run.results) || !Number.isFinite(startedAtMs) ||
      !Number.isFinite(endedAtMs) || endedAtMs < startedAtMs ||
      !Number.isInteger(planned) || planned < 0 || !Number.isFinite(spacingMs)) {
    throw new Error('Invalid capture batch metrics input');
  }
  const counts = { newlyComplete: 0, newlyReadable: 0, questionSlotsObserved: 0,
    cachedComplete: 0, partial: 0, failed: 0, skipped: 0 };
  for (const record of run.results) {
    if (!record) { counts.skipped++; continue; }
    if (!record.ok) { counts.failed++; continue; }
    if (record.value?.status !== 'cached_complete' &&
        Number.isInteger(record.value?.observedQuestions) && record.value.observedQuestions > 0) {
      counts.newlyReadable++;
      counts.questionSlotsObserved += record.value.observedQuestions;
    }
    switch (record.value?.status) {
      case 'complete': counts.newlyComplete++; break;
      case 'cached_complete': counts.cachedComplete++; break;
      default: counts.partial++; break;
    }
  }
  if (run.results.length !== planned) throw new Error('Capture batch size differs from scheduled jobs');
  const durationMs = Math.round(endedAtMs - startedAtMs);
  const hourlyRate = durationMs > 0 ? Math.round(counts.newlyComplete * 36000000 / durationMs) / 10 : null;
  const readableRate = durationMs > 0 ? Math.round(counts.newlyReadable * 36000000 / durationMs) / 10 : null;
  return {
    schemaVersion: 1,
    kind: 'gwy-fenbi-capture-batch-metrics',
    startedAt: new Date(startedAtMs).toISOString(),
    endedAt: new Date(endedAtMs).toISOString(),
    durationMs,
    planned,
    pagesUsed: run.concurrency,
    minimumNavigationSpacingMs: spacingMs,
    counts,
    newlyCompletePerHour: hourlyRate,
    newlyReadablePerHour: readableRate,
    stopped: Boolean(run.stopped),
    stopReason: run.reason ?? null,
    note: 'Complete means source structural capture only; it does not certify answers or redistribution rights.',
  };
}
