import { load } from 'cheerio';
import { createHash } from 'node:crypto';
import { readFile, realpath } from 'node:fs/promises';
import path from 'node:path';

const sha = value => createHash('sha256').update(value).digest('hex');
const str = value => value == null ? '' : String(value);
const result = (status, reason, extra = {}) => ({ status, reason, ...extra });
const imageToken = ' ⟦IMAGE⟧ ';

/** Preserve mathematical symbols, digits, punctuation and image positions. */
export function normalizeComparisonText(value) {
  const images = [];
  const markdown = str(value).replace(/!\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+["'][^"']*["'])?\)/gu, (_, a, b) => {
    const reference = (a || b).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;');
    return `<img src="${reference}">`;
  }).replace(/\[([^\]]+)\]\([^)]*\)/gu, '$1').replace(/\*\*([^*]+)\*\*/gu, '$1').replace(/`([^`]+)`/gu, '$1');
  const $ = load(markdown, null, false);
  $('script, style').remove();
  $('img, image, source').each((_, element) => {
    images.push($(element).attr('src') || $(element).attr('data-src') || $(element).attr('href') || $(element).attr('xlink:href') || '');
    $(element).replaceWith(imageToken);
  });
  $('br').replaceWith('\n');
  $('p, div, li, tr').each((_, element) => { $(element).prepend(' '); $(element).append(' '); });
  // NFKC would erase meaningful mathematics: x² -> x2, a₁ -> a1.
  // Fold only fullwidth ASCII and the ideographic space.
  const strict = $.root().text().replace(/[\uFF01-\uFF5E]/gu, character => String.fromCharCode(character.charCodeAt(0) - 0xFEE0))
    .replace(/\u3000/gu, ' ').replace(/\s+/gu, ' ').trim();
  return { strict, formatOnly: strict.replace(/\s+/gu, ''), images };
}

function compareText(source, repository) {
  const a = normalizeComparisonText(source), b = normalizeComparisonText(repository);
  if (!a.strict) return result('unknown', 'source-content-not-observed');
  if (!b.strict) return result('different', 'repository-content-absent');
  return a.strict === b.strict ? result('same', 'normalized-text-equal', { formatOnly: false })
    : a.formatOnly === b.formatOnly ? result('same', 'whitespace-only-difference', { formatOnly: true })
      : result('different', 'content-differs');
}

/** Parse only the established repository format; all heading boundaries end blocks. */
export function parseRepositoryPaper(markdownText) {
  const markdown = str(markdownText), answerStart = markdown.search(/^#{1,6}\s+答案与解析\s*$/mu);
  const body = answerStart < 0 ? markdown : markdown.slice(0, answerStart);
  const headings = [...body.matchAll(/^#{1,6}\s+(.+)$/gmu)];
  const questions = [], materials = [];
  for (let index = 0; index < headings.length; index++) {
    const heading = headings[index], text = heading[1], chunk = body.slice(heading.index + heading[0].length, headings[index + 1]?.index ?? body.length).trim();
    const question = text.match(/^第\s*(\d+)\s*题/u);
    const material = text.match(/^材料\s*(\d+)/u);
    if (material) {
      const range = text.match(/第\s*(\d+)\s*[—–\-~～至]\s*(\d+)\s*题/u);
      materials.push({ id: material[1], contentHtml: chunk, range: range ? [Number(range[1]), Number(range[2])] : null });
    }
    if (!question) continue;
    const optionMatches = [...chunk.matchAll(/^\s*-\s*\*\*([A-Z])\*\*[.．、:]\s*/gmu)];
    const options = optionMatches.map((match, j) => ({ label: match[1], contentHtml: chunk.slice(match.index + match[0].length, optionMatches[j + 1]?.index ?? chunk.length).trim() }));
    questions.push({ id: text.match(/\bqid\s+([\w-]+)/u)?.[1] ?? '', number: Number(question[1]),
      contentHtml: chunk.slice(0, optionMatches[0]?.index ?? chunk.length).trim(), options, materialIds: [], answerHtml: '', explanationHtml: '' });
  }
  for (const q of questions) q.materialIds = materials.filter(m => m.range && q.number >= m.range[0] && q.number <= m.range[1]).map(m => m.id);
  const answers = answerStart < 0 ? '' : markdown.slice(answerStart);
  for (const block of answers.matchAll(/<details\b[^>]*>([\s\S]*?)<\/details>/giu)) {
    const number = block[1].match(/<summary[^>]*>\s*第\s*(\d+)\s*题[\s\S]*?<\/summary>/iu)?.[1];
    const candidates = questions.filter(q => q.number === Number(number));
    if (candidates.length !== 1) continue;
    const q = candidates[0], rest = block[1].replace(/^[\s\S]*?<\/summary>/iu, '');
    const answer = rest.match(/\*\*答案\*\*\s*[：:]\s*([^\r\n]+)/u);
    q.answerHtml = answer?.[1]?.trim() ?? '';
    q.explanationHtml = rest.replace(/\*\*答案\*\*\s*[：:]\s*[^\r\n]+/u, '')
      .replace(/^\s*\*\*[^\r\n]*解析[^\r\n]*\*\*\s*$/gmu, '').replace(/^\s*---\s*$/gmu, '').trim();
  }
  return { questions, materials };
}

function compareOptions(source, repository, subject) {
  if (!source.length && subject === 'shenlun') return result('not_compared', 'essay-options-not-applicable');
  if (!source.length) return result('unknown', 'source-options-not-observed');
  if (source.length !== repository.length) return result('different', 'option-count-differs');
  if (source.some(option => !option.label)) return result('unknown', 'source-option-labels-not-observed');
  const parts = source.map((option, index) => option.label !== repository[index]?.label
    ? result('different', 'option-label-or-order-differs') : compareText(option.contentHtml, repository[index].contentHtml));
  return parts.some(p => p.status === 'different') ? result('different', 'option-content-label-or-order-differs')
    : parts.some(p => p.status === 'unknown') ? result('unknown', 'option-content-not-observed')
      : result('same', 'all-options-equal', { formatOnly: parts.some(p => p.formatOnly) });
}

function textMatches(a, b, subject) {
  return compareText(a.contentHtml, b.contentHtml).status === 'same'
    && compareOptions(a.options || [], b.options || [], subject).status === (subject === 'shenlun' ? 'not_compared' : 'same');
}

async function fileWithin(root, relative) {
  const canonicalRoot = await realpath(root), full = await realpath(path.resolve(canonicalRoot, relative));
  if (full !== canonicalRoot && !full.startsWith(`${canonicalRoot}${path.sep}`)) throw new Error('outside-root');
  return readFile(full);
}

async function compareImages(source, repository, doc, options) {
  const a = normalizeComparisonText(source).images, b = normalizeComparisonText(repository).images;
  if (a.length !== b.length) return result('different', 'image-reference-count-differs', { sourceCount: a.length, repositoryCount: b.length });
  if (!a.length) return result('not_compared', 'no-image-references', { sourceCount: 0, repositoryCount: 0 });
  if (!options.assetRoot || !options.repoRoot || !options.paperPath) return result('unknown', 'image-bytes-not-compared', { sourceCount: a.length, repositoryCount: b.length });
  try {
    for (let index = 0; index < a.length; index++) {
      let sourceUrl;
      try {
        // Resolve precisely as the captured source document would. A relative
        // reference without a recorded base is unverified, never guessed.
        sourceUrl = new URL(a[index], doc.source?.url || undefined);
        if (!['https:', 'http:'].includes(sourceUrl.protocol)) return result('unknown', 'source-image-url-not-http');
      } catch { return result('unknown', 'source-image-base-url-not-observed'); }
      const asset = (doc.assets || []).find(item => item.url === sourceUrl.href);
      if (!asset?.localPath || !asset.sha256 || asset.status !== 'downloaded') return result('unknown', 'source-image-not-verified');
      const sourceBytes = await fileWithin(options.assetRoot, asset.localPath);
      if (sha(sourceBytes) !== asset.sha256) return result('unknown', 'source-image-hash-invalid');
      if (/^[a-z][a-z0-9+.-]*:/iu.test(b[index])) return result('unknown', 'repository-image-is-not-local');
      const paper = path.isAbsolute(options.paperPath) ? options.paperPath : path.resolve(options.repoRoot, options.paperPath);
      const repositoryBytes = await fileWithin(options.repoRoot, path.relative(options.repoRoot, path.resolve(path.dirname(paper), decodeURIComponent(b[index]))));
      if (sha(sourceBytes) !== sha(repositoryBytes)) return result('different', 'image-bytes-differ');
    }
    return result('same', 'all-image-bytes-equal', { sourceCount: a.length, repositoryCount: b.length });
  } catch { return result('unknown', 'image-file-could-not-be-verified'); }
}

/** Read-only comparison. Reports contain identifiers/statuses, never question text or credentials. */
export async function comparePaper(document, markdownText, options = {}) {
  const repo = parseRepositoryPaper(markdownText), source = document.questions || [], matched = new Set(), questions = [];
  const repositoryQuestionIdNamespace = options.repositoryQuestionIdNamespace ?? 'repository-qid';
  // Legacy callers historically provide repository qids. An explicitly declared
  // DOM key namespace must never be treated as those numeric repository IDs.
  const sourceQuestionIdNamespace = document.identity?.questionIdNamespace ?? repositoryQuestionIdNamespace;
  const compatibleIds = sourceQuestionIdNamespace === repositoryQuestionIdNamespace;
  const duplicateIds = values => [...new Set(values.filter((value, index) => value && values.indexOf(value) !== index))];
  for (const q of source) {
    let candidates = compatibleIds && q.id ? repo.questions.filter(item => item.id === str(q.id)) : [], matchMethod = 'qid';
    if (!candidates.length) {
      candidates = Number.isInteger(q.number) ? repo.questions.filter(item => item.number === q.number && textMatches(q, item, document.identity?.subject)) : [];
      matchMethod = 'explicit-number-and-content';
    }
    if (!candidates.length && !q.id) {
      candidates = repo.questions.filter(item => textMatches(q, item, document.identity?.subject)); matchMethod = 'unique-content-and-options';
    }
    const target = candidates.length === 1 && !matched.has(candidates[0]) ? candidates[0] : null;
    if (!target) {
      questions.push({ sourceId: str(q.id) || null, sourceNumber: q.number ?? null, repositoryId: null, repositoryNumber: null,
        matchMethod: null, status: 'unmatched', reason: candidates.length > 1 ? 'ambiguous-match' : 'no-safe-unique-match' }); continue;
    }
    matched.add(target);
    const sourceMaterials = (q.materialIds || []).map(id => (document.materials || []).find(m => str(m.id) === str(id)));
    const repositoryMaterials = target.materialIds.map(id => repo.materials.find(m => m.id === id));
    const materialResults = sourceMaterials.map((m, index) => m && repositoryMaterials[index]
      ? compareText(m.contentHtml, repositoryMaterials[index].contentHtml) : result('unknown', 'material-body-or-link-not-observed'));
    const refsKnown = q.materialIdsObserved === true || (q.materialIds || []).length > 0;
    const materialStatus = !refsKnown ? result('unknown', 'source-material-links-not-observed')
      : sourceMaterials.length !== repositoryMaterials.length ? result('different', 'material-reference-count-differs')
        : materialResults.some(item => item.status === 'different') ? result('different', 'material-content-differs')
          : materialResults.some(item => item.status === 'unknown') ? result('unknown', 'material-content-not-observed')
            : result('same', 'material-count-and-content-equal');
    const sourceImages = [q.contentHtml, ...(q.options || []).map(o => o.contentHtml), ...sourceMaterials.filter(Boolean).map(m => m.contentHtml), q.answerHtml, q.explanationHtml].join('\n');
    const repoImages = [target.contentHtml, ...(q.options?.length ? target.options.map(o => o.contentHtml) : []), ...(refsKnown ? repositoryMaterials.map(m => m.contentHtml) : []),
      // Do not compare unseen source answer/explanation images with repository-only evidence.
      q.answerHtml ? target.answerHtml : '', q.explanationHtml ? target.explanationHtml : ''].join('\n');
    const dimensions = {
      qid: !compatibleIds ? result('not_compared', 'question-id-namespaces-incompatible')
        : q.id && target.id ? result(str(q.id) === target.id ? 'same' : 'different', 'source-id-comparison') : result('unknown', 'source-or-repository-id-absent'),
      number: Number.isInteger(q.number) ? result(q.number === target.number ? 'same' : 'different', 'explicit-number-comparison') : result('unknown', 'source-number-not-observed'),
      stem: compareText(q.contentHtml, target.contentHtml), options: compareOptions(q.options || [], target.options, document.identity?.subject),
      materials: materialStatus,
      answer: compareText(q.answerHtml, target.answerHtml), explanation: compareText(q.explanationHtml, target.explanationHtml),
      images: materialStatus.status === 'unknown' && repositoryMaterials.some(m => normalizeComparisonText(m.contentHtml).images.length)
        ? result('unknown', 'material-images-not-observed-completely') : await compareImages(sourceImages, repoImages, document, options),
    };
    questions.push({ sourceId: str(q.id) || null, sourceNumber: q.number ?? null, repositoryId: target.id || null, repositoryNumber: target.number,
      matchMethod, status: 'matched', dimensions });
  }
  const allSourceIds = source.map(q => str(q.id)), allRepoIds = repo.questions.map(q => q.id);
  const completeIds = allSourceIds.every(Boolean) && allRepoIds.every(Boolean);
  const uniqueSourceIds = duplicateIds(allSourceIds), uniqueRepoIds = duplicateIds(allRepoIds);
  const idSetEqual = completeIds && !uniqueSourceIds.length && !uniqueRepoIds.length && allSourceIds.length === allRepoIds.length && allSourceIds.every(id => allRepoIds.includes(id));
  const dimensions = {};
  for (const row of questions.filter(q => q.status === 'matched')) for (const [name, value] of Object.entries(row.dimensions)) {
    dimensions[name] ??= { same: 0, different: 0, unknown: 0, not_compared: 0 }; dimensions[name][value.status]++;
  }
  const countKnown = Number.isInteger(document.expected?.questions);
  const sourceMaterialCountKnown = Number.isInteger(document.expected?.materials);
  const numberedRows = questions.filter(q => q.status === 'matched' && Number.isInteger(q.sourceNumber));
  const duplicateNumbers = duplicateIds(source.map(q => q.number).filter(n => Number.isInteger(n)));
  const orderByNumber = numberedRows.some(row => row.sourceNumber !== row.repositoryNumber)
    ? result('different', 'explicit-source-number-and-matched-repository-number-differ')
    : !source.length || numberedRows.length !== source.length || duplicateNumbers.length
      ? result('unknown', 'not-all-source-questions-uniquely-matched-with-explicit-numbers')
      : result('same', 'all-matched-explicit-source-and-repository-numbers-equal');
  return { schemaVersion: 1, identity: { sourcePaperId: str(document.identity?.id) || null,
    sourceQuestionIdNamespace, repositoryQuestionIdNamespace },
    paper: {
      questionCount: !countKnown ? result('unknown', 'source-total-not-observed')
        : document.expected.questions !== source.length ? result('unknown', 'source-capture-incomplete', { expected: document.expected.questions, observed: source.length })
          : result(source.length === repo.questions.length ? 'same' : 'different', 'verified-source-total-comparison'),
      qidSet: !compatibleIds ? result('not_compared', 'question-id-namespaces-incompatible')
        : !completeIds ? result('unknown', 'not-all-question-ids-observed') : result(idSetEqual ? 'same' : 'different', 'question-id-set-comparison'),
      order: orderByNumber,
      orderById: !compatibleIds ? result('not_compared', 'question-id-namespaces-incompatible')
        : !completeIds ? result('unknown', 'not-all-question-ids-observed') : result(idSetEqual && allSourceIds.every((id, index) => id === allRepoIds[index]) ? 'same' : 'different', 'captured-id-sequence-comparison'),
      materialCount: sourceMaterialCountKnown ? result(document.expected.materials === repo.materials.length ? 'same' : 'different', 'explicit-source-material-total-comparison') : result('unknown', 'source-material-total-not-observed'),
    }, summary: { sourceQuestions: source.length, repositoryQuestions: repo.questions.length, matched: matched.size,
      unmatchedSource: questions.filter(q => q.status === 'unmatched').length, unmatchedRepository: repo.questions.length - matched.size,
      duplicateSourceIds: uniqueSourceIds, duplicateRepositoryIds: uniqueRepoIds, dimensionCounts: dimensions,
      allQualityPassed: false, limitation: 'Alignment measures observed equivalence; it does not certify authoritative exam accuracy or unobserved content.' },
    questions, unmatchedRepository: repo.questions.filter(q => !matched.has(q)).map(q => ({ id: q.id || null, number: q.number })) };
}
