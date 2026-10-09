import { useMemo, useState } from 'react'
import type { Check, Selection, Snapshot, Task } from './types'
import { kindNames } from './types'
import { Icon, dateText, toneFor } from './ui'
import { profileForKind } from './equipmentTaxonomy'
import './safetyChainGraph.css'

export type ChainNodeType = 'plan' | 'step' | 'chemical' | 'equipment' | 'control' | 'rule' | 'document' | 'task' | 'approval'
export const CHAIN_NODE_TYPES: ChainNodeType[] = ['plan', 'step', 'chemical', 'equipment', 'control', 'rule', 'document', 'task', 'approval']
export const CHAIN_NODE_NAMES: Record<ChainNodeType, string> = {
  plan: '计划', step: '步骤', chemical: '物料', equipment: '设备', control: '控制', rule: '规则', document: '证据', task: '任务', approval: '审批',
}

export type ChainNode = {
  id: string; label: string; code: string; type: ChainNodeType; icon: string; state: string
  lane: number; index: number; detail: string; selection?: NonNullable<Selection>
}
export type ChainEdge = { id: string; from: string; to: string; label: string; description: string; state: 'pass' | 'unknown' | 'blocked' }
export type SafetyChainGraphModel = { nodes: ChainNode[]; edges: ChainEdge[] }

/** Terms are only used to locate candidate mentions already present in plan text. */
const CHEMICAL_TERMS = ['乙酸乙酯', '二氯甲烷', '乙酸铵', '氢氧化钠', '浓硫酸', '正己烷', '乙腈', '甲醇', '甲苯', '丙酮', '乙醇', '硫酸', '盐酸', '氮气', '氩气', '氢气', '氧气', '冰醋酸', '甲酸', '水']
const unique = (items: string[]) => [...new Set(items.filter(Boolean))]
const nodeId = (type: ChainNodeType, id: string) => `chain-${type}-${id}`
const chemicalId = (planId: string, name: string) => `chain-chemical-${planId}-${encodeURIComponent(name)}`
const safeText = (value: string) => value.replace(/\s+/g, ' ').trim()

export function chemicalsFrom(source: string) {
  return CHEMICAL_TERMS.filter(term => source.includes(term)).filter((term, index, items) => !items.some((other, otherIndex) => otherIndex !== index && other.includes(term)))
}
function statusForChecks(checks: Check[]) { return checks.some(c => c.state === 'blocked') ? 'blocked' : checks.some(c => c.state === 'unknown') ? 'unknown' : 'pass' }
function taskState(task: Task) { return task.status === 'done' ? 'pass' : 'unknown' }

