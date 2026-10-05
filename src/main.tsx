import { StrictMode, useEffect, useMemo, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Page = 'dashboard' | 'new-review' | 'plan-parse' | 'risk' | 'approval' | 'incident' | 'evidence' | 'knowledge' | 'evaluation'
type Severity = '严重' | '高' | '中' | '低'
const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

const nav: { id: Page; label: string; icon: string; group?: string }[] = [
  { id: 'dashboard', label: '总览仪表盘', icon: '⌂' },
  { id: 'new-review', label: '新建审查', icon: '＋', group: '实验 SOP 工作流' },
  { id: 'plan-parse', label: '计划解析', icon: '⌁' },
  { id: 'risk', label: '风险工作台', icon: '◈' },
  { id: 'approval', label: '审批闸门', icon: '◉' },
  { id: 'incident', label: '事故演练', icon: '✣', group: '运营中心' },
  { id: 'evidence', label: '证据中心', icon: '▣' },
  { id: 'knowledge', label: '化学知识库', icon: '◫', group: '知识与评测' },
  { id: 'evaluation', label: '安全评测', icon: '◎' },
]

const cases = [
  { id: 'LLX-01', name: '液液萃取', description: '挥发性有机溶剂、分液漏斗与废液分流', status: '待复核', risk: '高' as Severity, owner: '实验指导教师', evidence: 'SOP §2.1–2.4' },
  { id: 'STE-02', name: '溶剂转移与蒸发', description: '点火源、局部排风与设备边界', status: '阻断', risk: '严重' as Severity, owner: 'EHS 负责人', evidence: 'SOP §3.2–3.6' },
  { id: 'CHR-03', name: '色谱与有机废液', description: '多溶剂清单、容器标识与废液相容性', status: '已通过', risk: '中' as Severity, owner: '分析平台主管', evidence: 'SOP §4.1–4.8' },
]

const riskItems = [
  { title: '蒸发步骤缺少设备联锁边界', severity: '严重' as Severity, reason: 'SOP 只写“启动蒸发”，未给出温控上限或二次确认。', evidence: 'SOP §3.4「启动旋转蒸发仪」', rule: 'EQUIP-002', control: '补充设备检查项、停止条件和负责人确认。', status: 'BLOCKED' },
  { title: '挥发性溶剂转移的通风证据不足', severity: '高' as Severity, reason: '未找到通风柜状态或局部排风检查记录。', evidence: 'SOP §2.2「转移乙酸乙酯」', rule: 'VENT-001', control: '关联通风柜检查记录，确认有效局部排风。', status: 'NEEDS_REVIEW' },
  { title: '有机废液容器未明确分流', severity: '高' as Severity, reason: '步骤提到废液，但未指定兼容类别、标签和暂存位置。', evidence: 'SOP §4.7「收集剩余溶剂」', rule: 'WASTE-001', control: '指定有机废液流、容器标签和暂存责任人。', status: 'NEEDS_REVIEW' },
  { title: 'PPE 与暴露路径已覆盖', severity: '低' as Severity, reason: '护目镜、实验服和耐溶剂手套均在步骤中有证据。', evidence: 'SOP §2.1–2.3', rule: 'PPE-001', control: '保留操作前 PPE 勾选项。', status: 'PASS' },
]

const incidents = [
  { id: 'spill', title: '有机溶剂泄漏', subtitle: '验证暂停操作、区域隔离与通风确认', steps: [{ prompt: '发现容器外壁出现泄漏迹象，第一动作是什么？', options: ['继续完成当前转移', '暂停操作并通知负责人', '直接用手擦拭'], correct: 1, explain: '先停止相关操作并建立人员与区域控制。' }, { prompt: '完成初始报告后，下一步应确认什么？', options: ['隔离区域并确认通风状态', '关闭所有通风', '让无关人员进入查看'], correct: 0, explain: '隔离和通风状态确认是后续处置的前置条件。' }] },
  { id: 'vent', title: '通风设备故障', subtitle: '验证挥发性操作的停止条件与升级记录', steps: [{ prompt: '局部排风指示异常且步骤未完成，应如何处理？', options: ['继续操作观察', '暂停操作并撤离暴露区域', '提高加热功率'], correct: 1, explain: '通风异常时不能继续进行挥发性操作。' }, { prompt: '设备故障如何进入可追溯流程？', options: ['只口头告诉同伴', '通知负责人并记录故障', '删除运行记录'], correct: 1, explain: '设备故障需要进入维修和复核流程。' }] },
  { id: 'ignition', title: '点火源异常', subtitle: '验证易燃溶剂作业的点火源检查与恢复审批', steps: [{ prompt: '易燃溶剂作业区出现未确认热源，应如何处理？', options: ['停止作业并隔离点火源', '继续转移并加快速度', '覆盖热源继续操作'], correct: 0, explain: '必须先消除未确认的点火源。' }, { prompt: '恢复实验前由谁确认条件？', options: ['操作者自行宣布恢复', '安全负责人确认恢复条件', '跳过审批直接恢复'], correct: 1, explain: '恢复必须经过有权限的负责人确认。' }] },
]

const sampleSop = `SOP-ORG-002 v1.0｜溶剂转移与蒸发\n1. 在通风柜内确认乙酸乙酯和甲苯容器标签。\n2. 佩戴护目镜、实验服和耐溶剂手套，将溶剂转移至旋转蒸发仪。\n3. 将残余溶剂收集至有机废液容器并完成标签。`

function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [toast, setToast] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [parsedHash, setParsedHash] = useState('待解析')
  const [activeReview, setActiveReview] = useState<any | null>(null)
  const [activeEvaluation, setActiveEvaluation] = useState<any | null>(null)
  const [apiMode, setApiMode] = useState<'offline' | 'remote'>('offline')
  const notify = (text: string) => { setToast(text); window.setTimeout(() => setToast(''), 2600) }
  const active = nav.find(item => item.id === page)!
  return <div className="app-shell">
    <aside className={mobileOpen ? 'sidebar open' : 'sidebar'}>
      <div className="brand"><div className="brand-mark">A</div><div><b>Aegis<span>Lab</span></b><small>化学实验安全台</small></div></div>
      <div className="workspace-switch"><div className="workspace-avatar">D</div><div><strong>Demo Lab A</strong><small>有机溶剂安全治理</small></div><span>⌄</span></div>
      <nav>{nav.map(item => <div key={item.id}>{item.group && <div className="nav-group">{item.group}</div>}<button className={page === item.id ? 'nav-item active' : 'nav-item'} onClick={() => { setPage(item.id); setMobileOpen(false) }}><i>{item.icon}</i><span>{item.label}</span>{item.id === 'approval' && <em>2</em>}</button></div>)}</nav>
      <div className="sidebar-foot"><div className="status-dot"><i />{apiMode === 'remote' ? 'API 已连接' : '离线演示就绪'}</div><div className="profile"><div className="avatar">E</div><div><strong>安全负责人</strong><small>Demo Lab A · safety owner</small></div><span>•••</span></div></div>
    </aside>
    <main className="main"><header className="topbar"><button className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)}>☰</button><div className="crumb"><span>AegisLab</span><b>/</b><strong>{active.label}</strong></div><div className="top-actions"><div className="command">⌘ K <span>快速跳转</span></div><button className="icon-btn" onClick={() => notify('暂无新的系统通知')}>♢<i /></button><button className="help" onClick={() => notify('安全负责人可在证据中心查看操作记录')}>?</button></div></header><div className="content"><PageView page={page} notify={notify} parsedHash={parsedHash} setParsedHash={setParsedHash} activeReview={activeReview} activeEvaluation={activeEvaluation} setActiveReview={setActiveReview} setActiveEvaluation={setActiveEvaluation} setApiMode={setApiMode} /></div></main>
    {toast && <div className="toast">✓ {toast}</div>}
  </div>
}

