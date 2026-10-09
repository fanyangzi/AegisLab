import type { EquipmentFamily, EquipmentOperationalProfile, EvidenceKind, Kind } from './types'

/**
 * Operational vocabulary used by the resource register and the AI preflight.
 * The catalog is intentionally sourced from the public university/research
 * institute equipment survey in docs/equipment-taxonomy-research.md; it is an
 * indexing aid, not a substitute for a manufacturer's manual or local SOP.
 */
type Definition = Partial<Omit<EquipmentOperationalProfile, 'family'>> & { family: EquipmentFamily; subtype: string }

const SOURCE_REFS = [
  'docs/equipment-taxonomy-research.md',
  'https://www.lab.pku.edu.cn/info/3151/45321.htm',
  'http://ac.tsinghua.edu.cn/yqsb1.htm',
  'https://www.huanke.sdu.edu.cn/kypt/xdfxcszx.htm',
  'https://ipc.cas.cn/kyzb/ggjsfwzx/hxfxsyq/',
  'https://lab.env.tsinghua.edu.cn/info/1567/2795.htm',
]

const definition = (family: EquipmentFamily, subtype: string, extra: Partial<Definition> = {}): Definition => ({
  family,
  subtype,
  aliases: [],
  typicalUse: '共享平台实验、样品处理或分析测试',
  hazardTags: [],
  controlTags: ['关联当前 SOP', '核对设备状态与适用范围'],
  utilityRequirements: [],
  requiredTraining: ['设备使用培训'],
  calibrationOrInspection: ['检查记录与规格版本'],
  evidenceKinds: ['sop', 'inspection', 'training', 'calibration'] as EvidenceKind[],
  sourceRefs: SOURCE_REFS,
  ...extra,
})