/** Build a graph only from relationships represented in the workspace snapshot. */
export function buildSafetyChainGraph(snapshot: Snapshot, labId: string): SafetyChainGraphModel {
  const w = snapshot.workspace
  const plans = w.plans.filter(plan => !plan.archived && plan.labId === labId)
  const planIds = new Set(plans.map(plan => plan.id))
  const equipment = w.equipment.filter(item => item.labId === labId)
  const equipmentIds = new Set(equipment.map(item => item.id))
  const checks = snapshot.checks.filter(check => planIds.has(check.planId))
  const referencedDocumentIds = new Set(checks.flatMap(check => check.documentIds))
  const documents = w.documents.filter(doc => (doc.equipmentId !== null && equipmentIds.has(doc.equipmentId)) || referencedDocumentIds.has(doc.id))
  const documentIds = new Set(documents.map(doc => doc.id))
  const tasks = w.tasks.filter(task => (task.planId !== null && planIds.has(task.planId)) || (task.equipmentId !== null && equipmentIds.has(task.equipmentId)))
  const decisions = w.decisions.filter(decision => planIds.has(decision.planId))
  const nodes: ChainNode[] = []
  const edges: ChainEdge[] = []
  const seenEdges = new Set<string>()
  const add = (node: Omit<ChainNode, 'index'>) => { const full = { ...node, index: 0 }; nodes.push(full); return full }
  const link = (from: string, to: string, label: string, description: string, state: ChainEdge['state'] = 'pass', relationId = '') => {
    const id = `${from}|${to}|${label}|${relationId}`
    if (seenEdges.has(id)) return
    seenEdges.add(id)
    edges.push({ id, from, to, label, description, state })
  }

  const nodesByEquipment = new Map<string, ChainNode>()
  equipment.forEach(item => {
    const relevantChecks = checks.filter(check => check.equipmentId === item.id)
    const node = add({
      id: nodeId('equipment', item.id), label: item.name, code: item.code, type: 'equipment', icon: 'resources', state: statusForChecks(relevantChecks), lane: 3,
      detail: `${kindNames[item.kind]} · ${item.status === 'available' ? '登记可用' : item.status === 'unknown' ? '台账待确认' : '登记停用'}`,
      selection: { type: 'equipment', id: item.id },
    })
    nodesByEquipment.set(item.id, node)
  })

  const nodesByPlan = new Map<string, ChainNode>()
  plans.forEach(plan => {
    const planChecks = checks.filter(check => check.planId === plan.id)
    const planNode = add({
      id: nodeId('plan', plan.id), label: plan.name, code: plan.code, type: 'plan', icon: 'flask', state: snapshot.statuses[plan.id] || 'unknown', lane: 0, detail: `计划 v${plan.revision} · ${plan.owner}`,
      selection: { type: 'plan', id: plan.id },
    })
    nodesByPlan.set(plan.id, planNode)

    const stepNodes = plan.steps.map((step, index) => add({
      id: nodeId('step', `${plan.id}-${step.id}`), label: safeText(step.text), code: `步骤 ${index + 1} · 原文 L${step.line}`, type: 'step', icon: 'plans', state: step.confirmed ? 'pass' : 'unknown', lane: 1,
      detail: step.confirmed ? `已人工确认原文第 ${step.line} 行` : `待人工确认原文第 ${step.line} 行`,
    }))
    stepNodes.forEach((stepNode, index) => {
      const step = plan.steps[index]
      link(planNode.id, stepNode.id, '拆解', `计划 ${plan.code} 的步骤来自原文第 ${step.line} 行。`, step.confirmed ? 'pass' : 'unknown')
      step.equipmentIds.forEach(equipmentId => {
        const equipmentNode = nodesByEquipment.get(equipmentId)
        if (equipmentNode) link(stepNode.id, equipmentNode.id, '引用设备', `原文第 ${step.line} 行明确引用设备 ${equipmentNode.code}。`)
      })
    })

    const chemicalNodes = new Map<string, ChainNode>()
    plan.steps.forEach((step, index) => {
      chemicalsFrom(step.text).forEach(name => {
        const id = chemicalId(plan.id, name)
        const chemical = chemicalNodes.get(name) || add({
          id, label: name, code: `原文识别 · L${step.line}`, type: 'chemical', icon: 'flask', state: 'unknown', lane: 2,
          detail: `候选物料来自计划原文第 ${step.line} 行；仍需关联 SDS 与相容性。`,
        })
        chemicalNodes.set(name, chemical)
        link(stepNodes[index].id, chemical.id, '识别物料', `物料“${name}”出现在计划原文第 ${step.line} 行，尚未形成已核验化学实体。`, 'unknown')
      })
    })

    plan.reservations.forEach(reservation => {
      const equipmentNode = nodesByEquipment.get(reservation.equipmentId)
      if (equipmentNode) {
        const equipmentChecks = planChecks.filter(check => check.equipmentId === reservation.equipmentId)
        link(planNode.id, equipmentNode.id, '预约资源', `${plan.code} 有一条资源预约，使用 ${equipmentNode.code}，${dateText(reservation.start)}–${dateText(reservation.end)}。`, statusForChecks(equipmentChecks) as ChainEdge['state'], reservation.id)
      }
    })
    planChecks.forEach(check => {
      const ruleNode = add({ id: nodeId('rule', check.id), label: check.title, code: check.code, type: 'rule', icon: 'alert', state: check.state, lane: 5, detail: check.detail })
      link(planNode.id, ruleNode.id, '规则核验', `规则 ${check.code} 针对计划 ${plan.code} 产生了这条检查结果。`, check.state)
      if (check.equipmentId) {
        const equipmentNode = nodesByEquipment.get(check.equipmentId)
        if (equipmentNode) link(ruleNode.id, equipmentNode.id, '核验对象', `规则 ${check.code} 的检查结果明确关联设备 ${equipmentNode.code}。`, check.state)
      }
      check.documentIds.forEach(documentId => {
        if (documentIds.has(documentId)) {
          const document = documents.find(item => item.id === documentId)!
          link(ruleNode.id, nodeId('document', document.id), '支持依据', `规则 ${check.code} 明确引用资料“${document.name}”；资料状态为 ${document.status}。`, document.status === 'verified' ? 'pass' : 'unknown')
        }
      })
      check.relatedPlanIds.filter(relatedPlanId => planIds.has(relatedPlanId) && relatedPlanId !== plan.id).forEach(relatedPlanId => {
        const relatedPlan = nodesByPlan.get(relatedPlanId)
        if (relatedPlan) link(ruleNode.id, relatedPlan.id, '关联计划', `规则 ${check.code} 的快照记录明确关联计划 ${relatedPlan.code}。`, check.state)
      })
    })

    const planDecisions = decisions.filter(decision => decision.planId === plan.id)
    if (planDecisions.length) {
      planDecisions.forEach(decision => {
        const approvalNode = add({ id: nodeId('approval', decision.id), label: decision.comment || '人工决策已记录', code: decision.basis || '审批记录', type: 'approval', icon: 'shield', state: 'approved', lane: 8, detail: `${decision.actor} · ${dateText(decision.at)}` })
        link(planNode.id, approvalNode.id, '人工决策', `计划 ${plan.code} 的人工记录由 ${decision.actor} 于 ${dateText(decision.at)} 写入。`)
      })
    } else {
      const approvalNode = add({ id: `chain-approval-${plan.id}-pending`, label: '等待人工放行', code: '审批前提', type: 'approval', icon: 'shield', state: 'unknown', lane: 8, detail: '当前没有该计划的人工决策记录；AI 与规则都不能替代负责人最终复核。' })
      link(planNode.id, approvalNode.id, '待人工决策', `计划 ${plan.code} 尚无人工决策记录，不能把规则结果解释为放行。`, 'unknown')
    }
  })

  // Controls are profile tags, so each edge has an equipment source. There is no
  // control→rule or control→evidence edge unless the source model has one.
  const controlNodes = new Map<string, ChainNode>()
  equipment.forEach(item => {
    const profile = item.profile || profileForKind(item.kind)
    unique(item.controlTags || profile.controlTags).forEach(control => {
      const controlNode = controlNodes.get(control) || add({ id: `chain-control-${encodeURIComponent(control)}`, label: control, code: '设备画像标签', type: 'control', icon: 'shield', state: 'unknown', lane: 4, detail: `来自 ${item.code} 的运行画像控制标签；需按机构 SOP 核验适用性。` })
      controlNodes.set(control, controlNode)
      const equipmentNode = nodesByEquipment.get(item.id)
      if (equipmentNode) link(equipmentNode.id, controlNode.id, '需要控制', `${item.code} 的设备运行画像声明了控制标签“${control}”；这不是规则通过结论。`, 'unknown')
    })
  })

  documents.forEach(document => {
    const documentNode = add({ id: nodeId('document', document.id), label: document.name, code: document.status === 'verified' ? '已核验' : document.status === 'rejected' ? '已退回' : '待核验', type: 'document', icon: 'file', state: document.status, lane: 6, detail: `${document.source} · 有效至 ${dateText(document.validUntil)}`, selection: { type: 'document', id: document.id } })
    if (document.equipmentId) {
      const equipmentNode = nodesByEquipment.get(document.equipmentId)
      if (equipmentNode) link(equipmentNode.id, documentNode.id, '设备证据', `${equipmentNode.code} 的资料关联字段明确指向“${document.name}”。`, document.status === 'verified' ? 'pass' : 'unknown')
    }
  })

  tasks.forEach(task => {
    const taskNode = add({ id: nodeId('task', task.id), label: task.title, code: task.status === 'done' ? '已完成' : task.status === 'submitted' ? '待核验' : '待处理', type: 'task', icon: 'tasks', state: taskState(task), lane: 7, detail: `${task.owner} · 截止 ${dateText(task.dueAt)}${task.note ? ` · ${task.note}` : ''}`, selection: { type: 'task', id: task.id } })
    if (task.planId) {
      const planNode = nodesByPlan.get(task.planId)
      if (planNode) link(planNode.id, taskNode.id, '协同动作', `任务“${task.title}”的关联计划字段指向 ${planNode.code}。`, task.status === 'done' ? 'pass' : 'unknown')
    }
    if (task.equipmentId) {
      const equipmentNode = nodesByEquipment.get(task.equipmentId)
      if (equipmentNode) link(equipmentNode.id, taskNode.id, '设备动作', `任务“${task.title}”的设备字段指向 ${equipmentNode.code}。`, task.status === 'done' ? 'pass' : 'unknown')
    }
  })
  return { nodes, edges }
}

