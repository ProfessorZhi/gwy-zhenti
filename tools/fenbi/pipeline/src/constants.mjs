/**
 * Queue vocabulary shared by every role.
 *
 * A *stage* is a unit of work that produces one artifact. `capture_ready` is the only stage
 * whose consumer owns a browser profile; everything after it is offline. `verified` is not a
 * work stage: it is the terminal state reached when `candidate_ready` completes and a separate
 * verifier records a receipt. Keeping it out of STAGES makes "someone can claim verified" a
 * type error rather than a policy mistake.
 */

export const STAGES = Object.freeze([
  'capture_ready',
  'normalized',
  'aligned',
  'assets_qa',
  'answer_explanation_qa',
  'human_review',
  'candidate_ready',
]);

export const STAGE_INDEX = Object.freeze(Object.fromEntries(STAGES.map((stage, index) => [stage, index])));

/** The artifact produced by each stage, and the stage that must have completed first. */
export const PRODUCES = Object.freeze({
  capture_ready: 'staged_raw',
  normalized: 'normalized',
  aligned: 'aligned',
  assets_qa: 'assets_qa',
  answer_explanation_qa: 'answer_explanation_qa',
  human_review: 'human_review',
  candidate_ready: 'candidate_ready',
});

/** Only `capture_ready` may be claimed by the profile owner. All other stages are offline. */
export const ROLE_STAGES = Object.freeze({
  collector: Object.freeze(['capture_ready']),
  normalizer: Object.freeze(['normalized']),
  matcher: Object.freeze(['aligned']),
  assets_qa: Object.freeze(['assets_qa']),
  answer_qa: Object.freeze(['answer_explanation_qa']),
  reviewer: Object.freeze(['human_review']),
  verifier: Object.freeze(['candidate_ready']),
});

export const ROLES = Object.freeze(Object.keys(ROLE_STAGES));

/** Stages that require a browser profile. There is exactly one: the collector's. */
export const BROWSER_STAGES = Object.freeze(['capture_ready']);

/**
 * Stage outcomes. `pending`/`leased` are in-flight, `done` is the only success that unlocks the
 * next stage. `partial` is retryable and must never be reported as complete. The rest are
 * terminal for the current job revision and require an explicit, reasoned `reopen`.
 */
export const OUTCOMES = Object.freeze([
  'pending', 'leased', 'done', 'partial',
  'skipped_placeholder', 'blocked_auth', 'blocked_rights',
  'needs_review', 'dead_letter',
]);

export const TERMINAL_BAD = Object.freeze([
  'skipped_placeholder', 'blocked_auth', 'blocked_rights', 'needs_review', 'dead_letter',
]);

export const SUCCESS = 'done';

/** A job-level status is derived from the first non-pending stage; never from a count alone. */
export const JOB_STATUSES = Object.freeze([
  'queued', 'partial', 'blocked_auth', 'blocked_rights', 'skipped_placeholder',
  'needs_review', 'dead_letter', 'candidate_ready', 'verified',
]);

/** The only outcomes a worker may report without a second human decision. */
export const REPORTABLE_OUTCOMES = Object.freeze([
  'done', 'partial', 'skipped_placeholder', 'blocked_auth', 'blocked_rights',
  'needs_review', 'dead_letter',
]);

/** Human-review outcomes that must never become `candidate_ready` automatically. */
export const NON_COMPLETION = Object.freeze([
  'skipped_placeholder', 'blocked_auth', 'blocked_rights', 'needs_review', 'partial', 'dead_letter',
]);

export const SCHEMA_VERSION = 1;

export const EXIT = Object.freeze({
  OK: 0,
  BLOCKED: 2,
  BACKOFF: 3,
  BACKPRESSURE: 4,
  INVALID: 5,
});
