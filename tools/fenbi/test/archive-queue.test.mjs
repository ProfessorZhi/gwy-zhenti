import test from 'node:test';
import assert from 'node:assert/strict';
import {runQueue} from '../driver/archive-queue.mjs';
test('parallelizes separate sessions but preserves order and exclusivity within each session',async()=>{
 const active=new Set(),order=[],jobs=[{session:'a',id:1},{session:'b',id:2},{session:'a',id:3}];let peak=0;
 await runQueue(jobs,2,async j=>{assert.ok(!active.has(j.session));active.add(j.session);peak=Math.max(peak,active.size);order.push(j.id);await new Promise(r=>setTimeout(r,15));active.delete(j.session)});
 assert.equal(peak,2);assert.ok(order.indexOf(1)<order.indexOf(3));
});
test('bounds concurrency and supports an empty queue',async()=>{
 await assert.rejects(()=>runQueue([],0,async()=>{}),/concurrency/);
 await assert.rejects(()=>runQueue([],5,async()=>{}),/concurrency/);
 await runQueue([],2,async()=>{throw new Error('unexpected')});
});
