import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareArchive } from '../driver/archive-loaded.mjs';

const input = {url:'https://v.huatu.com/tiku/analysis/123?token=secret',title:'测试卷',html:'<div class="exercise-main-topic" id="question1"><div class="main-topic-stem">测试题</div><div class="jiexi-answers">正确答案：A</div><img src="https://img.huatu.com/a.png"><script>secret</script><div class="videoAnalysis" data-token="secret">视频</div></div>'};
test('archives question evidence, removes script and credentials, preserves image mapping',()=>{
 const a=prepareArchive(input,'huatu','测试卷');
 assert.equal(a.questionCount,1);assert.equal(a.answerBlockCount,1);
 assert.equal(a.url,'https://v.huatu.com/tiku/analysis/123');
 assert.ok(!a.html.includes('secret'));assert.deepEqual(a.imageUrls,['https://img.huatu.com/a.png']);
});
test('practice page cannot be reported as answers archived',()=>{
 const a=prepareArchive({...input,url:'https://spa.fenbi.com/ti/exam/exercise/example',html:'<app-tis><app-ti>题目</app-ti></app-tis>'},'fenbi','测试卷');
 assert.equal(a.answerBlockCount,0);assert.equal(a.answerStatus,'not_present');
});
test('rejects wrong title and empty capture rather than reporting success',()=>{
 assert.throws(()=>prepareArchive(input,'huatu','另一份卷'),/title/);
 assert.throws(()=>prepareArchive({...input,html:''},'huatu','测试卷'),/questions/);
});
test('source placeholders remain explicit and are not counted as available answers',()=>{
 const a=prepareArchive({...input,html:'<div class="exercise-main-topic" id="question18"><div class="main-topic-stem">（占位题）</div></div>'},'huatu','测试卷');
 assert.equal(a.placeholderCount,1);assert.equal(a.answerBlockCount,0);
});