function PageView({ page, notify, parsedHash, setParsedHash, activeReview, activeEvaluation, setActiveReview, setActiveEvaluation, setApiMode }: { page: Page; notify: (s: string) => void; parsedHash: string; setParsedHash: (s: string) => void; activeReview: any | null; activeEvaluation: any | null; setActiveReview: (review: any) => void; setActiveEvaluation: (evaluation: any) => void; setApiMode: (mode: 'offline' | 'remote') => void }) {
  if (page === 'dashboard') return <Dashboard notify={notify} />
  if (page === 'new-review') return <NewReviewV2 notify={notify} setParsedHash={setParsedHash} onReviewReady={(review, evaluation, mode) => { setActiveReview(review); setActiveEvaluation(evaluation); setApiMode(mode) }} />
  if (page === 'plan-parse') return <PlanParse notify={notify} parsedHash={parsedHash} review={activeReview} />
  if (page === 'risk') return <RiskWorkspace notify={notify} review={activeReview} evaluation={activeEvaluation} />
  if (page === 'approval') return <ApprovalGate notify={notify} review={activeReview} evaluation={activeEvaluation} onUpdated={(review, evaluation) => { setActiveReview(review); setActiveEvaluation(evaluation) }} />
  if (page === 'incident') return <Incident notify={notify} review={activeReview} />
  if (page === 'evidence') return <Evidence notify={notify} parsedHash={parsedHash} review={activeReview} />
  if (page === 'knowledge') return <Knowledge notify={notify} />
  return <Evaluation notify={notify} />
}

function PageHead({ eyebrow, title, desc, action, onAction }: { eyebrow: string; title: string; desc: string; action?: string; onAction?: () => void }) { return <div className="page-head"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{desc}</p></div>{action && <button className="primary" onClick={onAction}>＋ {action}</button>}</div> }
function Metric({ label, value, delta, tone = 'blue' }: { label: string; value: string; delta: string; tone?: string }) { return <div className="metric"><div className="metric-top"><span>{label}</span><div className={'metric-icon ' + tone}>{tone === 'red' ? '!' : tone === 'green' ? '✓' : '↗'}</div></div><strong>{value}</strong><small>{delta}</small></div> }
function Status({ children, kind = 'neutral' }: { children: ReactNode; kind?: string }) { return <span className={'status ' + kind}><i />{children}</span> }
function Section({ title, action, children }: { title: string; action?: string; children: ReactNode }) { return <section className="panel"><div className="section-head"><h2>{title}</h2>{action && <button className="link-btn">{action} →</button>}</div>{children}</section> }

