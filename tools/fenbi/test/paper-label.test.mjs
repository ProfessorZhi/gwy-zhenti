import { test } from 'node:test';
import assert from 'node:assert/strict';
import { paperLabel, labelsIn } from '../src/paper-label.mjs';

test('粉笔卷落到本库同一卷：标题里出现的已有卷名优先', () => {
  const existing = labelsIn(['行测-下半年.md', '行测-统考.md', '行测-tongkao.md', '申论-统考.md'], '行测');
  assert.deepEqual(existing, ['下半年', '统考']);
  assert.equal(paperLabel({ title: '2019年四川省公务员录用考试《行测》题（下半年）（网友回忆版）', variant: 'tongkao', existing }), '下半年');
  assert.equal(paperLabel({ title: '2019年四川省公务员录用考试《行测》题（网友回忆版）', variant: 'tongkao', existing }), '统考');
  assert.equal(paperLabel({ title: '2020年国家公务员录用考试《行测》题（地市级）', variant: 'dishiji', existing: ['副省级', '地市级'] }), '地市级');
  assert.equal(paperLabel({ title: '2021年广州市考《行测》（乡镇卷）', variant: 'township', existing: ['乡镇卷', '县级以上'] }), '乡镇卷');
  assert.equal(paperLabel({ title: '2023年浙江省考《行测》（A类）', variant: 'a', existing: [] }), 'A类');
  assert.equal(paperLabel({ title: '2020年青海省公务员录用考试《行测》试题（A卷）', variant: 'tongkao', existing: ['A类', 'B类'] }), 'A类');
  assert.equal(paperLabel({ title: '2016年黑龙江省公务员录用考试《行测》题（公检法卷）', variant: 'tongkao', existing: ['县乡卷', '统考'] }), '公检法');
  assert.equal(paperLabel({ title: '广东省2019年选调优秀大学毕业生笔试 思维能力测验', variant: 'tongkao', existing: ['乡镇卷', '县级卷'] }), '选调生');
  assert.equal(paperLabel({ title: '2017年福建省选调生考试《行政职业能力测验》', variant: 'tongkao', existing: ['统考'] }), '选调生');
});
