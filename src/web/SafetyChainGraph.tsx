import { useMemo, useState } from 'react'
import type { Check, Selection, Snapshot } from './types'
import { kindNames } from './types'
import { Icon, dateText, toneFor } from './ui'
import { profileForKind } from './equipmentTaxonomy'
import './safetyChainGraph.css'

type ChainNodeType = 'plan' | 'step' | 'chemical' | 'equipment' | 'control' | 'rule' | 'document' | 'task' | 'approval'
type ChainNode = {
  id: string; label: string; code: string; type: ChainNodeType; icon: string; state: string
  lane: number; index: number; detail: string; selection?: NonNullable<Selection>
}
type ChainEdge = { from: string; to: string; label: string; description: string; bad?: boolean }

/** Terms used only to locate candidate material mentions in the plan source. */
const CHEMICAL_TERMS = ['乙酸乙酯', '二氯甲烷', '乙酸铵', '氢氧化钠', '浓硫酸', '正己烷', '乙腈', '甲醇', '甲苯', '丙酮', '乙醇', '硫酸', '盐酸', '氮气', '氩气', '氢气', '氧气', '冰醋酸', '甲酸', '水']
const unique = (items: string[]) => [...new Set(items.filter(Boolean))]
function chemicalsFrom(source: string) {
  return CHEMICAL_TERMS.filter(term => source.includes(term)).filter((term, index, items) => !items.some((other, otherIndex) => otherIndex !== index && other.includes(term)))
}
function statusForChecks(checks: Check[]) {
  return checks.some(c => c.state === 'blocked') ? 'blocked' : checks.some(c => c.state === 'unknown') ? 'unknown' : 'pass'
}

export interface SafetyChainGraphProps {
  snapshot: Snapshot
  labId: string
  selection: Selection
  onSelect: (selection: Selection) => void
  all?: boolean
}

/**
 * A traceable, read-only projection of the current workspace. It deliberately
 * does not invent persistent entities: chemicals and controls are candidates
 * derived from plan text and equipment profiles until a reviewer confirms them.
 */
