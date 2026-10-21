// 粉笔卷落到本库哪个文件：本库同目录已有的卷名（"行测-下半年.md" 里的"下半年"）出现在粉笔卷标题里就用它，
// 这样粉笔卷覆盖本库同一卷，而不是另存一份；都对不上时用卷型的中文名。
const LABELS = { tongkao: '统考', a: 'A类', b: 'B类', c: 'C类', fushengji: '副省级', dishiji: '地市级',
  xingzheng: '行政执法', county: '县级卷', township: '乡镇卷', hangce1: '行测一', hangce2: '行测二' };
// 本库没有对应卷名时，标题里这些词说明它不是统考卷，直接用作卷名（不能去覆盖"统考"）。
const KEYWORDS = ['选调生', '选调', '公检法', '司法所', '法检', '省直', '省级', '下半年', '上半年'];
const norm = s => String(s || '').replace(/\s+/g, '').replace(/[卷类]$/u, '');
// "A类"在标题里可能写成"A卷"：单个字母的卷名要求后面紧跟 类/卷。
const inTitle = (t, l) => /^[A-Z]$/u.test(norm(l)) ? new RegExp(norm(l) + '[类卷]', 'u').test(t) : t.includes(norm(l));

// existing：同目录同科目的已有卷名（不含拼音名）。返回文件名里科目后面的部分。
export function paperLabel({ title = '', variant, existing = [] }) {
  const t = String(title || '').replace(/\s+/g, '');
  const hits = existing.filter(l => /[^\x00-\x7f]/u.test(l) && norm(l) && inTitle(t, l))
    .sort((a, b) => norm(b).length - norm(a).length);
  if (hits.length) return hits[0];
  const word = KEYWORDS.find(k => t.includes(k));
  if (word) return word === '选调' ? '选调生' : word;
  return LABELS[variant] || variant;
}

// 目录里某科目的已有卷名：申论-统考.md → 统考。拼音名（旧落盘留下的）不算。
export const labelsIn = (files, subject) => files
  .filter(f => f.startsWith(subject + '-') && f.endsWith('.md'))
  .map(f => f.slice(subject.length + 1, -3))
  .filter(l => /[^\x00-\x7f]/u.test(l));