function Dashboard({ notify }: { notify: (s: string) => void }) { return <><PageHead eyebrow="AegisLab / OFFLINE DEMO" title="实验开始前，先把风险说清楚" desc="面向高校有机溶剂实验的 SOP 前审、人工放行与事故演练。" action="新建审查" onAction={() => notify('已创建新的离线审查草稿')} /><div className="demo-banner"><span>离线演示</span><p>当前数据为 synthetic/demo，仅用于展示流程；规则结论、证据和审批事件均可追溯。</p><button className="link-btn" onClick={() => notify('已打开数据边界说明')}>查看边界 →</button></div><div className="metrics"><Metric label="演示案例" value="03" delta="同一有机溶剂场景" /><Metric label="阻断风险" value="02" delta="需安全负责人处理" tone="red" /><Metric label="事故剧本" value="03" delta="可重复运行" tone="green" /><Metric label="运行模式" value="离线" delta="无 API 仍可审查" /></div><div className="grid-2"><Section title="当前风险态势" action="打开风险工作台"><div className="risk-overview"><div className="donut"><div><strong>2<small> 条</small></strong><span>待处理阻断</span></div></div><div className="legend"><div><i className="dot red" /><span>严重 / 高</span><b>03</b></div><div><i className="dot orange" /><span>待复核</span><b>02</b></div><div><i className="dot green" /><span>已通过</span><b>01</b></div><div><i className="dot gray" /><span>证据待补</span><b>02</b></div></div></div><div className="callout"><strong>安全门保持关闭</strong><span>高风险结论必须由安全负责人确认，学生角色不能放行。</span></div></Section><Section title="最近活动" action="查看审计事件"><div className="activity"><Activity icon="!" color="red" text="蒸发步骤触发设备边界阻断" time="12 分钟前 · EQUIP-002" /><Activity icon="⌁" color="blue" text="液液萃取 SOP 解析完成" time="34 分钟前 · synthetic/demo" /><Activity icon="✣" color="purple" text="有机溶剂泄漏演练待运行" time="昨天 · 2 个分支" /><Activity icon="▣" color="green" text="证据包哈希校验通过" time="昨天 · SHA-256" /></div></Section></div><Section title="同域演示案例" action="打开审查中心"><div className="table-wrap"><table><thead><tr><th>实验案例</th><th>风险焦点</th><th>状态</th><th>责任角色</th><th>证据</th></tr></thead><tbody>{cases.map(item => <tr key={item.id}><td><strong>{item.name}</strong><small className="mono">{item.id} · synthetic/demo</small></td><td>{item.description}</td><td><Status kind={item.status === '已通过' ? 'success' : item.status === '阻断' ? 'danger' : 'warning'}>{item.status}</Status></td><td>{item.owner}</td><td className="muted">{item.evidence}</td></tr>)}</tbody></table></div></Section></> }
function Activity({ icon, color, text, time }: { icon: string; color: string; text: string; time: string }) { return <div className="activity-row"><span className={'activity-icon ' + color}>{icon}</span><div><strong>{text}</strong><small>{time}</small></div></div> }

function NewReview({ notify, setParsedHash }: { notify: (s: string) => void; setParsedHash: (s: string) => void }) { const [title, setTitle] = useState('溶剂转移与蒸发 · Demo SOP'); const [sop, setSop] = useState(sampleSop); const [busy, setBusy] = useState(false); const parse = async () => { setBusy(true); try { const response = await fetch(`${API_BASE}/parse/sop`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, sop_text: sop, room: 'Demo Lab A' }) }); if (!response.ok) throw new Error('offline'); const result = await response.json(); setParsedHash(result.input_sha256 || '已生成'); notify(`解析完成：识别 ${result.steps?.length || 0} 个步骤和 ${result.substances?.length || 0} 个化学品`) } catch { setParsedHash('离线演示哈希 · 运行时生成'); notify('离线解析完成：已进入计划解析页') } finally { setBusy(false) } }; return <><PageHead eyebrow="REVIEW WORKFLOW / 01" title="新建实验安全审查" desc="导入 SOP 和试剂信息，生成可追溯的实验前安全闸门。" /><div className="stepper"><div className="step active"><b>01</b><span>导入材料</span></div><i /><div className="step"><b>02</b><span>解析证据</span></div><i /><div className="step"><b>03</b><span>核验风险</span></div><i /><div className="step"><b>04</b><span>人工放行</span></div></div><div className="form-grid"><div className="panel form-panel"><div className="section-head"><h2>实验基础信息</h2><span className="required">synthetic/demo</span></div><label>SOP 名称 <em>*</em><input value={title} onChange={event => setTitle(event.target.value)} /></label><label>实验域 <em>*</em><select defaultValue="有机溶剂实验"><option>有机溶剂实验</option><option>其他实验类型（规划中）</option></select></label><label>实验室与角色 <input defaultValue="Demo Lab A · 实验指导教师" /></label><label>SOP / 实验计划文本 <em>*</em><textarea value={sop} onChange={event => setSop(event.target.value)} rows={9} /></label><div className="form-note"><span>⌁</span><div><strong>上传内容只作为数据</strong><small>解析器和 Harness 不执行 SOP 内的代码、命令或路径。</small></div></div><button className="primary wide" onClick={parse} disabled={busy}>{busy ? '解析中…' : '保存并解析'} <span>→</span></button></div><div className="panel side-note"><div className="note-orb">✦</div><h3>可信安全审查</h3><p>AI 只负责从自然语言中提取实验步骤和实体；PPE、通风、废液、设备边界等硬约束由版本化规则引擎核验。</p><div className="mini-check"><span>✓</span>默认 fail-safe，证据不足即待复核</div><div className="mini-check"><span>✓</span>高风险由安全负责人人工放行</div><div className="mini-check"><span>✓</span>每条结论关联原文与规则版本</div></div></div></> }

async function sha256Text(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest)).map(value => value.toString(16).padStart(2, '0')).join('')
}

