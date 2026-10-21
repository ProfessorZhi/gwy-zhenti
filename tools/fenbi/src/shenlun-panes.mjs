// 申论材料页签的纯合并逻辑（无浏览器、无网络）。
//
// 现场观察到的真实结构（2026-10-21，浙江 2020 A）：
//   * 材料页签条是 nav.nav-container > .tabs-container > .tabs-content > a.tab，
//     标签形如「材料1」；题目页签条是同结构但标签形如「1题」。
//   * 页签条是**按题**渲染的：第 1 题只露出该题引用的 3 个材料，第 2 题露出全部 7 个。
//   * 逐个点击页签，.material-body 会切换成对应材料的正文；同一材料在不同题下正文哈希一致。
//
// 所以「采集所有材料」不能只快照当前激活的 .material-body，而要：
//   逐题点击材料页签 → 逐 pane 快照 → 按 htmlSha 去重合并成卷级 materials[]，
//   同时保留每题实际看到的 pane 作为 materialsThisQuestion[]（这是来源证据，不是推测）。
//
// 合并绝不补造：没有点击到的 pane 不会出现在 materials[] 里，题目的引用也不会被猜出来。

import { createHash } from 'node:crypto';

/** 材料页签标签里的序号（现场是阿拉伯数字，如 材料1）。 */
export const MATERIAL_TAB_LABEL = /材料\s*(\d+)/u;

export function sha256(value) {
  return createHash('sha256').update(String(value ?? ''), 'utf8').digest('hex');
}

function textLength(html) {
  return String(html ?? '')
    .replace(/<[^>]*>/gu, ' ')
    .replace(/&nbsp;/gu, ' ')
    .replace(/\s+/gu, ' ')
    .trim()
    .length;
}

function tabNumberOf(label) {
  const match = MATERIAL_TAB_LABEL.exec(String(label ?? ''));
  return match ? Number(match[1]) : null;
}

/**
 * 把逐题点击得到的 pane 快照合并为卷级材料与逐题引用。
 *
 * @param {{questions: Array<{
 *   index?: number,
 *   panes: Array<{ tabIndex?: number, tabLabel?: string, html?: string, htmlSha?: string, textLen?: number, images?: number }>,
 * }>}} input
 * @returns {{materials: object[], questions: object[], evidence: object}}
 */
export function assembleMaterialPanes({ questions = [] } = {}) {
  if (!Array.isArray(questions) || questions.length === 0) throw new Error('questions-required');
  const materials = [];
  const byHash = new Map();
  const evidence = {
    paneObservations: 0,
    distinctPanes: 0,
    emptyPanes: 0,
    duplicateHashesWithinQuestion: [],
    duplicateTabNumberWithinQuestion: [],
    labelNumbering: { fromLabel: 0, fromPosition: 0 },
    perQuestionPanes: [],
    tabNumbersObserved: [],
    declaredMaterialTabs: null,
  };
  const declared = new Set();

  const outQuestions = questions.map((question, position) => {
    const index = Number.isInteger(question?.index) ? question.index : position + 1;
    const panes = Array.isArray(question?.panes) ? question.panes : [];
    const seenHashes = new Set();
    const seenNumbers = new Map();
    const references = [];
    for (const [ordinal, pane] of panes.entries()) {
      evidence.paneObservations += 1;
      const html = typeof pane?.html === 'string' ? pane.html : '';
      const sha = typeof pane?.htmlSha === 'string' && pane.htmlSha
        ? pane.htmlSha
        : (html.trim() ? sha256(html) : null);
      if (!sha) { evidence.emptyPanes += 1; continue; }
      let number = tabNumberOf(pane?.tabLabel);
      if (number !== null) evidence.labelNumbering.fromLabel += 1;
      else { number = (Number.isInteger(pane?.tabIndex) ? pane.tabIndex : ordinal) + 1; evidence.labelNumbering.fromPosition += 1; }
      if (seenHashes.has(sha)) {
        evidence.duplicateHashesWithinQuestion.push({ questionIndex: index, htmlSha: sha });
        continue;
      }
      seenHashes.add(sha);
      if (seenNumbers.has(number)) {
        evidence.duplicateTabNumberWithinQuestion.push({ questionIndex: index, tabNumber: number, htmlSha: sha, otherHtmlSha: seenNumbers.get(number) });
      } else {
        seenNumbers.set(number, sha);
      }
      let material = byHash.get(sha);
      if (!material) {
        material = {
          index: materials.length,
          number: materials.length + 1,
          html,
          htmlSha: sha,
          textLen: Number.isInteger(pane?.textLen) ? pane.textLen : textLength(html),
          images: Number.isInteger(pane?.images) ? pane.images : null,
          firstSeenQuestionIndex: index,
          tabNumbers: [],
        };
        materials.push(material);
        byHash.set(sha, material);
        evidence.distinctPanes += 1;
      }
      if (!material.tabNumbers.includes(number)) material.tabNumbers.push(number);
      declared.add(number);
      references.push({ htmlSha: sha, textLen: material.textLen, images: material.images, tabNumber: number, materialIndex: material.index });
    }
    evidence.perQuestionPanes.push({ questionIndex: index, panes: references.length, tabNumbers: references.map(reference => reference.tabNumber) });
    return { index, materialReferences: references };
  });

  evidence.tabNumbersObserved = [...declared].sort((a, b) => a - b);
  // 只有当所有页签都带序号、且序号从 1 连续时，才敢把它当成「卷面声明了几个材料」。
  const contiguous = evidence.tabNumbersObserved.every((number, position) => number === position + 1);
  evidence.declaredMaterialTabs = evidence.labelNumbering.fromPosition === 0
    && evidence.duplicateTabNumberWithinQuestion.length === 0
    && contiguous && declared.size
    ? evidence.tabNumbersObserved[evidence.tabNumbersObserved.length - 1]
    : null;

  return {
    materials: materials.map(material => ({
      index: material.index,
      number: material.number,
      html: material.html,
      htmlSha: material.htmlSha,
      textLen: material.textLen,
      images: material.images,
      firstSeenQuestionIndex: material.firstSeenQuestionIndex,
      tabNumbers: [...material.tabNumbers],
    })),
    questions: outQuestions,
    evidence,
  };
}

/**
 * 由合并结果生成 schemaVersion 2 的 materialsThisQuestion 数组，
 * 供 parseShenlunCapture 按 htmlSha 解析回 material-N。
 */
export function materialsThisQuestion(references = []) {
  return references.map(reference => ({
    htmlSha: reference.htmlSha,
    textLen: reference.textLen,
    images: reference.images,
    tabNumber: reference.tabNumber,
  }));
}
