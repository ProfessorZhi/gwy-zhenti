/**
 * Bounded scheduling for one persistent browser profile.
 *
 * The profile is owned by exactly one `launchPersistentContext`; parallelism happens *inside* that
 * context as extra `Page`s, never as a second process opening the same profile directory. This
 * module only decides how many tasks may be in flight and how fast one host may be hit — it never
 * decides what to fetch. Everything it returns is data, so a caller can stop, report and skip
 * without any of the fetching policy leaking in here.
 */

/** Hard ceiling. A third concurrent page is the most this framework will ever open on one profile. */
export const MAX_CONCURRENCY = 3;

/** Coerce a configured/CLI concurrency to an integer in [1, MAX_CONCURRENCY]. */
export function clampConcurrency(value, fallback = 1) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1) return fallback;
  return Math.min(number, MAX_CONCURRENCY);
}

/** Penalties on one host before the throttle reports itself saturated. */
export const SATURATION_PENALTIES = 3;

/**
 * One shared gate per host. Callers reserve their slot synchronously before awaiting, so two
 * concurrent pages can never both decide they may go now.
 */
export function createHostThrottle({ minIntervalMs = 900, maxIntervalMs = 60000, factor = 2,
  now = Date.now, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) } = {}) {
  const nextAt = new Map(), interval = new Map(), penalties = new Map();

  async function acquire(host) {
    const base = interval.get(host) ?? minIntervalMs;
    const at = nextAt.get(host) ?? 0;
    const wait = Math.max(0, at - now());
    // Reserve before awaiting: the reservation is synchronous, the wait is not.
    nextAt.set(host, Math.max(now(), at) + base);
    if (wait > 0) await sleep(wait);
    return wait;
  }

  return {
    acquire,
    /** Run `task` under this host's gate. */
    async run(host, task) { await acquire(host); return task(); },
    /** A 429/503 pushes every queued caller on this host further out and widens the spacing. */
    penalize(host, status = 429) {
      const widened = Math.min(maxIntervalMs, (interval.get(host) ?? minIntervalMs) * factor);
      interval.set(host, widened);
      const count = (penalties.get(host) ?? 0) + 1;
      penalties.set(host, count);
      nextAt.set(host, Math.max(now(), nextAt.get(host) ?? 0) + widened);
      return { host, status, intervalMs: widened, penalties: count };
    },
    /** A clean observation narrows the spacing back toward the configured floor, one step at a time. */
    settle(host) {
      const current = interval.get(host);
      if (current === undefined) return null;
      const relaxed = Math.max(minIntervalMs, Math.floor(current / factor));
      interval.set(host, relaxed);
      if (relaxed === minIntervalMs) { interval.delete(host); penalties.delete(host); }
      return relaxed;
    },
    saturated() { return [...penalties.values()].some((count) => count >= SATURATION_PENALTIES); },
    state() {
      const hosts = {};
      for (const host of new Set([...nextAt.keys(), ...interval.keys(), ...penalties.keys()])) {
        hosts[host] = { intervalMs: interval.get(host) ?? minIntervalMs, penalties: penalties.get(host) ?? 0, nextAt: nextAt.get(host) ?? 0 };
      }
      return { minIntervalMs, maxIntervalMs, maxConcurrency: MAX_CONCURRENCY, saturated: this.saturated(), hosts };
    },
  };
}

/**
 * Run `worker` over `items` with at most `concurrency` in flight, one dedicated slot each so a
 * caller can pin a slot to its own page. Failures are isolated per item; `control.stop()` ends the
 * run without killing work already in flight, and every item that never started is reported skipped.
 */
export async function runBounded(items, worker, { concurrency = 1, control = {}, onFailure } = {}) {
  const limit = clampConcurrency(concurrency);
  const slots = Math.min(limit, items.length);
  const results = new Array(items.length).fill(null);
  const failures = [];
  let cursor = 0;
  const claim = () => {
    if (control.stopped) return -1;
    if (cursor >= items.length) return -1;
    cursor += 1;
    return cursor - 1;
  };
  await Promise.all(Array.from({ length: slots }, async (_unused, slot) => {
    for (;;) {
      const index = claim();
      if (index < 0) return;
      try { results[index] = { ok: true, value: await worker(items[index], { index, slot, control }) }; }
      catch (error) {
        results[index] = { ok: false, error };
        failures.push({ index, item: items[index], error });
        if (onFailure) onFailure(error, items[index], index);
      }
    }
  }));
  const skipped = results.map((entry, index) => entry === null ? index : -1).filter((index) => index >= 0);
  return { concurrency: slots, results, failures, skipped, stopped: Boolean(control.stopped), reason: control.reason ?? null };
}

/** Shared records must be written one at a time; two pages finishing together must not lose an update. */
export function createSerialQueue() {
  let tail = Promise.resolve();
  return (task) => {
    const run = tail.then(task, task);
    tail = run.then(() => undefined, () => undefined);
    return run;
  };
}

/** A stop flag the workers themselves can raise once they observe an authentication or rate limit. */
export function createControl() {
  return {
    stopped: false, reason: null,
    stop(reason) { this.stopped = true; this.reason ??= reason; return this.reason; },
  };
}