function NewReviewV2({ notify, setParsedHash, onReviewReady }: { notify: (s: string) => void; setParsedHash: (s: string) => void; onReviewReady: (review: any, evaluation: any, mode: 'offline' | 'remote') => void }) {
  const [title, setTitle] = useState('溶剂转移与蒸发 · Demo SOP')
  const [sop, setSop] = useState(sampleSop)
  const [reagents, setReagents] = useState('甲苯；乙酸乙酯')
  const [setup, setSetup] = useState('Demo Lab A · 通风柜 · 旋转蒸发仪 · 实验指导教师')
  const [busy, setBusy] = useState(false)
  const importFile = async (file?: File) => {
    if (!file) return
    const text = await file.text()
    setSop(text)
    notify(`已导入 ${file.name}；当前支持 SOP 文本、Markdown 和已提取 PDF 文本`)
  }
  const parse = async () => {
    setBusy(true)
    const hash = await sha256Text(sop)
    setParsedHash(hash)
    try {
      const response = await fetch(`${API_BASE}/reviews/from-sop`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, sop_text: sop, requester: 'demo', room: 'Demo Lab A' }) })
      if (!response.ok) throw new Error('offline')
      const review = await response.json()
      const submittedResponse = await fetch(`${API_BASE}/reviews/${review.id}/submit?actor=demo`, { method: 'POST' })
      const submitted = submittedResponse.ok ? await submittedResponse.json() : review
      const evaluationResponse = await fetch(`${API_BASE}/reviews/${review.id}/evaluate?with_llm=true`, { method: 'POST' })
      const evaluation = evaluationResponse.ok ? await evaluationResponse.json() : null
      onReviewReady(submitted, evaluation, 'remote')
      notify(`已创建审查 ${review.id.slice(0, 8)}：解析 ${review.steps?.length || 0} 个步骤、${review.substances?.length || reagents.split(/[；,，]/).filter(Boolean).length} 个化学品，并完成规则评估`)
    } catch {
      onReviewReady({ id: 'offline-demo', title, status: 'in_review', sop, metadata: { input_sha256: hash, synthetic: true }, gates: [] }, null, 'offline')
      notify('离线解析完成：规则引擎仍可继续核验')
    } finally { setBusy(false) }
  }
  return <><PageHead eyebrow="REVIEW WORKFLOW / 01" title="新建实验安全审查" desc="导入 SOP、试剂清单和实验条件，生成可追溯的实验前安全闸门。" /><div className="stepper"><div className="step active"><b>01</b><span>导入材料</span></div><i /><div className="step"><b>02</b><span>解析证据</span></div><i /><div className="step"><b>03</b><span>核验风险</span></div><i /><div className="step"><b>04</b><span>人工放行</span></div></div><div className="form-grid"><div className="panel form-panel"><div className="section-head"><h2>实验基础信息</h2><span className="required">synthetic/demo</span></div><label>SOP 名称 <em>*</em><input value={title} onChange={event => setTitle(event.target.value)} /></label><label>导入材料（文本 / Markdown / 已提取 PDF 文本）<input type="file" accept=".txt,.md,.csv,.text" onChange={event => importFile(event.target.files?.[0])} /></label><label>SOP / 实验计划文本 <em>*</em><textarea value={sop} onChange={event => setSop(event.target.value)} rows={8} /></label><label>试剂清单 <em>*</em><input value={reagents} onChange={event => setReagents(event.target.value)} placeholder="例如：甲苯；乙酸乙酯；正己烷" /></label><label>实验室、设备与角色 <input value={setup} onChange={event => setSetup(event.target.value)} /></label><div className="form-note"><span>⌁</span><div><strong>输入 SHA-256 会在保存时实时计算</strong><small>解析器和 Harness 不执行 SOP 内的代码、命令或路径；API Key 不进入证据包。</small></div></div><button className="primary wide" onClick={parse} disabled={busy}>{busy ? '解析中…' : '保存并解析'} <span>→</span></button></div><div className="panel side-note"><div className="note-orb">✦</div><h3>可信安全审查</h3><p>AI 只负责从自然语言中提取实验步骤和实体；PPE、通风、废液、设备边界等硬约束由版本化规则引擎核验。</p><div className="mini-check"><span>✓</span>默认 fail-safe，证据不足即待复核</div><div className="mini-check"><span>✓</span>高风险由安全负责人人工放行</div><div className="mini-check"><span>✓</span>每条结论关联原文与规则版本</div></div></div></>
}

