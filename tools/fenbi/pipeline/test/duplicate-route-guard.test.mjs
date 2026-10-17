import test from 'node:test';
import assert from 'node:assert/strict';
import { sanitizeSourceUrl, urlMatchesObserved } from '../src/identity.mjs';

const base = 'https://www.fenbi.com/spa/tiku/exam/9000001';
const opts = { routeParams: ['routecs'] };

test('a single declared observed route remains reproducible', () => {
  const observed = base + '?labelId=4&routecs=xingce';
  const saved = sanitizeSourceUrl(observed, opts);
  assert.equal(urlMatchesObserved(observed, saved, opts), true);
  assert.match(saved, /routecs=xingce/);
});

test('two different observed routecs values are ambiguous, not capture-ready', () => {
  const observed = base + '?routecs=xingce&routecs=another';
  const saved = sanitizeSourceUrl(observed, opts);
  // Sanitizer currently collapses repeats; the equality guard must reject.
  assert.equal((saved.match(/routecs=/g) ?? []).length, 1);
  assert.equal(urlMatchesObserved(observed, saved, opts), false);
});

test('two identical routecs values also require review', () => {
  const observed = base + '?routecs=xingce&routecs=xingce';
  assert.equal(urlMatchesObserved(observed, sanitizeSourceUrl(observed, opts), opts), false);
});

test('URL-decoded duplicate route names and built-in labelId are rejected', () => {
  for (const observed of [
    base + '?routecs=xingce&%72outecs=other',
    base + '?labelId=1&labelId=2&routecs=xingce',
  ]) {
    assert.equal(urlMatchesObserved(observed, sanitizeSourceUrl(observed, opts), opts), false);
  }
});

test('intentionally ignorable tracking values may repeat', () => {
  const observed = base + '?labelId=1&routecs=xingce&utm_source=one&utm_source=two';
  const saved = sanitizeSourceUrl(observed, opts);
  assert.equal(urlMatchesObserved(observed, saved, opts), true);
});

test('an undeclared route and a credential query still fail closed', () => {
  const observed = base + '?routecs=xingce';
  const saved = sanitizeSourceUrl(observed, { routeParams: [] });
  assert.equal(urlMatchesObserved(observed, saved, { routeParams: [] }), false);
  assert.throws(() => sanitizeSourceUrl(base + '?token=SECRET', opts), /credential-like/);
});
