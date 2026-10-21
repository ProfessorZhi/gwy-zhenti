// 整卷视图的组件配对：有些申论卷（广东 2026 公安）不渲染题目/材料页签条，
// 而是把整卷摊开——每道题一个 app-ti，旁边一个 app-materials。配对只能靠结构：
// 组件数量相等、按文档顺序一一对应、且左右两列的纵坐标同序（在版面上是同一行）。
//
// 任何一条不成立都返回错误，绝不按「第 i 个材料就是第 i 题的材料」硬猜。

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export function pairPaperViewComponents({ materials, questions }) {
  if (!Array.isArray(materials) || !Array.isArray(questions)) throw fail('COMPONENTS_REQUIRED', 'materials and questions must be arrays');
  if (materials.length === 0 || questions.length === 0) throw fail('COMPONENTS_EMPTY', 'no material/question components observed');
  if (materials.length !== questions.length) {
    throw fail('COMPONENT_COUNT_MISMATCH', `materials ${materials.length} vs questions ${questions.length}`);
  }
  for (const [position, material] of materials.entries()) {
    if (material?.bodies !== 1) throw fail('MATERIAL_BODIES_NOT_ONE', `material component ${position} has ${material?.bodies} bodies`);
    if (typeof material?.top !== 'number' || Number.isNaN(material.top)) throw fail('MATERIAL_TOP_MISSING', `material component ${position} has no layout position`);
  }
  for (const [position, question] of questions.entries()) {
    if (question?.contents !== 1) throw fail('QUESTION_CONTENTS_NOT_ONE', `question component ${position} has ${question?.contents} contents`);
    if (typeof question?.top !== 'number' || Number.isNaN(question.top)) throw fail('QUESTION_TOP_MISSING', `question component ${position} has no layout position`);
  }
  for (let position = 1; position < materials.length; position += 1) {
    if (!(materials[position].top > materials[position - 1].top)) throw fail('MATERIAL_ORDER_NOT_MONOTONIC', `material ${position} is not below ${position - 1}`);
    if (!(questions[position].top > questions[position - 1].top)) throw fail('QUESTION_ORDER_NOT_MONOTONIC', `question ${position} is not below ${position - 1}`);
  }
  return materials.map((material, position) => ({
    position,
    materialTop: material.top,
    questionTop: questions[position].top,
    verticalDelta: Math.abs(questions[position].top - material.top),
  }));
}