function PlanParse({ notify, parsedHash, review }: { notify: (s: string) => void; parsedHash: string; review: any | null }) {
  const steps = review?.steps?.length ? review.steps : [
    { order: 1, instruction: '确认容器标签与通风柜', hazard: '挥发性有机溶剂', evidence_refs: ['SOP §1'], requires_ppe: ['护目镜', '实验服'] },
    { order: 2, instruction: '转移至旋转蒸发仪', hazard: '易燃溶剂 · 点火源 · 设备边界', evidence_refs: ['SOP §2'], requires_ppe: ['耐溶剂手套'] },
    { order: 3, instruction: '分流并标识有机废液', hazard: '废液容器 · 标签 · 暂存', evidence_refs: ['SOP §3'], requires_ppe: [] },
  ]
  const substances = review?.substances?.length ? review.substances : [{ name: '甲苯', cas_number: '108-88-3', hazard_classes: ['flammable', 'toxic'], sds_reference: 'synthetic/demo' }, { name: '乙酸乙酯', cas_number: '141-78-6', hazard_classes: ['flammable'], sds_reference: 'synthetic/demo' }]
  return <><PageHead eyebrow="REVIEW WORKFLOW / 02" title="计划解析" desc="把非结构化 SOP 转成可核验的步骤、化学品、设备与证据引用。" action="重新解析" onAction={() => notify('已使用当前 SOP 重新解析')} /><div className="parse-meta"><Status kind="success">{review?.id && review.id !== 'offline-demo' ? 'API 审查已保存' : '离线解析器可用'}</Status><span>输入 SHA-256：<code>{review?.metadata?.input_sha256 || parsedHash}</code></span><span>来源：SOP 文本 · {review?.metadata?.synthetic === true ? 'synthetic/demo' : '运行时审查'}</span></div><div className="parse-layout"><div className="panel"><div className="section-head"><h2>实验步骤时间线</h2><Status kind="warning">{steps.length} 项已解析</Status></div><div className="timeline">{steps.map((step: any) => <TimelineStep key={step.id || step.order} n={String(step.order).padStart(2, '0')} title={step.instruction} text={`${step.hazard || '未标注危险源'} · ${step.requires_ppe?.join('、') || 'PPE 待复核'}`} risk={step.hazard ? '高' : '中'} evidence={step.evidence_refs?.[0] || '运行时提取'} />)}</div></div><div className="panel parse-result"><div className="section-head"><h2>结构化实体</h2><Status kind="success">证据已绑定</Status></div>{substances.map((item: any) => <Entity key={item.id || item.name} name={item.name} type={`化学品 · ${(item.hazard_classes || []).join('/') || '待分类'}`} detail={`CAS ${item.cas_number || '待补'} · SDS ${item.sds_reference || '待复核'}`} risk="高" />)}<Entity name="通风柜" type="工程控制" detail={review?.ventilation || '证据待复核'} risk="低" /><Entity name="实验设备" type="设备边界" detail={review?.equipment?.join('、') || '温控上限待复核'} risk="严重" /><div className="parse-footer"><span>Skill Registry：parse_sop · normalize_substances · extract_controls</span><button className="primary" onClick={() => notify('已确认解析结果，进入风险工作台')}>确认并核验 →</button></div></div></div></> }
function TimelineStep({ n, title, text, risk, evidence }: { n: string; title: string; text: string; risk: Severity; evidence: string }) { return <div className="timeline-step"><b>{n}</b><div><h3>{title}<span className={'risk-level ' + risk}>{risk}</span></h3><p>{text}</p><small>⌁ {evidence} · evidence_ref</small></div></div> }
function Entity({ name, type, detail, risk }: { name: string; type: string; detail: string; risk: Severity }) { return <div className="entity-row"><span className="entity-icon">◫</span><div><strong>{name}</strong><small>{type}</small><em>{detail}</em></div><span className={'risk-level ' + risk}>{risk}</span></div> }

function RiskWorkspace({ notify, review, evaluation }: { notify: (s: string) => void; review: any | null; evaluation: any | null }) {
  const label = (value: string) => value === 'critical' ? '严重' : value === 'high' ? '高' : value === 'medium' ? '中' : '低'
  const dynamicItems = evaluation?.results?.filter((result: any) => !result.passed).map((result: any) => ({ title: result.message, severity: label(result.severity), reason: result.message, evidence: result.evidence_refs?.join('、') || '待补证据', rule: result.rule_id, control: result.recommended_control || '进入人工复核', status: result.severity === 'critical' || result.severity === 'high' ? 'BLOCKED' : 'NEEDS_REVIEW' }))
  const items = dynamicItems?.length ? dynamicItems : riskItems
  const blocked = items.filter((item: any) => item.status === 'BLOCKED').length
  return <><PageHead eyebrow="RISK OPERATIONS / 03" title="风险工作台" desc="每条结论都指向原文证据、规则版本和下一步控制措施。" action="导出检查清单" onAction={() => notify('已生成操作前检查清单（演示）')} /><div className="risk-banner"><strong>当前审查：{review?.title || '溶剂转移与蒸发'} · {blocked ? 'BLOCKED' : 'READY'}</strong><span>{blocked ? `${blocked} 条高风险控制尚未完成，安全负责人确认前不得开始实验。` : '当前规则已通过，仍需按机构流程确认。'}</span></div><div className="filterbar"><div className="search">⌕ <input placeholder="搜索风险、规则或证据" /></div><button className="filter active">全部 <span>{items.length}</span></button><button className="filter">严重 <span>{items.filter((item: any) => item.severity === '严重').length}</span></button><button className="filter">高 <span>{items.filter((item: any) => item.severity === '高').length}</span></button><button className="filter">待复核 <span>{items.filter((item: any) => item.status === 'NEEDS_REVIEW').length}</span></button></div><div className="risk-list">{items.map((item: any) => <div className="risk-card detailed" key={`${item.rule}-${item.title}`}><div className={'severity ' + item.severity}>{item.severity === '严重' ? '!' : item.severity === '高' ? '↑' : '•'}</div><div className="risk-main"><div className="risk-title"><h3>{item.title}</h3><span className={'risk-level ' + item.severity}>{item.severity}</span></div><p>{item.reason}</p><div className="evidence-inline"><span>⌁ {item.evidence}</span><span>规则 {item.rule} · {evaluation?.results?.find((result: any) => result.rule_id === item.rule)?.rule_version || 'v2026.10'}</span><span>来源：{review?.metadata?.synthetic ? 'synthetic/demo' : '运行时审查'}</span></div><div className="control-line"><strong>建议控制</strong><span>{item.control}</span></div></div><div className="risk-action"><Status kind={item.status === 'BLOCKED' ? 'danger' : item.status === 'PASS' ? 'success' : 'warning'}>{item.status}</Status><button className="icon-btn" onClick={() => notify(`${item.rule} 已加入人工复核队列`)}>•••</button></div></div>)}</div></> }

