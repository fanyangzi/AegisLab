"""Small end-to-end smoke checks for the offline domain service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db import SQLiteRepository
from backend.app.parser import parse_sop
from backend.app.service import AegisService
from backend.app.models import GateDecisionRequest, GateStatus, ReviewCreate


def main() -> None:
    repo = SQLiteRepository(":memory:")
    service = AegisService(repo=repo)
    text = "1. 在通风柜内处理甲苯。\n2. 佩戴护目镜、实验服和手套，收集有机废液。"
    parsed = parse_sop(text)
    assert parsed["input_sha256"]
    review = service.create_review(ReviewCreate(
        title="Smoke organic solvent review",
        objective="核验有机溶剂操作的前置安全控制。",
        sop=text,
        steps=parsed["steps"],
        substances=parsed["substances"],
        ppe=parsed["ppe"],
        ventilation=parsed["ventilation"],
        waste_streams=parsed["waste_streams"],
    ))
    evaluation = service.evaluate_review(review.id, with_llm=False)
    assert evaluation.review_id == review.id
    gate = review.gates[0]
    try:
        service.decide_gate(review.id, gate.id, GateDecisionRequest(status=GateStatus.PASSED, actor="student", actor_role="student"))
    except ValueError:
        pass
    else:
        raise AssertionError("student must not pass an approval gate")
    print("AegisLab smoke: PASS")


if __name__ == "__main__":
    main()
