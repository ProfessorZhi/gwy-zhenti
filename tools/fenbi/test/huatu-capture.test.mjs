import assert from 'node:assert/strict';
import test from 'node:test';
import { args, bareUrl, questionScore } from '../driver/huatu-capture.mjs';

test('记录的地址去掉查询参数与片段，避免带出令牌', () => {
  assert.equal(bareUrl('https://api.example.com/q/list?token=abc&uid=1#x'), 'https://api.example.com/q/list');
});

test('题目数据得分高于无关响应', () => {
  const paper = { data: { questionList: [{ stem: 'x', options: ['a'], answer: 'A', analysis: 'y' }] } };
  assert.ok(questionScore(paper) >= 5);
  assert.equal(questionScore({ code: 0, msg: 'ok' }), 0);
});

test('参数校验', () => {
  assert.equal(args(['--login']).login, true);
  assert.equal(args(['--paper-id', '4056552', '--url', 'https://x/y']).paperId, '4056552');
  assert.throws(() => args(['--paper-id', 'abc', '--url', 'https://x/y']));
  assert.throws(() => args(['--paper-id', '1']));
  assert.throws(() => args(['--login', '--profile', '../evil']));
});
