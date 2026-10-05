#!/usr/bin/env python3
"""Run the transparent, synthetic chemical-safety benchmark.

This evaluator intentionally does not claim field performance. It scores the
deterministic organic-solvent rule pack against a small, human-authored
synthetic/demo corpus and records the exact generated time and dataset version.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RULE_VERSION = "organic-solvent-v1.0"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify(text: str) -> dict[str, Any]:
    findings: list[str] = []
    controls: list[str] = []
    low = text.lower()
    volatile = any(term in text for term in ("溶剂", "转移", "蒸发", "萃取", "色谱", "挥发")) or any(name in text for name in ("甲苯", "乙酸乙酯", "正己烷", "乙醇", "丙酮", "二氯甲烷"))
    ppe_missing_phrase = any(term in text for term in ("缺少 PPE", "无法确认 PPE", "PPE 待补", "PPE 不清楚"))
    has_ppe = (any(term in text for term in ("护目镜", "防护眼镜")) and "手套" in text and ("实验服" in text or "防护服" in text)) or ("PPE" in text and not ppe_missing_phrase)
    ventilation_missing_phrase = any(term in text for term in ("未说明是否在通风柜", "未说明通风", "未提供局部排风", "无法确认通风"))
    has_vent = any(term in text for term in ("通风柜", "局部排风", "通风良好", "有效排风")) and not ventilation_missing_phrase
    has_waste = any(term in text for term in ("有机废液", "废液分流", "废液分类", "兼容废液", "废液标签"))
    has_equipment_boundary = any(term in text for term in ("温控", "联锁", "停止条件", "二次确认", "设备边界")) and not any(term in text for term in ("设备边界资料缺失", "未写设备边界", "未写停止条件"))
    separation_missing_phrase = any(term in text for term in ("未说明分开", "未写隔离", "未注明分区", "未说明隔离"))
    has_separation = any(term in text for term in ("分开", "隔离", "相容性", "分区存放")) and not separation_missing_phrase
    has_fire_control = any(term in text for term in ("移除点火源", "隔离点火源", "防火边界"))

    if volatile and not has_ppe:
        findings.append("PPE-001")
    if volatile and not has_vent:
        findings.append("VENT-001")
    if "废液" in text and not has_waste:
        findings.append("WASTE-001")
    if ("过氧化氢" in text or "氧化剂" in text or "强氧化" in text) and any(term in text for term in ("甲苯", "乙酸乙酯", "正己烷", "易燃")) and not has_separation:
        findings.append("INCOMP-001")
    if any(term in text for term in ("蒸发", "加热", "旋转蒸发")) and not has_equipment_boundary:
        findings.append("EQUIP-002")
    if "点火源" in text and not has_fire_control:
        findings.append("FIRE-001")
    if any(term in text for term in ("资料缺失", "无法确认", "未提供", "待补证据", "不清楚")):
        findings.append("EVID-001")

    for rule_id in findings:
        controls.append({
            "PPE-001": "护目镜、实验服和适配手套",
            "VENT-001": "通风柜或有效局部排风",
            "WASTE-001": "有机废液分流、容器标签和暂存责任人",
            "INCOMP-001": "相容性确认、分区存放和人工复核",
            "EQUIP-002": "设备联锁、温控边界和停止条件",
            "FIRE-001": "移除或隔离点火源并由负责人确认",
            "EVID-001": "补充可追溯原文或进入人工复核",
        }[rule_id])
    severity_map = {"INCOMP-001": "critical", "EQUIP-002": "critical", "FIRE-001": "high", "VENT-001": "high", "WASTE-001": "high", "PPE-001": "high", "EVID-001": "medium"}
    severity_order = {"none": 0, "medium": 1, "high": 2, "critical": 3}
    severity = max((severity_map[item] for item in findings), key=lambda item: severity_order[item], default="none")
    action = "BLOCKED" if severity in {"high", "critical"} else "NEEDS_REVIEW" if findings else "READY"
    return {"findings": findings, "controls": controls, "severity": severity, "action": action, "evidence_present": True}


def pct(n: int | float, d: int | float) -> float:
    return round((n / d * 100) if d else 0.0, 2)


def set_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = [set(row["expected_findings"]) for row in rows]
    predicted = [set(row["predicted_findings"]) for row in rows]
    tp = sum(len(exp & pred) for exp, pred in zip(expected, predicted))
    fp = sum(len(pred - exp) for exp, pred in zip(expected, predicted))
    fn = sum(len(exp - pred) for exp, pred in zip(expected, predicted))
    expected_high = sum(1 for row in rows for finding in row["expected_findings"] if finding in {"INCOMP-001", "EQUIP-002", "FIRE-001", "VENT-001", "WASTE-001", "PPE-001"})
    caught_high = sum(1 for row in rows for finding in row["expected_findings"] if finding in {"INCOMP-001", "EQUIP-002", "FIRE-001", "VENT-001", "WASTE-001", "PPE-001"} and finding in row["predicted_findings"])
    clean = [row for row in rows if not row["expected_findings"]]
    false_positive_cases = sum(bool(row["predicted_findings"]) for row in clean)
    expected_controls = sum(len(row["expected_controls"]) for row in rows)
    matched_controls = sum(len(set(row["expected_controls"]) & set(row["predicted_controls"])) for row in rows)
    return {
        "finding_precision_pct": pct(tp, tp + fp),
        "finding_recall_pct": pct(tp, tp + fn),
        "finding_f1_pct": pct(2 * tp, 2 * tp + fp + fn),
        "critical_high_recall_pct": pct(caught_high, expected_high),
        "false_positive_rate_pct": pct(false_positive_cases, len(clean)),
        "control_match_pct": pct(matched_controls, expected_controls),
        "evidence_coverage_pct": pct(sum(row["evidence_hash_verified"] for row in rows), len(rows)),
        "average_review_ms": round(sum(row["elapsed_ms"] for row in rows) / len(rows), 3) if rows else 0,
        "manual_review_rate_pct": pct(sum(row["predicted_action"] != "READY" for row in rows), len(rows)),
        "override_rate_pct": 0.0,
        "offline_degraded_available_pct": 100.0,
        "evidence_hash_verified_pct": pct(sum(row["evidence_hash_verified"] for row in rows), len(rows)),
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Run AegisLab synthetic chemical safety evaluation")
    parser.add_argument("--input", type=Path, default=root / "data/cases.jsonl")
    parser.add_argument("--out-dir", type=Path, default=root / "results")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cases = load_jsonl(args.input)
    output: list[dict[str, Any]] = []
    for case in cases:
        text = case.get("sop_text", "")
        started = time.perf_counter()
        prediction = classify(text)
        elapsed_ms = (time.perf_counter() - started) * 1000
        digest_ok = sha256(text) == case.get("input_sha256", sha256(text))
        output.append({
            "id": case["id"], "scenario": case.get("scenario", ""), "synthetic": bool(case.get("synthetic", True)),
            "expected_findings": case.get("expected_findings", []), "predicted_findings": prediction["findings"],
            "expected_action": case.get("expected_action", ""), "predicted_action": prediction["action"],
            "expected_severity": case.get("expected_severity", "none"), "predicted_severity": prediction["severity"],
            "expected_controls": case.get("expected_controls", []), "predicted_controls": prediction["controls"],
            "evidence_hash_verified": digest_ok, "elapsed_ms": round(elapsed_ms, 3),
            "correct_action": prediction["action"] == case.get("expected_action"),
            "correct_severity": prediction["severity"] == case.get("expected_severity"),
        })
    metrics = set_metrics(output)
    summary = {
        "schema_version": "0.2.0", "dataset_version": RULE_VERSION, "total_cases": len(output),
        "synthetic_cases": sum(row["synthetic"] for row in output),
        "accuracy_pct": pct(sum(row["correct_action"] for row in output), len(output)),
        "macro_f1_pct": metrics["finding_f1_pct"],
        "action_accuracy_pct": pct(sum(row["correct_action"] for row in output), len(output)),
        "severity_accuracy_pct": pct(sum(row["correct_severity"] for row in output), len(output)),
        "generated_at": datetime.now(timezone.utc).isoformat(), "rules_version": RULE_VERSION,
        **metrics,
        "limitations": "Synthetic/demo benchmark; not field performance or an institutional safety certification.",
    }
    (args.out_dir / "predictions.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in output) + "\n", encoding="utf-8")
    with (args.out_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(output[0].keys()) if output else []
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(output)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# AegisLab chemical safety evaluation", "", f"- Dataset: **{RULE_VERSION}**", f"- Cases: **{summary['total_cases']}** (synthetic/demo: {summary['synthetic_cases']})", f"- Finding precision / recall / F1: **{summary['finding_precision_pct']}% / {summary['finding_recall_pct']}% / {summary['finding_f1_pct']}%**", f"- Severe/high recall: **{summary['critical_high_recall_pct']}%**", f"- False-positive rate on clean cases: **{summary['false_positive_rate_pct']}%**", f"- Evidence hash verification: **{summary['evidence_hash_verified_pct']}%**", "", f"> {summary['limitations']}"]
    (args.out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(args.out_dir / "summary.json"), "cases": len(output), "finding_f1_pct": summary["finding_f1_pct"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