function ApprovalGate({ notify, review, evaluation, onUpdated }: { notify: (s: string) => void; review: any | null; evaluation: any | null; onUpdated: (review: any, evaluation: any) => void }) {
  const [reason, setReason] = useState('')
  const [mitigation, setMitigation] = useState('')
  const [busy, setBusy] = useState(false)
  const refresh = async () => {
    if (!review?.id || review.id === 'offline-demo') return
    const [reviewResponse, evaluationResponse] = await Promise.all([
      fetch(`${API_BASE}/reviews/${review.id}`),
      fetch(`${API_BASE}/reviews/${review.id}/evaluate?with_llm=true`, { method: 'POST' }),
    ])
    if (reviewResponse.ok && evaluationResponse.ok) onUpdated(await reviewResponse.json(), await evaluationResponse.json())
  }
  const decide = async (decision: 'approved' | 'rejected') => {
    if (!review?.id || review.id === 'offline-demo') { notify(decision === 'approved' ? '离线演示保持安全门关闭' : '离线演示已记录退回动作'); return }
    setBusy(true)
    try {
      const response = await fetch(`${API_BASE}/reviews/${review.id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, actor: 'safety_owner', reason: decision === 'rejected' ? '补充设备、通风和废液证据' : '安全负责人确认全部控制措施' }) })
      if (!response.ok) throw new Error(await response.text())
      notify(decision === 'approved' ? '审查已放行并写入审计事件' : '审查已退回，等待补充证据')
      await refresh()
    } catch (error) { notify(`服务器拒绝操作：${String(error).slice(0, 120)}`) } finally { setBusy(false) }
  }
  const override = async () => {
    if (!reason.trim() || !mitigation.trim()) { notify('请填写理由和缓解措施'); return }
    if (!review?.id || review.id === 'offline-demo') { notify('离线演示已记录 Override 草稿'); return }
    setBusy(true)
    try {
      const response = await fetch(`${API_BASE}/reviews/${review.id}/override`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor: 'safety_owner', actor_role: 'safety_owner', reason, mitigation }) })
      if (!response.ok) throw new Error(await response.text())
      notify('Override 已记录，事件日志已更新')
      setReason(''); setMitigation(''); await refresh()
    } catch (error) { notify(`服务器拒绝 Override：${String(error).slice(0, 120)}`) } finally { setBusy(false) }
  }
  const gates = review?.gates?.length ? review.gates : [{ id: 'offline-gate', name: '安全负责人审批', description: '通风、废液和设备边界待复核', status: 'pending' }]
  const passed = gates.filter((gate: any) => gate.status === 'passed' || gate.status === 'waived').length
  const blocked = evaluation ? !evaluation.eligible : true
  return <><PageHead eyebrow="GOVERNANCE / 04" title="审批闸门" desc="高风险默认阻断；Accept、Override、Request changes 都会写入审计事件。" /><div className="approval-layout"><div className="panel approval-main"><div className="approval-title"><div><Status kind={blocked ? 'danger' : 'success'}>{blocked ? 'BLOCKED' : 'READY'}</Status><h2>{review?.title || '溶剂转移与蒸发 · Demo SOP'}</h2><p>{review?.id || 'STE-02'} · 有机溶剂实验 · {review?.room || 'Demo Lab A'} · {review?.metadata?.synthetic ? 'synthetic/demo' : 'API review'}</p></div><div className="approval-score"><span>规则通过</span><strong>{evaluation ? evaluation.results.filter((result: any) => result.passed).length : 6}</strong><small> / {evaluation?.results?.length || 10}</small></div></div><div className="gate-progress"><div><span>安全门进度</span><b>{passed} / {gates.length}</b></div><div className="progress"><i style={{ width: `${Math.round(passed / Math.max(1, gates.length) * 100)}%` }} /></div><small>{blocked ? '仍有规则或证据未满足，安全负责人确认前不得开始实验。' : '规则已通过，仍需按机构流程确认。'}</small></div><div className="gate-list">{gates.map((gate: any) => <GateItem key={gate.id} title={gate.name} desc={gate.description || '审批闸门'} done={gate.status === 'passed' || gate.status === 'waived'} current={gate.status === 'pending'} />)}</div><div className="approval-footer"><button className="secondary" disabled={busy} onClick={() => decide('rejected')}>Request changes</button><button className="primary" disabled={busy} onClick={() => decide('approved')}>Accept</button></div></div><div className="panel approver-panel"><h2>Override（安全负责人）</h2><p className="muted">只有安全负责人、EHS 经理或管理员可使用。理由与缓解措施必填，学生角色不可放行。</p><label className="compact-label">Override 理由<textarea value={reason} onChange={event => setReason(event.target.value)} placeholder="例如：设备联锁记录已在现场核验…" rows={3} /></label><label className="compact-label">缓解措施<textarea value={mitigation} onChange={event => setMitigation(event.target.value)} placeholder="填写有效期、负责人和补充控制…" rows={3} /></label><button className="secondary wide" disabled={busy} onClick={override}>Override 并留档</button><div className="divider" /><h3>当前操作者</h3><div className="approver"><div className="avatar purple">SO</div><div><strong>安全负责人</strong><small>actor_role: safety_owner</small></div><Status kind={blocked ? 'warning' : 'success'}>{blocked ? '待处理' : '已通过'}</Status></div></div></div></> }
function GateItem({ title, desc, done, current }: { title: string; desc: string; done?: boolean; current?: boolean }) { return <div className={'gate-item ' + (current ? 'current' : '')}><span className={done ? 'gate-check' : 'gate-number'}>{done ? '✓' : '○'}</span><div><strong>{title}</strong><small>{desc}</small></div>{done && <Status kind="success">已完成</Status>}{current && <Status kind="warning">待复核</Status>}</div> }

function Incident({ notify, review }: { notify: (s: string) => void; review: any | null }) { const [selected, setSelected] = useState(incidents[0].id); const [answers, setAnswers] = useState<Record<number, number>>({}); const [result, setResult] = useState<number | null>(null); const [busy, setBusy] = useState(false); const drill = incidents.find(item => item.id === selected)!; const submit = async () => { const score = drill.steps.reduce((sum, step, index) => sum + (answers[index] === step.correct ? 1 : 0), 0); const localScore = Math.round(score / drill.steps.length * 100); setResult(localScore); if (review?.id && review.id !== 'offline-demo') { setBusy(true); try { const seedResponse = await fetch(`${API_BASE}/demo/incidents/seed`, { method: 'POST' }); if (seedResponse.ok) { const seeded = await seedResponse.json(); const remote = seeded[incidents.findIndex(item => item.id === selected)] || seeded[0]; if (remote?.id) { const choices: Record<string, number> = {}; remote.steps.forEach((step: any, index: number) => { choices[step.id] = answers[index] ?? -1 }); const runResponse = await fetch(`${API_BASE}/incidents/${remote.id}/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ choices, actor: 'demo' }) }); if (runResponse.ok) { const completed = await runResponse.json(); setResult(completed.score); } } } notify(`演练完成：${localScore} 分，结果已写入证据中心`) } catch { notify(`演练完成：${localScore} 分（离线回退）`) } finally { setBusy(false) } } else notify(`演练完成：${localScore} 分，结果已写入本地演示证据`) }; return <><PageHead eyebrow="RESILIENCE / 05" title="事故决策演练" desc="用状态机练习异常条件下的选择，演练结果只用于培训与改进。" /><div className="incident-hero panel"><div><Status kind="success">培训模拟 · 非现场应急指南</Status><h2>把风险变成可排练的决策。</h2><p>选择一个同域事故剧本，完成动作选择，查看错误解释和复训建议。</p></div><div className="hero-grid"><span>01</span><span>✣</span><span>03</span><span>↗</span><span>02</span><span>◎</span></div></div><div className="drill-tabs">{incidents.map(item => <button key={item.id} className={selected === item.id ? 'drill-tab active' : 'drill-tab'} onClick={() => { setSelected(item.id); setAnswers({}); setResult(null) }}>{item.title}<small>{item.subtitle}</small></button>)}</div><div className="panel incident-run"><div className="section-head"><div><h2>{drill.title}</h2><p className="muted">{drill.subtitle} · 状态机分支 {drill.id}</p></div>{result !== null && <div className="incident-score"><strong>{result}</strong><span>/100</span></div>}</div>{drill.steps.map((step, index) => <div className="incident-question" key={step.prompt}><div className="question-number">0{index + 1}</div><div><h3>{step.prompt}</h3><div className="option-grid">{step.options.map((option, optionIndex) => <button key={option} className={answers[index] === optionIndex ? 'option selected' : 'option'} onClick={() => { setAnswers({ ...answers, [index]: optionIndex }); setResult(null) }}>{option}</button>)}</div>{result !== null && answers[index] !== step.correct && <p className="error-copy">{step.explain} 建议：复训对应 SOP 的停止条件并重新演练。</p>}</div></div>)}<button className="primary" disabled={busy} onClick={submit}>{busy ? '正在写入证据…' : '提交演练并生成培训卡'}</button></div></> }

