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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

RULE_PACK = "resource-prerequisites/1.0"
ROOT = Path(__file__).resolve().parents[2]

# The browser scene uses a deliberately small set of semantic resource kinds.
# Keeping their approximate footprint here gives the server enough information
# to place a newly-created resource without making the scene layout part of the
# approval basis.  These are placement hints, not a claim about certified
# equipment dimensions.
EQUIPMENT_FOOTPRINTS: dict[str, tuple[float, float]] = {
    "hood": (3.0, 1.5),
    "bench": (2.4, 1.4),
    "storage": (1.8, 1.2),
    "analyzer": (2.2, 1.8),
    "sink": (1.8, 1.3),
    "waste": (1.4, 1.2),
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

class Equipment(StrictModel):
    id: str
    labId: str
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=180)
    kind: Literal["hood", "bench", "storage", "analyzer", "sink", "waste"]
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

class Task(StrictModel):
    id: str
    title: str = Field(min_length=1, max_length=240)
    planId: str | None
    equipmentId: str | None
    owner: str = Field(min_length=1, max_length=180)
    dueAt: str
    status: Literal["open", "submitted", "done"]
    note: str = Field(max_length=5000)

class Decision(StrictModel):
    id: str
    planId: str
    revision: int
    basis: str
    actor: str
    comment: str = Field(min_length=1, max_length=2000)
    at: str

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
    for d in w["documents"]:
        if d["equipmentId"] is not None and d["equipmentId"] not in equipment:
            raise ValueError("资料关联的设备不存在。")
        interval(d["validFrom"], d["validUntil"])
        if not d["content"].strip() or not d["source"].strip():
            raise ValueError("资料内容和来源为必填项。")
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
    ids = {r["equipmentId"] for r in p["reservations"]}
    excluded = {"x", "z", "rotation", "name", "owner", "description"}
    return canonical(dict(rulePack=RULE_PACK, plan=p,
        equipment=[{k: v for k, v in e.items() if k not in excluded} for e in w["equipment"] if e["id"] in ids],
        documents=[d for d in w["documents"] if d["equipmentId"] in ids],
        otherReservations=[dict(planId=q["id"], **r) for q in w["plans"] if q["id"] != p["id"] and not q["archived"] for r in q["reservations"] if r["equipmentId"] in ids]))


def check_workspace(w: dict) -> list[dict]:
    results: list[dict] = []
    for p in [p for p in w["plans"] if not p["archived"]]:
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
            assigned = [dict(planId=q["id"], **r) for q in w["plans"] if not q["archived"] for r in q["reservations"] if r["equipmentId"] == identifier]
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
                add("EVIDENCE", "pass" if covered else "unknown", f"{e['code']} 的检查证据适用" if covered else f"{e['code']} 缺少适用的检查证据", "对象、规格版本、核验状态与全部使用时段均匹配。" if covered else "需要已核验且覆盖整个使用时段的记录；上传、过期、其他设备的记录都不能代替。", identifier, documents=[d["id"] for d in docs])
    return results


def plan_status(w: dict, p: dict, checks: list[dict]) -> str:
    if p["archived"]:
        return "archived"
    decisions = [d for d in w["decisions"] if d["planId"] == p["id"]]
    decision = decisions[-1] if decisions else None
    if decision and decision["basis"] != basis(w, p):
        return "recheck"
    if not p["steps"] or any(not s["confirmed"] for s in p["steps"]):
        return "draft"
    relevant = [c for c in checks if c["planId"] == p["id"]]
    if any(c["state"] == "blocked" for c in relevant):
        return "blocked"
    if any(c["state"] == "unknown" for c in relevant):
        return "unknown"
    return "approved" if decision else "ready"


