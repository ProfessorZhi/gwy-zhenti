import { test } from 'node:test';
import assert from 'node:assert/strict';
import { yearAllowed } from '../driver/year-policy.mjs';
import { validateDocument } from '../src/validate.mjs';

// 用户决定（2026-10-23）：粉笔上能看到的全部年份都要，不限地区。
test('任何地区的历史年份都准入，只挡住未来年份与非法年份', () => {
  assert.equal(yearAllowed('浙江', 2005), true);
  assert.equal(yearAllowed('江苏', 2015), true);
  assert.equal(yearAllowed('国考', 2005), true);
  assert.equal(yearAllowed('西藏', 2008), true);
  assert.equal(yearAllowed('浙江', new Date().getFullYear() + 1), false);
  assert.equal(yearAllowed('江苏', 'not-a-year'), false);
});

test('校验器不再按地区卡 2016：江苏 2005 不报 year-invalid，未来年份照报', async () => {
  const doc = (area, year) => ({ schemaVersion: 1, questions: [], materials: [], assets: [],
    identity: { id: '1', title: 't', subject: 'xingce', year, area, variant: 'a' } });
  const codes = async (area, year) => (await validateDocument(doc(area, year))).issues.map(i => i.code);
  assert.ok(!(await codes('江苏', 2005)).includes('year-invalid'));
  assert.ok(!(await codes('浙江', 2005)).includes('year-invalid'));
  assert.ok((await codes('江苏', new Date().getFullYear() + 1)).includes('year-invalid'));
});
