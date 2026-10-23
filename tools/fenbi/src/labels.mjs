/**
 * 卷型标签：从标题里的括号限定语推导中文卷型名。
 *
 * 仓库长期用的落盘规则是 `地区/年份/科目-卷型.md`（如 `国考/2016/申论-副省级.md`），
 * 卷型是给人看的中文名而不是内部 slug。仓库既有的 1300+ 份卷由 `tools/gwyzhenti/naming.py`
 * 命名，所以这里**照抄它的规则**：同一份卷在两条流水线上必须落到同一个文件名，否则合并
 * 分支时会出现「同卷不同名」的成对冲突。下面是该文件的 Python 版 `_ptype()` 的移植，
 * 规则顺序（长模式在前）与词表都保持一致。
 *
 * 推导不出限定语的卷回落到「统考」；真正的同地区同年多卷冲突由落地环节加 `-<源试卷ID>` 后缀解决。
 */

// 括号内容里这些词是性质/形式，不是卷型。
const NOT_PTYPE = /网友回忆(整理)?版|精选|联考/gu;
// 省考与普通选调**合卷发布**时上游写作 `安徽A、普通选调卷`；「普通选调卷」是伴随卷型名，不是独立考试。
const XUANDIAO_COMPANION = /[、,，]?\s*普通选调卷/gu;

const PAREN = /[（(]([^）)]*)[）)]/gu;
const ANGLE = /《([^》]*)》/gu;
// 书名号里整段是「科目+序号」或独立科目名时才算卷型（`《行测1》`/`《思维能力测验》`）。
const ANGLE_PTYPE = /^(?:行测\d+|思维能力测验)$/u;

// 顺序有讲究：`县级以上` 必须排在 `县级` 之前，`定向乡镇` 排在 `乡镇` 之前，
// 否则长模式的 search 会被更短的短模式抢先命中。全部按 fullmatch 使用。
const PTYPE_RULES = [
  [/^副省级$/u, '副省级'],
  [/^地市级$/u, '地市级'],
  [/^行政执法$/u, '行政执法'],
  [/^A类$|^A卷$|^A$/u, 'A类'],
  [/^B类$|^B卷$|^B$/u, 'B类'],
  [/^C类$|^C卷$|^C$/u, 'C类'],
  [/^D类$|^D卷$|^D$/u, 'D类'],
  [/^甲级$|^甲卷$/u, '甲级'],
  [/^乙级$|^乙卷$/u, '乙级'],
  [/^上半年$/u, '上半年'],
  [/^下半年$/u, '下半年'],
  [/^县乡卷$|^县乡$/u, '县乡卷'],
  [/^省直卷$|^省直$/u, '省直'],
  [/^兵团$/u, '兵团'],
  [/^县级以上$/u, '县级以上'],
  [/^区级及以上$/u, '区级及以上'],
  [/^定向乡镇$/u, '定向乡镇'],
  [/^单考区卷$/u, '单考区卷'],
  [/^乡镇卷$|^乡镇$/u, '乡镇卷'],
  [/^县级卷$|^县级$/u, '县级卷'],
];
const PTYPE_VALUES = new Set(PTYPE_RULES.map(([, value]) => value));

const FULL_TITLE_RULES = [
  [/副省级/u, '副省级'], [/地市级/u, '地市级'], [/行政执法/u, '行政执法'],
  [/A类|A卷/u, 'A类'], [/B类|B卷/u, 'B类'], [/C类|C卷/u, 'C类'], [/D类|D卷/u, 'D类'],
  [/甲级|甲卷/u, '甲级'], [/乙级|乙卷/u, '乙级'], [/上半年/u, '上半年'], [/下半年/u, '下半年'],
  [/县乡卷|县乡/u, '县乡卷'], [/省直卷|省直/u, '省直'], [/兵团/u, '兵团'],
  [/县级以上/u, '县级以上'], [/区级及以上/u, '区级及以上'], [/定向乡镇/u, '定向乡镇'],
  [/单考区卷/u, '单考区卷'], [/乡镇卷|乡镇/u, '乡镇卷'], [/县级卷|县级/u, '县级卷'],
];

function ptypeTokens(region, title) {
  const out = [];
  for (const [, raw] of title.matchAll(PAREN)) {
    let s = raw.trim();
    if (region && s.startsWith(region)) s = s.slice(region.length);
    s = s.replace(NOT_PTYPE, '');
    // `安徽A、普通选调卷` 剥掉伴随卷型后剩下 `A、`，去尾部分隔符后才是本卷卷型。
    s = s.replace(XUANDIAO_COMPANION, '').replace(/^[、,，\s　]+|[、,，\s　]+$/gu, '');
    if (s === '卷') s = '';
    if (s) out.push(s);
  }
  for (const [, raw] of title.matchAll(ANGLE)) {
    const s = raw.trim();
    if (ANGLE_PTYPE.test(s)) out.push(s);
  }
  return out;
}

function matchValue(token) {
  for (const [pattern, value] of PTYPE_RULES) if (pattern.test(token)) return value;
  // 尾缀 `卷` 的容差是窄的：只在剥掉后能落回词表时才剥（`县乡卷`/`县乡` 不合并成同一值）。
  if (token.endsWith('卷') && PTYPE_VALUES.has(token.slice(0, -1))) return token.slice(0, -1);
  return null;
}

function ptype(region, title) {
  const tokens = ptypeTokens(region, title);
  for (const token of tokens) {
    const value = matchValue(token);
    if (value) return value;
  }
  if (tokens.length) return [...new Set(tokens)].sort().join('+');
  // 没有括号后缀 —— 回落到全标题扫描（覆盖 `2026·国家公务员考试副省级` 这种无括号写法）。
  for (const [pattern, value] of FULL_TITLE_RULES) if (pattern.test(title)) return value;
  return '统考';
}

// 文件名与 frontmatter 只接受 `[\w\p{Script=Han}-]`：`A卷：省直` 这类复合 token 用 `-` 连接。
const safe = (value) => value.replace(/[^\w一-鿿-]+/gu, '-').replace(/^-+|-+$/gu, '') || '统考';

/**
 * @param {string} title 源站标题
 * @param {string} region 源站地区（`安徽`/`国考`）——用于把 `（安徽A卷）` 里的地区前缀剥掉
 * @returns {string} 中文卷型名
 */
export function paperVariantLabel(title, region = '') {
  const text = String(title ?? '');
  // 选调/法检/公安在仓库里自成卷型（main 上已有 `行测-选调生.md`、`行测-法检.md`、
  // `申论-公安.md`），不并进 `统考`；否则同一地区同年两份卷会抢同一个文件名。
  if (!/普通选调/u.test(text) && /选调/u.test(text)) return '选调生';
  if (/法检|法院|检察院/u.test(text)) return '法检';
  if (/公安院校/u.test(text)) return '公安院校';
  if (/公安/u.test(text)) return '公安';
  return safe(ptype(String(region ?? ''), text));
}
