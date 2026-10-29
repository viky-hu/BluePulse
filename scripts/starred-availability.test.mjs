import assert from 'node:assert/strict';
import { test } from 'node:test';
const api = await import('../src/app/starred/availability.ts').catch(() => null);
test('availability requires exact unique coverage and consistent explicit permissions', () => {
  assert.ok(api);
  assert.deepEqual(api.parseAvailability({items:[{id:'a',available:true},{id:'b',available:false}]}, ['a','b']), {a:{status:'public'},b:{status:'unavailable'}});
  assert.throws(() => api.parseAvailability({items:[{id:'a',available:true},{id:'a',available:true}]}, ['a','b']));
  assert.throws(() => api.parseAvailability({items:[{id:'a',available:false,status:'summary-only'}]}, ['a']));
  assert.deepEqual(api.parseAvailability({items:[{id:'a',available:true,status:'summary-only',source_name:'现名'}]}, ['a']), {a:{status:'summary-only',sourceName:'现名'}});
  assert.throws(() => api.parseAvailability({items:[]}, ['a']));
});
test('independent batches preserve successes when another batch fails', async () => {
  assert.ok(api);
  const ids=Array.from({length:101},(_,i)=>String(i));
  const requests=[];
  const result=await api.loadAvailability(ids, new AbortController().signal, async (url, options)=>{
    requests.push([url,options]);
    const batch=new URL(url,'https://pulse.local').searchParams.get('ids').split(',');
    if(batch.includes('100')) throw Error('offline');
    return {ok:true,json:async()=>({items:batch.map(id=>({id,available:true}))})};
  });
  assert.equal(requests.length,2);
  assert.equal(requests[0][1].cache,'no-store');
  assert.equal(Object.keys(result.items).length,100);
  assert.equal(result.error,true);
  assert.equal(result.items['100'],undefined);
});
