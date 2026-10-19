/**
 * Offline image-decode proof, consumed by batch-ingest.
 *
 * A capture can contain assets whose bytes and header dimensions are correct but which never
 * received a browser decode binding. The image gate asks for "a complete decode bound to these
 * exact bytes" — not for human visual review. An offline decoder produces exactly that: a full
 * decode of the bytes, with the dimensions it observed.
 *
 * This module only *offers* such a proof to the validator. It never decides a grade. A proof is
 * accepted only when it binds to the paper being ingested right now:
 *   - the file is named for this paper key, which ends with the source id
 *   - its asset set is exactly the document's asset set (no missing reference, no extra entry)
 *   - every entry repeats the asset's sha256 and dimensions and is marked verified
 * If anything does not line up the proof is ignored and the paper keeps whatever grade it had.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
export const OFFLINE_DECODE_METHOD = 'offline-pil-decode';

/** Load `<paperKey>.decode.json` from a proof directory, if present. */
export async function loadDecodeProof(proofDir, paperKey) {
  if (!proofDir || !paperKey) return null;
  try {
    const raw = await fs.readFile(path.join(proofDir, `${paperKey}.decode.json`));
    return JSON.parse(raw.toString('utf8'));
  } catch { return null; }
}

/**
 * Bind a proof to a live document. Returns { ok, reason, decode } where `decode` maps
 * asset url -> { sha256, width, height } to merge into the document's assets.
 */
export function bindDecodeProof(doc, proof, { paperKey, sourceId, sourceSha256, documentSha256 } = {}) {
  if (!proof || !Array.isArray(proof.assets)) return { ok: false, reason: 'proof-shape-invalid' };
  // The proof must be for this paper: the key carries the source id as its last segment.
  if (paperKey && sourceId && !String(paperKey).endsWith('-' + String(sourceId))) {
    return { ok: false, reason: 'proof-source-id-mismatch' };
  }
  // If the proof states provenance, it must match what we are ingesting right now.
  for (const [field, actual] of [['sourceSha256', sourceSha256], ['documentSha256', documentSha256], ['sourceId', sourceId]]) {
    if (proof[field] != null && actual != null && String(proof[field]) !== String(actual)) {
      return { ok: false, reason: `proof-${field}-mismatch` };
    }
  }
  const assets = Array.isArray(doc?.assets) ? doc.assets : [];
  const proofByUrl = new Map();
  for (const entry of proof.assets) {
    if (!entry || !entry.url) return { ok: false, reason: 'proof-entry-without-url' };
    if (proofByUrl.has(entry.url)) return { ok: false, reason: 'proof-duplicate-url' };
    proofByUrl.set(entry.url, entry);
  }
  // Exact coverage in both directions: every document reference has a proof and nothing extra.
  if (proofByUrl.size !== assets.length) return { ok: false, reason: 'proof-coverage-mismatch' };
  const decode = new Map();
  for (const asset of assets) {
    const entry = proofByUrl.get(asset.url);
    if (!entry) return { ok: false, reason: 'proof-missing-asset' };
    if (entry.method !== OFFLINE_DECODE_METHOD) return { ok: false, reason: 'proof-method-unexpected' };
    if (entry.verified !== true) return { ok: false, reason: 'proof-not-verified' };
    if (!entry.sha256 || entry.sha256 !== asset.sha256 || entry.declaredSha256 !== asset.sha256) {
      return { ok: false, reason: 'proof-sha-mismatch' };
    }
    if (entry.width !== asset.width || entry.height !== asset.height) {
      return { ok: false, reason: 'proof-dimension-mismatch' };
    }
    decode.set(asset.url, { sha256: entry.sha256, width: entry.width, height: entry.height });
  }
  return { ok: true, reason: null, decode };
}

/** Return a shallow document copy whose assets carry the proven offline decode. */
export function applyDecodeProof(doc, decode) {
  if (!decode?.size) return doc;
  return {
    ...doc,
    assets: (doc.assets || []).map(asset => {
      const proof = decode.get(asset.url);
      if (!proof) return asset;
      return { ...asset, decoded: true,
        decode: { method: OFFLINE_DECODE_METHOD, sha256: proof.sha256, width: proof.width, height: proof.height } };
    }),
  };
}

export const proofDigest = value => sha(JSON.stringify(value ?? null));
