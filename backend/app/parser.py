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


def _classify_occurrence(text: str, term: str, index: int) -> str:
    """Classify one occurrence of ``term`` using its preceding clause."""
    clause_start = max(text.rfind("，", 0, index), text.rfind(",", 0, index), text.rfind("；", 0, index), text.rfind(";", 0, index), text.rfind("。", 0, index)) + 1
    prefix = text[clause_start:index]
    suffix_end = len(text)
    for mark in ("，", ",", "；", ";", "。"):
        found = text.find(mark, index + len(term))
        if found >= 0:
            suffix_end = min(suffix_end, found)
    suffix = text[index + len(term):suffix_end]
    if re.search(r"(?:未(?:检查|确认|配备|开启|设置|使用)?|没有|无|尚未|未曾|不(?:使用|需要)?|未能)$", prefix):
        return "negated"
    if re.search(r"(?:未(?:检查|确认|配备|开启|设置|使用)?|没有|尚未|未确认|未检查)[^，,；;。]{0,10}$", suffix):
        return "negated"
    if re.search(r"(?:若|如果|如|条件是|在必要时|必要时).{0,12}$", prefix):
        return "conditional"
    if re.search(r"(?:拟|计划|将|准备|建议)(?:采用|使用|设置|配备|补充|确认)?$", prefix):
        return "proposed"
    if re.search(r"(?:曾经|历史|过去|上周|此前|之前|去年|历史上).{0,8}$", prefix):
        return "historical"
    return "satisfied"


def _assertion_state(text: str, term: str) -> str:
    """Classify a mention before promoting it to a satisfied control.

    The parser is deliberately conservative: a negated, conditional, planned
    or historical mention remains a typed assertion and never becomes a live
    control merely because a keyword is present.
    """
    index = text.find(term)
    if index < 0:
        return "absent"
    return _classify_occurrence(text, term, index)


def _term_state(text: str, terms: tuple[str, ...]) -> str:
    """Return the strongest state for any occurrence of a semantic term.

    A satisfied occurrence is accepted only when the source contains one;
    otherwise the most conservative non-live state is retained.  This keeps
    aggregate fields from turning a sentence such as ``未检查通风柜`` into a
    satisfied ventilation control merely because the keyword is present.
    """
    states: list[str] = []
    for term in terms:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            # Do not let the short alias ``通风`` create a second satisfied
            # occurrence inside a negated ``通风柜`` mention.
            if term == "通风" and text[index:index + len("通风柜")] == "通风柜":
                start = index + len(term)
                continue
            states.append(_classify_occurrence(text, term, index))
            start = index + len(term)
    if "satisfied" in states:
        return "satisfied"
    for state in ("negated", "conditional", "proposed", "historical"):
        if state in states:
            return state
    return "absent"


def parse_sop(text: str) -> Dict[str, Any]:
    source_lines = [(line_no, raw.strip()) for line_no, raw in enumerate(text.splitlines(), 1) if raw.strip()]
    lines = [line for _, line in source_lines]
    steps: List[LabStep] = []
    document_revision_id = f"docrev-{_hash(text)[:16]}"
    assertions: List[Dict[str, Any]] = []
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
        ventilation_state = _term_state(instruction, ("通风柜", "局部排风", "通风"))
        if ventilation_state == "satisfied":
            controls.append("在通风柜或有效局部排风下操作")
        if any(term in instruction for term in ("防火", "火源", "点火")):
            controls.append("移除点火源并确认防火边界")
        waste_state = _term_state(instruction, ("废液", "废弃物"))
        if waste_state == "satisfied":
            controls.append("按相容性和类别分流并标识废液")
        if "分液漏斗" in instruction:
            equipment.append("分液漏斗")
        if "旋转蒸发" in instruction or "蒸发" in instruction:
            equipment.append("旋转蒸发仪")
        if "色谱" in instruction:
            equipment.append("色谱柱/收集容器")
        for term, normalized in PPE_TERMS.items():
            if term in instruction and _assertion_state(instruction, term) == "satisfied":
                ppe.append(normalized)
        waste_stream = "有机废液" if waste_state == "satisfied" else None
        ventilation = "通风柜" if ventilation_state == "satisfied" else None
        for subject, state in (("ventilation", ventilation_state), ("waste_stream", waste_state)):
            if state not in ("absent", "satisfied"):
                assertions.append({"subject": subject, "state": state, "line": line_no, "text": line, "documentRevisionId": document_revision_id})
        for term, normalized in PPE_TERMS.items():
            if term in instruction:
                state = _assertion_state(instruction, term)
                if state != "satisfied":
                    assertions.append({"subject": normalized, "state": state, "line": line_no, "text": line, "documentRevisionId": document_revision_id})
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
            document_revision_id=document_revision_id,
            source_line=line_no,
            source_text_hash=_hash(line),
            control_assertions=[a for a in assertions if a.get("line") == line_no],
        ))

    if not steps and lines:
        steps.append(LabStep(order=1, instruction=lines[0], evidence_refs=[_evidence_id(1, lines[0])], document_revision_id=document_revision_id, source_line=1, source_text_hash=_hash(lines[0])))

    ppe = sorted({item for step in steps for item in step.requires_ppe})
    equipment = sorted({item for step in steps for item in step.equipment})
    # Only live, source-anchored step assertions become aggregate controls.
    # Mentions in a negation, condition, proposal or historical note remain in
    # ``control_assertions`` and therefore remain visible to the reviewer.
    ventilation = "通风柜" if any(step.ventilation for step in steps) else None
    waste_streams = ["有机废液"] if any(step.waste_stream for step in steps) else []
    return {
        "input_sha256": _hash(text),
        "steps": steps,
        "substances": substances,
        "ppe": ppe,
        "equipment": equipment,
        "ventilation": ventilation,
        "waste_streams": waste_streams,
        "document_revision_id": document_revision_id,
        "control_assertions": assertions,
        "evidence": [
            {
                "id": _evidence_id(i, line),
                "type": "document",
                "title": f"SOP 原文第 {i} 行",
                "content": line,
                "source": "user-provided SOP",
                "sha256": _hash(line),
                "metadata": {"line": i, "synthetic": False, "provenance": "user-provided"},
            }
            for i, line in source_lines
        ],
    }
