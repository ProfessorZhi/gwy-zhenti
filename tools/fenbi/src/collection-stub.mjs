/**
 * Shared source-collection placeholder vocabulary.
 *
 * Source bodies use the anchored form in validate.mjs; rendered Markdown and
 * promotion fail closed if any marker survives rendering or legacy fallback.
 * Being stub-free does not establish completeness, correctness or publication rights.
 */
export const COLLECTION_STUB_CORE = '(?:题目正在全力以赴征集|正在搜集中|本题暂无收集到|暂无收集到|网友未回忆起|题目缺失|非客观题，请交卷后查看参考解析估分)';
export const RENDERED_COLLECTION_STUB = new RegExp(COLLECTION_STUB_CORE, 'u');
