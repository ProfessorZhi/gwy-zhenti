import test from 'node:test';
import assert from 'node:assert/strict';
import { paperVariantLabel } from '../src/labels.mjs';

test('卷型标签从标题括号里推导，与仓库既有命名一致', () => {
  assert.equal(paperVariantLabel('2016年国家公务员录用考试《申论》题（副省级）', '国考'), '副省级');
  assert.equal(paperVariantLabel('2016年国家公务员录用考试《行测》题（地市级）', '国考'), '地市级');
  assert.equal(paperVariantLabel('2022年公务员多省联考《申论》题（安徽A卷）', '安徽'), 'A类');
  assert.equal(paperVariantLabel('2021年江苏省公务员录用考试《申论》题（C类）', '江苏'), 'C类');
  assert.equal(paperVariantLabel('2019年广东省公务员录用考试《申论》题（乡镇卷）', '广东'), '乡镇卷');
  // 仓库里北京 2020 申论就叫 `申论-区级.md`（行测是 `行测-区级及以上.md`）：
  // 词表认不出的括号限定语逐字保留，不回落「统考」，否则会与真正的统考卷抢同一个文件名。
  assert.equal(paperVariantLabel('2020年北京市公考《申论》题（区级）', '北京'), '区级');
  assert.equal(paperVariantLabel('2020年北京市公考《行测》题（区级及以上）', '北京'), '区级及以上');
});

test('括号里的「网友回忆版/精选」不算卷型，选调写在标题里也认得出', () => {
  assert.equal(paperVariantLabel('2018年江西省考《行测》题（网友回忆版）', '江西'), '统考');
  assert.equal(paperVariantLabel('广东省2019年选调优秀大学毕业生笔试 综合行政能力测验题（网友回忆版）'), '选调生');
  assert.equal(paperVariantLabel('2017年湖北省选调生行测题（精选）'), '选调生');
});

test('推导不出限定语时回落统考，不会产生空卷型', () => {
  for (const title of ['', '2017年公务员天津市滨海新区《申论》题', null]) assert.equal(paperVariantLabel(title), '统考');
});
