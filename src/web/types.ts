export type Page = 'space' | 'plans' | 'tasks' | 'library' | 'resources' | 'settings'
export type View = 'space' | 'graph' | 'time'
export type Kind = 'hood' | 'bench' | 'storage' | 'analyzer' | 'sink' | 'waste'
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
export const kindNames: Record<Kind, string> = { hood: '通风柜', bench: '操作台', storage: '储存柜', analyzer: '分析仪器', sink: '清洗设施', waste: '废液暂存' }
export const statusNames: Record<string, string> = { draft: '待确认', blocked: '存在阻断', unknown: '待补证', ready: '待复核', approved: '复核已记录', recheck: '需重新复核', archived: '已归档' }
export const uid = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`