function Evidence({ notify, parsedHash, review }: { notify: (s: string) => void; parsedHash: string; review: any | null }) {
  const download = async () => {
    if (!review?.id || review.id === 'offline-demo') { notify('离线演示已生成 JSON + Markdown evidence bundle'); return }
    try {
      const response = await fetch(`${API_BASE}/reviews/${review.id}/evidence-package`)
      if (!response.ok) throw new Error('download failed')
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `aegislab-${review.id}.zip`; link.click(); URL.revokeObjectURL(url); notify('证据包已下载：包含审查、评估和审计事件')
    } catch { notify('证据包下载失败，已保留本地演示记录') }
  }
  const title = review?.title || 'STE-02 · 溶剂转移与蒸发'
  return <><PageHead eyebrow="AUDIT TRAIL / 06" title="证据中心" desc="输入哈希、SOP 引用、规则版本、审批事件和演练结果集中留痕。" action="导出证据包" onAction={download} /><div className="evidence-layout"><div className="panel evidence-tree"><div className="search">⌕ <input placeholder="搜索证据" /></div><div className="tree-group"><small>审查任务</small><button className="tree-row active">▾ {title} <b>{review?.id && review.id !== 'offline-demo' ? 'API' : '12'}</b></button><button className="tree-row">▸ LLX-01 · 液液萃取 <b>08</b></button><button className="tree-row">▸ CHR-03 · 色谱与有机废液 <b>10</b></button></div><div className="tree-group"><small>证据类型</small><button className="tree-row">◇ SOP 原文与哈希 <b>03</b></button><button className="tree-row">▣ 规则运行结果 <b>10</b></button><button className="tree-row">✣ 演练与培训卡 <b>03</b></button></div></div><div className="panel evidence-main"><div className="section-head"><div><h2>{title}</h2><p className="muted">{review?.metadata?.synthetic ? 'synthetic/demo' : 'API review'} · 证据包可导出</p></div><button className="secondary" onClick={() => notify('已校验全部证据哈希')}>校验哈希</button></div><EvidenceRow icon="⌁" title="输入 SOP SHA-256" meta={(review?.metadata?.input_sha256 || parsedHash) + ' · 运行时计算 · 不保存 API Key'} tag="已记录" /><EvidenceRow icon="◈" title="规则运行快照" meta="规则版本随 API evaluation 记录 · 证据可回溯" tag="可追溯" /><EvidenceRow icon="◎" title="模型与降级状态" meta="模型：gpt-6.1-sol（未配置时 offline fallback）· trace_id 不含密钥" /><EvidenceRow icon="◉" title="人工审批事件" meta="Request changes / Override · actor_role=safety_owner · 原因必填" /><EvidenceRow icon="✣" title="事故演练结果" meta="有机溶剂泄漏 · score 与错误解释写入 evidence bundle" /></div></div></> }
