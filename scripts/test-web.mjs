// Run the actual TypeScript domain module with Node's built-in test/assert API.
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
const temp=mkdtempSync(join(tmpdir(),'aegis-web-tests-'))
const req=createRequire(import.meta.url)
execFileSync(process.execPath,[resolve('node_modules/typescript/bin/tsc'),'--ignoreConfig','--module','commonjs','--target','es2022','--lib','ES2022,DOM','--skipLibCheck','--outDir',temp,'src/web/types.ts','src/web/domain.ts'],{stdio:'inherit'})
writeFileSync(join(temp,'package.json'),'{"type":"commonjs"}')
const d=req(join(temp,'domain.js')),template=JSON.parse(readFileSync('data/spatial-example.json','utf8'))
let count=0
const test=(name,fn)=>{fn();count++;console.log(`PASS ${count}: ${name}`)}
const fixture=()=>structuredClone(template)
try {
 test('empty workspace has no fabricated findings',()=>assert.deepEqual(d.checkWorkspace(d.emptyWorkspace()),[]))
 test('seed validates and contains explicitly synthetic provenance',()=>{const w=fixture();d.assertWorkspace(w);assert.equal(w.provenance,'example')})
 test('resource conflict computed from two simultaneous plans',()=>{assert(d.checkWorkspace(fixture()).some(c=>c.planId==='EXP-001'&&c.code==='CAPACITY'&&c.state==='blocked'))})
 test('unknown source is not a pass',()=>{assert(d.checkWorkspace(fixture()).some(c=>c.planId==='EXP-004'&&c.code==='SOURCE'&&c.state==='unknown'))})
 test('pending evidence does not satisfy requirements',()=>{const w=fixture();w.documents.find(d=>d.equipmentId==='A-01').status='pending';assert(d.checkWorkspace(w).some(c=>c.planId==='EXP-003'&&c.code==='EVIDENCE'&&c.state==='unknown'))})
 test('half-open intervals do not conflict at the shared boundary',()=>assert(!d.overlaps({start:'2026-10-09T09:00:00Z',end:'2026-10-09T10:00:00Z'},{start:'2026-10-09T10:00:00Z',end:'2026-10-09T11:00:00Z'})))
 test('different timezone representations compare by instant',()=>assert(d.overlaps({start:'2026-10-09T09:00:00+08:00',end:'2026-10-09T10:00:00+08:00'},{start:'2026-10-09T01:30:00Z',end:'2026-10-09T02:30:00Z'})))
 test('capacity two permits exactly two concurrent allocations',()=>{const w=fixture();w.equipment.find(e=>e.id==='F-01').capacity=2;assert(!d.checkWorkspace(w).some(c=>c.code==='CAPACITY'&&c.equipmentId==='F-01'&&c.state==='blocked'))})
 test('overlapping maintenance is a real blocker',()=>{const w=fixture();w.equipment.find(e=>e.id==='A-01').maintenance.push({id:'m',start:'2026-10-09T08:30:00+08:00',end:'2026-10-09T09:30:00+08:00',reason:'检查'});assert(d.checkWorkspace(w).some(c=>c.planId==='EXP-003'&&c.code==='AVAILABILITY'&&c.state==='blocked'))})
 test('approved evidence with wrong equipment version remains unknown',()=>{const w=fixture();const e=w.equipment.find(e=>e.id==='A-01');e.specVersion++;assert(d.checkWorkspace(w).some(c=>c.planId==='EXP-003'&&c.code==='EVIDENCE'&&c.state==='unknown'))})
 test('evidence must cover the whole reserved interval',()=>{const w=fixture();for(const doc of w.documents.filter(d=>d.equipmentId==='A-01'))doc.validUntil='2026-10-09T08:30:00+08:00';assert(d.checkWorkspace(w).some(c=>c.planId==='EXP-003'&&c.code==='EVIDENCE'&&c.state==='unknown'))})
 test('an isolated candidate does not mutate its baseline',()=>{const w=fixture(),p=w.plans[0],before=JSON.stringify(w),b={id:'b',name:'候选',planId:p.id,baseRevision:p.revision,baseBasis:d.basis(w,p),reservations:structuredClone(p.reservations),createdAt:new Date().toISOString()};b.reservations[0].equipmentId='F-02';d.candidateWorkspace(w,b);assert.equal(JSON.stringify(w),before)})
 test('replacing equipment requires reconciling the source',()=>{const w=fixture(),p=w.plans[0];p.reservations[0].equipmentId='F-02';assert(d.checkWorkspace(w).some(c=>c.planId===p.id&&c.code==='BINDING'&&c.state==='unknown'))})
 test('moving geometry does not invalidate a decision',()=>{const w=fixture(),p=w.plans[2],before=d.basis(w,p);w.equipment.find(e=>e.id==='A-01').x-=.3;assert.equal(d.basis(w,p),before)})
 test('changing resource state does invalidate a decision',()=>{const w=fixture(),p=w.plans[2],before=d.basis(w,p);w.equipment.find(e=>e.id==='A-01').status='unavailable';assert.notEqual(d.basis(w,p),before)})
 test('source lines remain exact including blank-line offsets',()=>{const w=fixture(),steps=d.parseSteps('标题\n\n  使用 F-01。\n',w.equipment);assert.equal(steps[1].line,3);assert.equal(steps[1].text,'使用 F-01。');assert.deepEqual(steps[1].equipmentIds,['F-01'])})
 test('device identifiers are not matched inside longer identifiers',()=>assert.deepEqual(d.parseSteps('使用 F-010。',fixture().equipment)[0].equipmentIds,[]))
 test('bad source locator is rejected',()=>{const w=fixture();w.plans[0].steps[0].line=999;assert.throws(()=>d.assertWorkspace(w))})
 test('cross-room resource assignments are rejected',()=>{const w=fixture();w.laboratories.push({id:'l2',name:'另一间',description:'',width:15,depth:11});w.equipment[0].labId='l2';assert.throws(()=>d.assertWorkspace(w))})
 test('negative/empty time intervals are rejected',()=>{const w=fixture();w.plans[0].reservations[0].end=w.plans[0].reservations[0].start;assert.throws(()=>d.assertWorkspace(w))})
 test('timezone-free times are rejected',()=>{const w=fixture();w.plans[0].reservations[0].start='2026-10-09T09:00:00';assert.throws(()=>d.assertWorkspace(w))})
 test('same plan cannot reserve overlapping slots for the same resource twice',()=>{const w=fixture();w.plans[0].reservations.push({...w.plans[0].reservations[0],id:'duplicate-slot'});assert.throws(()=>d.assertWorkspace(w))})
 test('local mode never creates a formal review',()=>assert.throws(()=>d.applyLocal(fixture(),{type:'approve',payload:{planId:'EXP-003',comment:'test'}})))
 test('invalid evidence status is rejected rather than coerced to verified',()=>assert.throws(()=>d.applyLocal(fixture(),{type:'verify_document',payload:{id:fixture().documents[0].id,status:'garbage'}})))
 test('task completion does not fabricate verified evidence',()=>{const w=fixture(),result=d.applyLocal(w,{type:'update_task',payload:{id:w.tasks[0].id,status:'done',note:'材料已提交'}});assert.deepEqual(result.documents,w.documents);assert.equal(result.decisions.length,0)})
 test('updated source always requires fresh confirmation',()=>{const w=fixture(),p=structuredClone(w.plans[0]);p.source+='\n新的步骤';p.steps=d.parseSteps(p.source,w.equipment).map(s=>({...s,confirmed:true}));const next=d.applyLocal(w,{type:'save_plan',payload:{plan:p,expectedPlanRevision:1}});assert(next.plans[0].steps.every(s=>!s.confirmed))})
 test('stale plan revision cannot overwrite a current record',()=>assert.throws(()=>d.applyLocal(fixture(),{type:'save_plan',payload:{plan:fixture().plans[0],expectedPlanRevision:999}})))
 test('stale branch is rejected after a resource change',()=>{let w=fixture();const p=w.plans[0],branch={id:'b',name:'候选',planId:p.id,baseRevision:p.revision,baseBasis:d.basis(w,p),reservations:structuredClone(p.reservations),createdAt:new Date().toISOString()};w=d.applyLocal(w,{type:'save_branch',payload:{branch}});w.equipment[0].status='unavailable';assert.throws(()=>d.applyLocal(w,{type:'apply_branch',payload:{id:'b'}}))})
 test('non-empty workspace cannot be replaced by example initialization',()=>assert.throws(()=>d.applyLocal(fixture(),{type:'initialize',payload:{workspace:fixture()}})))
 test('example dates shift consistently without changing the template',()=>{const before=JSON.stringify(template),shifted=d.prepareExample(template,'2026-11-01');assert.equal(Date.parse(shifted.plans[0].reservations[0].start)-Date.parse(template.plans[0].reservations[0].start),23*86400000);assert.equal(JSON.stringify(template),before)})
 if(process.argv.includes('--parity'))writeFileSync('tests/web-parity.json',JSON.stringify({basis:template.plans.map(p=>d.basis(template,p)),checks:d.checkWorkspace(template).map(c=>({id:c.id,state:c.state})),statuses:template.plans.map(p=>d.planStatus(template,p))}))
 console.log(`\n${count} browser-domain tests passed.`)
}finally{rmSync(temp,{recursive:true,force:true})}
