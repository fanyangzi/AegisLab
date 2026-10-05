"""Application service coordinating repositories, rules and the audit trail."""

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from .db import SQLiteRepository
from .llm import LLMAdapter
from .models import (
    ApprovalGate, GateDecisionRequest, GateStatus, IncidentDrill, IncidentDrillCreate,
    IncidentRunRequest, IncidentStep, OverrideRequest, Review, ReviewCreate, ReviewStatus, DecisionRequest, Evaluation, utcnow, LabStep, Evidence,
)
from .rules import ReviewRuleEngine


def _model_validate(cls: Any, data: Dict[str, Any]) -> Any:
    return cls.model_validate(data) if hasattr(cls, "model_validate") else cls.parse_obj(data)


def _dump(model: Any) -> Dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


class AegisService:
    def __init__(self, repo: SQLiteRepository | None = None, rules: ReviewRuleEngine | None = None, llm: LLMAdapter | None = None):
        self.repo = repo or SQLiteRepository()
        self.rules = rules or ReviewRuleEngine()
        self.llm = llm or LLMAdapter()

    def create_review(self, payload: ReviewCreate) -> Review:
        now = utcnow()
        gates = payload.gates or [ApprovalGate(name="security-owner", description="Security owner approval")]
        data = _dump(payload)
        review = Review(id=str(uuid4()), status=ReviewStatus.DRAFT, gates=gates, created_at=now, updated_at=now, **{k: v for k, v in data.items() if k != "gates"})
        self.repo.save_review(review)
        self.repo.add_event("review", review.id, "created", review.requester, {"title": review.title})
        return review

    def get_review(self, review_id: str) -> Review:
        data = self.repo.get_review(review_id)
        if not data:
            raise KeyError(review_id)
        return _model_validate(Review, data)

    def list_reviews(self, limit: int = 50) -> List[Review]:
        return [_model_validate(Review, item) for item in self.repo.list_reviews(limit)]

    def submit_review(self, review_id: str, actor: str = "requester") -> Review:
        review = self.get_review(review_id)
        if review.status not in (ReviewStatus.DRAFT, ReviewStatus.REJECTED):
            return review
        review.status = ReviewStatus.IN_REVIEW
        review.submitted_at = utcnow()
        review.updated_at = utcnow()
        self.repo.save_review(review)
        self.repo.add_event("review", review.id, "submitted", actor, {})
        return review

    def add_evidence(self, review_id: str, evidence: Evidence, actor: str = "requester") -> Review:
        review = self.get_review(review_id)
        review.evidence.append(evidence)
        review.updated_at = utcnow()
        self.repo.save_review(review)
        self.repo.add_event("review", review.id, "evidence_added", actor, {"evidence_id": evidence.id, "title": evidence.title})
        return review

    def evaluate_review(self, review_id: str, with_llm: bool = True) -> Evaluation:
        review = self.get_review(review_id)
        evaluation = self.rules.evaluate(review)
        if with_llm:
            llm_result = self.llm.summarize(_dump(review), _dump(evaluation))
            evaluation.llm_summary = llm_result.text
        return evaluation

    def decide_review(self, review_id: str, request: DecisionRequest) -> Review:
        review = self.get_review(review_id)
        evaluation = self.rules.evaluate(review)
        if request.decision == ReviewStatus.APPROVED and not evaluation.eligible:
            raise ValueError("review is not eligible for approval; resolve failed rules first")
        if request.decision not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.CLOSED):
            raise ValueError("decision must be approved, rejected, or closed")
        review.status = request.decision
        review.decision_reason = request.reason
        review.decided_at = utcnow()
        review.updated_at = utcnow()
        self.repo.save_review(review)
        self.repo.add_event("review", review.id, "decision", request.actor, {"decision": request.decision, "reason": request.reason})
        return review

    def decide_gate(self, review_id: str, gate_id: str, request: GateDecisionRequest) -> Review:
        review = self.get_review(review_id)
        gate = next((item for item in review.gates if item.id == gate_id), None)
        if gate is None:
            raise KeyError(gate_id)
        if request.status in (GateStatus.PASSED, GateStatus.WAIVED) and request.actor_role not in {"safety_owner", "administrator", "ehs_manager"}:
            raise ValueError("only a safety owner or administrator can pass or waive an approval gate")
        if request.status == GateStatus.WAIVED and len(request.comment.strip()) < 3:
            raise ValueError("waiving a gate requires a recorded reason")
        gate.status = request.status
        gate.approver = request.actor
        gate.comment = request.comment
        gate.decided_at = utcnow()
        review.updated_at = utcnow()
        self.repo.save_review(review)
        self.repo.add_event("review", review.id, "gate_decision", request.actor, {"gate_id": gate_id, "status": request.status, "actor_role": request.actor_role, "comment": request.comment})
        return review

    def override_review(self, review_id: str, request: OverrideRequest) -> Review:
        if request.actor_role not in {"safety_owner", "administrator", "ehs_manager"}:
            raise ValueError("only a safety owner or administrator can override a high-risk review")
        review = self.get_review(review_id)
        evaluation = self.rules.evaluate(review)
        if not any(result.severity.value in {"high", "critical"} and not result.passed for result in evaluation.results):
            raise ValueError("override is only available when a high-risk rule is blocked")
        review.status = ReviewStatus.APPROVED
        review.decision_reason = f"Override: {request.reason}; mitigation: {request.mitigation}"
        review.decided_at = utcnow()
        review.updated_at = utcnow()
        self.repo.save_review(review)
        self.repo.add_event("review", review.id, "override", request.actor, {
            "actor_role": request.actor_role,
            "reason": request.reason,
            "mitigation": request.mitigation,
        })
        return review

    def events(self, review_id: str) -> List[Dict[str, Any]]:
        self.get_review(review_id)
        return self.repo.list_events("review", review_id)

    def create_incident(self, payload: IncidentDrillCreate) -> IncidentDrill:
        drill = IncidentDrill(id=str(uuid4()), created_at=utcnow(), **_dump(payload))
        self.repo.save_incident(drill)
        self.repo.add_event("incident", drill.id, "created", drill.owner, {"name": drill.name})
        return drill

    def get_incident(self, incident_id: str) -> IncidentDrill:
        data = self.repo.get_incident(incident_id)
        if not data:
            raise KeyError(incident_id)
        return _model_validate(IncidentDrill, data)

    def list_incidents(self, limit: int = 50) -> List[IncidentDrill]:
        return [_model_validate(IncidentDrill, item) for item in self.repo.list_incidents(limit)]

    def seed_incident_drills(self) -> List[IncidentDrill]:
        templates = [
            ("有机溶剂泄漏", "在有机溶剂转移环节发现容器外壁有泄漏迹象。", [
                IncidentStep(name="初始响应", expected="暂停操作并通知负责人", options=["继续完成转移", "暂停操作并通知负责人", "直接用手擦拭"], correct_option=1, explanation="应先停止相关操作并建立人员与区域控制。", training_recommendation="复训：泄漏发现后的第一响应。"),
                IncidentStep(name="区域控制", expected="隔离区域并确认通风状态", options=["隔离区域并确认通风状态", "关闭所有通风", "让无关人员进入查看"], correct_option=0, explanation="隔离和通风状态确认是后续处置的前置条件。", training_recommendation="复训：实验室区域隔离与通风确认。"),
            ]),
            ("通风设备故障", "操作中局部排风状态指示异常，实验步骤尚未完成。", [
                IncidentStep(name="停止暴露", expected="暂停挥发性操作并撤离暴露区域", options=["继续操作观察", "暂停操作并撤离暴露区域", "提高加热功率"], correct_option=1, explanation="通风异常时不能继续进行挥发性操作。", training_recommendation="复训：通风故障时的停止条件。"),
                IncidentStep(name="升级报告", expected="通知实验负责人并记录设备故障", options=["仅口头告诉同伴", "通知负责人并记录设备故障", "删除运行记录"], correct_option=1, explanation="设备故障需要进入可追溯的维修和复核流程。", training_recommendation="复训：设备故障的升级和留痕。"),
            ]),
            ("点火源异常", "易燃溶剂作业区附近出现未确认的热源或电火花风险。", [
                IncidentStep(name="点火源控制", expected="停止作业并移除或隔离点火源", options=["停止作业并隔离点火源", "继续转移并加快速度", "覆盖热源继续操作"], correct_option=0, explanation="易燃溶剂区域必须先消除未确认的点火源。", training_recommendation="复训：易燃溶剂作业的点火源检查。"),
                IncidentStep(name="负责人确认", expected="由安全负责人确认恢复条件", options=["自行宣布恢复", "由安全负责人确认恢复条件", "跳过审批直接恢复"], correct_option=1, explanation="恢复必须经过有权限的负责人确认。", training_recommendation="复训：高风险实验恢复前审批。"),
            ]),
        ]
        drills: List[IncidentDrill] = []
        for name, scenario, steps in templates:
            drills.append(self.create_incident(IncidentDrillCreate(name=name, scenario=scenario, owner="demo", steps=steps)))
        return drills

    def run_incident(self, incident_id: str, request: IncidentRunRequest | None = None) -> IncidentDrill:
        drill = self.get_incident(incident_id)
        choices = request.choices if request else {}
        drill.status = "completed"
        passed = 0
        feedback: List[str] = []
        for step in drill.steps:
            choice = choices.get(step.id)
            if choice is None or not step.options:
                step.observed = "未提交动作"
                step.passed = False
                feedback.append(f"{step.name}：未提交选择，需完成复训。{step.training_recommendation}".strip())
                continue
            step.observed = step.options[choice] if 0 <= choice < len(step.options) else "无效选项"
            step.passed = step.correct_option is not None and choice == step.correct_option
            if step.passed:
                passed += 1
            else:
                feedback.append(f"{step.name}：{step.explanation} {step.training_recommendation}".strip())
        drill.completed_at = utcnow()
        drill.score = round((passed / len(drill.steps) * 100) if drill.steps else 0, 2)
        drill.feedback = feedback
        self.repo.save_incident(drill)
        self.repo.add_event("incident", drill.id, "completed", request.actor if request else drill.owner, {"passed_steps": passed, "total_steps": len(drill.steps), "score": drill.score})
        return drill

    def seed_demo(self) -> Review:
        payload = ReviewCreate(
            title="Offline safety review",
            objective="在实验开始前核验有机溶剂转移、通风、PPE 和废液留痕。",
            requester="demo",
            requester_role="safety_owner",
            system="aegislab-demo",
            experiment_name="溶剂转移与蒸发（离线演示）",
            protocol_type="organic_solvent",
            room="Demo Lab A",
            ventilation="通风柜",
            equipment=["旋转蒸发仪"],
            waste_streams=["有机废液"],
            sop="SOP-ORG-002 v1.0\n1. 在通风柜内确认乙酸乙酯和甲苯容器标签。\n2. 佩戴护目镜、实验服和耐溶剂手套，将溶剂转移至旋转蒸发仪。\n3. 将残余溶剂收集至有机废液容器并完成标签。",
            steps=[
                LabStep(order=1, instruction="在通风柜内确认乙酸乙酯和甲苯容器标签。", hazard="挥发性有机溶剂", controls=["在通风柜内操作"], requires_ppe=["护目镜", "实验服"], ventilation="通风柜", equipment=["通风柜"], evidence_refs=["demo-sop-1"]),
                LabStep(order=2, instruction="佩戴护目镜、实验服和耐溶剂手套，将溶剂转移至旋转蒸发仪。", hazard="易燃溶剂转移", controls=["移除点火源"], requires_ppe=["护目镜", "实验服", "耐溶剂手套"], equipment=["旋转蒸发仪"], evidence_refs=["demo-sop-2"]),
                LabStep(order=3, instruction="将残余溶剂收集至有机废液容器并完成标签。", hazard="废液暴露", controls=["按类别分流并标识废液"], requires_ppe=["护目镜", "耐溶剂手套"], waste_stream="有机废液", evidence_refs=["demo-sop-3"]),
            ],
            substances=[],
            findings=[],
            evidence=[Evidence(title="离线演示 SOP", content="synthetic/demo protocol", source="AegisLab demo corpus", metadata={"synthetic": True})],
            metadata={"offline": True, "synthetic": True},
        )
        review = self.create_review(payload)
        return review
