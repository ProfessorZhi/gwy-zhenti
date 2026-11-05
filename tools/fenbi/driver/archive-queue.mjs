/** A session owns one navigation stream; only separate sessions can run concurrently. */
export async function runQueue(jobs, concurrency, execute) {
 if(!Number.isInteger(concurrency)||concurrency<1||concurrency>4)throw new Error('concurrency must be 1..4');
 const groups=new Map();for(const job of jobs){if(!groups.has(job.session))groups.set(job.session,[]);groups.get(job.session).push(job)}
 const queue=[...groups.values()];let next=0;
 await Promise.all(Array.from({length:Math.min(concurrency,queue.length)},async()=>{
  while(next<queue.length){const group=queue[next++];for(const job of group)await execute(job)}
 }));
}