function EvidenceRow({ icon, title, meta, tag }: { icon: string; title: string; meta: string; tag?: string }) { return <div className="evidence-row"><span className="evidence-icon">{icon}</span><div><strong>{title}</strong><small>{meta}</small></div>{tag && <Status kind="success">{tag}</Status>}<button className="icon-btn">↓</button></div> }

function Knowledge({ notify }: { notify: (s: string) => void }) { const sources = [{ name: 'PubChem PUG REST', scope: '化学品身份与 CAS 映射', terms: '公开 API · 检索时间和 hash 随证据记录' }, { name: 'NIOSH Pocket Guide', scope: '暴露与工程控制参考', terms: '公开资料 · 仅作辅助证据' }, { name: 'OSHA Laboratory Safety', scope: '实验室安全基线', terms: '公开资料 · 不替代机构制度' }, { name: 'NOAA CAMEO Chemicals', scope: '相容性与应急参考', terms: '公开资料 · 版本化引用' }]; return <><PageHead eyebrow="KNOWLEDGE / 07" title="化学知识库" desc="把来源、版本、适用范围和授权条款一起保存，避免把公开资料误说成机构 SDS。" action="新建规则条目" onAction={() => notify('已创建规则条目草稿')} /><div className="knowledge-toolbar"><div className="search">⌕ <input placeholder="搜索化学品、控制措施或来源" /></div><button className="filter active">全部</button><button className="filter">化学品</button><button className="filter">控制措施</button><button className="filter">规则来源</button></div><div className="knowledge-grid">{sources.map((source, index) => <div className="knowledge-card" key={source.name}><div className={'knowledge-icon ' + ['purple', 'blue', 'orange', 'green'][index]}>{index === 0 ? '◈' : index === 1 ? '⌁' : index === 2 ? '▣' : '✣'}</div><h3>{source.name}</h3><p>{source.scope}</p><small>{source.terms}</small><button className="link-btn">查看来源元数据 →</button></div>)}</div><div className="empty-tip"><span>✦</span><div><strong>规则包 organic-solvent-v1</strong><small>包含 PPE、通风、设备边界、废液和证据充分性检查；当前版本 v2026.10。</small></div><button className="link-btn" onClick={() => notify('规则版本已复制到审查上下文')}>复制版本 →</button></div></> }

type EvaluationSnapshot = { total_cases: number; accuracy_pct: number; macro_f1_pct: number; finding_precision_pct: number; finding_recall_pct: number; finding_f1_pct: number; critical_high_recall_pct: number; false_positive_rate_pct: number; control_match_pct: number; evidence_coverage_pct: number; average_review_ms: number; manual_review_rate_pct: number; override_rate_pct: number; offline_degraded_available_pct: number; evidence_hash_verified_pct: number; synthetic_cases: number; dataset_version: string; generated_at: string }
function Evaluation({ notify }: { notify: (s: string) => void }) { const [snapshot, setSnapshot] = useState<EvaluationSnapshot | null>(null); useEffect(() => { fetch('/eval-summary.json').then(response => response.ok ? response.json() : Promise.reject()).then(setSnapshot).catch(() => setSnapshot(null)) }, []); const metrics = useMemo(() => snapshot ? [['Finding Precision', snapshot.finding_precision_pct + '%'], ['Finding Recall', snapshot.finding_recall_pct + '%'], ['Finding F1', snapshot.finding_f1_pct + '%'], ['严重/高风险召回', snapshot.critical_high_recall_pct + '%'], ['控制措施匹配', snapshot.control_match_pct + '%'], ['证据覆盖率', snapshot.evidence_coverage_pct + '%'], ['平均审查耗时', snapshot.average_review_ms + ' ms'], ['误报率', snapshot.false_positive_rate_pct + '%'], ['人工复核率', snapshot.manual_review_rate_pct + '%'], ['Override 率', snapshot.override_rate_pct + '%'], ['离线降级可用', snapshot.offline_degraded_available_pct + '%'], ['证据哈希校验', snapshot.evidence_hash_verified_pct + '%']] : [], [snapshot]); return <><PageHead eyebrow="QUALITY / 08" title="安全评测中心" desc="数字来自 eval/run_eval.py 的实际运行结果；合成数据和运行时间明确标注。" action="重新运行评测" onAction={() => notify('请在终端运行 python3 eval/run_eval.py 后刷新页面')} />{snapshot ? <><div className="eval-source"><Status kind="success">已加载运行结果</Status><span>数据集 {snapshot.dataset_version} · {snapshot.synthetic_cases}/{snapshot.total_cases} 条 synthetic/demo · 生成于 {snapshot.generated_at}</span></div><div className="eval-metrics">{metrics.map(([label, value]) => <div className="eval-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><Section title="评测边界" action="查看原始 CSV"><p className="muted">这些指标验证的是固定的离线化学安全检查集，不代表真实高校事故率、试点效果或法规结论。每条案例可回溯到输入、预期规则和运行结果。</p></Section></> : <div className="panel empty-state"><strong>尚未加载评测结果</strong><p>运行 <code>python3 eval/run_eval.py</code> 生成结果后刷新页面。</p></div>}</> }

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
