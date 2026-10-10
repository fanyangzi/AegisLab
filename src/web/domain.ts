import type { Workspace, Plan, Check, Operation, Equipment, DocumentRecord, Task, Branch, Laboratory } from './types'
import { uid, kindNames, equipmentFamilies, evidenceKinds } from './types'

export const RULE_PACK = 'resource-prerequisites/1.0'
export const emptyWorkspace = (): Workspace => ({ schemaVersion: 1, revision: 0, name: '我的实验工作区', provenance: 'user', laboratories: [], equipment: [], plans: [], documents: [], tasks: [], decisions: [], events: [], branches: [] })
export const taskTransitions: Record<Task['status'], readonly Task['status'][]> = {
  open: ['open', 'submitted', 'done', 'cancelled'],
  submitted: ['submitted', 'done', 'returned', 'cancelled'],
  returned: ['returned', 'reopened', 'cancelled'],
  reopened: ['reopened', 'submitted', 'done', 'cancelled'],
  done: ['done', 'reopened'],
  cancelled: ['cancelled', 'reopened'],
}
export const millis = (value: string) => Date.parse(value)
export const overlaps = (a: { start: string; end: string }, b: { start: string; end: string }) => millis(a.start) < millis(b.end) && millis(b.start) < millis(a.end)
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value !== null && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`
  return JSON.stringify(value)
}
/** Fingerprint of decision-relevant facts, not of camera position or UI selection. */
export function basis(workspace: Workspace, plan: Plan): string {
  const reservations = plan.reservations.map(r => ({ ...r })).sort((a, b) => `${a.equipmentId}|${a.start}|${a.end}|${a.id}`.localeCompare(`${b.equipmentId}|${b.start}|${b.end}|${b.id}`))
  const ids = new Set(reservations.map(r => r.equipmentId))
  const relevant = (a: {start: string; end: string}, b: {start: string; end: string}) => overlaps(a, b)
  const equipment = workspace.equipment.filter(e => ids.has(e.id)).map(e => ({
    id: e.id, labId: e.labId, kind: e.kind, status: e.status, capacity: e.capacity,
    requiresEvidence: e.requiresEvidence, specVersion: e.specVersion,
    maintenance: e.maintenance.filter(m => reservations.filter(r => r.equipmentId === e.id).some(r => relevant(m, r))).sort((a, b) => `${a.start}|${a.end}|${a.id}`.localeCompare(`${b.start}|${b.end}|${b.id}`)),
  })).sort((a, b) => a.id.localeCompare(b.id))
  const documents = workspace.documents.filter(d => {
    if (!d.equipmentId || !ids.has(d.equipmentId)) return false
    if (d.kind !== 'inspection') return true
    return reservations.some(r => relevant({ start: d.validFrom, end: d.validUntil }, r))
  }).map(d => ({ id: d.id, equipmentId: d.equipmentId, kind: d.kind, specVersion: d.specVersion, status: d.status, validFrom: d.validFrom, validUntil: d.validUntil, content: d.content, source: d.source, reviewedBy: d.reviewedBy, reviewedAt: d.reviewedAt })).sort((a, b) => `${a.equipmentId ?? ''}|${a.kind}|${a.id}`.localeCompare(`${b.equipmentId ?? ''}|${b.kind}|${b.id}`))
  const otherReservations = workspace.plans.filter(p => p.id !== plan.id && !p.archived && p.lifecycle !== 'cancelled').flatMap(p => p.reservations.filter(r => ids.has(r.equipmentId) && reservations.some(current => relevant(r, current))).map(r => ({ planId: p.id, ...r }))).sort((a, b) => `${a.equipmentId}|${a.start}|${a.end}|${a.planId}|${a.id}`.localeCompare(`${b.equipmentId}|${b.start}|${b.end}|${b.planId}|${b.id}`))
  const planFacts = { id: plan.id, labId: plan.labId, revision: plan.revision, sourceName: plan.sourceName, source: plan.source, steps: plan.steps.map(({ id, text, line, equipmentIds, confirmed }) => ({ id, text, line, equipmentIds, confirmed })).sort((a, b) => a.line - b.line || a.id.localeCompare(b.id)), reservations }
  return canonical({ rulePack: RULE_PACK, plan: planFacts, equipment, documents, otherReservations })
}
export function parseSteps(source: string, equipment: Equipment[]) {
  return source.split(/\r?\n/).map((raw, index) => ({ raw, index })).filter(({ raw }) => raw.trim()).map(({ raw, index }) => ({ id: uid('step'), text: raw.trim(), line: index + 1, confirmed: false, equipmentIds: equipment.filter(e => new RegExp(`(^|[^A-Za-z0-9_-])${e.code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_-])`).test(raw)).map(e => e.id) }))
}
export function checkWorkspace(w: Workspace): Check[] {
  const all: Check[] = []
  for (const p of w.plans.filter(p => !p.archived && p.lifecycle !== 'cancelled')) {
    const add = (code: string, state: Check['state'], title: string, detail: string, equipmentId: string | null = null, relatedPlanIds: string[] = [], documentIds: string[] = []) => all.push({ id: `${p.id}:${code}:${equipmentId ?? 'plan'}`, planId: p.id, code, state, title, detail, equipmentId, relatedPlanIds, documentIds, line: equipmentId ? p.steps.find(s => s.equipmentIds.includes(equipmentId))?.line ?? null : null })
    const confirmed = p.steps.length > 0 && p.steps.every(s => s.confirmed)
    add('SOURCE', confirmed ? 'pass' : 'unknown', confirmed ? '原文与步骤已确认' : '步骤提取需要人工确认', confirmed ? `${p.steps.length} 个步骤绑定到原文行号。` : '请核对原文、步骤及设备匹配；机器提取不代表事实已确认。')
    if (!p.reservations.length) add('SCHEDULE', 'unknown', '尚未设置资源使用时段', '设备、开始和结束时间是资源核验的必要输入。')
    const eqIds = [...new Set(p.reservations.map(r => r.equipmentId))]
    for (const id of new Set(p.steps.flatMap(step => step.equipmentIds))) if (!eqIds.includes(id)) add('BINDING', 'unknown', '原文设备与预约尚未对齐', '步骤引用的设备没有对应预约。更换资源后须修订原文并重新确认，不能只替换画面中的连线。', id)
    for (const id of eqIds) {
      const e = w.equipment.find(e => e.id === id)
      if (!e) { add('RESOURCE', 'unknown', '资源不存在', '重新绑定有效资源。', id); continue }
      const reservations = p.reservations.filter(r => r.equipmentId === id)
      const maintenance = e.status === 'unavailable' || reservations.some(r => e.maintenance.some(m => overlaps(r, m)))
      add('AVAILABILITY', maintenance ? 'blocked' : e.status === 'unknown' ? 'unknown' : 'pass', maintenance ? `${e.code} 在预约范围内不可用` : e.status === 'unknown' ? `${e.code} 的台账状态待确认` : `${e.code} 的预约不冲突于维护`, maintenance ? '当前停用状态或维护窗口与使用计划交叠；需更换资源或调整时段。' : '仅依据已登记的台账与维护窗口；不代表现场传感器状态。', id)
      const assigned = w.plans.filter(q => !q.archived && q.lifecycle !== 'cancelled').flatMap(q => q.reservations.filter(r => r.equipmentId === id).map(r => ({ ...r, planId: q.id })))
      let conflicts = new Set<string>()
      for (const r of reservations) {
        const active = assigned.filter(a => overlaps(a, r))
        const points = [...new Set([millis(r.start), ...active.map(a => Math.max(millis(r.start), millis(a.start)))])]
        for (const point of points) {
          const at = active.filter(a => millis(a.start) <= point && point < millis(a.end))
          if (at.length > e.capacity) at.forEach(a => { if (a.planId !== p.id) conflicts.add(a.planId) })
        }
      }
      add('CAPACITY', conflicts.size ? 'blocked' : 'pass', conflicts.size ? `${e.code} 超出并发使用容量` : `${e.code} 的资源容量已满足`, conflicts.size ? `登记容量为 ${e.capacity}；与 ${[...conflicts].join('、')} 同时占用。` : `当前使用安排未超出登记容量 ${e.capacity}。相邻时段按半开区间计算。`, id, [...conflicts])
      if (e.requiresEvidence) {
        const docs = w.documents.filter(d => d.equipmentId === id && d.kind === 'inspection')
        const valid = docs.filter(d => d.status === 'verified' && d.specVersion === e.specVersion)
        const covered = reservations.every(r => valid.some(d => millis(d.validFrom) <= millis(r.start) && millis(d.validUntil) >= millis(r.end)))
        const evidenceApplicability = docs.map(d => ({ documentId: d.id, state: d.status !== 'verified' ? 'candidate' as const : d.specVersion !== e.specVersion ? 'mismatched' as const : reservations.some(r => millis(d.validFrom) <= millis(r.start) && millis(d.validUntil) >= millis(r.end)) ? 'supports' as const : 'expired' as const, specVersion: d.specVersion, validFrom: d.validFrom, validUntil: d.validUntil }))
        const check = { id: `${p.id}:EVIDENCE:${id}`, planId: p.id, code: 'EVIDENCE', state: covered ? 'pass' as const : 'unknown' as const, title: covered ? `${e.code} 的检查证据适用` : `${e.code} 缺少适用的检查证据`, detail: covered ? '对象、规格版本、核验状态与全部使用时段均匹配。' : '需要已核验且覆盖整个使用时段的记录；上传、过期、其他设备的记录都不能代替。', equipmentId: id, relatedPlanIds: [] as string[], documentIds: docs.map(d => d.id), line: p.steps.find(s => s.equipmentIds.includes(id))?.line ?? null, evidenceApplicability }
        all.push(check)
      }
    }
  }
  return all
}
export function planStatus(w: Workspace, p: Plan, checks: Check[] = checkWorkspace(w)): string {
  if (p.archived) return 'archived'
  if (p.lifecycle === 'cancelled') return 'cancelled'
  const decision = w.decisions.filter(d => d.planId === p.id).at(-1)
  if (decision && decision.basis !== basis(w, p)) return 'recheck'
  if (!p.steps.length || p.steps.some(s => !s.confirmed)) return 'draft'
  const relevant = checks.filter(c => c.planId === p.id)
  if (relevant.some(c => c.state === 'blocked')) return 'blocked'
  if (relevant.some(c => c.state === 'unknown')) return 'unknown'
  return decision ? 'approved' : 'ready'
}
export function assertWorkspace(w: Workspace): void {
  const fail = (message: string) => { throw new Error(message) }
  if (!w || w.schemaVersion !== 1 || !Number.isSafeInteger(w.revision) || w.revision < 0) fail('工作区版本不受支持。')
  for (const collection of [w.laboratories, w.equipment, w.plans, w.documents, w.tasks, w.decisions, w.events, w.branches]) {
    if (!Array.isArray(collection) || collection.length > 5000) fail('工作区列表无效或超出当前容量。')
    const ids = collection.map(x => x.id)
    if (new Set(ids).size !== ids.length || ids.some(id => typeof id !== 'string' || !id || id.length > 128)) fail('对象 ID 必须唯一且有效。')
  }
  const interval = (a: string, b: string) => { if (!/(Z|[+-]\d{2}:\d{2})$/.test(a) || !/(Z|[+-]\d{2}:\d{2})$/.test(b) || !Number.isFinite(millis(a)) || !Number.isFinite(millis(b)) || millis(a) >= millis(b)) fail('结束时间必须晚于开始时间。') }
  const labIds = new Set(w.laboratories.map(l => l.id)), eqIds = new Set(w.equipment.map(e => e.id)), planIds = new Set(w.plans.map(p => p.id))
  for (const l of w.laboratories) if (!l.name?.trim() || !Number.isFinite(l.width) || !Number.isFinite(l.depth) || l.width < 6 || l.width > 40 || l.depth < 6 || l.depth > 40) fail('实验室名称或尺寸无效。')
  for (const e of w.equipment) {
    if (!labIds.has(e.labId) || !e.name?.trim() || !e.code?.trim() || !(e.kind in kindNames) || !['available','unavailable','unknown'].includes(e.status)) fail('设备资料不完整。')
    if (e.family && !equipmentFamilies.includes(e.family)) fail('设备领域分类无效。')
    if (e.evidenceKinds?.some(kind => !evidenceKinds.includes(kind))) fail('设备证据类型无效。')
    if (e.hazardTags && e.hazardTags.length > 30 || e.controlTags && e.controlTags.length > 40) fail('设备风险或控制标签过多。')
    if (![e.x,e.z,e.rotation,e.specVersion].every(Number.isFinite) || !Number.isInteger(e.capacity) || e.capacity < 1 || e.capacity > 100 || e.specVersion < 1) fail('设备坐标、容量或规格版本无效。')
    const l = w.laboratories.find(l => l.id === e.labId)!
    if (Math.abs(e.x) > l.width / 2 - 0.5 || Math.abs(e.z) > l.depth / 2 - 0.5) fail('设备位置超出实验室边界。')
    if (w.equipment.filter(q => q.labId === e.labId && q.code === e.code).length > 1) fail('同一实验室内设备编号不能重复。')
    e.maintenance.forEach(m => interval(m.start,m.end))
  }
  for (const p of w.plans) {
    if (!labIds.has(p.labId) || !p.name?.trim() || !p.owner?.trim() || !p.source?.trim() || p.source.length > 100000) fail('计划名称、负责人、实验室和原文为必填项。')
    if (!Number.isSafeInteger(p.revision) || p.revision < 1 || !Array.isArray(p.steps) || p.steps.length > 500) fail('计划步骤或版本无效。')
    const lines = p.source.split(/\r?\n/)
    for (const s of p.steps) if (!Number.isInteger(s.line) || !lines[s.line - 1] || lines[s.line - 1].trim() !== s.text || s.equipmentIds.some(id => w.equipment.find(e => e.id === id)?.labId !== p.labId)) fail('步骤必须准确引用原文，不得编造行号。')
    for (const r of p.reservations) { interval(r.start,r.end); if (w.equipment.find(e => e.id === r.equipmentId)?.labId !== p.labId) fail('预约设备必须属于当前实验室。') }
    if (p.reservations.some((r,i) => p.reservations.slice(i+1).some(b => b.equipmentId === r.equipmentId && overlaps(r,b)))) fail('同一计划不能重复占用同一资源的重叠时段。')
  }
  for (const d of w.documents) { if (!d.name?.trim() || !d.content?.trim() || !d.source?.trim() || d.content.length > 200000 || (d.equipmentId !== null && !eqIds.has(d.equipmentId))) fail('资料名称、来源、内容或关联对象无效。'); interval(d.validFrom,d.validUntil) }
  for (const t of w.tasks) if (!t.title?.trim() || !t.owner?.trim() || !Number.isFinite(millis(t.dueAt)) || !Object.prototype.hasOwnProperty.call(taskTransitions, t.status) || (t.planId !== null && !planIds.has(t.planId)) || (t.equipmentId !== null && !eqIds.has(t.equipmentId))) fail('任务标题、负责人、期限或关联对象无效。')
  if (JSON.stringify(w).length > 5_000_000) fail('工作区超过当前容量，请先归档。')
}
export function prepareExample(template: Workspace, date: string): Workspace {
  const delta = millis(`${date}T00:00:00+08:00`) - millis('2026-10-09T00:00:00+08:00')
  const shifted = JSON.parse(JSON.stringify(template).replace(/2026-\d\d-\d\dT\d\d:\d\d:\d\d\+08:00/g, match => new Date(millis(match) + delta).toISOString())) as Workspace
  assertWorkspace(shifted)
  return shifted
}
export function candidateWorkspace(w: Workspace, branch: Branch): Workspace {
  const next = structuredClone(w)
  const p = next.plans.find(p => p.id === branch.planId)
  if (!p) throw new Error('计划不存在。')
  p.reservations = structuredClone(branch.reservations)
  assertWorkspace(next)
  return next
}
/** Local draft mutations. Authoritative approval is deliberately server-only. */
export function applyLocal(w: Workspace, op: Operation): Workspace {
  let next = structuredClone(w)
  const x = op.payload as any
  let objectId = x.id || x.planId || 'workspace', summary = ''
  const upsert = <T extends {id: string}>(items: T[], value: T) => { const index = items.findIndex(i => i.id === value.id); if (index >= 0) items[index] = value; else items.push(value) }
  switch (op.type) {
    case 'initialize': {
      if ([w.laboratories,w.plans,w.equipment,w.documents,w.tasks,w.decisions,w.branches].some(items=>items.length)) throw new Error('已有数据的工作区不能被初始化覆盖。')
      next = structuredClone(x.workspace)
      next.decisions = []; next.events = []; next.branches = []
      summary = next.provenance === 'example' ? '导入明确标记的样例工作区' : '建立空白工作区'
      break
    }
    case 'save_lab': upsert(next.laboratories, x.lab as Laboratory); objectId=x.lab.id; summary='保存实验室资料'; break
    case 'save_equipment': {
      const e = structuredClone(x.equipment) as Equipment, previous = next.equipment.find(q => q.id === e.id)
      e.specVersion = previous ? previous.specVersion + Number(previous.kind !== e.kind || previous.capacity !== e.capacity || previous.requiresEvidence !== e.requiresEvidence) : 1
      upsert(next.equipment,e); objectId=e.id; summary=`更新资源 ${e.code}，核验依赖同步重算`; break
    }
    case 'save_plan': {
      const p=structuredClone(x.plan) as Plan, prev=next.plans.find(q=>q.id===p.id)
      if (prev && prev.revision !== x.expectedPlanRevision) throw new Error('计划已变更，请重新载入后保存。')
      if (prev?.archived && !p.archived) throw new Error('已归档计划只能引用或复制，不能直接复活为当前计划。')
      p.revision=prev ? prev.revision+1 : 1
      if (prev && prev.source !== p.source) { p.steps.forEach(s=>s.confirmed=false); p.lifecycle='revising' }
      else if (prev) p.lifecycle=prev.lifecycle || 'draft'
      else p.lifecycle=p.lifecycle || 'draft'
      if (p.lifecycle === 'submitted' && (!p.steps.length || p.steps.some(s=>!s.confirmed))) throw new Error('计划提交前必须完成全部步骤的人工确认。')
      if (p.archived) {
        if (!p.steps.length || p.steps.some(s=>!s.confirmed)) throw new Error('计划归档前必须完成全部步骤的人工确认。')
        const candidate=structuredClone(next), candidatePlan=candidate.plans.find(q=>q.id===p.id)
        if (candidatePlan) Object.assign(candidatePlan,structuredClone(p)); else candidate.plans.push(structuredClone(p))
        const checkedPlan=candidate.plans.find(q=>q.id===p.id)!; checkedPlan.archived=false; checkedPlan.lifecycle='submitted'
        const candidateChecks=checkWorkspace(candidate).filter(c=>c.planId===p.id)
        if (!candidateChecks.length || candidateChecks.some(c=>c.state!=='pass')) throw new Error('计划仍有阻断或未知项，不能归档。')
        const decisions=next.decisions.filter(d=>d.planId===p.id)
        if (decisions.length && decisions.at(-1)!.basis !== basis(candidate,checkedPlan)) throw new Error('当前计划基线与最近复核不一致，请先重新复核后归档。')
        p.lifecycle='archived'
      } else if (p.lifecycle === 'archived') throw new Error('归档生命周期必须同时设置 archived=true。')
      upsert(next.plans,p); objectId=p.id; summary=`保存计划 ${p.code} · v${p.revision}`; break
    }
    case 'confirm_steps': { const p=next.plans.find(p=>p.id===x.planId); if (!p || !p.steps.length) throw new Error('计划不存在或没有可确认的步骤'); p.steps.forEach(s=>s.confirmed=true); p.revision++; summary='人工核对原文与全部步骤'; break }
    case 'transition_plan': {
      const p=next.plans.find(p=>p.id===x.planId), requested=x.lifecycle as Plan['lifecycle']
      if (!p || !requested || !['draft','submitted','revising','archived','cancelled'].includes(requested)) throw new Error('计划生命周期无效。')
      const current=(p.archived?'archived':p.lifecycle||'draft') as NonNullable<Plan['lifecycle']>
      const transitions:Record<NonNullable<Plan['lifecycle']>,NonNullable<Plan['lifecycle'][]>>={draft:['draft','submitted','cancelled'],submitted:['submitted','revising','cancelled','archived'],revising:['revising','submitted','cancelled'],cancelled:['cancelled'],archived:['archived']}
      if (!transitions[current].includes(requested)) throw new Error(`计划不能从“${current}”流转到“${requested}”。`)
      if (requested==='submitted') { if (!p.steps.length || p.steps.some(s=>!s.confirmed)) throw new Error('计划提交前必须完成全部步骤的人工确认。'); p.lifecycle='submitted'; summary='提交当前计划版本，等待资源与证据复核' }
      else if (requested==='revising') { p.lifecycle='revising'; summary='打开计划修订状态；正式版本未被候选覆盖' }
      else if (requested==='cancelled') { p.lifecycle='cancelled'; p.archived=false; summary='取消计划；保留历史记录且不再参与当前资源检查' }
      else if (requested==='archived') {
        if (!p.steps.length || p.steps.some(s=>!s.confirmed)) throw new Error('计划归档前必须完成全部步骤的人工确认。')
        const candidate=structuredClone(next), candidatePlan=candidate.plans.find(q=>q.id===p.id)!; candidatePlan.archived=false; candidatePlan.lifecycle='submitted'
        const candidateChecks=checkWorkspace(candidate).filter(c=>c.planId===p.id)
        if (!candidateChecks.length || candidateChecks.some(c=>c.state!=='pass')) throw new Error('计划仍有阻断或未知项，不能归档。')
        const decisions=next.decisions.filter(d=>d.planId===p.id)
        if (decisions.length && decisions.at(-1)!.basis !== basis(candidate,candidatePlan)) throw new Error('当前计划基线与最近复核不一致，请先重新复核后归档。')
        p.lifecycle='archived'; p.archived=true; summary='归档当前计划版本；历史依据仍可追溯，不能直接复活'
      } else { p.lifecycle=requested; summary='更新计划生命周期' }
      break
    }
    case 'save_document': {
      const d=structuredClone(x.document) as DocumentRecord
      d.status='pending'; d.reviewedAt=null; d.reviewedBy=null
      upsert(next.documents,d); objectId=d.id; summary='提交资料，等待独立核验'; break
    }
    case 'verify_document': {
      const d=next.documents.find(d=>d.id===x.id); if (!d) throw new Error('资料不存在')
      if (!['verified','rejected'].includes(x.status)) throw new Error('资料核验状态无效。'); d.status=x.status; d.reviewedAt=new Date().toISOString(); d.reviewedBy='本机操作者'
      summary=d.status==='verified'?'记录资料核验结果':'退回资料'; break
    }
    case 'save_task': { const task=structuredClone(x.task) as Task; if (task.sourceId && task.actionKind && next.tasks.some(existing => existing.id!==task.id && existing.planId===task.planId && existing.sourceId===task.sourceId && existing.sourceLine===task.sourceLine && existing.actionKind===task.actionKind && ['open','submitted','returned','reopened'].includes(existing.status))) throw new Error('该 AI 建议已有未完成任务，请打开原任务继续处理。'); upsert(next.tasks,task); objectId=task.id; summary='创建协作任务'; break }
    case 'update_task': {
      const t=next.tasks.find(t=>t.id===x.id), requested=x.status as Task['status']
      if (!t || !Object.prototype.hasOwnProperty.call(taskTransitions, requested)) throw new Error('任务状态无效')
      if (!taskTransitions[t.status].includes(requested)) throw new Error(`任务不能从“${t.status}”流转到“${requested}”。`)
      const note=String(x.note ?? t.note).trim()
      if (['returned','cancelled','reopened'].includes(requested) && !note) throw new Error('退回、取消或重开任务必须填写处理说明。')
      t.status=requested; t.note=note
      summary=({returned:'退回补充',cancelled:'取消任务',reopened:'重新打开'} as Record<string,string>)[requested] ? `${({returned:'退回补充',cancelled:'取消任务',reopened:'重新打开'} as Record<string,string>)[requested]}；不自动改变证据或审批` : '更新任务进度，不自动改变证据或审批'
      break
    }
    case 'save_branch': {
      const b=x.branch as Branch; const p=next.plans.find(p=>p.id===b.planId)
      if (!p || p.revision!==b.baseRevision || basis(next,p)!==b.baseBasis) throw new Error('方案基线已变化，请以当前计划重新创建。')
      candidateWorkspace(next,b); upsert(next.branches,b); objectId=b.id; summary='保存独立候选方案，正式计划未改变'; break
    }
    case 'apply_branch': {
      const b=next.branches.find(b=>b.id===x.id), p=next.plans.find(p=>p.id===b?.planId)
      if (!b || !p || p.revision!==b.baseRevision || basis(next,p)!==b.baseBasis) throw new Error('方案已过期：计划、资源或证据发生变化，请重新比较。')
      p.reservations=structuredClone(b.reservations); p.revision++; objectId=p.id; summary=`应用方案「${b.name}」，产生新修订并触发重新复核`; break
    }
    case 'approve': throw new Error('浏览器草稿不记录正式复核。请连接服务端 API，由服务器核验最新版本。')
    default: throw new Error('不支持的操作。')
  }
  next.revision=w.revision+1
  next.events.push({id:uid('event'),at:new Date().toISOString(),actor:'本机操作者',action:op.type,objectId,summary})
  assertWorkspace(next)
  return next
}
