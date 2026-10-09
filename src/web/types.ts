export type Page = 'space' | 'plans' | 'tasks' | 'library' | 'resources' | 'settings'
export type View = 'space' | 'graph' | 'time'
/**
 * Equipment taxonomy used by university and research-institute laboratories.
 * The legacy six values remain valid for existing workspaces; new values make
 * the scene and resource register expressive enough for analytical chemistry,
 * sample preparation, storage, and emergency infrastructure.
 */
export type Kind =
  | 'hood' | 'bench' | 'storage' | 'analyzer' | 'sink' | 'waste'
  | 'clean_bench' | 'biosafety_cabinet' | 'balance' | 'centrifuge' | 'pcr'
  | 'gc' | 'hplc' | 'uv_vis' | 'mass_spec' | 'elemental_analyzer'
  | 'evaporator' | 'vacuum_pump' | 'nitrogen_blowdown' | 'water_purification'
  | 'refrigerator' | 'freezer' | 'drying_oven' | 'furnace' | 'gas_cabinet'
  | 'flammable_cabinet' | 'acid_base_cabinet' | 'solvent_waste' | 'solid_waste'
  | 'eyewash' | 'safety_shower' | 'gas_detector' | 'environment_monitor'
  | 'access_control' | 'chromatography' | 'ion_chromatography'
export type Tone = 'blue' | 'green' | 'amber' | 'red' | 'muted'
export type Selection = { type: 'equipment' | 'plan' | 'document' | 'task'; id: string } | null
export interface Laboratory { id: string; name: string; description: string; width: number; depth: number }
export interface Window { id: string; start: string; end: string; reason: string }
export interface Equipment {
  id: string; labId: string; code: string; name: string; kind: Kind;
  x: number; z: number; rotation: number; capacity: number; status: 'available' | 'unavailable' | 'unknown';
  owner: string; description: string; requiresEvidence: boolean; specVersion: number; maintenance: Window[]
}
export interface Step { id: string; text: string; line: number; equipmentIds: string[]; confirmed: boolean }
export interface Reservation { id: string; equipmentId: string; start: string; end: string }
export interface Plan {
  id: string; code: string; labId: string; name: string; owner: string; revision: number;
  source: string; sourceName: string; steps: Step[]; reservations: Reservation[]; archived: boolean
}
export interface DocumentRecord {
  id: string; name: string; kind: 'inspection' | 'sop' | 'reference'; equipmentId: string | null;
  specVersion: number; status: 'pending' | 'verified' | 'rejected'; validFrom: string; validUntil: string;
  content: string; source: string; reviewedBy: string | null; reviewedAt: string | null
}
export interface Task {
  id: string; title: string; planId: string | null; equipmentId: string | null;
  owner: string; dueAt: string; status: 'open' | 'submitted' | 'done'; note: string
}
export interface Decision { id: string; planId: string; revision: number; basis: string; actor: string; comment: string; at: string }
export interface AuditEvent { id: string; at: string; actor: string; action: string; objectId: string; summary: string }
export interface Branch {
  id: string; name: string; planId: string; baseRevision: number; baseBasis: string; reservations: Reservation[]; createdAt: string
}
export interface Workspace {
  schemaVersion: 1; revision: number; name: string; provenance: 'user' | 'example';
  laboratories: Laboratory[]; equipment: Equipment[]; plans: Plan[]; documents: DocumentRecord[];
  tasks: Task[]; decisions: Decision[]; events: AuditEvent[]; branches: Branch[]
}
export interface Check {
  id: string; planId: string; equipmentId: string | null; code: string;
  state: 'pass' | 'unknown' | 'blocked'; title: string; detail: string;
  relatedPlanIds: string[]; documentIds: string[]; line: number | null
}
export interface Operation { type: string; payload: Record<string, unknown> }
export interface Snapshot { workspace: Workspace; checks: Check[]; statuses: Record<string, string>; mode: 'local' | 'server' }
export const kindNames: Record<Kind, string> = {
 hood: '通风柜', bench: '操作台', storage: '通用储存柜', analyzer: '分析仪器', sink: '清洗设施', waste: '废液暂存',
 clean_bench: '洁净工作台', biosafety_cabinet: '生物安全柜', balance: '分析天平 / 称量台', centrifuge: '离心机', pcr: 'PCR / 实时荧光 PCR',
 gc: '气相色谱 GC', hplc: '液相色谱 HPLC', uv_vis: '紫外可见分光光度计', mass_spec: '质谱系统', elemental_analyzer: '元素分析仪',
 evaporator: '旋转蒸发仪', vacuum_pump: '真空泵', nitrogen_blowdown: '氮吹仪', water_purification: '纯水系统', refrigerator: '实验室冰箱',
 freezer: '低温 / 超低温冰箱', drying_oven: '干燥箱', furnace: '马弗炉 / 高温炉', gas_cabinet: '气瓶柜', flammable_cabinet: '防火防爆柜',
 acid_base_cabinet: '酸碱柜', solvent_waste: '有机废液柜', solid_waste: '固体废物暂存', eyewash: '洗眼器', safety_shower: '紧急喷淋',
 gas_detector: '气体报警器', environment_monitor: '环境监测点', access_control: '门禁与人员识别', chromatography: '色谱分析系统', ion_chromatography: '离子色谱系统',
}
export const statusNames: Record<string, string> = { draft: '待确认', blocked: '存在阻断', unknown: '待补证', ready: '待复核', approved: '复核已记录', recheck: '需重新复核', archived: '已归档' }
export const uid = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`
