import test from 'node:test';
import assert from 'node:assert/strict';
import { createDocument } from '../src/model.mjs';
import { assemble, renderIngest, structureGrade } from '../src/batch-ingest.mjs';

const makeQuestion = (number, body) => ({
  id: 'f-'+number, number, contentHtml: body,
  options: [{label:'A',contentHtml:'选项甲答案'},{label:'B',contentHtml:'选项乙答案'}],
  materialIds:[],materialIdsObserved:true,answerHtml:'',explanationHtml:'',requirementsHtml:'',
});
const body = n => '第'+n+'个完全不同的测试题干，题目条件必须保留数字'+n+'。';
function source(rows) {
  const doc=createDocument({id:'100',title:'合成测试卷',area:'浙江',year:2026,subject:'xingce',variant:'C类'},
    {url:'https://www.fenbi.com/spa/tiku',capturedAt:'2026-10-18T00:00:00Z'});
  doc.questions=rows;doc.expected.questions=rows.length;doc.expected.materials=0;
  return doc;
}
function oldPaper(n=4) {
  let md='---\n地区: "浙江"\n科目: "行测"\n---\n# 测试卷\n';
  for(let i=1;i<=n;i++) md+='\n## 第 '+i+' 题 <sub>qid '+(700+i)+'</sub>\n\n'+body(i)+
    '\n\n- **A**. 选项甲答案\n- **B**. 选项乙答案\n';
  md+='\n## 答案与解析\n';
  for(let i=1;i<=n;i++)md+='\n<details><summary>第 '+i+' 题</summary>\n\n**答案**：'+(i%2?'A':'B')+
   '\n\n**解析**\n\n历史来源解析内容'+i+'。\n\n</details>\n';
  return md;
}
test('batch ingest preserves unique old answers without pretending Fenbi showed them', () => {
  const a=assemble(source([1,2,3,4].map(n=>makeQuestion(n,body(n)))),oldPaper());
  assert.equal(a.counters.mappedQuestions,4);
  assert.equal(a.counters.oldAnswersInherited,4);
  assert.equal(a.counters.sourceAnswers,0);
  const md=renderIngest(a,oldPaper());
  assert.match(md,/原库来源/u);
  assert.doesNotMatch(md,/正在征集/u);
  assert.equal(structureGrade(a,md,{dimensions:{images:{status:'complete'}}}).grade,'A');
});
test('safe source stub can inherit same-number legacy when numbering stable', () => {
  const q=[1,2,3,4].map(n=>makeQuestion(n,body(n)));
  q[3].contentHtml='题目正在全力以赴征集，将会第一时间上传';
  const a=assemble(source(q),oldPaper());
  assert.equal(a.numberingStable,true);
  assert.equal(a.counters.inheritedStubs,1);
  const md=renderIngest(a,oldPaper());
  assert.match(md,/本题来源：原库/u);
  assert.match(md,/第4个完全不同的测试题干/u);
  assert.equal(structureGrade(a,md,{dimensions:{images:{status:'complete'}}}).grade,'A');
});
test('reordering does not attach old answer by equal number', () => {
  const q=[4,3,2,1].map((n,i)=>makeQuestion(i+1,body(n)));
  const a=assemble(source(q),oldPaper());
  assert.equal(a.numberingStable,false);
  assert.equal(a.counters.oldAnswersInherited,4);
  assert.equal(a.prepared.questions[0].answerHtml,'B');
});
test('ambiguous or mismatched legacy question remains unknown, no guessing', () => {
  const q=[makeQuestion(1,'完全不相同的题目条件与旧卷不同。'),...([2,3,4].map(n=>makeQuestion(n,body(n))))];
  const a=assemble(source(q),oldPaper());
  assert.equal(a.counters.oldAnswersInherited,3);
  assert.equal(a.prepared.questions[0].answerHtml,'');
  assert.equal(a.counters.oldAnswersUnmapped,1);
  const md=renderIngest(a,oldPaper());
  assert.match(md,/未自动迁移的旧版答案/u);
});
test('stub without reliable numbering is C rather than invented content', () => {
  const q=[4,3,2,1].map((n,i)=>makeQuestion(i+1,body(n)));
  q[3].contentHtml='题目正在全力以赴征集';
  const a=assemble(source(q),oldPaper());
  const md=renderIngest(a,oldPaper());
  assert.equal(a.counters.unresolvedStubs,1);
  assert.equal(structureGrade(a,md,{dimensions:{images:{status:'complete'}}}).grade,'C');
});
test('wrong question count and duplicate source numbering fail closed', () => {
  const q=[makeQuestion(1,body(1)),makeQuestion(1,body(2))];
  const a=assemble(source(q),'');
  const md=renderIngest(a);
  assert.ok(structureGrade(a,md,{dimensions:{images:{status:'complete'}}}).blockers.includes('question-numbers-not-contiguous'));
});


test('actual legacy splice containing a collection stub cannot retain A grading', () => {
  const q=[1,2,3,4].map(n=>makeQuestion(n,body(n)));
  q[3].contentHtml='题目正在全力以赴征集，将会第一时间上传';
  const before='## 第 4 题 <sub>qid 704</sub>\n\n'+body(4)+'\n\n- **A**. 选项甲答案';
  const after='## 第 4 题 <sub>qid 704</sub>\n\n'+body(4)+'\n\n- **A**. 题目缺失';
  const old=oldPaper().replace(before,after);
  assert.notEqual(old,oldPaper(), 'fixture must contain a genuine legacy option stub');
  const assembly=assemble(source(q),old);
  assert.equal(assembly.numberingStable,true);
  assert.equal(assembly.counters.inheritedStubs,1);
  const md=renderIngest(assembly,old);
  assert.match(md,/题目缺失/u);
  const grade=structureGrade(assembly,md,{dimensions:{images:{status:'complete'}}});
  assert.equal(grade.grade,'C');
  assert.ok(grade.blockers.includes('rendered-collection-stub-remains'));
});
test('option-only collection stub is C even when its stem is valid', () => {
  const q=[1,2,3,4].map(n=>makeQuestion(n,body(n)));
  q[1].options[0].contentHtml='网友未回忆起';
  const assembly=assemble(source(q),'');
  const md=renderIngest(assembly);
  const grade=structureGrade(assembly,md,{dimensions:{images:{status:'complete'}}});
  assert.equal(grade.grade,'C');
  assert.ok(grade.blockers.includes('rendered-collection-stub-remains'));
});
test('explanation-only collection stub cannot pass rendered grade A', () => {
  const q=[1,2,3,4].map(n=>makeQuestion(n,body(n)));
  q[0].explanationHtml='题目正在全力以赴征集';
  const assembly=assemble(source(q),'');
  const md=renderIngest(assembly);
  const grade=structureGrade(assembly,md,{dimensions:{images:{status:'complete'}}});
  assert.equal(grade.grade,'C');
  assert.ok(grade.blockers.includes('rendered-collection-stub-remains'));
});


test('a nonobjective view notice cannot be graded as a complete question', () => {
  const q=[1,2,3,4].map(n=>makeQuestion(n,body(n)));
  q[1].contentHtml='非客观题，请交卷后查看参考解析估分';
  const assembly=assemble(source(q),'');
  const md=renderIngest(assembly);
  const grade=structureGrade(assembly,md,{dimensions:{images:{status:'complete'}}});
  assert.equal(grade.grade,'C');
  assert.ok(grade.blockers.includes('rendered-collection-stub-remains'));
});
