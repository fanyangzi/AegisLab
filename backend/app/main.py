"""FastAPI entry point for the AegisLab offline review console."""

from typing import Any, Dict, List
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from .spatial import _merge_model_parse, local_owner

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .evidence import build_evidence_package
from .llm import LLMAdapter
from .parser import parse_sop
from .skills import SafeHarness
from .models import (
    DecisionRequest, Evidence, GateDecisionRequest, HealthResponse, IncidentDrill, IncidentDrillCreate,
    IncidentRunRequest, LabStep, OverrideRequest, Review, ReviewCreate, ReviewStatus, SOPParseRequest, SkillExecutionRequest, Substance,
)
from .service import AegisService


app = FastAPI(title="AegisLab Chemical Safety API", version="0.2.0", description="Browser-based laboratory review and resource workspace")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("AEGIS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173").split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def guard_browser_workspace(request: Request, call_next):
    # Static assets and preflight are handled normally; all API/legacy data routes
    # share the same owner guard. Local mode is not public multi-user auth.
    public = request.url.path in {"/", "/health", "/api/health"} or request.url.path.startswith("/assets/")
    if request.method != "OPTIONS" and not public:
        try:
            local_owner(request)
        except HTTPException as error:
            return JSONResponse({"detail": error.detail}, status_code=error.status_code)
    return await call_next(request)

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


@app.post("/parse/sop/ai-preview", tags=["parser"])
@app.post("/api/parse/sop/ai-preview", include_in_schema=False, tags=["parser"])
def ai_preview_sop(payload: SOPParseRequest) -> Dict[str, Any]:
    """Return a reviewable AI candidate before a spatial plan is saved.

    The deterministic parser always supplies the evidence-preserving baseline.
    If an OpenAI-compatible model is configured, it may enrich ambiguous SOP
    language.  The response is explicitly a candidate preview: it does not
    write a review, approve a plan, or replace the hard-rule checks.
    """
    parsed = parse_sop(payload.sop_text)
    llm_fields = service.llm.extract_sop(payload.sop_text)
    parsed, llm_used = _merge_model_parse(parsed, llm_fields)

    # Build a compact decision trace for the form.  It makes the model's role
    # observable even when it is unavailable: the UI can distinguish model
    # enrichment, deterministic extraction and the pending human decision.
    relations: list[dict[str, str]] = []
    actions: list[dict[str, str]] = []
    for index, step in enumerate(parsed["steps"], 1):
        item = step.model_dump(mode="json") if hasattr(step, "model_dump") else step
        source = f"SOP L{index}"
        for substance in parsed["substances"]:
            substance_name = getattr(substance, "name", substance.get("name") if isinstance(substance, dict) else "")
            if substance_name and substance_name in str(item.get("instruction", "")):
                relations.append({"from": f"步骤 {item.get('order', index)}", "to": substance_name, "kind": "化学品", "source": source})
        for control in item.get("controls", []):
            relations.append({"from": f"步骤 {item.get('order', index)}", "to": control, "kind": "控制措施", "source": source})
        for equipment in item.get("equipment", []):
            relations.append({"from": f"步骤 {item.get('order', index)}", "to": equipment, "kind": "设备", "source": source})
        if item.get("hazard") or item.get("controls") or item.get("requires_ppe"):
            actions.append({"title": f"确认步骤 {item.get('order', index)} 的控制与 PPE", "detail": "将候选结构与原文逐条比对后再写入计划。", "source": source, "status": "待人工确认"})
    if not actions:
        actions.append({"title": "核对模型未识别出的实验条件", "detail": "没有候选风险信号不代表全面安全通过，仍需人工复核。", "source": "SOP 原文", "status": "待人工确认"})

    status = service.llm.status()
    return {
        "title": payload.title,
        "room": payload.room,
        "steps": [item.model_dump(mode="json") for item in parsed["steps"]],
        "substances": [item.model_dump(mode="json") for item in parsed["substances"]],
        "ppe": parsed["ppe"],
        "equipment": parsed["equipment"],
        "ventilation": parsed["ventilation"],
        "waste_streams": parsed["waste_streams"],
        "evidence": parsed["evidence"],
        "trace": {"stages": [
            {"id": "understand", "label": "结构化理解", "status": "model" if llm_used else "deterministic", "detail": f"识别 {len(parsed['steps'])} 个步骤与 {len(parsed['substances'])} 个化学品"},
            {"id": "link", "label": "关系绑定", "status": "derived", "detail": f"建立 {len(relations)} 条步骤—对象关系"},
            {"id": "action", "label": "动作建议", "status": "human-required", "detail": f"生成 {len(actions)} 个待确认动作"},
        ], "relations": relations[:40], "actions": actions[:12]},
        "ai": {
            "provider": status["provider"],
            "model": status["model"],
            "configured": status["configured"],
            "used": llm_used,
            "mode": "remote" if llm_used else "deterministic",
            "message": "模型已生成候选结构，待人工确认。" if llm_used else "当前使用确定性抽取；配置模型后可补充歧义字段。",
        },
        "scope": "候选结构仅用于人工确认；不写入工作区，不构成安全审批或开工许可。",
    }


@app.post("/reviews/from-sop", response_model=Review, status_code=201, tags=["parser"])
def create_review_from_sop(payload: SOPParseRequest) -> Review:
    parsed = parse_sop(payload.sop_text)
    llm_fields = service.llm.extract_sop(payload.sop_text)
    # The model can enrich ambiguous language, but deterministic evidence and
    # the hard-rule engine remain authoritative for safety decisions.
    if llm_fields:
        try:
            llm_steps = [LabStep(**item) for item in llm_fields.get("steps", []) if isinstance(item, dict) and item.get("instruction")]
            for index, step in enumerate(llm_steps):
                if not step.evidence_refs and index < len(parsed["steps"]):
                    step.evidence_refs = parsed["steps"][index].evidence_refs
            if llm_steps:
                parsed["steps"] = llm_steps
            llm_substances = [Substance(**item) for item in llm_fields.get("substances", []) if isinstance(item, dict) and item.get("name")]
            if llm_substances:
                parsed["substances"] = llm_substances
            for key in ("ppe", "equipment", "waste_streams"):
                values = llm_fields.get(key)
                if isinstance(values, list) and values:
                    parsed[key] = sorted({str(value).strip() for value in values if str(value).strip()})
            if isinstance(llm_fields.get("ventilation"), str) and llm_fields["ventilation"].strip():
                parsed["ventilation"] = llm_fields["ventilation"].strip()
        except (TypeError, ValueError):
            # Keep the deterministic parse when the model returns an invalid
            # or incomplete structure.
            llm_fields = {}
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
        metadata={"synthetic": True, "input_sha256": parsed["input_sha256"], "parser": "llm-enriched-deterministic-v1" if llm_fields else "deterministic-sop-v1", "llm_extraction_used": bool(llm_fields)},
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

# Browser spatial workspace; separate versioned store preserves legacy records.
from .spatial import router as spatial_router
app.include_router(spatial_router)


# Optional same-origin production website. Serve only built public assets.
if os.getenv("AEGIS_SERVE_WEB") == "1":
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    dist = Path(__file__).resolve().parents[2] / "dist"
    if not dist.exists():
        dist = Path(__file__).resolve().parents[3] / "dist"
    if dist.exists():
        # Override the root JSON response only in website-serving mode.
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="website")
