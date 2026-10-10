"""Browser workspace: validated snapshots, versioned mutations and resource checks.

This is a local/single-owner workspace, NOT an institutional identity system or
chemical-safety certification. The existing review API is left intact.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

RULE_PACK = "resource-prerequisites/1.0"
ROOT = Path(__file__).resolve().parents[2]
SOURCE_REGISTRY_PATH = ROOT / "data" / "knowledge_sources.json"

# The browser scene uses a deliberately small set of semantic resource kinds.
# Keeping their approximate footprint here gives the server enough information
# to place a newly-created resource without making the scene layout part of the
# approval basis.  These are placement hints, not a claim about certified
# equipment dimensions.
EQUIPMENT_FOOTPRINTS: dict[str, tuple[float, float]] = {
    "hood": (3.0, 1.5), "bench": (2.4, 1.4), "storage": (1.8, 1.2),
    "analyzer": (2.2, 1.8), "sink": (1.8, 1.3), "waste": (1.4, 1.2),
    "clean_bench": (2.4, 1.5), "biosafety_cabinet": (2.4, 1.6), "balance": (1.6, 1.1),
    "centrifuge": (1.8, 1.5), "pcr": (1.6, 1.3), "gc": (2.4, 1.7), "hplc": (2.5, 1.7),
    "uv_vis": (1.8, 1.3), "mass_spec": (3.0, 2.0), "elemental_analyzer": (2.6, 1.8),
    "evaporator": (1.8, 1.4), "vacuum_pump": (1.4, 1.1), "nitrogen_blowdown": (1.8, 1.2),
    "water_purification": (1.8, 1.1), "refrigerator": (1.5, 1.2), "freezer": (1.7, 1.3),
    "drying_oven": (1.8, 1.4), "furnace": (1.6, 1.4), "gas_cabinet": (1.7, 1.3),
    "flammable_cabinet": (1.8, 1.2), "acid_base_cabinet": (1.8, 1.2), "solvent_waste": (1.4, 1.1),
    "solid_waste": (1.4, 1.1), "eyewash": (1.0, .9), "safety_shower": (1.2, 1.0),
    "gas_detector": (.8, .8), "environment_monitor": (.8, .8), "access_control": (1.0, .6),
    "chromatography": (2.5, 1.7), "ion_chromatography": (2.5, 1.7),
    "glovebox": (2.8, 1.6), "nmr": (3.2, 2.4), "ftir": (1.8, 1.4), "raman": (2.0, 1.5),
    "xrd": (3.0, 2.0), "xps": (3.4, 2.4), "sem": (3.0, 2.0), "tem": (3.6, 2.6), "afm": (2.2, 1.8), "epr": (2.8, 2.0),
    "icp_ms": (3.0, 2.0), "icp_oes": (2.8, 1.9), "aas": (2.4, 1.7), "xrf": (2.5, 1.7), "spr": (2.1, 1.6), "dls": (1.8, 1.4),
    "bet": (2.5, 1.8), "tga": (2.2, 1.7), "dsc": (2.0, 1.5), "reactor": (2.8, 2.0), "microwave_reactor": (2.0, 1.6),
    "photoreactor": (2.2, 1.6), "electrochemistry": (1.8, 1.4), "preparative_hplc": (2.8, 1.9), "solid_phase_extraction": (1.8, 1.4),
    "liquid_nitrogen": (1.6, 1.4), "cold_trap": (1.4, 1.2), "gas_manifold": (1.8, 1.2), "exhaust_treatment": (2.0, 1.4),
    "lyophilizer": (2.5, 1.8), "spray_dryer": (2.4, 1.8), "co2_incubator": (1.8, 1.5), "gel_documentation": (1.8, 1.4),
    "electrophoresis": (1.6, 1.2), "flow_cytometer": (2.5, 1.8), "fluorescence_microscope": (2.2, 1.7), "cleanroom": (3.0, 2.5),
}
PLACEMENT_GAP = 0.35

def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def uid(prefix: str) -> str:
    return f"{prefix}-{str(uuid4())[:8]}"

def dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间必须包含时区。")
    return parsed

def overlap(a: dict, b: dict) -> bool:
    return dt(a["start"]) < dt(b["end"]) and dt(b["start"]) < dt(a["end"])

def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Lab(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(max_length=2000)
    width: float = Field(ge=6, le=40)
    depth: float = Field(ge=6, le=40)

class Maintenance(StrictModel):
    id: str
    start: str
    end: str
    reason: str = Field(max_length=2000)

class EquipmentSourceCitation(StrictModel):
    """A reviewable pointer from an example asset to a public source record.

    The citation proves only that a public page is relevant to a category or
    control topic. It never asserts that the page is an institutional asset
    register or that the example resource is currently installed there.
    """
    sourceId: str = Field(min_length=1, max_length=120)
    relation: Literal["category-or-control-reference"]
    note: str = Field(min_length=1, max_length=500)


EquipmentFamily = Literal[
    "containment", "workstation", "separation", "spectroscopy", "mass_analysis",
    "structure_material", "thermal_process", "cold_chain", "gas_vacuum",
    "bio_molecular", "safety_response", "waste_environment", "utility",
]
EvidenceKind = Literal["sop", "inspection", "sds", "training", "calibration", "reservation", "permit", "sensor"]

class Equipment(StrictModel):
    id: str
    labId: str
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=180)
    kind: Literal[
        "hood", "bench", "storage", "analyzer", "sink", "waste", "clean_bench", "biosafety_cabinet",
        "balance", "centrifuge", "pcr", "gc", "hplc", "uv_vis", "mass_spec", "elemental_analyzer",
        "evaporator", "vacuum_pump", "nitrogen_blowdown", "water_purification", "refrigerator", "freezer",
        "drying_oven", "furnace", "gas_cabinet", "flammable_cabinet", "acid_base_cabinet", "solvent_waste",
        "solid_waste", "eyewash", "safety_shower", "gas_detector", "environment_monitor", "access_control",
        "chromatography", "ion_chromatography", "glovebox", "nmr", "ftir", "raman", "xrd", "xps", "sem", "tem", "afm", "epr",
        "icp_ms", "icp_oes", "aas", "xrf", "spr", "dls", "bet", "tga", "dsc", "reactor", "microwave_reactor", "photoreactor",
        "electrochemistry", "preparative_hplc", "solid_phase_extraction", "liquid_nitrogen", "cold_trap", "gas_manifold", "exhaust_treatment",
        "lyophilizer", "spray_dryer", "co2_incubator", "gel_documentation", "electrophoresis", "flow_cytometer", "fluorescence_microscope", "cleanroom"
    ]
    x: float = Field(ge=-20, le=20)
    z: float = Field(ge=-20, le=20)
    rotation: float = Field(ge=-360, le=360)
    capacity: int = Field(ge=1, le=100, strict=True)
    status: Literal["available", "unavailable", "unknown"]
    owner: str = Field(max_length=180)
    description: str = Field(max_length=5000)
    requiresEvidence: bool
    specVersion: int = Field(ge=1, strict=True)
    maintenance: list[Maintenance] = Field(max_length=100)
    # Operational profile fields are optional so old exported workspaces remain valid.
    family: EquipmentFamily | None = None
    subtype: str | None = Field(default=None, max_length=180)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    typicalUse: str | None = Field(default=None, max_length=1000)
    hazardTags: list[str] = Field(default_factory=list, max_length=30)
    controlTags: list[str] = Field(default_factory=list, max_length=40)
    utilityRequirements: list[str] = Field(default_factory=list, max_length=30)
    requiredTraining: list[str] = Field(default_factory=list, max_length=30)
    calibrationOrInspection: list[str] = Field(default_factory=list, max_length=30)
    evidenceKinds: list[EvidenceKind] = Field(default_factory=list, max_length=20)
    sourceRefs: list[str] = Field(default_factory=list, max_length=20)
    sourceCitations: list[EquipmentSourceCitation] = Field(default_factory=list, max_length=20)

class Step(StrictModel):
    id: str
    text: str = Field(min_length=1, max_length=20000)
    line: int = Field(ge=1, strict=True)
    equipmentIds: list[str] = Field(max_length=100)
    confirmed: bool

class Reservation(StrictModel):
    id: str
    equipmentId: str
    start: str
    end: str

class BranchPatch(StrictModel):
    """A reviewable field-level change inside an isolated plan branch.

    Branch reservations remain the candidate state used by the checker.  The
    patch records make the user's intent explicit, so a resource switch and a
    time change can be accepted together without treating the branch as an
    opaque replacement snapshot.  ``before`` is checked against the branch
    base and ``after`` against the candidate state at save/apply time.
    """
    path: Literal["reservation.equipmentId", "reservation.start", "reservation.end"]
    targetId: str = Field(min_length=1, max_length=128)
    before: str
    after: str
    reason: str = Field(min_length=1, max_length=500)

class Plan(StrictModel):
    id: str
    code: str = Field(min_length=1, max_length=80)
    labId: str
    name: str = Field(min_length=1, max_length=180)
    owner: str = Field(min_length=1, max_length=180)
    revision: int = Field(ge=1, strict=True)
    source: str = Field(min_length=1, max_length=100000)
    sourceName: str = Field(max_length=240)
    steps: list[Step] = Field(max_length=500)
    reservations: list[Reservation] = Field(max_length=500)
    archived: bool
    # Explicit lifecycle is kept separate from the derived safety status.  Old
    # workspaces omit this field (``None`` is interpreted as draft, or archived
    # when archived=true); a transition operation writes it only after the
    # server rechecks the current plan and its evidence basis.
    lifecycle: Literal["draft", "submitted", "revising", "archived", "cancelled"] | None = None

class Document(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=240)
    kind: Literal["inspection", "sop", "reference"]
    equipmentId: str | None
    specVersion: int = Field(ge=1, strict=True)
    status: Literal["pending", "verified", "rejected"]
    validFrom: str
    validUntil: str
    content: str = Field(min_length=1, max_length=200000)
    source: str = Field(min_length=1, max_length=1000)
    reviewedBy: str | None
    reviewedAt: str | None
    # Provenance fields are optional for backwards-compatible imports.  They
    # describe where a document came from and when its text was captured; they
    # do not assert that the source is authoritative or that the evidence is
    # applicable to every plan.  Applicability is evaluated separately below.
    sourceType: Literal["upload", "manual", "external", "system"] | None = None
    sourceLocator: str | None = Field(default=None, max_length=1000)
    capturedAt: str | None = None
    contentLength: int | None = Field(default=None, ge=0, strict=True)
    provenanceNote: str | None = Field(default=None, max_length=1000)

class Task(StrictModel):
    id: str
    title: str = Field(min_length=1, max_length=240)
    planId: str | None
    equipmentId: str | None
    owner: str = Field(min_length=1, max_length=180)
    dueAt: str
    # ``returned`` and ``cancelled`` are persisted business states.  ``reopened``
    # is kept explicit so a completed/returned item can be reopened without
    # erasing the preceding decision from the audit trail.
    status: Literal["open", "submitted", "done", "returned", "cancelled", "reopened"]
    note: str = Field(max_length=5000)
    sourceId: str | None = Field(default=None, max_length=180)
    sourceLine: int | None = Field(default=None, ge=1)
    documentIds: list[str] = Field(default_factory=list, max_length=100)
    actionKind: str | None = Field(default=None, max_length=60)
    actionTarget: dict[str, Any] | None = None

class Decision(StrictModel):
    id: str
    planId: str
    revision: int
    basis: str
    actor: str
    comment: str = Field(min_length=1, max_length=2000)
    at: str
    # Decisions are immutable evidence of a human disposition.  Legacy
    # records omit these fields and remain interpreted as a normal approval.
    disposition: Literal["approved", "returned", "exception"] = "approved"
    actorRole: str = Field(default="safety_owner", max_length=80)
    stage: str = Field(default="safety_owner", max_length=80)
    checkSnapshot: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    exception: dict[str, Any] | None = None


def approval_stages() -> list[str]:
    """Return the server-configured approval stages without trusting the UI.

    The default remains the existing single safety-owner gate so old local
    workspaces keep their behavior.  Institutions can opt into a second EHS
    stage through an environment setting without changing the data contract.
    """
    raw = os.getenv("AEGIS_APPROVAL_STAGES", "safety_owner")
    stages = [item.strip() for item in raw.split(",") if item.strip()]
    return stages or ["safety_owner"]


def decision_check_snapshot(checks: list[dict]) -> list[dict]:
    return [
        {"id": str(check.get("id", "")), "state": str(check.get("state", "unknown")), "title": str(check.get("title", ""))[:240]}
        for check in checks
    ]


def approval_state(w: dict, p: dict, checks: list[dict]) -> dict:
    """Derive current approval state from immutable decisions and current basis."""
    decisions = [d for d in w.get("decisions", []) if d.get("planId") == p.get("id")]
    current_basis = basis(w, p)
    # Only the latest decision determines whether the current chain needs a
    # recheck. Older decisions remain immutable history; a new decision at
    # the current basis starts a fresh chain.
    stale = bool(decisions and decisions[-1].get("basis") != current_basis)
    latest = decisions[-1] if decisions else None
    stages = approval_stages()
    approved_stages = {item.get("stage", item.get("actorRole", "safety_owner")) for item in decisions if item.get("disposition", "approved") == "approved" and item.get("basis") == current_basis}
    pending = next((stage for stage in stages if stage not in approved_stages), None)
    disposition = latest.get("disposition", "approved") if latest else None
    return {
        "stages": stages,
        "latest": latest,
        "stale": stale,
        "pendingStage": pending,
        "disposition": disposition,
        "checkSnapshot": decision_check_snapshot(checks),
        "latestCheckSnapshot": latest.get("checkSnapshot", []) if latest else [],
    }

class Event(StrictModel):
    id: str
    at: str
    actor: str
    action: str
    objectId: str
    summary: str

class Branch(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=180)
    planId: str
    baseRevision: int
    baseBasis: str
    reservations: list[Reservation] = Field(max_length=500)
    createdAt: str
    patches: list[BranchPatch] = Field(default_factory=list, max_length=200)

class Workspace(StrictModel):
    schemaVersion: Literal[1]
    revision: int = Field(ge=0, strict=True)
    name: str = Field(min_length=1, max_length=180)
    provenance: Literal["user", "example"]
    laboratories: list[Lab] = Field(max_length=100)
    equipment: list[Equipment] = Field(max_length=2000)
    plans: list[Plan] = Field(max_length=2000)
    documents: list[Document] = Field(max_length=5000)
    tasks: list[Task] = Field(max_length=5000)
    decisions: list[Decision] = Field(max_length=5000)
    events: list[Event] = Field(max_length=5000)
    branches: list[Branch] = Field(max_length=2000)


def empty_workspace() -> dict:
    return dict(schemaVersion=1, revision=0, name="我的实验工作区", provenance="user", laboratories=[], equipment=[], plans=[], documents=[], tasks=[], decisions=[], events=[], branches=[])

def read_source_registry() -> list[dict]:
    """Read the public source directory without treating it as workspace fact."""
    try:
        raw = json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(503, "公开来源目录暂时不可用。") from error
    if not isinstance(raw, list):
        raise HTTPException(503, "公开来源目录格式无效。")
    return raw


def validate_workspace(w: dict) -> dict:
    # Validate without normalizing numeric JSON types: stable TS/Python fingerprints.
    Workspace.model_validate(w)
    for key in ("laboratories", "equipment", "plans", "documents", "tasks", "decisions", "events", "branches"):
        ids = [x["id"] for x in w[key]]
        if len(ids) != len(set(ids)) or any(not isinstance(x, str) or not x or len(x) > 128 for x in ids):
            raise ValueError("对象 ID 必须唯一且有效。")
    labs = {x["id"]: x for x in w["laboratories"]}
    equipment = {x["id"]: x for x in w["equipment"]}
    plans = {x["id"]: x for x in w["plans"]}
    def interval(a: str, b: str):
        if dt(a) >= dt(b):
            raise ValueError("结束时间必须晚于开始时间。")
    codes: set[tuple] = set()
    for e in equipment.values():
        if e["labId"] not in labs:
            raise ValueError("资源所属实验室不存在。")
        l = labs[e["labId"]]
        if abs(e["x"]) > l["width"] / 2 - .5 or abs(e["z"]) > l["depth"] / 2 - .5:
            raise ValueError("设备位置超出实验室边界。")
        code = (e["labId"], e["code"])
        if code in codes:
            raise ValueError("同一实验室内设备编号不能重复。")
        codes.add(code)
        for m in e["maintenance"]:
            interval(m["start"], m["end"])
    for p in plans.values():
        if p["labId"] not in labs or not p["name"].strip() or not p["owner"].strip() or not p["source"].strip():
            raise ValueError("计划基础资料不完整。")
        lines = p["source"].splitlines()
        for s in p["steps"]:
            if s["line"] > len(lines) or lines[s["line"] - 1].strip() != s["text"] or any(equipment.get(i, {}).get("labId") != p["labId"] for i in s["equipmentIds"]):
                raise ValueError("步骤必须准确引用原文，不得编造行号。")
        for i, r in enumerate(p["reservations"]):
            interval(r["start"], r["end"])
            if equipment.get(r["equipmentId"], {}).get("labId") != p["labId"]:
                raise ValueError("预约设备必须属于当前实验室。")
            if any(other["equipmentId"] == r["equipmentId"] and overlap(other, r) for other in p["reservations"][i + 1:]):
                raise ValueError("同一计划不能重复占用同一资源的重叠时段。")
        if p.get("archived") and p.get("lifecycle", "archived") not in {"archived"}:
            raise ValueError("已归档计划必须保持 archived 生命周期。")
    for d in w["documents"]:
        if d["equipmentId"] is not None and d["equipmentId"] not in equipment:
            raise ValueError("资料关联的设备不存在。")
        interval(d["validFrom"], d["validUntil"])
        if not d["content"].strip() or not d["source"].strip():
            raise ValueError("资料内容和来源为必填项。")
        if d.get("capturedAt") is not None:
            # A provenance timestamp is a claim about when the captured text
            # entered the workspace; reject ambiguous local timestamps.
            dt(d["capturedAt"])
        if d.get("contentLength") is not None and d["contentLength"] != len(d["content"]):
            raise ValueError("资料内容长度与 provenance 记录不一致。")
    for t in w["tasks"]:
        dt(t["dueAt"])
        if (t["planId"] is not None and t["planId"] not in plans) or (t["equipmentId"] is not None and t["equipmentId"] not in equipment):
            raise ValueError("任务关联的对象不存在。")
    for b in w["branches"]:
        if b["planId"] not in plans:
            raise ValueError("方案关联的计划不存在。")
    if len(json.dumps(w, ensure_ascii=False)) > 5_000_000:
        raise ValueError("工作区超过当前容量，请先归档。")
    return w


def equipment_footprint(kind: str) -> tuple[float, float]:
    """Return a conservative placement footprint for a resource kind.

    The footprint is only used for collision-free default placement.  It is
    intentionally kept outside ``Equipment`` so changing a visual placement
    cannot alter a resource's capability or review basis.
    """
    return EQUIPMENT_FOOTPRINTS.get(kind, (1.5, 1.2))


def equipment_overlaps(a: dict, b: dict, *, x: float | None = None, z: float | None = None) -> bool:
    """Whether two resources would occupy the same scene slot.

    Rotation is ignored for the conservative default layout.  The scene can
    still rotate a resource after it has been created; this check only prevents
    the common failure where every new resource is saved at ``(0, 0)``.
    """
    # Resources in different laboratories have independent coordinate spaces.
    # Comparing their scene coordinates would make a new object in one room
    # appear to collide with an object in another room.
    if a.get("labId") != b.get("labId"):
        return False
    ax = a["x"] if x is None else x
    az = a["z"] if z is None else z
    aw, ad = equipment_footprint(a["kind"])
    bw, bd = equipment_footprint(b["kind"])
    return (
        abs(ax - b["x"]) < (aw + bw) / 2 + PLACEMENT_GAP
        and abs(az - b["z"]) < (ad + bd) / 2 + PLACEMENT_GAP
    )


def find_equipment_position(w: dict, equipment: dict) -> tuple[float, float]:
    """Find a deterministic free position inside the owning laboratory.

    The center is preferred for the first resource.  Subsequent candidates are
    sampled on a stable grid from the back-left toward the front-right so a
    retry produces the same workspace.  An explicit position is never changed
    by this helper; callers opt into it only for newly-created resources that
    requested automatic placement.
    """
    lab = next((item for item in w["laboratories"] if item["id"] == equipment["labId"]), None)
    if lab is None:
        raise ValueError("资源所属实验室不存在。")
    width, depth = equipment_footprint(equipment["kind"])
    half_w, half_d = width / 2, depth / 2
    x_min, x_max = -lab["width"] / 2 + half_w, lab["width"] / 2 - half_w
    z_min, z_max = -lab["depth"] / 2 + half_d, lab["depth"] / 2 - half_d
    if x_min > x_max or z_min > z_max:
        raise ValueError("实验室空间不足，无法自动放置该资源。")

    existing = [item for item in w["equipment"] if item["labId"] == equipment["labId"] and item["id"] != equipment["id"]]
    # Start at the visual center, then use a fixed lattice.  Rounding avoids
    # accumulating floating-point noise in exported workspace JSON.
    candidates: list[tuple[float, float]] = [(0.0, 0.0)]
    step_x = max(1.0, min(width + PLACEMENT_GAP, 2.4))
    step_z = max(1.0, min(depth + PLACEMENT_GAP, 2.0))
    x = x_min
    while x <= x_max + 1e-6:
        z = z_min
        while z <= z_max + 1e-6:
            candidates.append((round(x, 2), round(z, 2)))
            z += step_z
        x += step_x
    # Prefer candidates closest to the center after the explicit center entry.
    candidates[1:] = sorted(candidates[1:], key=lambda point: (point[0] ** 2 + point[1] ** 2, point[1], point[0]))
    for candidate_x, candidate_z in candidates:
        if not (x_min - 1e-6 <= candidate_x <= x_max + 1e-6 and z_min - 1e-6 <= candidate_z <= z_max + 1e-6):
            continue
        if not any(equipment_overlaps(equipment, other, x=candidate_x, z=candidate_z) for other in existing):
            return candidate_x, candidate_z
    raise ValueError("实验室没有可用的自动放置位置，请扩大空间或调整已有资源。")


def basis(w: dict, p: dict) -> str:
    """Fingerprint only facts that can change this plan's checks.

    Display edits, camera placement, unrelated future maintenance and distant
    reservations must not revoke a recorded decision.  The fingerprint still
    changes for a source/step/booking edit, a relevant equipment state or
    specification change, and evidence whose applicability window intersects
    the plan's actual reservations.
    """
    reservations = sorted((dict(r) for r in p.get("reservations", [])), key=lambda r: (r.get("equipmentId", ""), r.get("start", ""), r.get("end", ""), r.get("id", "")))
    ids = {r["equipmentId"] for r in reservations}
    def relevant(interval: dict, windows: list[dict]) -> bool:
        return any(overlap(interval, window) for window in windows)
    relevant_equipment = []
    for e in w["equipment"]:
        if e["id"] not in ids:
            continue
        e_reservations = [r for r in reservations if r["equipmentId"] == e["id"]]
        maintenance = sorted((m for m in e.get("maintenance", []) if relevant(m, e_reservations)), key=lambda m: (m.get("start", ""), m.get("end", ""), m.get("id", "")))
        relevant_equipment.append({
            "id": e["id"], "labId": e["labId"], "kind": e["kind"],
            "status": e["status"], "capacity": e["capacity"],
            "requiresEvidence": e["requiresEvidence"], "specVersion": e["specVersion"],
            "maintenance": maintenance,
        })
    relevant_equipment.sort(key=lambda e: e["id"])
    relevant_documents = []
    for d in w["documents"]:
        if d.get("equipmentId") not in ids:
            continue
        doc_window = {"start": d["validFrom"], "end": d["validUntil"]}
        if not relevant(doc_window, reservations) and d.get("kind") == "inspection":
            continue
        document_facts = {k: d.get(k) for k in ("id", "equipmentId", "kind", "specVersion", "status", "validFrom", "validUntil", "content", "source", "reviewedBy", "reviewedAt")}
        # Keep legacy fingerprints byte-for-byte stable when an imported
        # document has no provenance metadata.  New records include only the
        # fields that were actually captured, so absent metadata is not a
        # fabricated claim and the browser/Python parity contract survives.
        document_facts.update({k: d[k] for k in ("sourceType", "sourceLocator", "capturedAt", "contentLength", "provenanceNote") if d.get(k) is not None})
        relevant_documents.append(document_facts)
    relevant_documents.sort(key=lambda d: (d.get("equipmentId") or "", d.get("kind", ""), d.get("id", "")))
    other = []
    for q in w["plans"]:
        if q["id"] == p["id"] or q["archived"] or q.get("lifecycle") == "cancelled":
            continue
        for r in q.get("reservations", []):
            if r["equipmentId"] in ids and relevant(r, reservations):
                other.append(dict(planId=q["id"], **r))
    other.sort(key=lambda r: (r.get("equipmentId", ""), r.get("start", ""), r.get("end", ""), r.get("planId", ""), r.get("id", "")))
    plan_facts = {
        "id": p["id"], "labId": p["labId"], "revision": p.get("revision"), "sourceName": p.get("sourceName"), "source": p["source"],
        "steps": [{k: s.get(k) for k in ("id", "text", "line", "equipmentIds", "confirmed")} for s in sorted(p.get("steps", []), key=lambda s: (s.get("line", 0), s.get("id", "")))],
        "reservations": reservations,
    }
    return canonical(dict(rulePack=RULE_PACK, plan=plan_facts, equipment=relevant_equipment,
        documents=relevant_documents, otherReservations=other))


def branch_candidate(w: dict, branch: dict) -> dict:
    """Build and validate a branch projection without mutating ``w``.

    ``reservations`` is the candidate snapshot retained for compatibility
    with existing branches.  New branches additionally carry field-level
    ``patches``.  Each patch is checked against the current base value and
    against the candidate snapshot, which prevents a stale or misleading diff
    from being stored as if it described the selected branch.
    """
    Branch.model_validate(branch)
    candidate = copy.deepcopy(w)
    plan = next((item for item in candidate["plans"] if item["id"] == branch["planId"]), None)
    base_plan = next((item for item in w["plans"] if item["id"] == branch["planId"]), None)
    if plan is None or base_plan is None:
        raise ValueError("方案关联的计划不存在。")
    plan["reservations"] = copy.deepcopy(branch["reservations"])
    reservation_by_id = {item["id"]: item for item in plan["reservations"]}
    base_reservation_by_id = {item["id"]: item for item in base_plan["reservations"]}
    for patch in branch.get("patches", []):
        path = patch["path"]
        target_id = patch["targetId"]
        base_row = base_reservation_by_id.get(target_id)
        candidate_row = reservation_by_id.get(target_id)
        if base_row is None or candidate_row is None:
            raise ValueError(f"候选字段目标不存在：{target_id}。")
        if base_row[path.removeprefix("reservation.")] != patch["before"]:
            raise ValueError("候选字段基线已变化，请重新创建方案。")
        if candidate_row[path.removeprefix("reservation.")] != patch["after"]:
            raise ValueError("候选字段与方案快照不一致，请重新生成方案。")
    validate_workspace(candidate)
    return candidate


def check_workspace(w: dict) -> list[dict]:
    results: list[dict] = []
    for p in [p for p in w["plans"] if not p["archived"] and p.get("lifecycle") != "cancelled"]:
        def add(code, state, title, detail, equipment_id=None, related=None, documents=None):
            line = next((s["line"] for s in p["steps"] if equipment_id in s["equipmentIds"]), None)
            results.append(dict(id=f"{p['id']}:{code}:{equipment_id or 'plan'}", planId=p["id"], equipmentId=equipment_id, code=code, state=state, title=title, detail=detail, relatedPlanIds=related or [], documentIds=documents or [], line=line))
        confirmed = bool(p["steps"]) and all(s["confirmed"] for s in p["steps"])
        add("SOURCE", "pass" if confirmed else "unknown", "原文与步骤已确认" if confirmed else "步骤提取需要人工确认", f"{len(p['steps'])} 个步骤绑定到原文行号。" if confirmed else "请核对原文、步骤及设备匹配；机器提取不代表事实已确认。")
        if not p["reservations"]:
            add("SCHEDULE", "unknown", "尚未设置资源使用时段", "设备、开始和结束时间是资源核验的必要输入。")
        ids = list(dict.fromkeys(r["equipmentId"] for r in p["reservations"]))
        for identifier in dict.fromkeys(i for step in p["steps"] for i in step["equipmentIds"]):
            if identifier not in ids:
                add("BINDING", "unknown", "原文设备与预约尚未对齐", "步骤引用的设备没有对应预约。更换资源后须修订原文并重新确认，不能只替换画面中的连线。", identifier)
        for identifier in ids:
            e = next((e for e in w["equipment"] if e["id"] == identifier), None)
            if not e:
                add("RESOURCE", "unknown", "资源不存在", "重新绑定有效资源。", identifier)
                continue
            reservations = [r for r in p["reservations"] if r["equipmentId"] == identifier]
            maintenance = e["status"] == "unavailable" or any(overlap(r, m) for r in reservations for m in e["maintenance"])
            state = "blocked" if maintenance else "unknown" if e["status"] == "unknown" else "pass"
            title = f"{e['code']} 在预约范围内不可用" if maintenance else f"{e['code']} 的台账状态待确认" if state == "unknown" else f"{e['code']} 的预约不冲突于维护"
            add("AVAILABILITY", state, title, "当前停用状态或维护窗口与使用计划交叠；需更换资源或调整时段。" if maintenance else "仅依据已登记的台账与维护窗口；不代表现场传感器状态。", identifier)
            assigned = [dict(planId=q["id"], **r) for q in w["plans"] if not q["archived"] and q.get("lifecycle") != "cancelled" for r in q["reservations"] if r["equipmentId"] == identifier]
            conflicts: list[str] = []
            for r in reservations:
                active = [a for a in assigned if overlap(a, r)]
                points = {dt(r["start"])} | {max(dt(a["start"]), dt(r["start"])) for a in active}
                for point in sorted(points):
                    at = [a for a in active if dt(a["start"]) <= point < dt(a["end"])]
                    if len(at) > e["capacity"]:
                        for a in at:
                            if a["planId"] != p["id"] and a["planId"] not in conflicts:
                                conflicts.append(a["planId"])
            add("CAPACITY", "blocked" if conflicts else "pass", f"{e['code']} 超出并发使用容量" if conflicts else f"{e['code']} 的资源容量已满足", f"登记容量为 {e['capacity']}；与 {'、'.join(conflicts)} 同时占用。" if conflicts else f"当前使用安排未超出登记容量 {e['capacity']}。相邻时段按半开区间计算。", identifier, conflicts)
            if e["requiresEvidence"]:
                docs = [d for d in w["documents"] if d["equipmentId"] == identifier and d["kind"] == "inspection"]
                valid = [d for d in docs if d["status"] == "verified" and d["specVersion"] == e["specVersion"]]
                covered = all(any(dt(d["validFrom"]) <= dt(r["start"]) and dt(d["validUntil"]) >= dt(r["end"]) for d in valid) for r in reservations)
                applicability = []
                for d in docs:
                    covered_reservation_ids = [
                        r["id"] for r in reservations
                        if dt(d["validFrom"]) <= dt(r["start"]) and dt(d["validUntil"]) >= dt(r["end"])
                    ]
                    missing_reservation_ids = [r["id"] for r in reservations if r["id"] not in covered_reservation_ids]
                    if d["status"] != "verified":
                        state, reason = "candidate", "not-verified"
                    elif d["specVersion"] != e["specVersion"]:
                        state, reason = "mismatched", "spec-version-mismatch"
                    elif not covered_reservation_ids:
                        state, reason = "expired", "outside-reservation-window"
                    else:
                        state = "supports"
                        reason = "covers-all-reservations" if not missing_reservation_ids else "partial-reservation-coverage"
                    applicability.append({
                        "documentId": d["id"], "state": state, "reason": reason,
                        "coverage": "complete" if not missing_reservation_ids and covered_reservation_ids else "partial" if covered_reservation_ids else "none",
                        "coverageBasis": "validity-window",
                        "effectiveForAllReservations": state == "supports" and not missing_reservation_ids,
                        "coveredReservationIds": covered_reservation_ids,
                        "missingReservationIds": missing_reservation_ids,
                        "equipmentId": identifier,
                        "specVersion": d["specVersion"], "expectedSpecVersion": e["specVersion"],
                        "validFrom": d["validFrom"], "validUntil": d["validUntil"],
                        "source": d["source"], "sourceType": d.get("sourceType"),
                        "sourceLocator": d.get("sourceLocator"), "capturedAt": d.get("capturedAt"),
                        "contentLength": d.get("contentLength"),
                        "provenanceNote": d.get("provenanceNote"),
                        "reviewedBy": d.get("reviewedBy"), "reviewedAt": d.get("reviewedAt"),
                    })
                add("EVIDENCE", "pass" if covered else "unknown", f"{e['code']} 的检查证据适用" if covered else f"{e['code']} 缺少适用的检查证据", "对象、规格版本、核验状态与全部使用时段均匹配。" if covered else "需要已核验且覆盖整个使用时段的记录；上传、过期、其他设备的记录都不能代替。", identifier, documents=[d["id"] for d in docs])
                results[-1]["evidenceApplicability"] = applicability
                results[-1]["evidenceScope"] = {
                    "equipmentId": identifier,
                    "specVersion": e["specVersion"],
                    "reservationIds": [r["id"] for r in reservations],
                    "requiredCoverage": "all-reservations",
                }
    return results


def plan_status(w: dict, p: dict, checks: list[dict]) -> str:
    if p["archived"] or p.get("lifecycle") == "archived":
        return "archived"
    if p.get("lifecycle") == "cancelled":
        return "cancelled"
    approval = approval_state(w, p, [c for c in checks if c["planId"] == p["id"]])
    decision = approval["latest"]
    if approval["stale"]:
        return "recheck"
    if decision and approval["disposition"] == "returned":
        return "returned"
    if decision and approval["disposition"] == "exception" and not approval["stale"]:
        return "approved_with_exception"
    if not p["steps"] or any(not s["confirmed"] for s in p["steps"]):
        return "draft"
    relevant = [c for c in checks if c["planId"] == p["id"]]
    if any(c["state"] == "blocked" for c in relevant):
        return "blocked"
    if any(c["state"] == "unknown" for c in relevant):
        return "unknown"
    if decision and approval["pendingStage"] is None:
        return "approved"
    return "pending_approval" if decision else "ready"


def envelope(w: dict) -> dict:
    checks = check_workspace(w)
    return dict(workspace=w, checks=checks, statuses={p["id"]: plan_status(w, p, checks) for p in w["plans"]}, mode="server", rulePack=RULE_PACK, scope="资源时段、台账可用性、检查证据适用性与原文确认；不构成全域化学安全评估或开工许可。")


def expiry_recheck_report(w: dict, as_of: str) -> dict:
    """Return a reproducible expiry/overdue report for the current snapshot.

    This is deliberately a pure report builder.  It does not mark evidence
    verified, alter a plan, or create work items.  The durable endpoint stores
    the report in ``spatial_jobs`` so a later browser request can inspect the
    same result instead of silently treating a fresh calculation as a worker
    run.  Plan impact is derived from the existing applicability checks, so an
    expired record only affects a plan when its object, version and reservation
    window make that record relevant.
    """
    as_of_dt = dt(as_of)
    expired_evidence: list[dict] = []
    expired_ids: set[str] = set()
    for document in w.get("documents", []):
        until = dt(document["validUntil"])
        if document.get("status") == "verified" and until <= as_of_dt:
            expired_ids.add(document["id"])
            expired_evidence.append({
                "documentId": document["id"],
                "name": document["name"],
                "equipmentId": document.get("equipmentId"),
                "specVersion": document.get("specVersion"),
                "validUntil": document["validUntil"],
                "source": document.get("source"),
                "status": document.get("status"),
                "reason": "valid-until-reached",
            })

    active_task_states = {"open", "submitted", "reopened"}
    overdue_tasks = [
        {
            "taskId": task["id"],
            "title": task["title"],
            "planId": task.get("planId"),
            "equipmentId": task.get("equipmentId"),
            "owner": task.get("owner"),
            "dueAt": task["dueAt"],
            "status": task["status"],
            "reason": "due-at-reached",
        }
        for task in w.get("tasks", [])
        if task.get("status") in active_task_states and dt(task["dueAt"]) <= as_of_dt
    ]

    checks = check_workspace(w)
    impacted_plans: list[dict] = []
    for plan in w.get("plans", []):
        if plan.get("archived") or plan.get("lifecycle") == "cancelled":
            continue
        plan_checks = [check for check in checks if check["planId"] == plan["id"]]
        expired_check_ids: list[str] = []
        expired_plan_document_ids: set[str] = set()
        for check in plan_checks:
            if check.get("code") != "EVIDENCE":
                continue
            for applicability in check.get("evidenceApplicability", []):
                document_id = applicability.get("documentId")
                if document_id in expired_ids and applicability.get("state") in {"expired", "partial", "mismatched", "candidate"}:
                    expired_check_ids.append(check["id"])
                    expired_plan_document_ids.add(document_id)
                    break
        decisions = [decision for decision in w.get("decisions", []) if decision.get("planId") == plan["id"]]
        decision_invalidated = bool(decisions and decisions[-1].get("basis") != basis(w, plan))
        if not expired_check_ids and not decision_invalidated:
            continue
        reasons: list[str] = []
        if expired_check_ids:
            reasons.append("evidence-valid-until-reached")
        if decision_invalidated:
            reasons.append("recorded-decision-basis-changed")
        impacted_plans.append({
            "planId": plan["id"],
            "code": plan["code"],
            "revision": plan["revision"],
            "status": plan_status(w, plan, plan_checks),
            "reasonCodes": reasons,
            "expiredDocumentIds": sorted(expired_plan_document_ids),
            "checkIds": sorted(set(expired_check_ids)),
            "decisionInvalidated": decision_invalidated,
        })

    impacted_plans.sort(key=lambda item: item["planId"])
    expired_evidence.sort(key=lambda item: (item["validUntil"], item["documentId"]))
    overdue_tasks.sort(key=lambda item: (item["dueAt"], item["taskId"]))
    return {
        "runType": "expiry_recheck",
        "trigger": "manual",
        "asOf": as_of,
        "worker": "not-running",
        "scope": "已核验资料有效期、未完成任务截止时间、受影响的当前计划",
        "expiredEvidence": expired_evidence,
        "overdueTasks": overdue_tasks,
        "impactedPlans": impacted_plans,
        "counts": {
            "expiredEvidence": len(expired_evidence),
            "overdueTasks": len(overdue_tasks),
            "impactedPlans": len(impacted_plans),
        },
        "nextStep": "由负责人查看影响对象并手动补证、修订或重新复核；本次重检不会自动批准、取消或创建任务。",
    }


COPILOT_ACTION_KINDS = {
    "source_line", "equipment", "evidence", "rule", "relationship", "task", "scenario",
}


def _copilot_packet(w: dict, plan: dict, parsed: dict, evaluation: Any) -> dict:
    """Build the reviewable, structured part of the AI copilot response.

    The language model is only responsible for the prose summary.  This packet
    is deterministic and keeps every suggestion tied to a parsed step, a rule
    result, or a resource check so the UI can show *why* the assistant reached
    a conclusion.  It deliberately never returns approval or executable
    incident instructions.
    """
    plan_checks = [c for c in check_workspace(w) if c["planId"] == plan["id"]]
    failed_rules = [r for r in evaluation.results if not r.passed]

    def action(kind: str, target: dict[str, Any]) -> dict[str, Any]:
        """Attach a review-only navigation target to an AI item.

        These targets are deliberately declarative.  The browser uses them to
        focus an existing source, resource, evidence record, rule or graph;
        they never approve a plan or mutate the workspace by themselves.
        """
        if kind not in COPILOT_ACTION_KINDS:
            raise ValueError(f"未知的 Copilot 动作类型：{kind}")
        # Keep the target's discriminator aligned with the typed action.  The
        # browser treats this as a navigation hint only; it never mutates a
        # plan or bypasses a revision/approval check.
        target = dict(target)
        target.setdefault("type", kind)
        return {"actionKind": kind, "actionTarget": target}

    def task_draft(item: dict[str, Any], title: str, note: str, owner: str, kind: str, target: dict[str, Any]) -> dict[str, Any]:
        """Carry the exact source item into a review-only task draft.

        A task form may be opened from several lists (evidence, conflicts, or
        a manual review fallback).  Capturing the source id and typed target
        prevents the form from silently falling back to the plan's first
        unresolved check.
        """
        draft_target = dict(target)
        draft_target.setdefault("type", kind)
        return {
            "itemId": item.get("id"),
            "sourceId": item.get("sourceId") or item.get("id"),
            "title": title,
            "note": note,
            "owner": owner,
            "line": item.get("line"),
            "equipmentId": item.get("equipmentId"),
            "documentIds": list(item.get("documentIds") or []),
            "actionKind": kind,
            "actionTarget": draft_target,
        }
    steps = [step.model_dump(mode="json") if hasattr(step, "model_dump") else step for step in parsed.get("steps", [])]
    substances = [substance.model_dump(mode="json") if hasattr(substance, "model_dump") else substance for substance in parsed.get("substances", [])]
    plan_steps_by_line = {int(item.get("line")): item for item in plan.get("steps", []) if item.get("line") is not None}
    for step in steps:
        # Source line is the only legal join key.  Never borrow a plan step by
        # array position after a model has reordered or omitted entries.
        source_step = plan_steps_by_line.get(step.get("source_line") or step.get("line"))
        if source_step:
            step.setdefault("line", source_step.get("line"))
            step.setdefault("planEquipmentIds", source_step.get("equipmentIds", []))
    hazards: list[dict] = []
    relations: list[dict] = []
    for index, step in enumerate(steps, 1):
        hazard = step.get("hazard")
        if hazard or step.get("requires_ppe") or step.get("waste_stream") or step.get("ventilation"):
            source = f"SOP 原文 L{step.get('line')}" if step.get("line") else "SOP 原文（待定位）"
            hazards.append({
                "id": f"step-{step.get('order', index)}",
                "step": step.get("order", index),
                "line": step.get("line"),
                "title": hazard or "需要控制措施的步骤",
                "detail": step.get("instruction", ""),
                "controls": step.get("controls", []),
                "ppe": step.get("requires_ppe", []),
                "evidence": step.get("evidence_refs", []),
                "severity": "high" if hazard else "medium",
                "source": source,
                "origin": "source-anchored",
                **(action("source_line", {"planId": plan["id"], "line": step.get("line")}) if step.get("line") else action("rule", {"planId": plan["id"], "ruleId": "step-controls"})),
            })
        for substance in substances:
            substance_name = str(substance.get("name", "")).strip()
            if substance_name and substance_name in str(step.get("instruction", "")):
                relation_id = f"step-{step.get('order', index)}:substance-{substance_name}:uses"
                relations.append({"id": relation_id, "from": f"step-{step.get('order', index)}", "to": f"substance-{substance_name}", "kind": "uses", "label": "使用化学品", "source": f"SOP L{step.get('line')}" if step.get('line') else "SOP 原文", **action("relationship", {"planId": plan["id"], "relationId": relation_id, "from": f"step-{step.get('order', index)}", "to": f"substance-{substance_name}", "relation": "uses"})})
        for equipment in step.get("equipment", []):
            relation_id = f"step-{step.get('order', index)}:equipment-{equipment}:requires"
            relations.append({"id": relation_id, "from": f"step-{step.get('order', index)}", "to": f"equipment-{equipment}", "kind": "requires", "label": "需要设备", "source": f"SOP L{step.get('line')}" if step.get('line') else "SOP 原文", **action("relationship", {"planId": plan["id"], "relationId": relation_id, "from": f"step-{step.get('order', index)}", "to": f"equipment-{equipment}", "relation": "requires"})})
        for control in step.get("controls", []):
            relation_id = f"step-{step.get('order', index)}:control-{control}:controlled-by"
            relations.append({"id": relation_id, "from": f"step-{step.get('order', index)}", "to": f"control-{control}", "kind": "controlled-by", "label": "控制措施", "source": f"SOP L{step.get('line')}" if step.get('line') else "SOP 原文", **action("relationship", {"planId": plan["id"], "relationId": relation_id, "from": f"step-{step.get('order', index)}", "to": f"control-{control}", "relation": "controlled-by"})})
    # If a plan uses generic wording rather than a known substance, retain a
    # signal from the deterministic rule engine instead of pretending the
    # parser identified a chemical that was not present in the source.
    for result in failed_rules:
        if result.rule_id in {"ventilation-required", "emergency-controls", "incompatibility-separation", "step-controls"}:
            hazards.append({
                "id": f"rule-{result.rule_id}", "step": None,
                "title": result.message, "detail": result.recommended_control or result.message,
                "controls": [], "ppe": [], "evidence": list(result.evidence_refs),
                "severity": result.severity.value, "source": result.source or f"规则包 {result.rule_version}", "origin": "deterministic-rule",
                **action("rule", {"type": "rule", "planId": plan["id"], "ruleId": result.rule_id}),
            })
    # Keep the graph compact and stable when a long SOP contains repeated
    # mentions of the same control.
    unique_hazards: list[dict] = []
    seen_hazard: set[str] = set()
    for item in hazards:
        key = f"{item['title']}|{item['detail']}"
        if key not in seen_hazard:
            seen_hazard.add(key)
            unique_hazards.append(item)

    conflicts = []
    evidence_gaps = []
    for check in plan_checks:
        if check["state"] == "blocked":
            conflicts.append({
                "id": check["id"], "code": check["code"], "title": check["title"],
                "detail": check["detail"], "equipmentId": check.get("equipmentId"),
                "relatedPlanIds": check.get("relatedPlanIds", []),
                "line": check.get("line"), "severity": "critical",
                **(action("equipment", {"planId": plan["id"], "equipmentId": check.get("equipmentId")}) if check.get("equipmentId") else action("source_line", {"planId": plan["id"], "line": check.get("line")}) if check.get("line") else action("rule", {"planId": plan["id"], "ruleId": check.get("code")})),
            })
        elif check["state"] == "unknown":
            evidence_gaps.append({
                "id": check["id"], "code": check["code"], "title": check["title"],
                "detail": check["detail"], "equipmentId": check.get("equipmentId"),
                "line": check.get("line"), "documentIds": check.get("documentIds", []),
                "priority": "high" if check["code"] in {"EVIDENCE", "SCHEDULE", "BINDING"} else "medium",
                **(action("evidence", {"planId": plan["id"], "documentId": check["documentIds"][0], "equipmentId": check.get("equipmentId")}) if check.get("documentIds") else action("source_line", {"planId": plan["id"], "line": check.get("line")}) if check.get("line") else action("rule", {"planId": plan["id"], "ruleId": check.get("code")})),
            })

    next_actions = []
    for gap in evidence_gaps[:6]:
        if gap["code"] == "EVIDENCE":
            title = "补齐对应设备的有效检查证据"
            detail = "需同时满足对象、规格版本、核验状态和完整使用时段。"
        elif gap["code"] == "SOURCE":
            title = "确认 SOP 步骤与原文行号"
            detail = "确认后才会把机器提取结果纳入资源核验。"
        elif gap["code"] == "SCHEDULE":
            title = "补充资源使用时段"
            detail = "没有时段无法判断维护窗口与共享容量。"
        elif gap["code"] == "BINDING":
            title = "把原文设备绑定到正式预约"
            detail = "不能只替换画面中的关系线；需要修订计划。"
        else:
            title, detail = gap["title"], gap["detail"]
        target = gap.get("actionTarget") or {"type": "rule", "planId": plan["id"], "ruleId": gap.get("code")}
        kind = gap.get("actionKind") or "rule"
        owner = "实验负责人"
        next_actions.append({"id": f"action-{gap['id']}", "title": title, "detail": detail, "sourceId": gap["id"], "owner": owner, "status": "suggested", "line": gap.get("line"), "equipmentId": gap.get("equipmentId"), "documentIds": list(gap.get("documentIds") or []), "taskDraft": task_draft(gap, title, detail, owner, kind, target), **action(kind, target)})
    for conflict in conflicts[:4]:
        target = {"planId": plan["id"], "scenarioId": "resource-alternative"}
        owner = "计划负责人"
        next_actions.append({"id": f"action-{conflict['id']}", "title": "打开方案推演，比较可行资源或时段", "detail": "候选方案先在隔离副本中核验，正式计划不会被自动覆盖。", "sourceId": conflict["id"], "owner": owner, "status": "suggested", "line": conflict.get("line"), "equipmentId": conflict.get("equipmentId"), "taskDraft": task_draft(conflict, "复核资源或时段冲突", conflict["detail"], owner, "scenario", target), **action("scenario", target)})
    if not next_actions:
        target = {"planId": plan["id"], "ruleId": "HUMAN_REVIEW"}
        fallback = {"id": "action-review", "title": "由安全负责人复核当前版本", "detail": "AI 解释和规则结果不能替代机构审批或现场确认。", "sourceId": plan["id"], "owner": "安全负责人", "status": "required"}
        next_actions.append({**fallback, "taskDraft": task_draft(fallback, fallback["title"], fallback["detail"], fallback["owner"], "task", {"planId": plan["id"], "taskId": "draft-human-review"}), **action("task", {"planId": plan["id"], "taskId": "draft-human-review"})})

    # Produce two deterministic candidates for the scenario comparison.  They
    # are suggestions only; applying one still requires the existing branch
    # workflow and creates a new plan revision.
    baseline_counts = {"blocked": sum(c["state"] == "blocked" for c in plan_checks), "unknown": sum(c["state"] == "unknown" for c in plan_checks), "pass": sum(c["state"] == "pass" for c in plan_checks)}
    scenarios = [{"id": "baseline", "name": "当前正式安排", "kind": "baseline", "status": "current", "summary": "以当前计划和已登记资源为基线。", "counts": baseline_counts, "changes": [], "reasoning": ["保留正式计划作为比较基准", "不会因为 AI 结果自动修改"], "actionability": "reference", **action("scenario", {"planId": plan["id"], "scenarioId": "baseline"})}]
    # Alternate resource candidate: use the first available same-kind resource
    # for a conflicted/unknown reservation, if one exists.
    candidate_reservations = [dict(r) for r in plan["reservations"]]
    changes = []
    for reservation in candidate_reservations:
        current = next((e for e in w["equipment"] if e["id"] == reservation["equipmentId"]), None)
        if current is None:
            continue
        current_bad = any(c.get("equipmentId") == current["id"] and c["state"] in {"blocked", "unknown"} for c in plan_checks)
        if not current_bad:
            continue
        replacement = next((e for e in w["equipment"] if e["labId"] == plan["labId"] and e["id"] != current["id"] and e["kind"] == current["kind"] and e["status"] == "available" and not any(overlap(reservation, m) for m in e.get("maintenance", []))), None)
        if replacement:
            reservation["equipmentId"] = replacement["id"]
            changes.append({"from": current["id"], "to": replacement["id"], "reason": "同类别、当前台账可用且不落在维护窗口"})
    if changes:
        candidate = copy.deepcopy(w)
        candidate_plan = next(q for q in candidate["plans"] if q["id"] == plan["id"])
        candidate_plan["reservations"] = candidate_reservations
        candidate_checks = [c for c in check_workspace(candidate) if c["planId"] == plan["id"]]
        scenarios.append({"id": "resource-alternative", "name": "AI 资源替代候选", "kind": "alternative", "status": "suggested", "summary": "用同类别且当前可用资源替代受约束对象，结果仍需人工确认。", "counts": {"blocked": sum(c["state"] == "blocked" for c in candidate_checks), "unknown": sum(c["state"] == "unknown" for c in candidate_checks), "pass": sum(c["state"] == "pass" for c in candidate_checks)}, "changes": changes, "reasoning": ["同类别资源保持设备能力语义", "避开已登记维护窗口和停用状态", "替代结果将在隔离副本中重新核验"], "actionability": "branch", **action("scenario", {"planId": plan["id"], "scenarioId": "resource-alternative"})})
    scenarios.append({"id": "evidence-first", "name": "先补证再放行", "kind": "workflow", "status": "suggested", "summary": "不改变排程，优先处理证据缺口和原文确认。", "counts": baseline_counts, "changes": [{"action": "complete-evidence", "count": len(evidence_gaps)}], "reasoning": ["不改变正式资源预约", f"先闭环 {len(evidence_gaps)} 个证据或确认缺口", "由负责人完成复核后再形成新修订"], "actionability": "task", **action("scenario", {"planId": plan["id"], "scenarioId": "evidence-first"})})

    return {
        "entities": {"steps": len(steps), "hazards": unique_hazards, "substances": substances, "ppe": parsed.get("ppe", []), "equipment": parsed.get("equipment", []), "wasteStreams": parsed.get("waste_streams", []), "ventilation": parsed.get("ventilation"), "modelCandidates": parsed.get("model_candidates", [])},
        "relations": relations,
        "riskSignals": unique_hazards,
        "conflicts": conflicts,
        "evidenceGaps": evidence_gaps,
        "nextActions": next_actions,
        "scenarios": scenarios,
        "ruleSummary": {"total": len(plan_checks), **baseline_counts, "failedTextRules": [r.rule_id for r in failed_rules]},
    }


def _merge_model_parse(parsed: dict, model_fields: Any) -> tuple[dict, bool]:
    """Merge a model candidate without losing deterministic source anchors.

    The model is useful for prose SOPs where the deterministic vocabulary is
    intentionally small.  A model step is accepted only when it carries an
    explicit document revision and source line/text hash that matches the
    source ledger.  Array order, title similarity and missing spans are never
    allowed to inherit a trusted citation.
    """
    if not isinstance(model_fields, dict):
        return parsed, False
    merged = dict(parsed)
    # Candidate output is kept separate from the confirmed deterministic
    # parse.  A model may explain an anchored line, but it cannot silently
    # promote a guessed control or chemical into a fact used by rules.
    merged["model_candidates"] = []
    used = False

    raw_steps = model_fields.get("steps")
    if isinstance(raw_steps, list):
        candidates = []
        from .models import LabStep, Substance
        source_steps = list(parsed.get("steps", []))
        for index, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                continue
            instruction = str(item.get("instruction", "")).strip()
            if not instruction:
                continue
            revision = item.get("documentRevisionId") or item.get("document_revision_id")
            source_line = item.get("sourceLine") or item.get("source_line")
            source_hash = item.get("sourceTextHash") or item.get("source_text_hash")
            try:
                source_line = int(source_line)
            except (TypeError, ValueError):
                source_line = None
            matched = next((candidate for candidate in source_steps if candidate.source_line == source_line), None)
            if not revision or revision != parsed.get("document_revision_id") or matched is None:
                # Unanchored model text remains visible only through the
                # deterministic fallback; it cannot become a cited fact.
                continue
            if source_hash and source_hash != matched.source_text_hash:
                continue
            if matched.instruction.strip() != instruction.strip():
                continue
            try:
                step = LabStep(
                    order=int(item.get("order") or index + 1),
                    instruction=instruction[:500],
                    hazard=str(item.get("hazard") or "").strip() or None,
                    controls=[str(v).strip() for v in item.get("controls", []) if str(v).strip()][:20],
                    requires_ppe=[str(v).strip() for v in item.get("requires_ppe", []) if str(v).strip()][:20],
                    equipment=[str(v).strip() for v in item.get("equipment", []) if str(v).strip()][:20],
                    ventilation=str(item.get("ventilation") or "").strip() or None,
                    waste_stream=str(item.get("waste_stream") or "").strip() or None,
                    evidence_refs=list(matched.evidence_refs),
                    document_revision_id=matched.document_revision_id,
                    source_line=matched.source_line,
                    source_text_hash=matched.source_text_hash,
                    control_assertions=list(matched.control_assertions),
                )
            except (TypeError, ValueError):
                continue
            candidates.append(step)
            merged["model_candidates"].append({
                "kind": "step",
                "documentRevisionId": matched.document_revision_id,
                "sourceLine": matched.source_line,
                "sourceTextHash": matched.source_text_hash,
                "instruction": instruction,
                "hazard": step.hazard,
                "controls": list(step.controls),
                "requiresPpe": list(step.requires_ppe),
                "equipment": list(step.equipment),
                "ventilation": step.ventilation,
                "wasteStream": step.waste_stream,
                "status": "candidate",
            })
        if candidates:
            # Deterministic fields remain authoritative.  This survives model
            # reordering, merging and omission without borrowing another
            # line's evidence or treating a candidate as confirmation.
            used = True

    raw_substances = model_fields.get("substances")
    if isinstance(raw_substances, list):
        candidates = []
        for item in raw_substances:
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                continue
            if str(item.get("name", "")).strip() not in parsed.get("source", "") and str(item.get("name", "")).strip() not in "\n".join(getattr(s, "instruction", "") for s in parsed.get("steps", [])):
                continue
            try:
                name = str(item["name"]).strip()[:180]
                candidates.append({
                    "name": name,
                    "casNumber": str(item.get("cas_number") or "").strip() or None,
                    "hazardClasses": [str(v).strip() for v in item.get("hazard_classes", []) if str(v).strip()][:10],
                    "status": "candidate",
                })
            except (TypeError, ValueError):
                continue
        if candidates:
            # A model may suggest a chemical and a hazard class, but a name
            # substring is not a source anchor.  Keep these suggestions in a
            # visible candidate lane; only the deterministic parser (or a
            # later independently verified SDS) may change authoritative
            # substances used by rules.  This prevents prompt-injected JSON
            # from turning an untrusted model guess into a risk fact.
            merged["model_candidates"].append({
                "kind": "substances",
                "values": candidates,
                "status": "candidate",
                "authority": "none-until-source-anchored-and-reviewed",
            })
            used = True

    for key in ("ppe", "equipment", "waste_streams"):
        values = model_fields.get(key)
        if isinstance(values, list):
            normalized = sorted({str(value).strip() for value in values if str(value).strip()})
            if normalized:
                source_present = [value for value in normalized if any(value in str(getattr(step, "instruction", "")) for step in parsed.get("steps", []))]
                # A substring is not a source assertion: it can appear in a
                # negated sentence or in a prompt-injection aside. Keep the
                # model output visible, but never let it change the
                # authoritative rule inputs without a later human/SDS review.
                merged["model_candidates"].append({"kind": key, "values": normalized, "sourcePresent": source_present, "status": "candidate", "authority": "none-until-reviewed"})
                used = True
    ventilation = model_fields.get("ventilation")
    if isinstance(ventilation, str) and ventilation.strip():
        candidate = ventilation.strip()
        source_present = bool(merged.get("ventilation")) and any(candidate in str(getattr(step, "instruction", "")) for step in parsed.get("steps", []))
        merged["model_candidates"].append({"kind": "ventilation", "value": candidate, "sourcePresent": source_present, "status": "candidate", "authority": "none-until-reviewed"})
        used = True
    return merged, used


def apply_operation(w: dict, action: str, x: dict, actor: str) -> dict:
    next_w = copy.deepcopy(w)
    object_id = x.get("id", x.get("planId", "workspace"))
    summary = ""
    def get(collection, identifier):
        value = next((a for a in next_w[collection] if a["id"] == identifier), None)
        if value is None:
            raise ValueError("关联对象不存在。")
        return value
    def upsert(collection, value):
        index = next((i for i, a in enumerate(next_w[collection]) if a["id"] == value["id"]), None)
        if index is None:
            next_w[collection].append(value)
        else:
            next_w[collection][index] = value
    if action == "initialize":
        if any(w[key] for key in ("laboratories", "equipment", "plans", "documents", "tasks", "decisions", "branches")):
            raise ValueError("已有数据的工作区不能被初始化覆盖。")
        next_w = copy.deepcopy(x["workspace"])
        next_w["decisions"], next_w["events"], next_w["branches"] = [], [], []
        summary = "导入明确标记的样例工作区" if next_w["provenance"] == "example" else "建立空白工作区"
    elif action == "save_lab":
        # Validate the submitted object before touching the workspace.  The
        # final workspace validation below remains authoritative, while this
        # gives callers a useful error when a malformed lab is submitted by a
        # browser form.
        Lab.model_validate(x["lab"])
        upsert("laboratories", x["lab"])
        object_id, summary = x["lab"]["id"], "保存实验室资料"
    elif action == "save_equipment":
        e = copy.deepcopy(x["equipment"])
        previous = next((a for a in w["equipment"] if a["id"] == e["id"]), None)
        if not any(lab["id"] == e["labId"] for lab in next_w["laboratories"]):
            raise ValueError("资源所属实验室不存在。")
        # The form starts a new resource at (0, 0).  Treat that untouched
        # default as a request for server-side placement so repeated saves do
        # not pile models on top of one another.  Callers that intentionally
        # want (0, 0) may pass ``autoPlace: false`` at the operation level.
        at_origin = abs(float(e["x"])) < 1e-9 and abs(float(e["z"])) < 1e-9
        auto_place = at_origin and x.get("autoPlace", True) is not False
        if previous is None and auto_place:
            e["x"], e["z"] = find_equipment_position(next_w, e)
        e["specVersion"] = previous["specVersion"] + int(any(e[k] != previous[k] for k in ("kind", "capacity", "requiresEvidence"))) if previous else 1
        upsert("equipment", e)
        object_id, summary = e["id"], f"更新资源 {e['code']}，核验依赖同步重算"
    elif action == "save_plan":
        p = copy.deepcopy(x["plan"])
        previous = next((a for a in w["plans"] if a["id"] == p["id"]), None)
        if previous and previous["revision"] != x.get("expectedPlanRevision"):
            raise ValueError("计划已变更，请重新载入后保存。")
        if previous and (previous["archived"] or previous.get("lifecycle") == "archived") and not p.get("archived"):
            raise ValueError("已归档计划只能引用或复制，不能直接复活为当前计划。")
        p["revision"] = previous["revision"] + 1 if previous else 1
        if previous and p["source"] != previous["source"]:
            for s in p["steps"]:
                s["confirmed"] = False
            p["lifecycle"] = "revising"
        elif previous:
            p["lifecycle"] = previous.get("lifecycle", "draft")
        else:
            p["lifecycle"] = p.get("lifecycle", "draft")
        if p.get("lifecycle") == "submitted" and (not p["steps"] or any(not s["confirmed"] for s in p["steps"])):
            raise ValueError("计划提交前必须完成全部步骤的人工确认。")
        if p.get("archived"):
            # Archive is a business transition, not a display toggle.  Check
            # the still-active candidate before setting archived=True, because
            # check_workspace intentionally excludes archived plans.
            if not p["steps"] or any(not s["confirmed"] for s in p["steps"]):
                raise ValueError("计划归档前必须完成全部步骤的人工确认。")
            candidate = copy.deepcopy(next_w)
            candidate_plan = next((q for q in candidate["plans"] if q["id"] == p["id"]), None)
            if candidate_plan is None:
                candidate["plans"].append(copy.deepcopy(p))
                candidate_plan = candidate["plans"][-1]
            else:
                candidate_plan.update(copy.deepcopy(p))
            candidate_plan["archived"] = False
            candidate_plan["lifecycle"] = "submitted"
            archive_checks = [c for c in check_workspace(candidate) if c["planId"] == p["id"]]
            if not archive_checks or any(c["state"] != "pass" for c in archive_checks):
                raise ValueError("计划仍有阻断或未知项，不能归档。")
            decisions = [d for d in w["decisions"] if d["planId"] == p["id"]]
            # Saving an archive record increments the plan revision for the
            # audit log.  Compare the approval against the pre-save revision;
            # lifecycle metadata itself must not invalidate an otherwise
            # unchanged decision.
            basis_plan = copy.deepcopy(candidate_plan)
            if previous:
                basis_plan["revision"] = previous["revision"]
            if decisions and decisions[-1]["basis"] != basis(candidate, basis_plan):
                raise ValueError("当前计划基线与最近复核不一致，请先重新复核后归档。")
            p["lifecycle"] = "archived"
        elif p.get("lifecycle") == "archived":
            raise ValueError("归档生命周期必须同时设置 archived=true。")
        upsert("plans", p)
        object_id, summary = p["id"], f"保存计划 {p['code']} · v{p['revision']}"
    elif action == "confirm_steps":
        p = get("plans", x["planId"])
        if not p["steps"]:
            raise ValueError("没有可确认的步骤。")
        if p["archived"] or p.get("lifecycle") in {"archived", "cancelled"}:
            raise ValueError("已归档或已取消计划不能重新确认步骤。")
        for s in p["steps"]:
            s["confirmed"] = True
        p["revision"] += 1
        summary = "人工核对原文与全部步骤"
    elif action == "save_document":
        d = copy.deepcopy(x["document"])
        previous = next((item for item in w["documents"] if item["id"] == d["id"]), None)
        # Preserve capture provenance across edits while recording a bounded,
        # inspectable text length for the exact content that was submitted.
        # This intentionally avoids treating a digest as evidence of source
        # authority; reviewers still verify source, object, version and time.
        if previous:
            for field in ("sourceType", "sourceLocator", "capturedAt", "provenanceNote"):
                if d.get(field) is None and previous.get(field) is not None:
                    d[field] = previous[field]
        d.setdefault("sourceType", "manual")
        d.setdefault("capturedAt", now())
        d["contentLength"] = len(d.get("content", ""))
        d.update(status="pending", reviewedBy=None, reviewedAt=None)
        upsert("documents", d)
        object_id, summary = d["id"], "提交资料，等待独立核验"
    elif action == "verify_document":
        d = get("documents", x["id"])
        if x.get("status") not in ("verified", "rejected"):
            raise ValueError("资料核验状态无效。")
        d.update(status=x["status"], reviewedBy=actor, reviewedAt=now())
        summary = "记录资料核验结果" if d["status"] == "verified" else "退回资料"
    elif action == "save_task":
        task = copy.deepcopy(x["task"])
        # An AI action carries a stable source id and action kind.  Reopening
        # the same suggestion must not create a second indistinguishable open
        # task; an explicitly completed task may be reopened only by changing
        # its source/action or by editing the existing record.
        if task.get("sourceId") and task.get("actionKind"):
            duplicate = next((existing for existing in next_w["tasks"] if existing["id"] != task.get("id")
                and existing.get("planId") == task.get("planId")
                and existing.get("sourceId") == task.get("sourceId")
                and existing.get("sourceLine") == task.get("sourceLine")
                and existing.get("actionKind") == task.get("actionKind")
                and existing.get("status") in {"open", "submitted", "returned", "reopened"}), None)
            if duplicate:
                raise ValueError("该 AI 建议已有未完成任务，请打开原任务继续处理。")
        upsert("tasks", task)
        object_id, summary = x["task"]["id"], "创建协作任务"
    elif action == "assign_task":
        # Assignment is an explicit collaboration mutation, separate from a
        # task status update.  It leaves the evidence/approval basis untouched
        # and records the hand-off reason in the audit event below.  The local
        # role gate in ``mutate_workspace`` keeps this operation from being
        # presented as a multi-user permission system.
        t = get("tasks", x["id"])
        if t["status"] in {"done", "cancelled"}:
            raise ValueError("已完成或已取消任务不能直接转交；请先重新打开任务。")
        new_owner = str(x.get("newOwner", "")).strip()
        note = str(x.get("note", "")).strip()
        expected_owner = x.get("expectedOwner")
        if expected_owner is not None and str(expected_owner) != t["owner"]:
            raise ValueError("任务负责人已变化，请刷新后重新转交。")
        if not new_owner or len(new_owner) > 180:
            raise ValueError("转交负责人不能为空且不能超过 180 个字符。")
        if new_owner == t["owner"]:
            raise ValueError("转交负责人必须与当前负责人不同。")
        if not note or len(note) > 2000:
            raise ValueError("转交任务必须填写不超过 2000 个字符的交接说明。")
        previous_owner = t["owner"]
        t["owner"] = new_owner
        object_id = t["id"]
        summary = f"转交协作任务：{previous_owner} → {new_owner}；{note}"
    elif action == "update_task":
        t = get("tasks", x["id"])
        requested = x.get("status")
        allowed = {"open", "submitted", "done", "returned", "cancelled", "reopened"}
        if requested not in allowed:
            raise ValueError("任务状态无效。")
        current = t["status"]
        transitions = {
            "open": {"open", "submitted", "done", "cancelled"},
            "submitted": {"submitted", "done", "returned", "cancelled"},
            "returned": {"returned", "reopened", "cancelled"},
            "reopened": {"reopened", "submitted", "done", "cancelled"},
            "done": {"done", "reopened"},
            "cancelled": {"cancelled", "reopened"},
        }
        if requested not in transitions.get(current, set()):
            raise ValueError(f"任务不能从“{current}”流转到“{requested}”。")
        note = str(x.get("note", t["note"])).strip()
        if requested in {"returned", "cancelled", "reopened"} and not note:
            raise ValueError("退回、取消或重开任务必须填写处理说明。")
        handoff_requested = any(key in x for key in ("newOwner", "expectedOwner", "handoffNote"))
        previous_owner = t["owner"]
        new_owner = ""
        handoff_note = ""
        if handoff_requested:
            # Status changes and ownership changes are one business operation.
            # This avoids leaving a task half-transferred when the second
            # request in a browser form fails or loses its revision race.
            if current in {"done", "cancelled"}:
                raise ValueError("已完成或已取消任务不能在同一操作中直接转交；请先重新打开任务。")
            expected_owner = x.get("expectedOwner")
            if expected_owner is None or str(expected_owner) != t["owner"]:
                raise ValueError("任务负责人已变化，请刷新后重新转交。")
            new_owner = str(x.get("newOwner", "")).strip()
            handoff_note = str(x.get("handoffNote", "")).strip()
            if not new_owner or len(new_owner) > 180:
                raise ValueError("转交负责人不能为空且不能超过 180 个字符。")
            if new_owner == t["owner"]:
                raise ValueError("转交负责人必须与当前负责人不同。")
            if not handoff_note or len(handoff_note) > 2000:
                raise ValueError("转交任务必须填写不超过 2000 个字符的交接说明。")
        t.update(status=requested, note=note)
        if handoff_requested:
            t["owner"] = new_owner
        labels = {"returned": "退回补充", "cancelled": "取消任务", "reopened": "重新打开"}
        summary = labels.get(requested, "更新任务进度") + "；不自动改变证据或审批"
        if handoff_requested:
            summary = f"{summary}；同时转交：{previous_owner} → {new_owner}；{handoff_note}"
    elif action == "save_branch":
        b = copy.deepcopy(x["branch"])
        p = get("plans", b["planId"])
        if p["revision"] != b["baseRevision"] or basis(w, p) != b["baseBasis"]:
            raise ValueError("方案基线已变化，请以当前计划重新创建。")
        branch_candidate(next_w, b)
        upsert("branches", b)
        object_id, summary = b["id"], "保存独立候选方案，正式计划未改变"
    elif action == "apply_branch":
        b = get("branches", x["id"])
        p = get("plans", b["planId"])
        if p["revision"] != b["baseRevision"] or basis(w, p) != b["baseBasis"]:
            raise ValueError("方案已过期：计划、资源或证据发生变化，请重新比较。")
        candidate = branch_candidate(next_w, b)
        candidate_plan = next(q for q in candidate["plans"] if q["id"] == p["id"])
        p["reservations"] = copy.deepcopy(candidate_plan["reservations"])
        p["revision"] += 1
        patch_count = len(b.get("patches", []))
        detail = f"，记录 {patch_count} 个字段变更" if patch_count else ""
        object_id, summary = p["id"], f"应用方案「{b['name']}」，产生新修订并触发重新复核{detail}"
    elif action == "approve":
        p = get("plans", x["planId"])
        if p["revision"] != x.get("expectedPlanRevision") or p["archived"] or p.get("lifecycle") in {"archived", "cancelled"}:
            raise ValueError("计划版本已改变或已归档。")
        if not x.get("comment", "").strip():
            raise ValueError("必须填写人工复核意见。")
        checks = [c for c in check_workspace(next_w) if c["planId"] == p["id"]]
        if not checks or any(c["state"] != "pass" for c in checks):
            raise ValueError("仍有阻断或未知项，不能记录复核通过。")
        role = str(x.get("_serverRole", "safety_owner"))
        stage = approval_stages()[0]
        next_w["decisions"].append(dict(
            id=uid("decision"), planId=p["id"], revision=p["revision"],
            basis=basis(next_w, p), actor=actor, comment=x["comment"], at=now(),
            disposition="approved", actorRole=role, stage=stage,
            checkSnapshot=decision_check_snapshot(checks), exception=None,
        ))
        p["lifecycle"] = "submitted"
        summary = "记录当前版本的资源前置条件复核；不构成化学安全认证"
    elif action == "approval_decision":
        p = get("plans", x["planId"])
        if p["revision"] != x.get("expectedPlanRevision") or p["archived"] or p.get("lifecycle") in {"archived", "cancelled"}:
            raise ValueError("计划版本已改变或已归档。")
        comment = str(x.get("comment", "")).strip()
        if not comment:
            raise ValueError("必须填写人工复核意见。")
        disposition = x.get("disposition")
        if disposition not in {"approved", "returned", "exception"}:
            raise ValueError("审批决定必须是 approved、returned 或 exception。")
        role = str(x.get("_serverRole", "safety_owner"))
        if role not in {"safety_owner", "ehs_manager", "administrator"}:
            raise ValueError("当前工作区身份没有记录正式审批的权限。")
        checks = [c for c in check_workspace(next_w) if c["planId"] == p["id"]]
        if not checks:
            raise ValueError("计划没有可供复核的检查快照。")
        current = approval_state(next_w, p, checks)
        stages = approval_stages()
        pending_stage = current["pendingStage"] or stages[0]
        if len(stages) > 1 and role != pending_stage and role != "administrator":
            raise ValueError(f"当前审批链等待“{pending_stage}”阶段，不能由当前身份越级处理。")
        stage = pending_stage
        exception_payload = None
        if disposition == "approved":
            if any(c["state"] != "pass" for c in checks):
                raise ValueError("仍有阻断或未知项，不能记录复核通过。")
            p["lifecycle"] = "submitted"
            summary = f"记录审批阶段 {stage} 的复核通过；不构成化学安全认证"
        elif disposition == "returned":
            p["lifecycle"] = "revising"
            summary = f"审批阶段 {stage} 退回计划，等待补充后重新复核"
        else:
            if role not in {"ehs_manager", "administrator"}:
                raise ValueError("例外授权只能由 EHS 负责人或管理员记录。")
            raw_exception = x.get("exception")
            if not isinstance(raw_exception, dict):
                raise ValueError("例外授权必须说明检查项、原因、缓解措施和失效时间。")
            check_ids = raw_exception.get("checkIds")
            reason = str(raw_exception.get("reason", "")).strip()
            mitigation = str(raw_exception.get("mitigation", "")).strip()
            expires_at = str(raw_exception.get("expiresAt", "")).strip()
            if not isinstance(check_ids, list) or not check_ids or any(not isinstance(item, str) for item in check_ids):
                raise ValueError("例外授权至少要指定一个检查项。")
            by_id = {c["id"]: c for c in checks}
            selected = [by_id.get(item) for item in check_ids]
            if any(item is None for item in selected):
                raise ValueError("例外授权引用了当前计划不存在的检查项。")
            if any(item["state"] == "pass" for item in selected):
                raise ValueError("例外授权只能针对当前阻断或待确认项。")
            if not reason or not mitigation:
                raise ValueError("例外授权必须填写原因和缓解措施。")
            try:
                expiry = dt(expires_at)
            except (TypeError, ValueError) as error:
                raise ValueError("例外失效时间必须是带时区的 ISO 时间。") from error
            if expiry <= datetime.now(timezone.utc):
                raise ValueError("例外失效时间必须晚于当前时间。")
            exception_payload = {"checkIds": list(dict.fromkeys(check_ids)), "reason": reason[:2000], "mitigation": mitigation[:2000], "expiresAt": expires_at}
            p["lifecycle"] = "submitted"
            summary = f"审批阶段 {stage} 记录限时例外；原始检查仍保留为阻断或待确认"
        next_w["decisions"].append(dict(
            id=uid("decision"), planId=p["id"], revision=p["revision"],
            basis=basis(next_w, p), actor=actor, comment=comment, at=now(),
            disposition=disposition, actorRole=role, stage=stage,
            checkSnapshot=decision_check_snapshot(checks), exception=exception_payload,
        ))
        object_id = p["id"]
    elif action == "transition_plan":
        p = get("plans", x["planId"])
        requested = x.get("lifecycle", x.get("status"))
        allowed = {"draft", "submitted", "revising", "archived", "cancelled"}
        if requested not in allowed:
            raise ValueError("计划生命周期无效。")
        current = "archived" if p["archived"] else p.get("lifecycle", "draft")
        transitions = {
            "draft": {"draft", "submitted", "cancelled"},
            "submitted": {"submitted", "revising", "cancelled", "archived"},
            "revising": {"revising", "submitted", "cancelled"},
            "cancelled": {"cancelled"},
            "archived": {"archived"},
        }
        if requested not in transitions[current]:
            raise ValueError(f"计划不能从“{current}”流转到“{requested}”。")
        if requested == "submitted":
            if not p["steps"] or any(not s["confirmed"] for s in p["steps"]):
                raise ValueError("计划提交前必须完成全部步骤的人工确认。")
            p["lifecycle"] = "submitted"
            summary = "提交当前计划版本，等待资源与证据复核"
        elif requested == "revising":
            p["lifecycle"] = "revising"
            summary = "打开计划修订状态；正式版本未被候选覆盖"
        elif requested == "cancelled":
            p["lifecycle"] = "cancelled"
            p["archived"] = False
            summary = "取消计划；保留历史记录且不再参与当前资源检查"
        elif requested == "archived":
            if not p["steps"] or any(not s["confirmed"] for s in p["steps"]):
                raise ValueError("计划归档前必须完成全部步骤的人工确认。")
            candidate = copy.deepcopy(next_w)
            candidate_plan = next(q for q in candidate["plans"] if q["id"] == p["id"])
            candidate_plan["archived"] = False
            candidate_plan["lifecycle"] = "submitted"
            archive_checks = [c for c in check_workspace(candidate) if c["planId"] == p["id"]]
            if not archive_checks or any(c["state"] != "pass" for c in archive_checks):
                raise ValueError("计划仍有阻断或未知项，不能归档。")
            decisions = [d for d in w["decisions"] if d["planId"] == p["id"]]
            if decisions and decisions[-1]["basis"] != basis(candidate, candidate_plan):
                raise ValueError("当前计划基线与最近复核不一致，请先重新复核后归档。")
            p["lifecycle"] = "archived"
            p["archived"] = True
            summary = "归档当前计划版本；历史依据仍可追溯，不能直接复活"
        else:
            p["lifecycle"] = requested
            summary = "更新计划生命周期"
    else:
        raise ValueError("不支持的操作。")
    next_w["revision"] = w["revision"] + 1
    next_w["events"].append(dict(id=uid("event"), at=now(), actor=actor, action=action, objectId=object_id, summary=summary))
    return validate_workspace(next_w)


class WorkspaceStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS spatial_workspace(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS spatial_operations(id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, result_revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS spatial_analysis_runs(
                    run_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, plan_revision INTEGER NOT NULL,
                    generated_at TEXT NOT NULL, degraded INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_spatial_analysis_plan ON spatial_analysis_runs(plan_id, generated_at DESC);
                CREATE TABLE IF NOT EXISTS spatial_evaluation_runs(
                    evaluation_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, plan_revision INTEGER NOT NULL,
                    evaluated_at TEXT NOT NULL, basis TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_spatial_evaluation_plan ON spatial_evaluation_runs(plan_id, evaluated_at DESC);
                CREATE TABLE IF NOT EXISTS spatial_jobs(
                    job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, plan_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    result_payload TEXT, error TEXT, request_payload TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_spatial_jobs_plan ON spatial_jobs(plan_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS spatial_workspace_snapshots(
                    snapshot_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    saved_at TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_spatial_workspace_snapshots_saved
                    ON spatial_workspace_snapshots(saved_at DESC);
            """)
            # Upgrade local databases created before queued browser jobs kept
            # their replay inputs.  The nullable column is intentionally
            # additive so existing job IDs and terminal history remain intact.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(spatial_jobs)").fetchall()}
            if "request_payload" not in columns:
                conn.execute("ALTER TABLE spatial_jobs ADD COLUMN request_payload TEXT")
            # There is no worker process in the browser-only deployment.  A
            # process that opens the database after a crash/restart therefore
            # must make an unfinished synchronous job explicit instead of
            # leaving a misleading `running` state forever.
            conn.execute(
                """UPDATE spatial_jobs
                   SET status='failed', finished_at=COALESCE(finished_at, ?),
                       error=COALESCE(error, ?)
                   WHERE status IN ('queued','running')""",
                (now(), "服务重启时进程内任务未能继续；本地部署没有持久 Worker，任务已标记失败，可按幂等边界重新发起。"),
            )
            conn.execute("INSERT OR IGNORE INTO spatial_workspace VALUES(1,0,?)", (json.dumps(empty_workspace(), ensure_ascii=False),))
    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    def read(self) -> dict:
        with self.connection() as conn:
            return json.loads(conn.execute("SELECT payload FROM spatial_workspace WHERE id=1").fetchone()[0])
    def mutate(self, expected: int, request_id: str, action: str, payload: dict, actor: str) -> dict:
        fingerprint = hashlib.sha256(canonical(dict(type=action, payload=payload)).encode()).hexdigest()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT revision,payload FROM spatial_workspace WHERE id=1").fetchone()
            previous = conn.execute("SELECT request_hash FROM spatial_operations WHERE id=?", (request_id,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise HTTPException(409, "同一操作标识不能用于不同请求。")
                return json.loads(row[1])
            if row[0] != expected:
                raise HTTPException(409, "工作区已被其他请求更新，请刷新后重试；未覆盖已有数据。")
            result = apply_operation(json.loads(row[1]), action, payload, actor)
            conn.execute("UPDATE spatial_workspace SET revision=?,payload=? WHERE id=1", (result["revision"], json.dumps(result, ensure_ascii=False)))
            conn.execute("INSERT INTO spatial_operations VALUES(?,?,?)", (request_id, fingerprint, result["revision"]))
            return result
    def save_analysis_run(self, payload: dict) -> None:
        trace = payload.get("trace") or {}
        run_id = str(trace.get("runId") or uid("analysis"))
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO spatial_analysis_runs(run_id,plan_id,plan_revision,generated_at,degraded,payload)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET
                   plan_revision=excluded.plan_revision,generated_at=excluded.generated_at,
                   degraded=excluded.degraded,payload=excluded.payload""",
                (run_id, str(payload.get("planId", "")), int(payload.get("planRevision", 0)), str(trace.get("generatedAt") or now()), 1 if payload.get("degraded") else 0, json.dumps(payload, ensure_ascii=False)),
            )
    def analysis_runs(self, plan_id: str, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT payload FROM spatial_analysis_runs WHERE plan_id=? ORDER BY generated_at DESC LIMIT ?", (plan_id, max(1, min(limit, 100)))).fetchall()
        return [json.loads(row[0]) for row in rows]
    def save_evaluation_run(self, payload: dict) -> dict:
        evaluation_id = str(payload.get("evaluationId") or uid("evaluation"))
        record = {**payload, "evaluationId": evaluation_id}
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO spatial_evaluation_runs(evaluation_id,plan_id,plan_revision,evaluated_at,basis,status,payload)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(evaluation_id) DO UPDATE SET
                   evaluated_at=excluded.evaluated_at,basis=excluded.basis,status=excluded.status,payload=excluded.payload""",
                (evaluation_id, str(record.get("planId", "")), int(record.get("planRevision", 0)), str(record.get("evaluatedAt") or now()), str(record.get("basis", "")), str(record.get("status", "completed")), json.dumps(record, ensure_ascii=False)),
            )
        return record
    def evaluation_runs(self, plan_id: str, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT payload FROM spatial_evaluation_runs WHERE plan_id=? ORDER BY evaluated_at DESC LIMIT ?", (plan_id, max(1, min(limit, 100)))).fetchall()
        return [json.loads(row[0]) for row in rows]
    def begin_job(self, *, job_id: str, kind: str, plan_id: str | None, idempotency_key: str, context: dict | None = None) -> dict:
        """Create or resume a durable job record.

        ``context`` contains only bounded replay inputs (for example an expiry
        ``asOf`` timestamp).  It lets duplicate queued requests compare their
        inputs without pretending that a process-local runner is durable.
        """
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM spatial_jobs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if row:
                return self._job_row(row)
            created = now()
            encoded_context = json.dumps(context, ensure_ascii=False, separators=(",", ":")) if context else None
            conn.execute("INSERT INTO spatial_jobs(job_id,kind,plan_id,idempotency_key,status,created_at,request_payload) VALUES(?,?,?,?,?,?,?)",
                         (job_id, kind, plan_id, idempotency_key, "queued", created, encoded_context))
            return self._job_row(conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone())
    @staticmethod
    def _job_row(row: sqlite3.Row | tuple) -> dict:
        keys = ("jobId", "kind", "planId", "idempotencyKey", "status", "createdAt", "startedAt", "finishedAt", "result", "error", "context")
        item = dict(zip(keys, row))
        if item.get("result"):
            item["result"] = json.loads(item["result"])
        if item.get("context"):
            item["context"] = json.loads(item["context"])
        return item
    def set_job_running(self, job_id: str) -> dict:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise HTTPException(404, "后台任务不存在。")
            if row[4] != "queued":
                if row[4] in {"running"}:
                    return self._job_row(row)
                raise HTTPException(409, f"任务已经进入终态 {row[4]}，不能重新运行。")
            conn.execute("UPDATE spatial_jobs SET status='running',started_at=COALESCE(started_at,?),error=NULL WHERE job_id=? AND status='queued'", (now(), job_id))
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job_row(row)
    def finish_job(self, job_id: str, *, status: str, result: dict | None = None, error: str | None = None) -> dict:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("无效的任务终态。")
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise HTTPException(404, "后台任务不存在。")
            current = row[4]
            if current in {"succeeded", "failed", "cancelled"}:
                if current == status:
                    return self._job_row(row)
                raise HTTPException(409, f"任务已经进入终态 {current}，不能改成 {status}。")
            if status == "succeeded" and current != "running":
                raise HTTPException(409, "只有运行中的任务可以完成。")
            conn.execute("UPDATE spatial_jobs SET status=?,finished_at=?,result_payload=?,error=? WHERE job_id=? AND status IN ('queued','running')",
                         (status, now(), json.dumps(result, ensure_ascii=False) if result is not None else None, error, job_id))
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job_row(row)
    def cancel_job(self, job_id: str, *, reason: str = "由负责人取消") -> dict:
        """Cancel a queued/running job and keep terminal states immutable."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise HTTPException(404, "后台任务不存在。")
            current = row[4]
            if current == "cancelled":
                return self._job_row(row)
            if current in {"succeeded", "failed"}:
                raise HTTPException(409, f"任务已经进入终态 {current}，不能取消。")
            conn.execute(
                "UPDATE spatial_jobs SET status='cancelled',finished_at=?,error=? WHERE job_id=? AND status IN ('queued','running')",
                (now(), reason[:500], job_id),
            )
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job_row(row)
    def job(self, job_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM spatial_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job_row(row) if row else None
    def jobs(self, plan_id: str, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM spatial_jobs WHERE plan_id=? ORDER BY created_at DESC LIMIT ?", (plan_id, max(1, min(limit, 100)))).fetchall()
        return [self._job_row(row) for row in rows]
    def expiry_recheck(self, *, request_id: str, as_of: str, actor: str) -> dict:
        """Run and persist a manual expiry scan using the durable job ledger.

        This is intentionally synchronous.  The returned ``worker`` marker is
        ``not-running`` and makes the boundary explicit until a real scheduler
        and outbox are introduced.  Idempotency is keyed by the caller's
        request ID, so retrying a browser request returns the original report.
        """
        try:
            dt(as_of)
        except (TypeError, ValueError) as error:
            raise ValueError("重检时间必须是带时区的 ISO 时间。") from error
        job_id = f"expiry-recheck:{request_id}"
        context = {"asOf": as_of}
        job = self.begin_job(job_id=job_id, kind="expiry_recheck", plan_id=None, idempotency_key=request_id, context=context)
        stored_context = job.get("context") or {}
        if stored_context.get("asOf") and dt(stored_context["asOf"]) != dt(as_of):
            raise HTTPException(409, "同一 requestId 不能用于不同的重检时间。")
        if job["status"] == "succeeded" and job.get("result"):
            stored_as_of = job["result"].get("asOf")
            if stored_as_of and dt(stored_as_of) != dt(as_of):
                raise HTTPException(409, "同一 requestId 不能用于不同的重检时间。")
            return job
        if job["status"] in {"failed", "cancelled"}:
            raise HTTPException(409, f"该重检任务已处于 {job['status']} 终态，请更换 requestId 重试。")
        self.set_job_running(job_id)
        try:
            report = expiry_recheck_report(self.read(), as_of)
            report.update({"requestId": request_id, "jobId": job_id, "generatedAt": now(), "actor": actor})
            return self.finish_job(job_id, status="succeeded", result=report)
        except Exception as error:
            current = self.job(job_id)
            if current and current["status"] in {"queued", "running"}:
                self.finish_job(job_id, status="failed", error=f"{type(error).__name__}: {str(error)[:500]}")
            raise
    def restore(self, *, expected_revision: int, request_id: str, candidate: dict, actor: str) -> dict:
        """Replace the workspace only after validation and a durable pre-restore snapshot.

        The imported revision is deliberately ignored.  Restore is an ordinary
        optimistic-concurrency mutation: a stale browser cannot overwrite a
        newer server state, and retrying the same request is idempotent.
        """
        fingerprint = hashlib.sha256(canonical(dict(type="restore_workspace", workspace=candidate)).encode()).hexdigest()
        validate_workspace(candidate)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT revision,payload FROM spatial_workspace WHERE id=1").fetchone()
            previous = conn.execute("SELECT request_hash FROM spatial_operations WHERE id=?", (request_id,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise HTTPException(409, "同一恢复操作标识不能用于不同存档。")
                return json.loads(row[1])
            if row[0] != expected_revision:
                raise HTTPException(409, "工作区已被其他请求更新，请刷新后重试；未覆盖已有数据。")
            before = json.loads(row[1])
            snapshot_id = uid("snapshot")
            saved_at = now()
            conn.execute(
                "INSERT INTO spatial_workspace_snapshots(snapshot_id,revision,saved_at,actor,reason,payload) VALUES(?,?,?,?,?,?)",
                (snapshot_id, int(row[0]), saved_at, actor, "restore_workspace_before_replace", json.dumps(before, ensure_ascii=False)),
            )
            restored = copy.deepcopy(candidate)
            restored["revision"] = int(row[0]) + 1
            restored.setdefault("events", [])
            restored["events"] = [*restored["events"], dict(
                id=uid("event"), at=saved_at, actor=actor, action="restore_workspace",
                objectId="workspace", summary=f"从服务端恢复文件替换工作区；恢复前快照 {snapshot_id}",
            )]
            validate_workspace(restored)
            conn.execute("UPDATE spatial_workspace SET revision=?,payload=? WHERE id=1", (restored["revision"], json.dumps(restored, ensure_ascii=False)))
            conn.execute("INSERT INTO spatial_operations VALUES(?,?,?)", (request_id, fingerprint, restored["revision"]))
            return restored
    def snapshots(self, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT snapshot_id,revision,saved_at,actor,reason FROM spatial_workspace_snapshots ORDER BY saved_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(snapshotId=row[0], revision=row[1], savedAt=row[2], actor=row[3], reason=row[4]) for row in rows]
    def snapshot(self, snapshot_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT snapshot_id,revision,saved_at,actor,reason,payload FROM spatial_workspace_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if not row:
            return None
        return dict(snapshotId=row[0], revision=row[1], savedAt=row[2], actor=row[3], reason=row[4], workspace=json.loads(row[5]))


_store: WorkspaceStore | None = None

def store() -> WorkspaceStore:
    global _store
    if _store is None:
        _store = WorkspaceStore(os.getenv("AEGIS_SPATIAL_DB_PATH", str(ROOT / "aegis-spatial.db")))
    return _store


def local_owner(request: Request) -> str:
    token = os.getenv("AEGIS_WORKSPACE_TOKEN", "")
    authorization = request.headers.get("authorization", "")
    if token:
        if not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, "工作区访问令牌无效。")
    else:
        peer = request.client.host if request.client else ""
        host = request.url.hostname
        origin = request.headers.get("origin")
        if peer not in {"127.0.0.1", "::1", "testclient"} or host not in {"localhost", "127.0.0.1", "::1", "testserver"}:
            raise HTTPException(403, "未配置访问令牌时仅允许本机访问。")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise HTTPException(403, "拒绝非本机网页来源。")
    return os.getenv("AEGIS_WORKSPACE_OWNER", "本机负责人")


def local_role() -> str:
    """Return the server-configured role for this local workspace.

    Browser payloads never choose this value.  The local single-owner default
    is a safety owner for development; deployments should set an explicit
    role and a workspace token before exposing the API beyond localhost.
    """
    role = os.getenv("AEGIS_WORKSPACE_ROLE", "safety_owner").strip()
    if role not in {"instructor", "researcher", "safety_owner", "ehs_manager", "administrator"}:
        raise HTTPException(500, "工作区角色配置无效。")
    return role

class Mutation(StrictModel):
    expectedRevision: int = Field(ge=0)
    requestId: str = Field(min_length=8, max_length=128)
    type: str = Field(max_length=60)
    payload: dict

class RestoreRequest(StrictModel):
    expectedRevision: int = Field(ge=0)
    requestId: str = Field(min_length=8, max_length=128)
    confirm: Literal["RESTORE"]
    workspace: dict


class ExpiryRecheckRequest(StrictModel):
    """A manually-triggered, durable expiry scan.

    ``asOf`` is injectable so an operator can reproduce a review at a known
    time.  The endpoint records the result as a durable job; it does not claim
    that a background worker or scheduler is running.
    """

    requestId: str = Field(default_factory=lambda: uid("expiry"), min_length=8, max_length=128)
    asOf: str | None = None

router = APIRouter(prefix="/api/spatial", tags=["web-workspace"])

# Keep this contract explicit instead of silently returning an empty graph for
# a misspelled type.  The endpoint is intentionally limited to entities that
# are persisted in the workspace snapshot; chemical/control candidates that
# only exist in the AI parser are not promoted to server graph facts here.
GRAPH_NODE_TYPES = frozenset({"plan", "step", "equipment", "document", "task", "check"})

@router.get("")
def get_workspace(actor: str = Depends(local_owner)):
    return envelope(store().read())

@router.get("/sources")
def get_source_registry(actor: str = Depends(local_owner)):
    """Return public source metadata used by equipment category citations."""
    sources = read_source_registry()
    return {"sources": sources, "scope": "公开类别与管理机制参考，不是机构资产台账"}

@router.get("/plans/{plan_id}/approval")
def get_plan_approval(plan_id: str, actor: str = Depends(local_owner)):
    """Return the server-derived approval chain for one current plan."""
    w = store().read()
    plan = next((item for item in w.get("plans", []) if item.get("id") == plan_id), None)
    if plan is None:
        raise HTTPException(404, "计划不存在。")
    checks = [item for item in check_workspace(w) if item.get("planId") == plan_id]
    state = approval_state(w, plan, checks)
    return {"planId": plan_id, "planRevision": plan.get("revision"), "role": local_role(), "status": plan_status(w, plan, checks), **state}

@router.get("/graph")
def get_relationship_graph(
    planId: str | None = None,
    labId: str | None = None,
    types: str | None = None,
    nodeId: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    hops: int = 0,
    actor: str = Depends(local_owner),
):
    """Return a server-derived relationship subgraph for the current snapshot.

    The browser graph is a projection, while this endpoint is the queryable
    source of truth: every edge is derived from a plan, step, reservation,
    document, task or deterministic check in the workspace payload.  ``types``
    filters node types (comma separated), ``nodeId`` plus ``hops`` requests a
    local neighbourhood, and date bounds retain reservations intersecting the
    requested interval.  Unknown or missing evidence is represented as a node
    state and is never promoted to a pass result.
    """
    if hops < 0 or hops > 2:
        raise HTTPException(422, "hops 必须在 0 到 2 之间。")
    w = store().read()
    # Keep the query scoped to the active laboratory as well as the optional
    # plan.  The browser already applies this scope to its local projection,
    # but direct graph consumers must not accidentally receive relationships
    # from another laboratory in the same workspace.
    plans = [
        p for p in w.get("plans", [])
        if (not planId or p.get("id") == planId)
        and (not labId or p.get("labId") == labId)
    ]
    if planId and not plans:
        if labId and any(p.get("id") == planId for p in w.get("plans", [])):
            raise HTTPException(404, "计划不属于当前实验室。")
        raise HTTPException(404, "计划不存在。")
    allowed_types = {item.strip() for item in (types or "").split(",") if item.strip()}
    unknown_types = sorted(allowed_types - GRAPH_NODE_TYPES)
    if unknown_types:
        raise HTTPException(422, f"types 包含不支持的节点类型：{', '.join(unknown_types)}。")
    try:
        start_bound = dt(dateFrom) if dateFrom else None
        end_bound = dt(dateTo) if dateTo else None
    except ValueError as error:
        raise HTTPException(422, "dateFrom/dateTo 必须是带时区的 ISO 时间。") from error
    if start_bound and end_bound and start_bound >= end_bound:
        raise HTTPException(422, "dateFrom 必须早于 dateTo。")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    def add_node(node_id: str, node_type: str, label: str, **extra: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "label": label, **extra}
    def canonical_edge_state(value: Any) -> str:
        if value in {"pass", "unknown", "blocked"}:
            return value
        return {"verified": "pass", "rejected": "blocked", "done": "pass"}.get(value, "unknown")

    def add_edge(edge_id: str, source: str, target: str, relation: str, *, state: str | None = None, provenance: str | None = None, **extra: Any) -> None:
        # Consumers can render a single state vocabulary for every relation.
        # Legacy status values are retained for evidence edges, while the
        # canonical state makes unknown/rejected evidence explicit.
        status = extra.get("status")
        canonical_state = canonical_edge_state(state if state is not None else status)
        edge = {"id": edge_id, "from": source, "to": target, "relation": relation, "state": canonical_state, **extra}
        if provenance:
            edge["provenance"] = provenance
        edges.append(edge)
    def in_window(item: dict) -> bool:
        if not start_bound and not end_bound:
            return True
        try:
            item_start, item_end = dt(item["start"]), dt(item["end"])
        except (KeyError, ValueError):
            return False
        return (not end_bound or item_start < end_bound) and (not start_bound or item_end > start_bound)

    equipment_by_id = {e["id"]: e for e in w.get("equipment", [])}
    documents = w.get("documents", [])
    tasks = w.get("tasks", [])
    all_checks = check_workspace(w)
    for plan in plans:
        pid = plan["id"]
        window_reservations = [r for r in plan.get("reservations", []) if in_window(r)]
        plan_checks = [check for check in all_checks if check.get("planId") == pid]
        current_status = plan_status(w, plan, plan_checks)
        add_node(
            f"plan:{pid}", "plan", plan.get("name", pid), planId=pid, labId=plan.get("labId"),
            revision=plan.get("revision"), state=current_status, status=current_status,
            source=plan.get("sourceName") or plan.get("source"),
            reservationCount=len(window_reservations),
            timeFiltered=bool(start_bound or end_bound),
        )
        used_equipment: set[str] = set()
        for index, step in enumerate(plan.get("steps", []), 1):
            sid = f"step:{plan['id']}:{step.get('line', index)}"
            add_node(sid, "step", step.get("text", f"步骤 {index}"), planId=pid, sourceLine=step.get("line"), state="confirmed" if step.get("confirmed") else "candidate")
            add_edge(f"{pid}:step:{step.get('line', index)}", f"plan:{pid}", sid, "contains", state="pass" if step.get("confirmed") else "unknown", sourceLine=step.get("line"), provenance="SOP 原文")
            for equipment_id in step.get("equipmentIds", []):
                if equipment_id not in equipment_by_id:
                    continue
                used_equipment.add(equipment_id)
                edge_id = f"{pid}:step:{step.get('line', index)}:equipment:{equipment_id}"
                add_edge(edge_id, sid, f"equipment:{equipment_id}", "requires", state="pass", sourceLine=step.get("line"), provenance="SOP 原文")
        for reservation in plan.get("reservations", []):
            if not in_window(reservation):
                continue
            equipment_id = reservation.get("equipmentId")
            equipment = equipment_by_id.get(equipment_id)
            if not equipment:
                continue
            used_equipment.add(equipment_id)
            add_node(f"equipment:{equipment_id}", "equipment", equipment.get("name", equipment_id), equipmentId=equipment_id, labId=equipment.get("labId"), kind=equipment.get("kind"), state=equipment.get("status"), start=reservation.get("start"), end=reservation.get("end"))
            add_edge(f"{pid}:reservation:{reservation.get('id', equipment_id)}", f"plan:{pid}", f"equipment:{equipment_id}", "reserves", state="pass", start=reservation.get("start"), end=reservation.get("end"), provenance="计划预约")
        for equipment_id in used_equipment:
            equipment = equipment_by_id.get(equipment_id)
            if not equipment:
                continue
            add_node(f"equipment:{equipment_id}", "equipment", equipment.get("name", equipment_id), equipmentId=equipment_id, labId=equipment.get("labId"), kind=equipment.get("kind"), state=equipment.get("status"))
            for document in documents:
                if document.get("equipmentId") != equipment_id:
                    continue
                did = f"document:{document['id']}"
                add_node(did, "document", document.get("name", document["id"]), documentId=document["id"], equipmentId=equipment_id, state=document.get("status"), status=document.get("status"), validFrom=document.get("validFrom"), validUntil=document.get("validUntil"), source=document.get("source"), sourceType=document.get("sourceType"), sourceLocator=document.get("sourceLocator"), capturedAt=document.get("capturedAt"))
                add_edge(f"{equipment_id}:document:{document['id']}", f"equipment:{equipment_id}", did, "evidence", status=document.get("status"), specVersion=document.get("specVersion"), provenance=document.get("source") or document.get("sourceType"))
        for task in tasks:
            if task.get("planId") != pid:
                continue
            tid = f"task:{task['id']}"
            add_node(tid, "task", task.get("title", task["id"]), taskId=task["id"], planId=pid, equipmentId=task.get("equipmentId"), state=task.get("status"), dueAt=task.get("dueAt"))
            add_edge(f"{pid}:task:{task['id']}", f"plan:{pid}", tid, "action", state=task.get("status"), provenance="工作区任务")
            if task.get("equipmentId"):
                add_edge(f"{task['id']}:equipment", tid, f"equipment:{task['equipmentId']}", "targets", state="pass", provenance="任务关联字段")
        for check in all_checks:
            if check.get("planId") != pid:
                continue
            cid = f"check:{check['id']}"
            add_node(cid, "check", check.get("title", check["id"]), checkId=check["id"], planId=pid, equipmentId=check.get("equipmentId"), state=check.get("state"), code=check.get("code"), sourceLine=check.get("line"))
            add_edge(f"{pid}:check:{check['id']}", f"plan:{pid}", cid, "evaluates", state=check.get("state"), code=check.get("code"), sourceLine=check.get("line"), provenance="规则核验快照")
            if check.get("equipmentId"):
                add_edge(f"{check['id']}:equipment", cid, f"equipment:{check['equipmentId']}", "evaluates", state=check.get("state"), provenance="规则核验对象")

    if nodeId:
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge["from"], set()).add(edge["to"])
            adjacency.setdefault(edge["to"], set()).add(edge["from"])
        if nodeId not in nodes:
            raise HTTPException(404, "关系图对象不存在。")
        visible = {nodeId}
        frontier = {nodeId}
        for _ in range(hops):
            frontier = {linked for item in frontier for linked in adjacency.get(item, set())} - visible
            visible.update(frontier)
        nodes = {key: value for key, value in nodes.items() if key in visible}
    if allowed_types:
        nodes = {key: value for key, value in nodes.items() if value["type"] in allowed_types}
    visible_ids = set(nodes)
    edges = [edge for edge in edges if edge["from"] in visible_ids and edge["to"] in visible_ids]
    return {"revision": w.get("revision", 0), "planId": planId, "labId": labId, "nodes": list(nodes.values()), "edges": edges, "filters": {"types": sorted(allowed_types), "nodeId": nodeId, "dateFrom": dateFrom, "dateTo": dateTo, "hops": hops, "labId": labId}}

@router.post("/actions")
def mutate_workspace(body: Mutation, actor: str = Depends(local_owner)):
    role = local_role()
    if body.type in {"approve", "approval_decision"} and role not in {"safety_owner", "ehs_manager", "administrator"}:
        raise HTTPException(403, "当前工作区身份没有记录正式复核的权限。")
    handoff_update = body.type == "update_task" and any(key in body.payload for key in ("newOwner", "expectedOwner", "handoffNote"))
    if (body.type == "assign_task" or handoff_update) and local_role() not in {"instructor", "safety_owner", "ehs_manager", "administrator"}:
        raise HTTPException(403, "当前工作区身份没有转交协作任务的权限。")
    try:
        payload = dict(body.payload)
        if body.type in {"approve", "approval_decision"}:
            payload["_serverRole"] = role
        return envelope(store().mutate(body.expectedRevision, body.requestId, body.type, payload, actor))
    except (ValidationError, ValueError, KeyError, TypeError) as error:
        message = str(error) if not isinstance(error, ValidationError) else "输入结构不符合工作区契约。"
        raise HTTPException(422, message) from error

@router.get("/export")
def export_workspace(actor: str = Depends(local_owner)):
    w = store().read()
    return {"exportedAt": now(), "scope": "资源与证据审查记录，不是安全证书", "sha256": hashlib.sha256(canonical(w).encode()).hexdigest(), **envelope(w)}

@router.post("/restore")
def restore_workspace(body: RestoreRequest, actor: str = Depends(local_owner)):
    """Restore a validated browser export with a durable rollback point.

    This endpoint is intentionally role-gated and never trusts the imported
    revision.  The current server payload is snapshotted before replacement;
    a stale browser receives 409 instead of overwriting newer work.
    """
    if local_role() not in {"safety_owner", "ehs_manager", "administrator"}:
        raise HTTPException(403, "当前工作区身份没有恢复服务端存档的权限。")
    try:
        restored = store().restore(expected_revision=body.expectedRevision, request_id=body.requestId, candidate=body.workspace, actor=actor)
        return envelope(restored)
    except (ValidationError, ValueError, KeyError, TypeError) as error:
        message = str(error) if not isinstance(error, ValidationError) else "恢复文件结构不符合工作区契约。"
        raise HTTPException(422, message) from error

@router.get("/snapshots")
def list_workspace_snapshots(limit: int = 20, actor: str = Depends(local_owner)):
    return {"snapshots": store().snapshots(limit)}

@router.get("/snapshots/{snapshot_id}")
def get_workspace_snapshot(snapshot_id: str, actor: str = Depends(local_owner)):
    snapshot = store().snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(404, "恢复前快照不存在。")
    return snapshot


@router.post('/import-text')
async def import_text(request: Request, filename: str, actor: str = Depends(local_owner)):
    """Bounded document extraction: never execute document commands or macros."""
    from io import BytesIO
    import zipfile
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, '文件不能超过 8 MB。')
    suffix = Path(filename).suffix.lower()
    try:
        if suffix in {'.txt', '.md'}:
            text = raw.decode('utf-8-sig')
        elif suffix == '.docx':
            from docx import Document as WordDocument
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                if len(archive.infolist()) > 1000 or sum(i.file_size for i in archive.infolist()) > 32 * 1024 * 1024:
                    raise ValueError('文档展开后过大。')
            doc = WordDocument(BytesIO(raw))
            # Preserve paragraph/table order. No unsupported page/line attribution.
            from docx.oxml.ns import qn
            from docx.text.paragraph import Paragraph
            from docx.table import Table
            parts = []
            for element in doc.element.body:
                if element.tag == qn('w:p'):
                    parts.append(Paragraph(element, doc).text)
                elif element.tag == qn('w:tbl'):
                    parts.extend(' | '.join(c.text for c in row.cells) for row in Table(element, doc).rows)
            text = '\n'.join(parts)
        elif suffix == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw), strict=False)
            if reader.is_encrypted:
                raise ValueError('请先移除文档密码。')
            if len(reader.pages) > 100:
                raise ValueError('本次导入最多支持 100 页。')
            text = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
        else:
            raise ValueError('仅支持 TXT、Markdown、DOCX 和带文本层的 PDF。')
        if not text.strip():
            raise ValueError('没有提取到可用文本；扫描件请先转成文本后导入，不自动编造内容。')
        if len(text) > 100000:
            raise ValueError('提取文本超过 100,000 字符，请按实验计划拆分。')
        return {
            'filename': Path(filename).name,
            'text': text,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'sourceType': 'upload',
            'sourceLocator': 'extracted-text-lines',
            'locator': 'extracted-text-lines',
            'capturedAt': now(),
            'contentLength': len(text),
            'note': '原文定位对应提取后文本行；不是 PDF 版面坐标。上传成功不会自动核验或证明适用性。',
        }
    except HTTPException:
        raise
    except ImportError as error:
        raise HTTPException(503, '服务端缺少文档解析依赖，请安装 backend/requirements.txt。') from error
    except Exception as error:
        raise HTTPException(422, f'文件无法提取：{str(error)[:180]}') from error


@router.get('/plans/{plan_id}/analysis/runs')
def list_analysis_runs(plan_id: str, limit: int = 20, actor: str = Depends(local_owner)):
    w = store().read()
    if not any(plan["id"] == plan_id for plan in w["plans"]):
        raise HTTPException(404, '计划不存在。')
    return {"planId": plan_id, "runs": store().analysis_runs(plan_id, limit)}

@router.get('/plans/{plan_id}/evaluations')
def list_evaluation_runs(plan_id: str, limit: int = 20, actor: str = Depends(local_owner)):
    w = store().read()
    if not any(plan["id"] == plan_id for plan in w["plans"]):
        raise HTTPException(404, '计划不存在。')
    return {"planId": plan_id, "evaluations": store().evaluation_runs(plan_id, limit)}

@router.get('/plans/{plan_id}/jobs')
def list_plan_jobs(plan_id: str, limit: int = 20, actor: str = Depends(local_owner)):
    if not any(plan["id"] == plan_id for plan in store().read()["plans"]):
        raise HTTPException(404, '计划不存在。')
    return {"planId": plan_id, "jobs": store().jobs(plan_id, limit)}

@router.get('/jobs/{job_id}')
def get_job(job_id: str, actor: str = Depends(local_owner)):
    job = store().job(job_id)
    if not job:
        raise HTTPException(404, '后台任务不存在。')
    return job


def _run_expiry_background(request_id: str, as_of: str, actor: str) -> None:
    """Execute one queued expiry job in the process-local FastAPI pool."""
    try:
        store().expiry_recheck(request_id=request_id, as_of=as_of, actor=actor)
    except Exception:
        # ``expiry_recheck`` persists failures; background callbacks cannot
        # propagate an exception after the HTTP response has been sent.
        return


@router.post('/expiry/recheck')
def recheck_expiry(body: ExpiryRecheckRequest, background_tasks: BackgroundTasks = None, background: bool = False, actor: str = Depends(local_owner)):
    """Persist a manual expiry/overdue scan for review.

    The endpoint is deliberately explicit about its boundary: it evaluates
    effective evidence windows and task deadlines at ``asOf`` but does not
    pretend that a background Worker, notification channel, or automatic task
    creator is present.  A client may omit ``asOf`` to use the current UTC
    instant; tests and incident reviews should pass a fixed, timezone-aware
    timestamp for reproducibility.
    """
    # FastAPI injects a string actor at request time.  Keeping a concrete
    # fallback makes direct Python calls (used by smoke tools and notebooks)
    # safe as well; a ``Depends`` marker must never leak into persisted JSON.
    if not isinstance(actor, str):
        actor = "本机负责人"
    as_of = body.asOf or now()
    if background:
        try:
            dt(as_of)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, "重检时间必须是带时区的 ISO 时间。") from error
        job_id = f"expiry-recheck:{body.requestId}"
        existing = store().job(job_id)
        if existing:
            context = existing.get("context") or {}
            if context.get("asOf") and dt(context["asOf"]) != dt(as_of):
                raise HTTPException(409, "同一 requestId 不能用于不同的重检时间。")
            if existing["status"] in {"failed", "cancelled"}:
                raise HTTPException(409, f"该重检任务已处于 {existing['status']} 终态，请更换 requestId 重试。")
            return existing
        job = store().begin_job(job_id=job_id, kind="expiry_recheck", plan_id=None,
                                idempotency_key=body.requestId, context={"asOf": as_of})
        if background_tasks is None:
            raise HTTPException(500, "后台任务调度器不可用。")
        background_tasks.add_task(_run_expiry_background, body.requestId, as_of, actor)
        return job
    try:
        return store().expiry_recheck(request_id=body.requestId, as_of=as_of, actor=actor)
    except HTTPException:
        raise
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(500, f"到期重检失败：{type(error).__name__}: {str(error)[:180]}") from error

@router.post('/jobs/{job_id}/cancel')
def cancel_job(job_id: str, actor: str = Depends(local_owner)):
    """Request cancellation for a durable local job.

    Analysis currently runs in the request process, so cancellation can stop
    queued work or prevent a later retry, but it cannot interrupt Python code
    that is already executing.  The state transition is persisted and a
    synchronous handler must still check it before publishing a result.
    """
    if local_role() not in {"safety_owner", "ehs_manager", "administrator"}:
        raise HTTPException(403, "当前工作区身份没有取消分析任务的权限。")
    return store().cancel_job(job_id, reason=f"{actor} 取消任务")


def _run_analysis_sync(plan_id: str, retry: bool = False, actor: str = "本机负责人", job_id_override: str | None = None):
    """Reuse legacy parsing/rules and optional LLM explanation without approval."""
    from .parser import parse_sop
    from .llm import LLMAdapter
    from .models import Review, Evidence, LabStep
    from .rules import ReviewRuleEngine
    w = store().read()
    p = next((p for p in w['plans'] if p['id'] == plan_id), None)
    if p is None:
        raise HTTPException(404, '计划不存在。')
    # A plan revision can have several immutable attempts after a provider
    # timeout or an explicit rerun. Opening Copilot without `retry=true` should
    # show the newest completed attempt for the current revision rather than
    # resurrecting the first (possibly degraded) idempotency record.
    if not retry and job_id_override is None:
        latest = next((run for run in store().analysis_runs(p['id'], 100)
                       if int(run.get('planRevision', -1)) == int(p['revision'])), None)
        if latest:
            run_id = str((latest.get('trace') or {}).get('runId') or '')
            latest_job_id = run_id.removeprefix('copilot:')
            latest_job = store().job(latest_job_id) if latest_job_id else None
            if latest_job and latest_job.get('status') == 'succeeded':
                return {**latest, 'job': latest_job}
    job_id = job_id_override or f"analysis:{p['id']}:v{p['revision']}"
    existing = store().job(job_id)
    if job_id_override is None and retry and existing and existing["status"] in {"failed", "cancelled", "succeeded"}:
        # A retry/rerun is a new durable attempt. Terminal history stays
        # immutable, while the new idempotency key allows the same plan
        # revision to run again after a transient model failure or a provider
        # configuration change. The current plan is never rewritten.
        suffix = "rerun" if existing["status"] == "succeeded" else "retry"
        job_id = f"{job_id}:{suffix}:{str(uuid4())[:8]}"
    job = store().begin_job(job_id=job_id, kind="analysis", plan_id=p['id'], idempotency_key=job_id)
    if job["status"] == "succeeded" and job.get("result"):
        return {**job["result"], "job": job}
    if job["status"] in {"cancelled", "failed"}:
        raise HTTPException(409, f"该分析任务已处于 {job['status']} 终态，请修改计划修订后使用 retry=true 重新发起。")
    store().set_job_running(job_id)
    try:
        parsed = parse_sop(p['source'])
        # Spatial plans already contain reviewer-visible, line-preserving steps.
        # Many institutional SOPs are prose rather than numbered instructions, so
        # the generic parser can legitimately return only its fallback first line.
        # In that case use the plan's confirmed structure for the copilot and rule
        # review instead of pretending the remaining steps do not exist.
        if len(parsed.get('steps', [])) < len(p.get('steps', [])):
            structured_steps = []
            for index, source_step in enumerate(p['steps'], 1):
                text = source_step['text']
                # Re-run the same deterministic parser on the exact source line;
                # do not invent PPE or controls merely because a word suggests a
                # hazard.  A missing control must remain an explicit unknown.
                line_parse = parse_sop(text)
                candidate = line_parse.get('steps', [None])[0]
                if candidate is None:
                    candidate = LabStep(order=index, instruction=text)
                equipment_names = [e['name'] for e in w['equipment'] if e['id'] in source_step.get('equipmentIds', [])]
                structured_steps.append(candidate.model_copy(update={
                    'order': index,
                    'instruction': text,
                    'equipment': sorted(set(candidate.equipment + equipment_names)),
                    'evidence_refs': [f"plan-line-{source_step['line']}"],
                    'document_revision_id': f"planrev-{p['id']}-v{p['revision']}",
                    'source_line': source_step['line'],
                    'source_text_hash': hashlib.sha256(source_step['text'].encode('utf-8')).hexdigest(),
                }))
            parsed['steps'] = structured_steps
            parsed['document_revision_id'] = f"planrev-{p['id']}-v{p['revision']}"
            parsed['ppe'] = sorted({ppe for step in structured_steps for ppe in step.requires_ppe})
            parsed['equipment'] = sorted({item for step in structured_steps for item in step.equipment})
            parsed['ventilation'] = '通风柜' if any(step.ventilation for step in structured_steps) else parsed.get('ventilation')
            parsed['waste_streams'] = sorted({step.waste_stream for step in structured_steps if step.waste_stream})
        adapter = LLMAdapter()
        model_fields = adapter.extract_sop(p['source'])
        parsed, model_used = _merge_model_parse(parsed, model_fields)
        review = Review(id=p['id'], title=p['name'], objective='实验计划辅助文本预审', requester=p['owner'], room=p['labId'],
            sop=p['source'], created_at=now(), updated_at=now(), steps=parsed['steps'], substances=parsed['substances'],
            ppe=parsed['ppe'], equipment=parsed['equipment'], ventilation=parsed['ventilation'], waste_streams=parsed['waste_streams'],
            evidence=[Evidence(**item) for item in parsed['evidence']])
        engine = ReviewRuleEngine()
        evaluation = engine.evaluate(review)
        result = adapter.summarize(review.model_dump(mode='json'), evaluation.model_dump(mode='json'))
        copilot = _copilot_packet(w, p, parsed, evaluation)
        # The trace is intentionally explicit in the response so the UI can show
        # what came from the model, what came from deterministic rules, and what
        # still requires a human decision.  It is metadata, not an approval.
        plan_checks = [item for item in evaluation.results if getattr(item, "rule_id", None)]
        check_counts = {
            "pass": sum(1 for item in plan_checks if item.passed),
            "needs_review": sum(1 for item in plan_checks if not item.passed),
        }
        decision_state = "blocked" if copilot["ruleSummary"]["blocked"] else "needs_review" if copilot["ruleSummary"]["unknown"] else "ready_for_human_review"
        decision_label = {
            "blocked": "存在阻断，安全门保持关闭",
            "needs_review": "存在未知项，需补证后人工复核",
            "ready_for_human_review": "规则范围内未见未满足项，仍需人工复核",
        }[decision_state]
        # This is a provenance ledger for the run, not a claim that the model or
        # public sources certify the experiment.  Keeping the input/output counts
        # next to each stage makes it visible which work was deterministic and
        # which part (if any) came from the configured model.
        trace = {
            # Include the durable job attempt so an explicit rerun of the same
            # plan revision remains a separate immutable history record.
            'runId': f"copilot:{job_id}",
            'generatedAt': now(),
            'stages': [
                {'id': 'understand', 'label': '结构化理解', 'status': 'model' if model_used else 'deterministic', 'detail': f"识别 {len(parsed['steps'])} 个步骤、{len(parsed['substances'])} 个化学品实体", 'inputs': ['计划原文'], 'outputs': ['步骤实体', '化学品实体', '设备语义']},
                {'id': 'check', 'label': '规则核验', 'status': 'rule', 'detail': f"{check_counts['pass']} 项满足，{check_counts['needs_review']} 项待处理", 'inputs': ['结构化步骤', '资源台账', '证据目录'], 'outputs': ['阻断项', '未知项', '规则来源']},
                {'id': 'scenario', 'label': '场景推演', 'status': 'deterministic', 'detail': f"生成 {len(copilot['scenarios'])} 个隔离候选方案", 'inputs': ['阻断项', '未知项', '预约安排'], 'outputs': ['替代资源候选', '先补证候选']},
                {'id': 'review', 'label': '人工复核', 'status': 'required', 'detail': '候选结果需要负责人确认后才可形成计划修订', 'inputs': ['候选结果', '来源与证据'], 'outputs': ['人工意见', '版本化决定']},
            ],
            'model': {'configured': adapter.status()['configured'], 'used': model_used, 'provider': result.provider, 'name': adapter.model or None, 'degradedReason': result.reason},
            'sources': [
                {'kind': 'sop', 'label': '计划原文', 'reference': p['sourceName'], 'detail': f"{len(parsed['steps'])} 个结构化步骤 · 保留原文行号", 'status': 'used'},
                {'kind': 'rules', 'label': '确定性规则包', 'reference': engine.version, 'detail': f"{len(plan_checks)} 条规则结果 · {check_counts['needs_review']} 项待处理", 'status': 'used'},
                {'kind': 'resources', 'label': '资源与证据目录', 'reference': f"{len(w['equipment'])} 台设备 · {len(w['documents'])} 份资料", 'detail': '只依据当前工作区登记，不替代现场核验', 'status': 'used'},
                {'kind': 'model', 'label': '模型解释层', 'reference': adapter.model or '未配置', 'detail': result.reason or '仅生成候选解释；不可自动批准或改写计划', 'status': 'used' if model_used else 'degraded'},
            ],
            'decision': {'state': decision_state, 'label': decision_label, 'approvalRequired': True, 'reason': 'AI 候选和规则结果不能替代机构审批或现场确认。'},
            'source_policy': '所有候选都绑定 SOP 行号、资源检查或证据记录；无法建立来源时保留为待确认。',
        }
        evaluation_record = {
            'evaluationId': uid('evaluation'), 'planId': p['id'], 'planRevision': p['revision'],
            'evaluatedAt': now(), 'basis': basis(w, p), 'status': 'completed',
            'ruleVersion': engine.version, 'results': [r.model_dump(mode='json') for r in evaluation.results],
            'checkCounts': copilot['ruleSummary'], 'decisionState': decision_state,
            'sourceRefs': [p['sourceName'], RULE_PACK],
        }
        response = {'planId': p['id'], 'planRevision': p['revision'], 'ruleVersion': engine.version,
            'parser': 'model-enriched-deterministic-sop-v2' if model_used else 'deterministic-sop-v1', 'provider': result.provider, 'model': adapter.model or None,
            'evaluationId': evaluation_record['evaluationId'], 'degraded': result.provider == 'offline' or result.degraded or not result.available,
            'degradedReason': result.reason,
            'summary': result.text, 'results': [r.model_dump(mode='json') for r in evaluation.results],
            'copilot': copilot,
            'trace': trace,
            'scope': 'AI 负责结构化理解与解释；确定性规则和人工复核负责约束结论。不会自动批准、修改计划或生成事故处置指令。'}
        # A cancellation request can arrive while a synchronous analysis is
        # assembling its result.  Never publish a successful result after the
        # durable job has been cancelled.
        current_job = store().job(job_id)
        if current_job and current_job["status"] == "cancelled":
            raise HTTPException(409, "分析任务已取消，未发布分析结果。")
        store().save_evaluation_run(evaluation_record)
        store().save_analysis_run(response)
        job = store().finish_job(job_id, status="succeeded", result=response)
        return {**response, "job": job}
    except HTTPException:
        current_job = store().job(job_id)
        if current_job and current_job["status"] in {"queued", "running"}:
            store().finish_job(job_id, status="failed", error="分析请求被拒绝或中断。")
        raise
    except Exception as error:
        current_job = store().job(job_id)
        if current_job and current_job["status"] in {"queued", "running"}:
            store().finish_job(job_id, status="failed", error=f"{type(error).__name__}: {str(error)[:500]}")
        raise HTTPException(500, "分析任务失败；请查看任务记录后修改计划或重新发起。") from error


def _prepare_background_analysis(plan_id: str, retry: bool) -> tuple[dict, dict | None, str | None, bool]:
    """Create an idempotent analysis job without doing model work in-request.

    The boolean return value indicates whether this request created the job;
    only the creator may enqueue the process-local runner.  A completed run is
    returned as ``job=None`` so opening Copilot remains read-only/idempotent.
    """
    workspace = store().read()
    plan = next((item for item in workspace["plans"] if item["id"] == plan_id), None)
    if plan is None:
        raise HTTPException(404, "计划不存在。")
    if not retry:
        latest = next((run for run in store().analysis_runs(plan_id, 100)
                       if int(run.get("planRevision", -1)) == int(plan["revision"])), None)
        if latest:
            run_id = str((latest.get("trace") or {}).get("runId") or "")
            latest_job = store().job(run_id.removeprefix("copilot:")) if run_id else None
            if latest_job and latest_job.get("status") == "succeeded":
                return plan, {**latest, "job": latest_job}, None, False
    base_id = f"analysis:{plan_id}:v{plan['revision']}"
    job_id = base_id
    existing = store().job(job_id)
    if retry and existing and existing["status"] in {"failed", "cancelled", "succeeded"}:
        job_id = f"{base_id}:{'rerun' if existing['status'] == 'succeeded' else 'retry'}:{str(uuid4())[:8]}"
        existing = None
    if existing and existing["status"] in {"failed", "cancelled"}:
        raise HTTPException(409, f"该分析任务已处于 {existing['status']} 终态，请修改计划修订后使用 retry=true 重新发起。")
    job = store().begin_job(job_id=job_id, kind="analysis", plan_id=plan_id, idempotency_key=job_id)
    return plan, job, job_id, existing is None


def _run_analysis_background(plan_id: str, job_id: str, actor: str) -> None:
    """Run one durable analysis in FastAPI's process-local background pool.

    This is deliberately not described as a multi-process Worker.  A restart
    marks queued/running rows failed; the browser can inspect the error and
    explicitly retry with a new immutable attempt.
    """
    try:
        # The queued row already owns an immutable attempt ID.  Force the
        # retry path so a completed attempt for the same plan revision cannot
        # short-circuit this worker and leave the newly queued row unfinished.
        _run_analysis_sync(plan_id, retry=True, actor=actor, job_id_override=job_id)
    except Exception:
        # The synchronous runner has already recorded the terminal error.  A
        # background callback must not surface an exception after the response.
        return


@router.post('/plans/{plan_id}/analysis')
def analyze_plan(
    plan_id: str,
    retry: bool = False,
    background: bool = False,
    background_tasks: BackgroundTasks = None,
    actor: str = Depends(local_owner),
):
    """Analyze a plan synchronously or via an explicit process-local job.

    ``background=true`` returns a durable queued job immediately.  It is
    intended for the browser UI to poll; it does not claim a persistent worker
    or survive a process restart.  The default remains synchronous for API
    compatibility and deterministic command-line checks.
    """
    if not background:
        return _run_analysis_sync(plan_id, retry=retry, actor=actor)
    plan, prepared, job_id, created = _prepare_background_analysis(plan_id, retry)
    if job_id is None:
        return prepared
    job = prepared
    if job is None:
        raise HTTPException(500, "分析任务创建失败。")
    if created:
        if background_tasks is None:
            # Direct Python calls are useful in smoke tests and must fail with
            # a meaningful HTTP error rather than an AttributeError.  The
            # actual FastAPI route always injects BackgroundTasks here.
            raise HTTPException(500, "后台任务调度器不可用。")
        background_tasks.add_task(_run_analysis_background, plan_id, job_id, actor)
    return {
        "planId": plan_id,
        "planRevision": plan["revision"],
        "background": True,
        "job": job,
        "scope": "进程内后台执行；服务重启不会伪称任务继续，失败后需显式 retry。",
    }
