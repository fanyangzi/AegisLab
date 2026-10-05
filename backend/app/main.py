"""FastAPI entry point for the AegisLab offline review console."""

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .evidence import build_evidence_package
from .llm import LLMAdapter
from .parser import parse_sop
from .skills import SafeHarness
from .models import (
    DecisionRequest, Evidence, GateDecisionRequest, HealthResponse, IncidentDrill, IncidentDrillCreate,
    IncidentRunRequest, OverrideRequest, Review, ReviewCreate, ReviewStatus, SOPParseRequest, SkillExecutionRequest,
)
from .service import AegisService


app = FastAPI(title="AegisLab Chemical Safety API", version="0.1.0", description="Offline-first chemical experiment safety review workflow")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = AegisService()
harness = SafeHarness()


def _not_found(error: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=f"resource not found: {error.args[0]}")


@app.get("/", tags=["system"])
def root() -> Dict[str, str]:
    return {"service": "aegislab", "message": "AegisLab API is running", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["system"])
@app.get("/api/health", response_model=HealthResponse, include_in_schema=False, tags=["system"])
def health() -> HealthResponse:
    llm_status = service.llm.status()
    return HealthResponse(status="ok", service="aegislab", database="ok" if service.repo.ping() else "degraded", llm_provider=llm_status["provider"], version=app.version)


@app.get("/llm/status", tags=["system"])
def llm_status() -> Dict[str, Any]:
    return service.llm.status()


@app.get("/skills", tags=["skills"])
def list_skills() -> List[Dict[str, str]]:
    return harness.list()


@app.post("/skills/execute", tags=["skills"])
def execute_skill(payload: SkillExecutionRequest) -> Dict[str, Any]:
    try:
        return {"skill": payload.skill, "result": harness.execute(payload.skill, payload.payload), "harness": "safe-json-only"}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/parse/sop", tags=["parser"])
@app.post("/api/parse/sop", include_in_schema=False, tags=["parser"])
def parse_sop_endpoint(payload: SOPParseRequest) -> Dict[str, Any]:
    parsed = parse_sop(payload.sop_text)
    return {"title": payload.title, "room": payload.room, **parsed}


@app.post("/reviews/from-sop", response_model=Review, status_code=201, tags=["parser"])
def create_review_from_sop(payload: SOPParseRequest) -> Review:
    parsed = parse_sop(payload.sop_text)
    return service.create_review(ReviewCreate(
        title=payload.title,
        experiment_name=payload.title,
        objective="在实验开始前核验有机溶剂实验的步骤、化学品、PPE、通风、设备和废液控制。",
        requester=payload.requester,
        requester_role="instructor",
        protocol_type="organic_solvent",
        room=payload.room,
        sop=payload.sop_text,
        steps=parsed["steps"],
        substances=parsed["substances"],
        ppe=parsed["ppe"],
        equipment=parsed["equipment"],
        ventilation=parsed["ventilation"],
        waste_streams=parsed["waste_streams"],
        evidence=[Evidence(**item) for item in parsed["evidence"]],
        metadata={"synthetic": True, "input_sha256": parsed["input_sha256"], "parser": "deterministic-sop-v1"},
    ))


@app.post("/reviews", response_model=Review, status_code=201, tags=["lab-reviews"])
@app.post("/api/reviews", response_model=Review, status_code=201, include_in_schema=False, tags=["lab-reviews"])
@app.post("/experiments", response_model=Review, status_code=201, include_in_schema=False, tags=["lab-reviews"])
@app.post("/lab/reviews", response_model=Review, status_code=201, include_in_schema=False, tags=["lab-reviews"])
def create_review(payload: ReviewCreate) -> Review:
    return service.create_review(payload)


@app.get("/reviews", response_model=List[Review], tags=["lab-reviews"])
@app.get("/api/reviews", response_model=List[Review], include_in_schema=False, tags=["lab-reviews"])
@app.get("/experiments", response_model=List[Review], include_in_schema=False, tags=["lab-reviews"])
def list_reviews(limit: int = 50) -> List[Review]:
    return service.list_reviews(max(1, min(limit, 200)))


@app.get("/reviews/{review_id}", response_model=Review, tags=["lab-reviews"])
@app.get("/api/reviews/{review_id}", response_model=Review, include_in_schema=False, tags=["lab-reviews"])
@app.get("/experiments/{review_id}", response_model=Review, include_in_schema=False, tags=["lab-reviews"])
def get_review(review_id: str) -> Review:
    try:
        return service.get_review(review_id)
    except KeyError as error:
        raise _not_found(error)


@app.post("/reviews/{review_id}/submit", response_model=Review, tags=["workflow"])
def submit_review(review_id: str, actor: str = "requester") -> Review:
    try:
        return service.submit_review(review_id, actor)
    except KeyError as error:
        raise _not_found(error)