export function localGraphIds(nodes: ChainNode[], edges: ChainEdge[], anchors: string[], hops: 1 | 2): Set<string> {
  const known = new Set(nodes.map(node => node.id))
  const visible = new Set(anchors.filter(id => known.has(id)))
  for (let depth = 0; depth < hops; depth += 1) {
    const frontier = [...visible]
    edges.forEach(edge => { if (visible.has(edge.from) && known.has(edge.to)) frontier.push(edge.to); if (visible.has(edge.to) && known.has(edge.from)) frontier.push(edge.from) })
    frontier.forEach(id => visible.add(id))
  }
  return visible
}

export interface SafetyChainGraphProps { snapshot: Snapshot; labId: string; selection: Selection; onSelect: (selection: Selection) => void; all?: boolean }
const laneNames = ['实验计划', '步骤', '化学品 / 物料', '设备', '控制措施', '规则', '证据', '协同任务', '人工审批']

export function SafetyChainGraph({ snapshot, labId, selection, onSelect, all = false }: SafetyChainGraphProps) {
  const [insight, setInsight] = useState('点击节点或关系线，查看这条安全链路的含义。')
  const [hops, setHops] = useState<1 | 2>(2)
  const [enabledTypes, setEnabledTypes] = useState<Set<ChainNodeType>>(() => new Set(CHAIN_NODE_TYPES))
  const [pinned, setPinned] = useState<Set<string>>(() => new Set())
  const model = useMemo(() => buildSafetyChainGraph(snapshot, labId), [snapshot, labId])
  const selectedNodeIds = useMemo(() => model.nodes.filter(node => node.selection && selection && node.selection.type === selection.type && node.selection.id === selection.id).map(node => node.id), [model.nodes, selection])
  const fallbackAnchor = model.nodes.find(node => node.type === 'plan')?.id || model.nodes[0]?.id
  const anchors = unique([...selectedNodeIds, ...pinned, ...(selectedNodeIds.length || pinned.size ? [] : fallbackAnchor ? [fallbackAnchor] : [])])
  const localIds = all ? new Set(model.nodes.map(node => node.id)) : localGraphIds(model.nodes, model.edges, anchors, hops)
  const visibleIds = new Set([...localIds].filter(id => { const node = model.nodes.find(item => item.id === id); return node && enabledTypes.has(node.type) }))
  const visibleNodes = useMemo(() => { const lanes: ChainNode[][] = Array.from({ length: laneNames.length }, () => []); model.nodes.filter(node => visibleIds.has(node.id)).forEach(node => lanes[node.lane].push(node)); return lanes.flatMap(lane => lane.map((node, index) => ({ ...node, index }))) }, [model.nodes, visibleIds])
  const nodeById = new Map(visibleNodes.map(node => [node.id, node]))
  const visibleEdges = model.edges.filter(edge => visibleIds.has(edge.from) && visibleIds.has(edge.to))
  const graphWidth = laneNames.length * 220 + 20
  const graphHeight = Math.max(430, ...Array.from({ length: laneNames.length }, (_, lane) => visibleNodes.filter(node => node.lane === lane).length * 94 + 120))
  const toggleType = (type: ChainNodeType) => setEnabledTypes(current => { const next = new Set(current); next.has(type) ? next.delete(type) : next.add(type); return next })
  const pin = (id: string) => setPinned(current => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next })
  const nodeY = (node: ChainNode) => 62 + node.index * 94
  const edgePath = (edge: ChainEdge) => { const a = nodeById.get(edge.from), b = nodeById.get(edge.to); if (!a || !b) return null; const x = a.lane * 220 + 210, y = nodeY(a) + 32, xx = b.lane * 220 + 20, yy = nodeY(b) + 32; return { x, y, xx, yy, d: `M${x} ${y} C${x + 62} ${y} ${xx - 62} ${yy} ${xx} ${yy}` } }

  return <div className="al-chain-view">
    <div className="al-chain-caption"><div><span className="al-eyebrow">SAFETY DEPENDENCY CHAIN</span><b>从原文到人工放行的可追溯链路</b><small>只绘制工作区中有来源字段的关系；没有声明的关系保持为空，不把候选识别当作已确认事实。</small></div><div className="al-chain-controls" aria-label="图谱范围控制"><span className="al-chain-control-label">局部范围</span><button className={hops === 1 && !all ? 'active' : ''} onClick={() => setHops(1)} disabled={all}>1 跳</button><button className={hops === 2 && !all ? 'active' : ''} onClick={() => setHops(2)} disabled={all}>2 跳</button><span className="al-chain-control-state">{all ? '全图' : `${visibleNodes.length} 个节点`}</span>{pinned.size > 0 && <button className="al-chain-clear" onClick={() => setPinned(new Set())}>清除 {pinned.size} 个固定焦点</button>}</div></div>
    <div className="al-chain-filters" aria-label="节点类型筛选"><span>显示类型</span><button className={enabledTypes.size === CHAIN_NODE_TYPES.length ? 'active' : ''} onClick={() => setEnabledTypes(new Set(CHAIN_NODE_TYPES))}>全部</button>{CHAIN_NODE_TYPES.map(type => <button key={type} className={enabledTypes.has(type) ? 'active' : ''} onClick={() => toggleType(type)}>{CHAIN_NODE_NAMES[type]}</button>)}</div>
    <div className="al-graph-scroll al-chain-scroll"><svg width={graphWidth} height={graphHeight} viewBox={`0 0 ${graphWidth} ${graphHeight}`} role="img" aria-label="步骤、化学品、设备、控制、规则、证据、任务与审批关系图"><defs><pattern id="chain-dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".8" fill="#dce5f1" /></pattern></defs><rect width="100%" height="100%" fill="url(#chain-dots)" />{laneNames.map((name, lane) => <text className="al-chain-lane" key={name} x={lane * 220 + 20} y={25}>{name}</text>)}{visibleEdges.map(edge => { const path = edgePath(edge); if (!path) return null; const stroke = edge.state === 'blocked' ? '#e47786' : edge.state === 'unknown' ? '#d1a55a' : '#93b0e4'; return <g key={edge.id} role="button" tabIndex={0} aria-label={edge.description} onClick={() => setInsight(edge.description)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setInsight(edge.description) }} className={`al-graph-edge ${edge.state}`}><path d={path.d} fill="none" stroke={stroke} strokeWidth={edge.state === 'blocked' ? '2.4' : '1.8'} /><path d={path.d} fill="none" stroke="transparent" strokeWidth="16" /><text x={(path.x + path.xx) / 2} y={(path.y + path.yy) / 2 - 5} textAnchor="middle">{edge.label}</text></g> })}{visibleNodes.map(node => <foreignObject key={node.id} x={node.lane * 220 + 20} y={nodeY(node)} width="194" height="70"><div className={`al-chain-node-wrap ${pinned.has(node.id) ? 'pinned' : ''}`} title={node.detail}><button className={`al-graph-node al-chain-node ${node.type} ${node.state === 'blocked' ? 'blocked' : ''} ${node.state === 'unknown' ? 'unknown' : ''} ${selection && node.selection?.type === selection.type && node.selection.id === selection.id ? 'selected' : ''}`} onClick={() => node.selection ? onSelect(node.selection) : setInsight(`${node.label}：${node.detail}`)}><span className={`al-node-icon ${toneFor(node.state)}`}><Icon name={node.icon} size={20} /></span><div><b>{node.label}</b><small>{node.code}</small></div><span className={`al-node-dot ${toneFor(node.state)}`} /></button><button className="al-chain-pin" aria-label={pinned.has(node.id) ? `取消固定 ${node.label}` : `固定 ${node.label}`} aria-pressed={pinned.has(node.id)} onClick={event => { event.stopPropagation(); pin(node.id) }}>{pinned.has(node.id) ? '●' : '○'}</button></div></foreignObject>)}</svg></div>
    <div className="al-graph-insight"><Icon name="link" size={18} />{insight}</div>
  </div>
}
