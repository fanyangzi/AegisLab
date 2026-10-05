"""A small, auditable Skill Registry and non-executing Harness.

Skills receive JSON-like values only. The harness never evaluates uploaded
text, starts a shell, imports a user path, or executes document content.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from .parser import parse_sop


SKILL_METADATA = [
    {"name": "parse_sop", "kind": "deterministic", "description": "Extract steps and evidence spans from SOP text."},
    {"name": "normalize_substances", "kind": "deterministic", "description": "Normalize known chemical names and hazard classes."},
    {"name": "extract_controls", "kind": "deterministic", "description": "Extract PPE, ventilation, equipment and waste controls."},
    {"name": "run_hazard_rules", "kind": "policy", "description": "Run versioned hard safety rules."},
    {"name": "generate_review_summary", "kind": "llm_optional", "description": "Generate a bounded review explanation with offline fallback."},
    {"name": "run_incident_branch", "kind": "state_machine", "description": "Score a pre-authored incident branch."},
    {"name": "export_evidence_bundle", "kind": "deterministic", "description": "Export JSON and Markdown evidence records."},
]


class SafeHarness:
    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            "parse_sop": lambda payload: parse_sop(str(payload.get("sop_text", ""))),
            "normalize_substances": lambda payload: parse_sop(str(payload.get("sop_text", ""))).get("substances", []),
            "extract_controls": lambda payload: {
                key: parse_sop(str(payload.get("sop_text", ""))).get(key)
                for key in ("ppe", "equipment", "ventilation", "waste_streams")
            },
        }

    def list(self) -> list[dict[str, str]]:
        return SKILL_METADATA

    def execute(self, name: str, payload: Dict[str, Any]) -> Any:
        if name not in self._handlers:
            raise ValueError(f"skill '{name}' is not exposed by the safe harness")
        return self._handlers[name](payload)
