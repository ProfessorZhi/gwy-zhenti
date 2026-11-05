import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../driver/fenbi-enter-solution.playwright.js',import.meta.url),'utf8');
const enter=new Function('return ('+source+'\n)')();
test('refuses unrelated pages before any interaction',async()=>{
 await assert.rejects(()=>enter({url:()=> 'https://example.org/ti/exam/exercise/a'}),/Expected a Fenbi/);
});
test('an existing solution is reused without another submission',async()=>{
 const r=await enter({url:()=> 'https://spa.fenbi.com/ti/exam/solution/a',title:async()=> '试卷'});
 assert.equal(r.status,'already_solution');
});