@app.post("/reviews/{review_id}/evaluate", tags=["workflow"])
def evaluate_review(review_id: str, with_llm: bool = True) -> Dict[str, Any]:
    try:
        evaluation = service.evaluate_review(review_id, with_llm=with_llm)
        return evaluation.model_dump() if hasattr(evaluation, "model_dump") else evaluation.dict()
    except KeyError as error:
        raise _not_found(error)


@app.post("/reviews/{review_id}/evidence", response_model=Review, tags=["evidence"])
def add_evidence(review_id: str, evidence: Evidence, actor: str = "requester") -> Review:
    try:
        return service.add_evidence(review_id, evidence, actor)
    except KeyError as error:
        raise _not_found(error)


@app.post("/reviews/{review_id}/decision", response_model=Review, tags=["workflow"])
def decide_review(review_id: str, request: DecisionRequest) -> Review:
    try:
        return service.decide_review(review_id, request)
    except KeyError as error:
        raise _not_found(error)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@app.post("/reviews/{review_id}/gates/{gate_id}", response_model=Review, tags=["approval"])
def decide_gate(review_id: str, gate_id: str, request: GateDecisionRequest) -> Review:
    try:
        return service.decide_gate(review_id, gate_id, request)
    except KeyError as error:
        raise _not_found(error)
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error))


@app.post("/reviews/{review_id}/override", response_model=Review, tags=["approval"])
def override_review(review_id: str, request: OverrideRequest) -> Review:
    try:
        return service.override_review(review_id, request)
    except KeyError as error:
        raise _not_found(error)
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error))


@app.get("/reviews/{review_id}/events", tags=["audit"])
def review_events(review_id: str) -> List[Dict[str, Any]]:
    try:
        return service.events(review_id)
    except KeyError as error:
        raise _not_found(error)


@app.get("/reviews/{review_id}/evidence-package", tags=["evidence"])
def evidence_package(review_id: str) -> StreamingResponse:
    try:
        review = service.get_review(review_id)
        evaluation = service.evaluate_review(review_id)
        events = service.events(review_id)
    except KeyError as error:
        raise _not_found(error)
    filename = f"aegislab-{review.id}.zip"
    return StreamingResponse(build_evidence_package(review, evaluation, events), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.post("/workflow/evaluate", tags=["workflow"])
@app.post("/api/workflow/evaluate", include_in_schema=False, tags=["workflow"])
def one_shot_workflow(payload: ReviewCreate) -> Dict[str, Any]:
    review = service.create_review(payload)
    review = service.submit_review(review.id, payload.requester)
    evaluation = service.evaluate_review(review.id)
    dump = evaluation.model_dump() if hasattr(evaluation, "model_dump") else evaluation.dict()
    return {"review": review, "evaluation": dump}


@app.post("/demo/seed", response_model=Review, tags=["demo"])
def seed_demo() -> Review:
    return service.seed_demo()


@app.post("/demo/run", tags=["demo"])
def run_demo() -> Dict[str, Any]:
    review = service.seed_demo()
    for gate in review.gates:
        service.decide_gate(review.id, gate.id, GateDecisionRequest(status="passed", actor="demo", comment="offline demo approval"))
    review = service.submit_review(review.id, "demo")
    evaluation = service.evaluate_review(review.id)
    return {"review": service.get_review(review.id), "evaluation": evaluation}


@app.post("/demo/incidents/seed", response_model=List[IncidentDrill], tags=["demo"])
def seed_incident_drills() -> List[IncidentDrill]:
    return service.seed_incident_drills()


@app.post("/incidents", response_model=IncidentDrill, status_code=201, tags=["incident-drills"])
@app.post("/api/incidents", response_model=IncidentDrill, status_code=201, include_in_schema=False, tags=["incident-drills"])
@app.post("/drills", response_model=IncidentDrill, status_code=201, include_in_schema=False, tags=["incident-drills"])
def create_incident(payload: IncidentDrillCreate) -> IncidentDrill:
    return service.create_incident(payload)


@app.get("/incidents/{incident_id}", response_model=IncidentDrill, tags=["incidents"])
@app.get("/drills/{incident_id}", response_model=IncidentDrill, include_in_schema=False, tags=["incidents"])
def get_incident(incident_id: str) -> IncidentDrill:
    try:
        return service.get_incident(incident_id)
    except KeyError as error:
        raise _not_found(error)


@app.get("/incidents", response_model=List[IncidentDrill], tags=["incidents"])
@app.get("/drills", response_model=List[IncidentDrill], include_in_schema=False, tags=["incidents"])
def list_incidents(limit: int = 50) -> List[IncidentDrill]:
    return service.list_incidents(max(1, min(limit, 200)))


@app.post("/incidents/{incident_id}/run", response_model=IncidentDrill, tags=["incidents"])
@app.post("/drills/{incident_id}/run", response_model=IncidentDrill, include_in_schema=False, tags=["incidents"])
def run_incident(incident_id: str, request: IncidentRunRequest | None = None) -> IncidentDrill:
    try:
        return service.run_incident(incident_id, request)
    except KeyError as error:
        raise _not_found(error)
