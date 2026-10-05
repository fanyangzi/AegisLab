"""Pydantic contracts and domain value objects for AegisLab.

The API intentionally uses plain JSON-friendly models so the same contracts can
be used by the offline demo, the UI, and a future event-driven adapter.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


class GateStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceType(str, Enum):
    TRACE = "trace"
    SCREENSHOT = "screenshot"
    LOG = "log"
    DOCUMENT = "document"
    METRIC = "metric"
    OTHER = "other"


class HazardClass(str, Enum):
    FLAMMABLE = "flammable"
    CORROSIVE = "corrosive"
    TOXIC = "toxic"
    OXIDIZER = "oxidizer"
    REACTIVE = "reactive"
    BIOLOGICAL = "biological"
    NONE = "none"


class LabStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order: int = Field(default=1, ge=1)
    instruction: str = Field(min_length=1, max_length=500)
    hazard: Optional[str] = None
    controls: List[str] = Field(default_factory=list)
    requires_ppe: List[str] = Field(default_factory=list)
    waste_stream: Optional[str] = None
    equipment: List[str] = Field(default_factory=list)
    ventilation: Optional[str] = None
    temperature_boundary: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)


class Substance(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=180)
    cas_number: Optional[str] = None
    amount: Optional[str] = None
    hazard_classes: List[HazardClass] = Field(default_factory=list)
    storage: Optional[str] = None
    sds_reference: Optional[str] = None


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="")
    severity: Severity = Severity.MEDIUM
    owner: Optional[str] = None
    remediation: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=0, le=10)
    tags: List[str] = Field(default_factory=list)
    rule_id: Optional[str] = None
    rule_version: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)
    source: Optional[str] = None


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EvidenceType = EvidenceType.OTHER
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(default="")
    source: Optional[str] = None
    sha256: Optional[str] = None
    collected_at: datetime = Field(default_factory=utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_url: Optional[str] = None
    source_version: Optional[str] = None
    license_or_terms: Optional[str] = None
    page_or_section: Optional[str] = None
    trace_id: Optional[str] = None


class ApprovalGate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="")
    required: bool = True
    status: GateStatus = GateStatus.PENDING
    approver: Optional[str] = None
    comment: Optional[str] = None
    decided_at: Optional[datetime] = None


class ReviewCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(default="")
    requester: str = Field(default="demo", max_length=160)
    system: Optional[str] = Field(default=None, max_length=160)
    findings: List[Finding] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    gates: List[ApprovalGate] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    experiment_name: Optional[str] = Field(default=None, max_length=240)
    sop: Optional[str] = None
    steps: List[LabStep] = Field(default_factory=list)
    substances: List[Substance] = Field(default_factory=list)
    ppe: List[str] = Field(default_factory=list)
    emergency_controls: List[str] = Field(default_factory=list)
    protocol_type: str = Field(default="organic_solvent", max_length=120)
    room: str = Field(default="Demo Lab A", max_length=160)
    equipment: List[str] = Field(default_factory=list)
    ventilation: Optional[str] = Field(default=None, max_length=240)
    waste_streams: List[str] = Field(default_factory=list)
    requester_role: str = Field(default="instructor", max_length=80)


class Review(BaseModel):
    id: str
    title: str
    objective: str
    requester: str
    system: Optional[str] = None
    status: ReviewStatus = ReviewStatus.DRAFT
    findings: List[Finding] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    gates: List[ApprovalGate] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decision_reason: Optional[str] = None
    experiment_name: Optional[str] = None
    sop: Optional[str] = None
    steps: List[LabStep] = Field(default_factory=list)
    substances: List[Substance] = Field(default_factory=list)
    ppe: List[str] = Field(default_factory=list)
    emergency_controls: List[str] = Field(default_factory=list)
    protocol_type: str = "organic_solvent"
    room: str = "Demo Lab A"
    equipment: List[str] = Field(default_factory=list)
    ventilation: Optional[str] = None
    waste_streams: List[str] = Field(default_factory=list)
    requester_role: str = "instructor"


class RuleResult(BaseModel):
    rule_id: str
    passed: bool
    message: str
    severity: Severity = Severity.LOW
    details: Dict[str, Any] = Field(default_factory=dict)
    rule_version: str = "2026.10"
    evidence_refs: List[str] = Field(default_factory=list)
    recommended_control: Optional[str] = None
    source: Optional[str] = None


class Evaluation(BaseModel):
    review_id: str
    eligible: bool
    recommendation: ReviewStatus
    results: List[RuleResult] = Field(default_factory=list)
    risk_score: float = Field(ge=0, le=10)
    evaluated_at: datetime = Field(default_factory=utcnow)
    llm_summary: Optional[str] = None


class DecisionRequest(BaseModel):
    decision: ReviewStatus
    actor: str = Field(default="reviewer", max_length=160)
    reason: str = Field(default="")


class GateDecisionRequest(BaseModel):
    status: GateStatus
    actor: str = Field(default="approver", max_length=160)
    comment: str = Field(default="")
    actor_role: str = Field(default="safety_owner", max_length=80)


class OverrideRequest(BaseModel):
    actor: str = Field(default="safety_owner", max_length=160)
    actor_role: str = Field(default="safety_owner", max_length=80)
    reason: str = Field(min_length=3, max_length=1000)
    mitigation: str = Field(min_length=3, max_length=1000)


class IncidentStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=180)
    expected: str = Field(default="")
    observed: Optional[str] = None
    passed: Optional[bool] = None
    options: List[str] = Field(default_factory=list)
    correct_option: Optional[int] = Field(default=None, ge=0)
    explanation: str = Field(default="")
    training_recommendation: str = Field(default="")


class IncidentDrillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scenario: str = Field(default="")
    owner: str = Field(default="incident-commander", max_length=160)
    steps: List[IncidentStep] = Field(default_factory=list)


class IncidentRunRequest(BaseModel):
    choices: Dict[str, int] = Field(default_factory=dict)
    actor: str = Field(default="trainee", max_length=160)


class IncidentDrill(BaseModel):
    id: str
    name: str
    scenario: str
    owner: str
    status: str = "planned"
    steps: List[IncidentStep] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None
    score: Optional[float] = Field(default=None, ge=0, le=100)
    feedback: List[str] = Field(default_factory=list)


class SOPParseRequest(BaseModel):
    title: str = Field(default="未命名实验 SOP", max_length=240)
    sop_text: str = Field(min_length=10, max_length=100000)
    requester: str = Field(default="demo", max_length=160)
    room: str = Field(default="Demo Lab A", max_length=160)


class SkillExecutionRequest(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    payload: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    llm_provider: str
    version: str