def envelope(w: dict) -> dict:
    checks = check_workspace(w)
    return dict(workspace=w, checks=checks, statuses={p["id"]: plan_status(w, p, checks) for p in w["plans"]}, mode="server", rulePack=RULE_PACK, scope="资源时段、台账可用性、检查证据适用性与原文确认；不构成全域化学安全评估或开工许可。")


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
        p["revision"] = previous["revision"] + 1 if previous else 1
        if previous and p["source"] != previous["source"]:
            for s in p["steps"]:
                s["confirmed"] = False
        upsert("plans", p)
        object_id, summary = p["id"], f"保存计划 {p['code']} · v{p['revision']}"
    elif action == "confirm_steps":
        p = get("plans", x["planId"])
        if not p["steps"]:
            raise ValueError("没有可确认的步骤。")
        for s in p["steps"]:
            s["confirmed"] = True
        p["revision"] += 1
        summary = "人工核对原文与全部步骤"
    elif action == "save_document":
        d = copy.deepcopy(x["document"])
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
        upsert("tasks", copy.deepcopy(x["task"]))
        object_id, summary = x["task"]["id"], "创建协作任务"
    elif action == "update_task":
        t = get("tasks", x["id"])
        if x.get("status") not in ("open", "submitted", "done"):
            raise ValueError("任务状态无效。")
        t.update(status=x["status"], note=x.get("note", t["note"]))
        summary = "更新任务进度，不自动改变证据或审批"
    elif action == "save_branch":
        b = copy.deepcopy(x["branch"])
        p = get("plans", b["planId"])
        if p["revision"] != b["baseRevision"] or basis(w, p) != b["baseBasis"]:
            raise ValueError("方案基线已变化，请以当前计划重新创建。")
        candidate = copy.deepcopy(next_w)
        next(q for q in candidate["plans"] if q["id"] == p["id"])["reservations"] = b["reservations"]
        validate_workspace(candidate)
        upsert("branches", b)
        object_id, summary = b["id"], "保存独立候选方案，正式计划未改变"
    elif action == "apply_branch":
        b = get("branches", x["id"])
        p = get("plans", b["planId"])
        if p["revision"] != b["baseRevision"] or basis(w, p) != b["baseBasis"]:
            raise ValueError("方案已过期：计划、资源或证据发生变化，请重新比较。")
        p["reservations"] = copy.deepcopy(b["reservations"])
        p["revision"] += 1
        object_id, summary = p["id"], f"应用方案「{b['name']}」，产生新修订并触发重新复核"
    elif action == "approve":
        p = get("plans", x["planId"])
        if p["revision"] != x.get("expectedPlanRevision") or p["archived"]:
            raise ValueError("计划版本已改变或已归档。")
        if not x.get("comment", "").strip():
            raise ValueError("必须填写人工复核意见。")
        checks = [c for c in check_workspace(next_w) if c["planId"] == p["id"]]
        if not checks or any(c["state"] != "pass" for c in checks):
            raise ValueError("仍有阻断或未知项，不能记录复核通过。")
        next_w["decisions"].append(dict(id=uid("decision"), planId=p["id"], revision=p["revision"], basis=basis(next_w, p), actor=actor, comment=x["comment"], at=now()))
        summary = "记录当前版本的资源前置条件复核；不构成化学安全认证"
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
            """)
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

class Mutation(StrictModel):
    expectedRevision: int = Field(ge=0)
    requestId: str = Field(min_length=8, max_length=128)
    type: str = Field(max_length=60)
    payload: dict

router = APIRouter(prefix="/api/spatial", tags=["web-workspace"])

@router.get("")
def get_workspace(actor: str = Depends(local_owner)):
    return envelope(store().read())

@router.post("/actions")
def mutate_workspace(body: Mutation, actor: str = Depends(local_owner)):
    try:
        return envelope(store().mutate(body.expectedRevision, body.requestId, body.type, body.payload, actor))
    except (ValidationError, ValueError, KeyError, TypeError) as error:
        message = str(error) if not isinstance(error, ValidationError) else "输入结构不符合工作区契约。"
        raise HTTPException(422, message) from error

@router.get("/export")
def export_workspace(actor: str = Depends(local_owner)):
    w = store().read()
    return {"exportedAt": now(), "scope": "资源与证据审查记录，不是安全证书", "sha256": hashlib.sha256(canonical(w).encode()).hexdigest(), **envelope(w)}


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
        return {'filename': Path(filename).name, 'text': text, 'sha256': hashlib.sha256(raw).hexdigest(), 'locator': 'extracted-text-lines', 'note': '原文定位对应提取后文本行；不是 PDF 版面坐标。'}
    except HTTPException:
        raise
    except ImportError as error:
        raise HTTPException(503, '服务端缺少文档解析依赖，请安装 backend/requirements.txt。') from error
    except Exception as error:
        raise HTTPException(422, f'文件无法提取：{str(error)[:180]}') from error


@router.post('/plans/{plan_id}/analysis')
def analyze_plan(plan_id: str, actor: str = Depends(local_owner)):
    """Reuse legacy parsing/rules and optional LLM explanation without approval."""
    from .parser import parse_sop
    from .llm import LLMAdapter
    from .models import Review, Evidence
    from .rules import ReviewRuleEngine
    w = store().read()
    p = next((p for p in w['plans'] if p['id'] == plan_id), None)
    if p is None:
        raise HTTPException(404, '计划不存在。')
    parsed = parse_sop(p['source'])
    review = Review(id=p['id'], title=p['name'], objective='实验计划辅助文本预审', requester=p['owner'], room=p['labId'],
        sop=p['source'], created_at=now(), updated_at=now(), steps=parsed['steps'], substances=parsed['substances'],
        ppe=parsed['ppe'], equipment=parsed['equipment'], ventilation=parsed['ventilation'], waste_streams=parsed['waste_streams'],
        evidence=[Evidence(**item) for item in parsed['evidence']])
    engine = ReviewRuleEngine()
    evaluation = engine.evaluate(review)
    result = LLMAdapter().summarize(review.model_dump(mode='json'), evaluation.model_dump(mode='json'))
    return {'planId': p['id'], 'planRevision': p['revision'], 'inputHash': parsed['input_sha256'], 'ruleVersion': engine.version,
        'parser': 'deterministic-sop-v1', 'provider': result.provider, 'degraded': result.provider == 'offline' or result.degraded or not result.available,
        'summary': result.text, 'results': [r.model_dump(mode='json') for r in evaluation.results],
        'scope': '辅助文本检查和解释，不修改资源状态、证据或人工决策。'}
