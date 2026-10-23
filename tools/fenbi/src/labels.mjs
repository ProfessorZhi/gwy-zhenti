/**
 * 卷型标签：从标题里的括号限定语推导中文卷型名。
 *
 * 仓库长期用的落盘规则是 `地区/年份/科目-卷型.md`（如 `国考/2016/申论-副省级.md`），
 * 卷型是给人看的中文名而不是内部 slug。早期采集写的是英文 slug（a/b/tongkao），
 * 与仓库既有文件对不上，导致同一份卷在库里出现两个路径。这里统一成中文名。
 *
 * 推导不出限定语的卷回落到「统考」；真正的同地区同年多卷冲突由落地环节加 `-<源试卷ID>` 后缀解决。
 */
const RULES = [
  [/副省级|省级以上|省直/u, '副省级'],
  [/地市级|市地级|市级以上/u, '地市级'],
  [/行政执法/u, '行政执法'],
  [/公安机关|公安/u, '公安'],
  [/兵团/u, '兵团'],
  [/乡镇|县乡|乡村/u, '乡镇卷'],
  [/县级|县市|旗县/u, '县级卷'],
  [/省市|省市县|市级/u, '省市卷'],
  [/选调/u, '选调生'],
  [/[Aa]卷|[Aa]类/u, 'A类'],
  [/[Bb]卷|[Bb]类/u, 'B类'],
  [/[Cc]卷|[Cc]类/u, 'C类'],
  [/甲级/u, '甲级'],
  [/乙级/u, '乙级'],
  [/通用/u, '通用卷'],
];

/** @param {string} title 源站标题 @returns {string} 中文卷型名 */
export function paperVariantLabel(title) {
  const text = String(title ?? '');
  const qualifiers = [...text.matchAll(/[（(]([^）)]*)[）)]/gu)].map((m) => m[1]).join('；')
    .replace(/网友回忆版|精选|完整版|新增|真题|试题|修订版/gu, '')
    .replace(/[；;、\s]+/gu, '')
    .replace(/^[：:]+|[：:]+$/gu, '');
  for (const [pattern, label] of RULES) if (pattern.test(qualifiers)) return label;
  // 限定语里没有卷型词时，选调/公安这类词经常直接写在标题主体上。
  if (/选调/u.test(text)) return '选调生';
  return '统考';
}