const TAXONOMY: Partial<Record<Kind, Definition>> = {
  hood: definition('containment', '普通化学通风柜', { hazardTags: ['挥发性有机物', '腐蚀性蒸气'], controlTags: ['面风速记录', '排风联锁', '尾气处理'] }),
  clean_bench: definition('containment', '洁净工作台', { hazardTags: ['交叉污染'], controlTags: ['HEPA 状态', '洁净度记录', '禁止处理挥发性危险物'] }),
  biosafety_cabinet: definition('containment', '生物安全柜 II 级', { hazardTags: ['生物气溶胶'], controlTags: ['HEPA 年检', '消毒记录', '生物安全边界'] }),
  glovebox: definition('containment', '手套箱 / 惰性气氛箱', { aliases: ['无水无氧操作箱'], hazardTags: ['缺氧窒息', '可燃溶剂蒸气'], controlTags: ['O₂/H₂O 指标', '气密性', '再生记录'], utilityRequirements: ['惰性气体', '排风'] }),
  bench: definition('workstation', '防腐蚀化学操作台', { controlTags: ['台面材质', '溢洒盘', '动线与应急通道'] }),
  balance: definition('workstation', '分析天平 / 微量称量台', { hazardTags: ['粉尘暴露', '静电'], controlTags: ['校准砝码', '防风罩', '称量环境'] }),
  centrifuge: definition('separation', '冷冻离心机', { hazardTags: ['高速旋转', '气溶胶'], controlTags: ['转子寿命', '配平', '密封杯'] }),
  gc: definition('separation', '气相色谱 GC', { aliases: ['GC-FID', 'GC-ECD'], hazardTags: ['高温', '可燃氢气', '载气压力'], controlTags: ['载气检查', '点火源控制', '废气导出'], utilityRequirements: ['载气', '电源', '排风'] }),
  hplc: definition('separation', '高效液相色谱 HPLC', { hazardTags: ['高压', '有机溶剂'], controlTags: ['柱压上限', '废液分类', '溶剂相容性'] }),
  chromatography: definition('separation', '超高效液相色谱 UPLC', { hazardTags: ['超高压', '有机溶剂'], controlTags: ['方法版本', '柱压联锁', '废液容量'] }),
  preparative_hplc: definition('separation', '制备液相色谱', { hazardTags: ['高压', '大体积有机溶剂'], controlTags: ['流动相库存', '废液容量', '柱压'] }),
  ion_chromatography: definition('separation', '离子色谱 IC', { hazardTags: ['高压', '酸碱淋洗液'], controlTags: ['抑制器状态', '淋洗液记录', '废液分类'] }),
  solid_phase_extraction: definition('separation', '固相萃取系统 SPE', { hazardTags: ['有机溶剂', '真空'], controlTags: ['真空等级', '柱型兼容性', '交叉污染控制'] }),
  evaporator: definition('separation', '旋转蒸发仪', { hazardTags: ['真空', '玻璃破裂', '溶剂蒸气'], controlTags: ['冷却水', '真空破坏', '冷阱与尾气'] }),
  nitrogen_blowdown: definition('separation', '氮吹浓缩仪', { hazardTags: ['氮气窒息', '溶剂蒸气', '加热'], controlTags: ['氮气压力', '局部排风', '温度上限'] }),
  mass_spec: definition('mass_analysis', '三重四极杆 / 高分辨质谱', { hazardTags: ['高压电', '真空', '氮气'], controlTags: ['真空状态', '离子源', '校准液与方法版本'], utilityRequirements: ['氮气', '真空', '排风'] }),
  icp_ms: definition('mass_analysis', '电感耦合等离子体质谱 ICP-MS', { hazardTags: ['高温等离子体', '酸雾', '氩气'], controlTags: ['氩气纯度', '酸消解', '尾气排放'] }),
  icp_oes: definition('mass_analysis', '电感耦合等离子体发射光谱 ICP-OES', { hazardTags: ['高温等离子体', '酸雾'], controlTags: ['氩气', '样品引入', '尾气'] }),
  elemental_analyzer: definition('mass_analysis', '元素分析仪 CHNS/O', { hazardTags: ['高温燃烧', '氧气'], controlTags: ['载气', '燃烧管维护', '粉体称量'] }),
  aas: definition('mass_analysis', '原子吸收光谱仪 AAS', { hazardTags: ['火焰', '乙炔', '高温'], controlTags: ['燃气联锁', '火焰检查', '排风'] }),
  xrf: definition('mass_analysis', 'X 射线荧光光谱仪 XRF', { hazardTags: ['X 射线辐射'], controlTags: ['联锁', '辐射指示', '样品腔完整性'], evidenceKinds: ['sop', 'inspection', 'training', 'permit'] as EvidenceKind[] }),
  uv_vis: definition('spectroscopy', '紫外可见分光光度计', { hazardTags: ['紫外辐射', '溶剂'], controlTags: ['光源状态', '比色皿兼容性'] }),
  ftir: definition('spectroscopy', '傅里叶变换红外 FTIR', { hazardTags: ['红外光源', '激光附件'], controlTags: ['附件互锁', '样品制备'] }),
  raman: definition('spectroscopy', '拉曼 / 显微拉曼', { hazardTags: ['激光'], controlTags: ['激光等级', '护目镜', '样品热损伤'], evidenceKinds: ['sop', 'inspection', 'training', 'calibration'] as EvidenceKind[] }),
  nmr: definition('spectroscopy', '液体 / 固体核磁 NMR', { hazardTags: ['强磁场', '液氮/液氦', '低温'], controlTags: ['禁带区', '铁磁物品检查', '样品管与转子'], utilityRequirements: ['冷却水', '液氮/液氦'] }),
  epr: definition('spectroscopy', '电子顺磁共振 EPR/ESR', { hazardTags: ['强磁场', '微波', '低温'], controlTags: ['禁带区', '波导与腔体', '样品兼容性'] }),
  xrd: definition('structure_material', '单晶 / 粉末 X 射线衍射 XRD', { hazardTags: ['X 射线辐射', '粉尘'], controlTags: ['辐射联锁', '指示灯', '样品腔'] }),
  xps: definition('structure_material', 'X 射线光电子能谱 XPS', { hazardTags: ['X 射线辐射', '超高真空'], controlTags: ['样品放气', '真空状态', '联锁'] }),
  sem: definition('structure_material', '扫描电子显微镜 SEM', { hazardTags: ['高压', '电子束', '真空'], controlTags: ['高压联锁', '样品导电性', '真空记录'] }),
  tem: definition('structure_material', '透射电子显微镜 TEM', { hazardTags: ['高压', '电子束', '真空'], controlTags: ['样品制备', '高压联锁', '真空记录'] }),
  afm: definition('structure_material', '原子力显微镜 AFM', { hazardTags: ['探针破损', '振动'], controlTags: ['防振', '探针登记', '样品洁净'] }),
  spr: definition('structure_material', '表面等离子共振 SPR', { hazardTags: ['微流控泄漏', '生物样品'], controlTags: ['芯片兼容性', '流路清洗', '废液'] }),
  dls: definition('structure_material', '动态光散射 DLS', { hazardTags: ['激光', '样品污染'], controlTags: ['激光联锁', '样品池洁净'] }),
  bet: definition('structure_material', '比表面积 / 孔径分析 BET', { hazardTags: ['高温脱气', '液氮', '真空'], controlTags: ['脱气温度', '真空完整性', '低温供给'] }),
  tga: definition('thermal_process', '热重分析 TGA', { hazardTags: ['高温', '样品放气'], controlTags: ['气氛流量', '尾气导出', '坩埚兼容性'] }),
  dsc: definition('thermal_process', '差示扫描量热 DSC', { hazardTags: ['高温', '密封坩埚'], controlTags: ['样品质量', '温程', '密封检查'] }),
  reactor: definition('thermal_process', '反应釜 / 流动反应器', { hazardTags: ['高温高压', '反应失控'], controlTags: ['压力等级', '泄压路径', '温控联锁'], utilityRequirements: ['冷却水', '惰性气体'] }),
  microwave_reactor: definition('thermal_process', '微波合成 / 消解仪', { hazardTags: ['压力', '微波', '高温'], controlTags: ['溶剂适配', '腔体完整性', '压力联锁'] }),
  photoreactor: definition('thermal_process', '光化学反应器', { hazardTags: ['UV', '高温', '可燃溶剂'], controlTags: ['光源屏蔽', '门禁联锁', '冷却'] }),
  electrochemistry: definition('thermal_process', '电化学工作站 / 电解槽', { hazardTags: ['电击', '腐蚀性电解液', '气体析出'], controlTags: ['电源隔离', '电极兼容性', '气体排放'] }),
  drying_oven: definition('thermal_process', '鼓风 / 真空干燥箱', { hazardTags: ['高温', '挥发性物料'], controlTags: ['超温保护', '禁限用物料', '通风'] }),
  furnace: definition('thermal_process', '马弗炉 / 管式炉', { hazardTags: ['高温', '气氛', '灼伤'], controlTags: ['温控联锁', '炉管检查', '防烫'] }),
  refrigerator: definition('cold_chain', '防爆冷藏柜', { hazardTags: ['易燃溶剂', '温度失控'], controlTags: ['防爆等级', '库存上限', '温度报警'] }),
  freezer: definition('cold_chain', '-20℃ / -80℃ 低温冰箱', { hazardTags: ['低温', '断电风险'], controlTags: ['温度报警', '断电预案', '样品台账'] }),
  liquid_nitrogen: definition('cold_chain', '液氮罐 / 低温供给', { hazardTags: ['缺氧', '冻伤', '压力释放'], controlTags: ['通风', '液位', '压力释放'] }),
  cold_trap: definition('cold_chain', '低温冷阱', { hazardTags: ['冻伤', '真空', '冷凝物'], controlTags: ['冷凝物兼容性', '真空破坏', '防冻'] }),
  gas_cabinet: definition('gas_vacuum', '气瓶柜', { hazardTags: ['可燃/有毒气体', '泄漏'], controlTags: ['固定', '泄漏检测', '分区与双阀'], evidenceKinds: ['sop', 'inspection', 'training', 'permit'] as EvidenceKind[] }),
  gas_manifold: definition('gas_vacuum', '气体汇流排 / 气路面板', { hazardTags: ['高压气体', '回火', '泄漏'], controlTags: ['减压器', '材料兼容', '气路标识'] }),
  vacuum_pump: definition('gas_vacuum', '干式 / 油式真空泵', { hazardTags: ['真空', '尾气', '油污染'], controlTags: ['回流防护', '尾气导出', '隔离阀'] }),
  exhaust_treatment: definition('gas_vacuum', '尾气吸收 / 净化装置', { hazardTags: ['有毒/腐蚀性尾气'], controlTags: ['吸收液', '压降', '饱和更换记录'] }),
  water_purification: definition('utility', '纯水 / 超纯水系统', { hazardTags: ['微生物污染', '漏水'], controlTags: ['电阻率记录', '滤芯更换', '漏水报警'] }),
  lyophilizer: definition('utility', '冷冻干燥机', { hazardTags: ['低温', '真空', '玻璃破裂'], controlTags: ['冷阱温度', '真空等级', '样品兼容性'] }),
  spray_dryer: definition('utility', '喷雾干燥机', { hazardTags: ['高温', '粉尘', '气溶胶'], controlTags: ['粉尘收集', '温度', '清洗记录'] }),
  co2_incubator: definition('bio_molecular', '二氧化碳培养箱', { hazardTags: ['CO₂ 缺氧', '生物污染'], controlTags: ['CO₂ 报警', '消毒记录', '温湿度'] }),
  pcr: definition('bio_molecular', 'PCR / 实时荧光 PCR', { hazardTags: ['扩增产物污染'], controlTags: ['前后区分离', '污染控制', '热循环记录'] }),
  gel_documentation: definition('bio_molecular', '凝胶成像系统', { hazardTags: ['UV/蓝光', '染料废物'], controlTags: ['光源屏蔽', '染料废液分类'] }),
  electrophoresis: definition('bio_molecular', '电泳系统', { hazardTags: ['高压电', '染料/缓冲液'], controlTags: ['电源隔离', '缓冲液与废液'] }),
  flow_cytometer: definition('bio_molecular', '流式细胞仪', { hazardTags: ['生物气溶胶', '高压液路'], controlTags: ['样品边界', '鞘液', '废液消毒'] }),
  fluorescence_microscope: definition('bio_molecular', '荧光 / 共聚焦显微镜', { hazardTags: ['激光/汞灯', '生物样品'], controlTags: ['光源联锁', '样品固定与废弃'] }),
  cleanroom: definition('containment', '洁净室 / 负压操作间', { hazardTags: ['压差失控', '交叉污染'], controlTags: ['压差', '换气', '门禁与进入培训'] }),
  eyewash: definition('safety_response', '洗眼器', { hazardTags: ['化学暴露应急'], controlTags: ['可达距离', '周检', '水质与水压'], evidenceKinds: ['inspection', 'training', 'sensor'] as EvidenceKind[] }),
  safety_shower: definition('safety_response', '紧急喷淋', { hazardTags: ['化学暴露应急'], controlTags: ['30 m 内可达', '月检', '常开阀与无遮挡'], evidenceKinds: ['inspection', 'training', 'sensor'] as EvidenceKind[] }),
  gas_detector: definition('safety_response', '可燃/有毒气体探测器', { hazardTags: ['气体泄漏'], controlTags: ['传感器校准', '报警联动排风', '报警记录'], evidenceKinds: ['inspection', 'calibration', 'sensor'] as EvidenceKind[] }),
  environment_monitor: definition('waste_environment', '温湿度 / 压差 / VOC 监测点', { hazardTags: ['环境偏离'], controlTags: ['阈值', '校准', '数据完整性'], evidenceKinds: ['inspection', 'calibration', 'sensor'] as EvidenceKind[] }),
  flammable_cabinet: definition('waste_environment', '化学品防爆柜', { hazardTags: ['易燃溶剂'], controlTags: ['接地', '库存上限', '分区与托盘'] }),
  acid_base_cabinet: definition('waste_environment', '酸碱柜 / 腐蚀品柜', { hazardTags: ['腐蚀性化学品'], controlTags: ['相容性分区', '托盘', '标签'] }),
  solvent_waste: definition('waste_environment', '有机废液柜', { hazardTags: ['易燃废液', '有毒蒸气'], controlTags: ['相容性', '容器标签', '容量与转运'] }),
  solid_waste: definition('waste_environment', '固体危废暂存柜', { hazardTags: ['污染耗材', '交叉污染'], controlTags: ['分类包装', '称重', '转运记录'] }),
  access_control: definition('safety_response', '门禁 / 访客终端', { hazardTags: ['未授权进入'], controlTags: ['培训授权', '访问日志', '紧急解锁'], evidenceKinds: ['training', 'permit', 'sensor'] as EvidenceKind[] }),
}

export function profileForKind(kind: Kind): EquipmentOperationalProfile {
  const found = TAXONOMY[kind]
  return {
    family: found?.family || 'utility',
    subtype: found?.subtype || kind,
    aliases: found?.aliases || [],
    typicalUse: found?.typicalUse || '共享实验室资源',
    hazardTags: found?.hazardTags || [],
    controlTags: found?.controlTags || ['关联当前 SOP', '核对设备状态与适用范围'],
    utilityRequirements: found?.utilityRequirements || [],
    requiredTraining: found?.requiredTraining || ['设备使用培训'],
    calibrationOrInspection: found?.calibrationOrInspection || ['检查记录与规格版本'],
    evidenceKinds: found?.evidenceKinds || ['sop', 'inspection', 'training', 'calibration'],
    sourceRefs: found?.sourceRefs || SOURCE_REFS,
  }
}

export { TAXONOMY }
