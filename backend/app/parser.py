"""Deterministic, evidence-preserving SOP parser used by the offline demo.

The parser intentionally extracts a small, reviewable vocabulary. An optional
LLM may later enrich the result, but it cannot execute document content or
replace the hard-rule checks.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from .models import HazardClass, LabStep, Substance


SUBSTANCES = {
    "甲苯": ("108-88-3", [HazardClass.FLAMMABLE, HazardClass.TOXIC]),
    "乙酸乙酯": ("141-78-6", [HazardClass.FLAMMABLE]),
    "正己烷": ("110-54-3", [HazardClass.FLAMMABLE, HazardClass.TOXIC]),
    "乙醇": ("64-17-5", [HazardClass.FLAMMABLE]),
    "丙酮": ("67-64-1", [HazardClass.FLAMMABLE]),
    "甲醇": ("67-56-1", [HazardClass.FLAMMABLE, HazardClass.TOXIC]),
    "乙腈": ("75-05-8", [HazardClass.FLAMMABLE, HazardClass.TOXIC]),
    "二氯甲烷": ("75-09-2", [HazardClass.TOXIC]),
    "浓硫酸": ("7664-93-9", [HazardClass.CORROSIVE, HazardClass.REACTIVE]),
    "过氧化氢": ("7722-84-1", [HazardClass.OXIDIZER, HazardClass.REACTIVE]),
}

PPE_TERMS = {
    "护目镜": "护目镜",
    "防护眼镜": "护目镜",
    "实验服": "实验服",
    "实验外套": "实验服",
    "耐溶剂手套": "耐溶剂手套",
    "手套": "化学防护手套",
    "面屏": "面屏",
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence_id(line_no: int, line: str) -> str:
    return f"sop-line-{line_no}-{_hash(line)[:10]}"


def parse_sop(text: str) -> Dict[str, Any]:
    source_lines = [(line_no, raw.strip()) for line_no, raw in enumerate(text.splitlines(), 1) if raw.strip()]
    lines = [line for _, line in source_lines]
    steps: List[LabStep] = []
    all_text = "\n".join(lines)
    substances: List[Substance] = []
    seen: set[str] = set()

    for name, (cas, hazards) in SUBSTANCES.items():
        if name in all_text:
            seen.add(name)
            substances.append(Substance(
                name=name,
                cas_number=cas,
                hazard_classes=hazards,
                storage="易燃液体柜" if HazardClass.FLAMMABLE in hazards else "腐蚀品柜",
                sds_reference=f"PubChem:{cas}; NIOSH Pocket Guide",
            ))

    for ordinal, (line_no, line) in enumerate(source_lines, 1):
        match = re.match(r"^(?:步骤\s*)?(\d+)[.、)）:]\s*(.+)$", line)
        order = int(match.group(1)) if match else ordinal
        instruction = match.group(2) if match else line
        refs = [_evidence_id(line_no, line)]
        lower = instruction.lower()
        hazard = None
        if any(term in instruction for term in ("转移", "蒸发", "萃取", "振摇", "加热", "废液", "色谱")):
            hazard = "有机溶剂暴露/火灾与废液风险"
        controls: List[str] = []
        ppe: List[str] = []
        equipment: List[str] = []
        if any(term in instruction for term in ("通风柜", "局部排风", "通风")):
            controls.append("在通风柜或有效局部排风下操作")
        if any(term in instruction for term in ("防火", "火源", "点火")):
            controls.append("移除点火源并确认防火边界")
        if any(term in instruction for term in ("废液", "废弃物")):
            controls.append("按相容性和类别分流并标识废液")
        if "分液漏斗" in instruction:
            equipment.append("分液漏斗")
        if "旋转蒸发" in instruction or "蒸发" in instruction:
            equipment.append("旋转蒸发仪")
        if "色谱" in instruction:
            equipment.append("色谱柱/收集容器")
        for term, normalized in PPE_TERMS.items():
            if term in instruction:
                ppe.append(normalized)
        waste_stream = "有机废液" if "废液" in instruction else None
        ventilation = "通风柜" if any(term in instruction for term in ("通风柜", "局部排风", "通风")) else None
        steps.append(LabStep(
            order=order,
            instruction=instruction,
            hazard=hazard,
            controls=controls,
            requires_ppe=sorted(set(ppe)),
            waste_stream=waste_stream,
            equipment=equipment,
            ventilation=ventilation,
            evidence_refs=refs,
        ))

    if not steps and lines:
        steps.append(LabStep(order=1, instruction=lines[0], evidence_refs=[_evidence_id(1, lines[0])]))

    ppe = sorted({item for step in steps for item in step.requires_ppe})
    equipment = sorted({item for step in steps for item in step.equipment})
    ventilation = "通风柜" if "通风柜" in all_text or "局部排风" in all_text else None
    waste_streams = ["有机废液"] if "废液" in all_text else []
    return {
        "input_sha256": _hash(text),
        "steps": steps,
        "substances": substances,
        "ppe": ppe,
        "equipment": equipment,
        "ventilation": ventilation,
        "waste_streams": waste_streams,
        "evidence": [
            {
                "id": _evidence_id(i, line),
                "type": "document",
                "title": f"SOP 原文第 {i} 行",
                "content": line,
                "source": "user-provided SOP",
                "sha256": _hash(line),
                "metadata": {"line": i, "synthetic": True},
            }
            for i, line in source_lines
        ],
    }
