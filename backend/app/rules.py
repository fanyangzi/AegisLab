"""Deterministic policy rules used before any optional LLM assistance."""

from typing import List

from .models import Evaluation, Review, ReviewStatus, RuleResult, Severity, utcnow, HazardClass


_WEIGHTS = {Severity.LOW: 2.0, Severity.MEDIUM: 4.0, Severity.HIGH: 7.0, Severity.CRITICAL: 10.0}


class ReviewRuleEngine:
    version = "2026.10"

    def _result(self, rule_id: str, passed: bool, message: str, severity: Severity = Severity.LOW,
                details: dict | None = None, evidence_refs: list[str] | None = None,
                recommended_control: str | None = None, source: str = "AegisLab rule pack") -> RuleResult:
        return RuleResult(
            rule_id=rule_id,
            passed=passed,
            message=message,
            severity=severity,
            details=details or {},
            rule_version=self.version,
            evidence_refs=evidence_refs or [],
            recommended_control=recommended_control,
            source=source,
        )

    def evaluate(self, review: Review) -> Evaluation:
        results: List[RuleResult] = []

        has_objective = bool(review.objective.strip())
        results.append(self._result(
            rule_id="objective-required",
            passed=has_objective,
            message="Review objective is present" if has_objective else "A review objective is required",
            severity=Severity.HIGH if not has_objective else Severity.LOW,
            recommended_control="补充实验目的、边界和操作者角色" if not has_objective else None,
        ))

        sop_ok = bool((review.sop or "").strip())
        results.append(self._result(
            rule_id="sop-required",
            passed=sop_ok,
            message="Approved SOP is attached" if sop_ok else "A written SOP is required for a chemical experiment",
            severity=Severity.HIGH if not sop_ok else Severity.LOW,
            recommended_control="附加当前版本 SOP，并保留输入哈希" if not sop_ok else None,
        ))

        step_failures = [step.order for step in review.steps if not step.controls or (step.hazard and not step.requires_ppe)]
        step_refs = [ref for step in review.steps for ref in step.evidence_refs]
        results.append(self._result(
            rule_id="step-controls",
            passed=not step_failures,
            message="Each hazardous step has controls and PPE" if not step_failures else "Hazardous steps need controls and PPE",
            severity=Severity.HIGH if step_failures else Severity.LOW,
            details={"steps": step_failures},
            evidence_refs=step_refs,
            recommended_control="为每个危险步骤补充控制措施和 PPE" if step_failures else None,
        ))

        hazardous_substances = [substance for substance in review.substances if any(hazard != HazardClass.NONE for hazard in substance.hazard_classes)]
        substance_failures = [substance.name for substance in hazardous_substances if not substance.storage or not substance.sds_reference]
        results.append(self._result(
            rule_id="substance-register",
            passed=not substance_failures,
            message="Hazardous substances have storage and SDS references" if not substance_failures else "Hazardous substances need storage and SDS references",
            severity=Severity.HIGH if substance_failures else Severity.LOW,
            details={"substances": substance_failures},
            recommended_control="补充 SDS 引用、储存位置和容器标识" if substance_failures else None,
        ))

        reactive_names = [s.name for s in hazardous_substances if HazardClass.REACTIVE in s.hazard_classes or HazardClass.OXIDIZER in s.hazard_classes]
        emergency_ok = not reactive_names or bool(review.emergency_controls)
        results.append(self._result(
            rule_id="emergency-controls",
            passed=emergency_ok,
            message="Emergency controls cover reactive substances" if emergency_ok else "Reactive or oxidizing substances require emergency controls",
            severity=Severity.CRITICAL if not emergency_ok else Severity.LOW,
            details={"substances": reactive_names},
            recommended_control="补充机构批准的应急资源、停止条件和人工负责人" if not emergency_ok else None,
        ))

        volatile = any(
            any(token in (step.instruction + " " + (step.hazard or "")) for token in ("挥发", "溶剂", "转移", "蒸发", "萃取", "色谱"))
            for step in review.steps
        ) or any(HazardClass.FLAMMABLE in s.hazard_classes or HazardClass.TOXIC in s.hazard_classes for s in hazardous_substances)
        ventilation_ok = not volatile or bool(review.ventilation) or any("通风" in c or "排风" in c for step in review.steps for c in step.controls)
        ventilation_refs = [ref for step in review.steps if step.ventilation for ref in step.evidence_refs]
        results.append(self._result(
            rule_id="ventilation-required",
            passed=ventilation_ok,
            message="Volatile/toxic work has a ventilation control" if ventilation_ok else "Volatile or toxic solvent work needs a recorded ventilation control",
            severity=Severity.CRITICAL if not ventilation_ok else Severity.LOW,
            evidence_refs=ventilation_refs,
            recommended_control="指定通风柜或有效局部排风，并记录检查结果" if not ventilation_ok else None,
        ))

        has_waste_language = "废液" in (review.sop or "") or any(step.waste_stream or "废液" in step.instruction for step in review.steps)
        waste_ok = not has_waste_language or bool(review.waste_streams) or any(step.waste_stream for step in review.steps)
        results.append(self._result(
            rule_id="waste-stream-required",
            passed=waste_ok,
            message="Waste stream is identified" if waste_ok else "Organic waste must have a labeled compatible stream",
            severity=Severity.HIGH if not waste_ok else Severity.LOW,
            recommended_control="指定有机废液类别、容器和标签要求" if not waste_ok else None,
        ))

        incompatibility = bool({HazardClass.OXIDIZER, HazardClass.REACTIVE}.intersection({h for s in hazardous_substances for h in s.hazard_classes})) and any(HazardClass.FLAMMABLE in s.hazard_classes for s in hazardous_substances)
        incompatibility_ok = not incompatibility or bool(review.emergency_controls) or any("分开" in step.instruction or "相容" in c for step in review.steps for c in step.controls)
        results.append(self._result(
            rule_id="incompatibility-separation",
            passed=incompatibility_ok,
            message="Reactive and flammable materials have separation controls" if incompatibility_ok else "Potentially incompatible material classes need explicit separation controls",
            severity=Severity.CRITICAL if not incompatibility_ok else Severity.LOW,
            recommended_control="由安全负责人确认相容性、分区存放和废弃物流向" if not incompatibility_ok else None,
        ))

        incomplete = [f.title for f in review.findings if f.severity in (Severity.HIGH, Severity.CRITICAL) and (not f.owner or not f.remediation)]
        results.append(self._result(
            rule_id="high-risk-owner-remediation",
            passed=not incomplete,
            message="High-risk findings have an owner and remediation" if not incomplete else "High-risk findings need owner and remediation",
            severity=Severity.HIGH if incomplete else Severity.LOW,
            details={"findings": incomplete},
            recommended_control="为每个高风险发现指定负责人、完成期限和缓解措施" if incomplete else None,
        ))

        required_gate_failures = [g.name for g in review.gates if g.required and g.status not in ("passed", "waived")]
        results.append(self._result(
            rule_id="approval-gates",
            passed=not required_gate_failures,
            message="All required approval gates passed" if not required_gate_failures else "Required approval gates are still pending",
            severity=Severity.HIGH if required_gate_failures else Severity.LOW,
            details={"gates": required_gate_failures},
            recommended_control="完成安全负责人审批闸门" if required_gate_failures else None,
        ))

        high_risk = any(f.severity in (Severity.HIGH, Severity.CRITICAL) for f in review.findings) or bool(hazardous_substances)
        evidence_ok = bool(review.evidence) if high_risk else True
        results.append(self._result(
            rule_id="evidence-for-risk",
            passed=evidence_ok,
            message="Evidence is attached for the risk profile" if evidence_ok else "At least one evidence item is required for high-risk findings",
            severity=Severity.HIGH if not evidence_ok else Severity.LOW,
            recommended_control="关联 SOP 原文、SDS 或设备检查证据" if not evidence_ok else None,
        ))

        finding_score = sum(_WEIGHTS[f.severity] for f in review.findings)
        substance_score = sum(6.0 for substance in hazardous_substances)
        denominator = max(1, len(review.findings) + len(hazardous_substances))
        risk_score = min(10.0, round((finding_score + substance_score) / denominator, 2))
        eligible = all(result.passed for result in results)
        recommendation = ReviewStatus.APPROVED if eligible else ReviewStatus.REJECTED
        return Evaluation(
            review_id=review.id,
            eligible=eligible,
            recommendation=recommendation,
            results=results,
            risk_score=risk_score,
            evaluated_at=utcnow(),
        )
