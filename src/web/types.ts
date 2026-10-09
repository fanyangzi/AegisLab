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
  | 'glovebox' | 'nmr' | 'ftir' | 'raman' | 'xrd' | 'xps' | 'sem' | 'tem' | 'afm' | 'epr'
  | 'icp_ms' | 'icp_oes' | 'aas' | 'xrf' | 'spr' | 'dls' | 'bet' | 'tga' | 'dsc'
  | 'reactor' | 'microwave_reactor' | 'photoreactor' | 'electrochemistry'
  | 'preparative_hplc' | 'solid_phase_extraction' | 'liquid_nitrogen' | 'cold_trap'
  | 'gas_manifold' | 'exhaust_treatment' | 'lyophilizer' | 'spray_dryer'
  | 'co2_incubator' | 'gel_documentation' | 'electrophoresis' | 'flow_cytometer'
  | 'fluorescence_microscope' | 'cleanroom'
export type EquipmentFamily =
  | 'containment' | 'workstation' | 'separation' | 'spectroscopy' | 'mass_analysis'
  | 'structure_material' | 'thermal_process' | 'cold_chain' | 'gas_vacuum'
  | 'bio_molecular' | 'safety_response' | 'waste_environment' | 'utility'
export type EvidenceKind = 'sop' | 'inspection' | 'sds' | 'training' | 'calibration' | 'reservation' | 'permit' | 'sensor'
export interface EquipmentOperationalProfile {
  family: EquipmentFamily;
  subtype: string;
  aliases: string[];
  typicalUse: string;
  hazardTags: string[];
  controlTags: string[];
  utilityRequirements: string[];
  requiredTraining: string[];
  calibrationOrInspection: string[];
  evidenceKinds: EvidenceKind[];
  sourceRefs: string[];
}
export interface EquipmentSourceCitation {
  sourceId: string;
  relation: 'category-or-control-reference';
  note: string;
}
export const equipmentFamilies: EquipmentFamily[] = ['containment','workstation','separation','spectroscopy','mass_analysis','structure_material','thermal_process','cold_chain','gas_vacuum','bio_molecular','safety_response','waste_environment','utility']
export const evidenceKinds: EvidenceKind[] = ['sop','inspection','sds','training','calibration','reservation','permit','sensor']
export type Tone = 'blue' | 'green' | 'amber' | 'red' | 'muted'
export type Selection = { type: 'equipment' | 'plan' | 'document' | 'task'; id: string } | null
export interface Laboratory { id: string; name: string; description: string; width: number; depth: number }
export interface Window { id: string; start: string; end: string; reason: string }
export interface Equipment {
  id: string; labId: string; code: string; name: string; kind: Kind;
  x: number; z: number; rotation: number; capacity: number; status: 'available' | 'unavailable' | 'unknown';
  owner: string; description: string; requiresEvidence: boolean; specVersion: number; maintenance: Window[];
  /** Optional for backwards compatibility with existing local workspaces. */
  profile?: EquipmentOperationalProfile;
  family?: EquipmentFamily;
  subtype?: string;
  aliases?: string[];
  typicalUse?: string;
  hazardTags?: string[];
  controlTags?: string[];
  utilityRequirements?: string[];
  requiredTraining?: string[];
  calibrationOrInspection?: string[];
  evidenceKinds?: EvidenceKind[];
  sourceRefs?: string[];
  sourceCitations?: EquipmentSourceCitation[];
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
 glovebox: '手套箱 / 惰性气氛箱', nmr: '核磁共振波谱仪 NMR', ftir: '傅里叶变换红外 FTIR', raman: '拉曼光谱仪', xrd: 'X 射线衍射仪 XRD',
 xps: 'X 射线光电子能谱 XPS', sem: '扫描电子显微镜 SEM', tem: '透射电子显微镜 TEM', afm: '原子力显微镜 AFM', epr: '电子顺磁共振 EPR',
 icp_ms: '电感耦合等离子体质谱 ICP-MS', icp_oes: '电感耦合等离子体发射光谱 ICP-OES', aas: '原子吸收光谱仪 AAS', xrf: 'X 射线荧光光谱仪 XRF',
 spr: '表面等离子共振 SPR', dls: '动态光散射 DLS', bet: '比表面积 / 孔径分析 BET', tga: '热重分析仪 TGA', dsc: '差示扫描量热仪 DSC',
 reactor: '反应釜 / 流动反应器', microwave_reactor: '微波合成 / 消解仪', photoreactor: '光化学反应器', electrochemistry: '电化学工作站',
 preparative_hplc: '制备液相色谱', solid_phase_extraction: '固相萃取系统 SPE', liquid_nitrogen: '液氮罐 / 低温供给', cold_trap: '低温冷阱',
 gas_manifold: '气体汇流排 / 气路面板', exhaust_treatment: '尾气吸收 / 净化装置', lyophilizer: '冷冻干燥机', spray_dryer: '喷雾干燥机',
 co2_incubator: '二氧化碳培养箱', gel_documentation: '凝胶成像系统', electrophoresis: '电泳系统', flow_cytometer: '流式细胞仪',
 fluorescence_microscope: '荧光 / 共聚焦显微镜', cleanroom: '洁净室 / 负压操作间',
}
export const statusNames: Record<string, string> = { draft: '待确认', blocked: '存在阻断', unknown: '待补证', ready: '待复核', approved: '复核已记录', recheck: '需重新复核', archived: '已归档' }
export const uid = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`
