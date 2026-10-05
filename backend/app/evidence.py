"""Portable evidence package generation."""

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict


def _dump(model: Any) -> Dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def build_evidence_package(review: Any, evaluation: Any, events: Any) -> io.BytesIO:
    payload = {
        "package_version": "1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "review": _dump(review),
        "evaluation": _dump(evaluation),
        "audit_events": events,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        markdown = _markdown_summary(review, evaluation, events)
        archive.writestr("manifest.json", json.dumps({"files": ["review.json", "evaluation.json", "audit-events.json", "evidence.md"]}, indent=2))
        archive.writestr("review.json", json.dumps(_dump(review), default=str, ensure_ascii=False, indent=2))
        archive.writestr("evaluation.json", json.dumps(_dump(evaluation), default=str, ensure_ascii=False, indent=2))
        archive.writestr("audit-events.json", json.dumps(events, default=str, ensure_ascii=False, indent=2))
        archive.writestr("evidence.md", markdown)
    buffer.seek(0)
    return buffer


def _markdown_summary(review: Any, evaluation: Any, events: Any) -> str:
    review_data = _dump(review)
    evaluation_data = _dump(evaluation)
    lines = [
        "# AegisLab evidence bundle",
        "",
        f"- Review: {review_data.get('title', '')}",
        f"- Protocol type: {review_data.get('protocol_type', '')}",
        f"- Room: {review_data.get('room', '')}",
        f"- Input SHA-256: {review_data.get('metadata', {}).get('input_sha256', 'not recorded')}",
        f"- Rule recommendation: {evaluation_data.get('recommendation', '')}",
        f"- Risk score: {evaluation_data.get('risk_score', '')}",
        "",
        "## Rule results",
        "",
    ]
    for result in evaluation_data.get("results", []):
        mark = "PASS" if result.get("passed") else "BLOCK"
        lines.append(f"- **{mark}** `{result.get('rule_id')}` v{result.get('rule_version')}: {result.get('message')}")
        if result.get("evidence_refs"):
            lines.append(f"  - Evidence refs: {', '.join(result['evidence_refs'])}")
        if result.get("recommended_control"):
            lines.append(f"  - Recommended control: {result['recommended_control']}")
    lines.extend(["", "## Audit events", "", f"- Events: {len(events)}", "", "This bundle is an audit aid, not a safety certification."])
    return "\n".join(lines) + "\n"
