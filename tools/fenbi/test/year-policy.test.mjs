import { test } from 'node:test';
import assert from 'node:assert/strict';
import { yearAllowed } from '../driver/year-policy.mjs';
import { validateDocument } from '../src/validate.mjs';

// 用户决定：浙江取粉笔上的全部年份；其他地区 2016–当前年。
test('浙江任何历史年份都准入，其他地区 2016 以前不准入', () => {
  assert.equal(yearAllowed('浙江', 2005), true);
  assert.equal(yearAllowed('浙江', 2015), true);
  assert.equal(yearAllowed('江苏', 2015), false);
  assert.equal(yearAllowed('国考', 2016), true);
  assert.equal(yearAllowed('浙江', new Date().getFullYear() + 1), false);
});

test('校验器按地区判断年份：浙江 2005 不报 year-invalid，江苏 2005 报', async () => {
  const doc = area => ({ schemaVersion: 1, questions: [], materials: [], assets: [],
    identity: { id: '1', title: 't', subject: 'xingce', year: 2005, area, variant: 'a' } });
  const codes = async area => (await validateDocument(doc(area))).issues.map(i => i.code);
  assert.ok(!(await codes('浙江')).includes('year-invalid'));
  assert.ok((await codes('江苏')).includes('year-invalid'));
});