export function SafetyChainGraph({ snapshot, labId, selection, onSelect, all = false }: SafetyChainGraphProps) {
  const [insight, setInsight] = useState('点击节点或关系线，查看这条安全链路的含义。')
  const w = snapshot.workspace
  const graph = useMemo(() => {
    const labPlans = w.plans.filter(p => !p.archived && p.labId === labId)
    const selectedPlanId = selection?.type === 'plan' ? selection.id : null
    const equipmentFocus = selection?.type === 'equipment' ? selection.id : null
    const taskFocus = selection?.type === 'task' ? w.tasks.find(t => t.id === selection.id)?.planId : null
    const documentFocus = selection?.type === 'document' ? w.documents.find(d => d.id === selection.id)?.equipmentId : null
    const focused = labPlans.filter(p => p.id === selectedPlanId || p.id === taskFocus || p.reservations.some(r => r.equipmentId === equipmentFocus || r.equipmentId === documentFocus))
    const plans = (all ? (focused.length ? focused : labPlans) : (focused.length ? focused : labPlans)).slice(0, all ? 3 : 1)
    const lanes: ChainNode[][] = Array.from({ length: 9 }, () => [])
    const edges: ChainEdge[] = []
    const add = (node: Omit<ChainNode, 'index'>) => {
      const full = { ...node, index: lanes[node.lane].length }
      lanes[node.lane].push(full)
      return full
    }
    const link = (from: ChainNode, to: ChainNode, label: string, description: string, bad = false) => edges.push({ from: from.id, to: to.id, label, description, bad })

    plans.forEach(plan => {
      const planChecks = snapshot.checks.filter(c => c.planId === plan.id)
      const planEquipment = w.equipment.filter(e => plan.reservations.some(r => r.equipmentId === e.id) || plan.steps.some(s => s.equipmentIds.includes(e.id)))
      const equipmentIds = new Set(planEquipment.map(e => e.id))
      const planDocs = w.documents.filter(d => (d.equipmentId !== null && equipmentIds.has(d.equipmentId)) || planChecks.some(c => c.documentIds.includes(d.id))).slice(0, 5)
      const planTasks = w.tasks.filter(t => t.planId === plan.id || (t.equipmentId !== null && equipmentIds.has(t.equipmentId))).slice(0, 4)
      const planNode = add({ id: `chain-plan-${plan.id}`, label: plan.name, code: plan.code, type: 'plan', icon: 'flask', state: snapshot.statuses[plan.id] || 'unknown', lane: 0, detail: `计划 v${plan.revision} · ${plan.owner}`, selection: { type: 'plan', id: plan.id } })
      const stepNodes = plan.steps.slice(0, 6).map((step, index) => add({ id: `chain-step-${plan.id}-${step.id}`, label: step.text, code: `步骤 ${index + 1} · 原文 L${step.line}`, type: 'step', icon: 'plans', state: step.confirmed ? 'pass' : 'unknown', lane: 1, detail: step.confirmed ? '已人工确认原文' : '待人工确认原文' }))
      const chemicalNames = chemicalsFrom(plan.source).slice(0, 6)
      const chemicalNodes = (chemicalNames.length ? chemicalNames : ['原文未声明化学品']).map((name, index) => add({ id: `chain-chemical-${plan.id}-${index}`, label: name, code: chemicalNames.length ? '原文识别' : '需人工确认', type: 'chemical', icon: 'flask', state: 'unknown', lane: 2, detail: chemicalNames.length ? '来自计划原文，需关联 SDS 与相容性' : '计划原文没有识别到可核验物料' }))
      const equipmentNodes = planEquipment.slice(0, 7).map(e => add({ id: `chain-equipment-${plan.id}-${e.id}`, label: e.name, code: e.code, type: 'equipment', icon: 'resources', state: statusForChecks(planChecks.filter(c => c.equipmentId === e.id)), lane: 3, detail: `${kindNames[e.kind]} · ${e.status === 'available' ? '登记可用' : e.status === 'unknown' ? '台账待确认' : '登记停用'}`, selection: { type: 'equipment', id: e.id } }))
      const controls = unique(planEquipment.flatMap(e => (e.profile?.controlTags || e.controlTags || profileForKind(e.kind).controlTags))).slice(0, 6)
      const controlNodes = (controls.length ? controls : ['关联当前 SOP、设备状态与工程控制']).map((control, index) => add({ id: `chain-control-${plan.id}-${index}`, label: control, code: '控制措施', type: 'control', icon: 'shield', state: 'unknown', lane: 4, detail: '由设备运行画像与当前计划共同提出，需按机构 SOP 核验' }))
      const ruleNodes = planChecks.length ? planChecks.slice(0, 6).map(check => add({ id: `chain-rule-${plan.id}-${check.id}`, label: check.title, code: check.code, type: 'rule', icon: 'alert', state: check.state, lane: 5, detail: check.detail })) : [add({ id: `chain-rule-${plan.id}-pack`, label: '当前规则包待运行', code: '规则核验', type: 'rule', icon: 'alert', state: 'unknown', lane: 5, detail: '尚未生成计划级检查结果' })]
      const evidenceNodes = planDocs.length ? planDocs.map(doc => add({ id: `chain-evidence-${plan.id}-${doc.id}`, label: doc.name, code: doc.status === 'verified' ? '已核验' : '待核验', type: 'document', icon: 'file', state: doc.status, lane: 6, detail: `${doc.source} · 有效至 ${dateText(doc.validUntil)}`, selection: { type: 'document', id: doc.id } })) : [add({ id: `chain-evidence-${plan.id}-missing`, label: '待补充适用证据', code: '证据缺口', type: 'document', icon: 'file', state: 'unknown', lane: 6, detail: '当前计划没有足够的对象、版本或时段证据' })]
      const taskNodes = planTasks.length ? planTasks.map(task => add({ id: `chain-task-${plan.id}-${task.id}`, label: task.title, code: task.status === 'done' ? '已完成' : task.status === 'submitted' ? '待核验' : '待处理', type: 'task', icon: 'tasks', state: task.status, lane: 7, detail: `${task.owner} · 截止 ${dateText(task.dueAt)}`, selection: { type: 'task', id: task.id } })) : [add({ id: `chain-task-${plan.id}-none`, label: '没有补证任务', code: '协同动作', type: 'task', icon: 'tasks', state: 'unknown', lane: 7, detail: 'AI 或人工复核可将证据缺口转为任务' })]
      const decisions = w.decisions.filter(d => d.planId === plan.id).slice(-1)
      const approvalNodes = decisions.length ? decisions.map(decision => add({ id: `chain-approval-${plan.id}-${decision.id}`, label: decision.comment || '人工决策已记录', code: decision.basis || '审批记录', type: 'approval', icon: 'shield', state: 'approved', lane: 8, detail: `${decision.actor} · ${dateText(decision.at)}` })) : [add({ id: `chain-approval-${plan.id}-pending`, label: '等待人工放行', code: '审批前提', type: 'approval', icon: 'shield', state: 'unknown', lane: 8, detail: 'AI 与规则都不能替代负责人最终复核' })]

      stepNodes.forEach(step => link(planNode, step, '拆解', '从计划原文保留步骤顺序和来源行', step.state === 'unknown'))
      chemicalNodes.forEach(chemical => link(stepNodes[0] || planNode, chemical, '识别物料', chemical.detail))
      equipmentNodes.forEach(equipment => link(planNode, equipment, '使用资源', `${plan.code} 依赖 ${equipment.code}；点击资源查看状态与证据`, equipment.state === 'blocked'))
      controlNodes.forEach(control => equipmentNodes.slice(0, 3).forEach(equipment => link(equipment, control, '需要控制', control.label)))
      ruleNodes.forEach(rule => controlNodes.slice(0, 3).forEach(control => link(control, rule, '规则核验', rule.detail, rule.state === 'blocked')))
      evidenceNodes.forEach(evidence => ruleNodes.slice(0, 3).forEach(rule => link(rule, evidence, '支持依据', evidence.detail, evidence.state !== 'verified')))
      taskNodes.forEach(task => evidenceNodes.slice(0, 3).forEach(evidence => link(evidence, task, '转为任务', task.detail, task.state !== 'done')))
      approvalNodes.forEach(approval => taskNodes.slice(0, 3).forEach(task => link(task, approval, '人工决策', approval.detail, approval.state !== 'approved')))
    })
    return { nodes: lanes.flat(), edges, width: lanes.length * 220 + 20, height: Math.max(430, ...lanes.map(lane => lane.length * 94 + 120)) }
  }, [w, snapshot, labId, selection, all])
  const laneNames = ['实验计划', '步骤', '化学品 / 物料', '设备', '控制措施', '规则', '证据', '协同任务', '人工审批']
  return <div className="al-chain-view"><div className="al-chain-caption"><span className="al-eyebrow">SAFETY DEPENDENCY CHAIN</span><b>从原文到人工放行的可追溯链路</b><small>候选关系来自计划原文、设备画像与当前检查快照；化学品与控制仍需人工确认。</small></div><div className="al-graph-scroll al-chain-scroll"><svg width={graph.width} height={graph.height} viewBox={`0 0 ${graph.width} ${graph.height}`} role="img" aria-label="步骤、化学品、设备、控制、规则、证据、任务与审批关系图"><defs><pattern id="chain-dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".8" fill="#dce5f1"/></pattern></defs><rect width="100%" height="100%" fill="url(#chain-dots)"/>{laneNames.map((name, lane) => <text className="al-chain-lane" key={name} x={lane * 220 + 20} y={25}>{name}</text>)}{graph.edges.map(edge => { const a = graph.nodes.find(node => node.id === edge.from), b = graph.nodes.find(node => node.id === edge.to); if (!a || !b) return null; const x = a.lane * 220 + 210, y = 62 + a.index * 94 + 32, xx = b.lane * 220 + 20, yy = 62 + b.index * 94 + 32; return <g key={`${edge.from}-${edge.to}-${edge.label}`} role="button" tabIndex={0} aria-label={edge.description} onClick={() => setInsight(edge.description)} onKeyDown={event => { if (event.key === 'Enter') setInsight(edge.description) }} className="al-graph-edge"><path d={`M${x} ${y} C${x + 62} ${y} ${xx - 62} ${yy} ${xx} ${yy}`} fill="none" stroke={edge.bad ? '#e47786' : '#93b0e4'} strokeWidth={edge.bad ? '2.4' : '1.8'} /><path d={`M${x} ${y} C${x + 62} ${y} ${xx - 62} ${yy} ${xx} ${yy}`} fill="none" stroke="transparent" strokeWidth="16" /><text x={(x + xx) / 2} y={(y + yy) / 2 - 5} textAnchor="middle">{edge.label}</text></g> })}{graph.nodes.map(node => <foreignObject key={node.id} x={node.lane * 220 + 20} y={62 + node.index * 94} width="194" height="70"><button className={`al-graph-node al-chain-node ${node.type} ${node.state === 'blocked' ? 'blocked' : ''} ${node.state === 'unknown' ? 'unknown' : ''}`} onClick={() => node.selection ? onSelect(node.selection) : setInsight(`${node.label}：${node.detail}`)}><span className={`al-node-icon ${toneFor(node.state)}`}><Icon name={node.icon} size={20} /></span><div><b>{node.label}</b><small>{node.code}</small></div><span className={`al-node-dot ${toneFor(node.state)}`} /></button></foreignObject>)}</svg></div><div className="al-graph-insight"><Icon name="link" size={18} />{insight}</div></div>
}
