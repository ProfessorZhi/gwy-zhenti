import test from 'node:test';
import assert from 'node:assert/strict';
import { pairPaperViewComponents } from '../src/shenlun-paper-view.mjs';

const code = (name) => (error) => error.code === name;
const material = (top, bodies = 1) => ({ top, bodies });
const question = (top, contents = 1) => ({ top, contents });

test('three stacked material/question components pair by document order', () => {
  const pairs = pairPaperViewComponents({
    materials: [material(82), material(802), material(1522)],
    questions: [question(136), question(856), question(1575)],
  });
  assert.deepEqual(pairs.map((pair) => pair.position), [0, 1, 2]);
  assert.ok(pairs.every((pair) => pair.verticalDelta < 60));
});

test('unequal component counts are refused, never zipped to the shorter side', () => {
  assert.throws(() => pairPaperViewComponents({
    materials: [material(0), material(100)], questions: [question(10)],
  }), code('COMPONENT_COUNT_MISMATCH'));
});

test('a component holding more than one material body is refused', () => {
  assert.throws(() => pairPaperViewComponents({
    materials: [material(0, 2)], questions: [question(10)],
  }), code('MATERIAL_BODIES_NOT_ONE'));
});

test('a component holding more than one question content is refused', () => {
  assert.throws(() => pairPaperViewComponents({
    materials: [material(0)], questions: [question(10, 2)],
  }), code('QUESTION_CONTENTS_NOT_ONE'));
});

test('components out of layout order are refused', () => {
  assert.throws(() => pairPaperViewComponents({
    materials: [material(500), material(100)], questions: [question(10), question(600)],
  }), code('MATERIAL_ORDER_NOT_MONOTONIC'));
  assert.throws(() => pairPaperViewComponents({
    materials: [material(0), material(400)], questions: [question(600), question(100)],
  }), code('QUESTION_ORDER_NOT_MONOTONIC'));
});

test('an empty page is refused rather than reported as zero questions', () => {
  assert.throws(() => pairPaperViewComponents({ materials: [], questions: [] }), code('COMPONENTS_EMPTY'));
  assert.throws(() => pairPaperViewComponents({ materials: null, questions: [] }), code('COMPONENTS_REQUIRED'));
});
