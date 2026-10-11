"""Durable local Worker for queued AegisLab spatial jobs.

Run from the repository root with ``python -m backend.worker --once`` or
``--loop``.  The API remains browser-first; this optional process only claims
rows that were explicitly queued with ``AEGIS_SPATIAL_JOB_EXECUTION=worker``.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


def _store_path() -> str:
    root = Path(__file__).resolve().parents[1]
    return os.getenv("AEGIS_SPATIAL_DB_PATH", str(root / "aegis-spatial.db"))


def run_once() -> bool:
    # Set the mode before importing the app module so its store does not mark
    # queued/running rows failed as a process-local restart recovery.
    os.environ["AEGIS_SPATIAL_JOB_EXECUTION"] = "worker"
    from backend.app import spatial

    worker_store = spatial.WorkspaceStore(_store_path(), recover_incomplete=False)
    spatial._store = worker_store
    job = worker_store.claim_next_job()
    if not job:
        return False
    try:
        if job["kind"] == "analysis":
            spatial._run_analysis_sync(
                job["planId"], retry=True, actor="后台 Worker", job_id_override=job["jobId"]
            )
        elif job["kind"] == "expiry_recheck":
            as_of = (job.get("context") or {}).get("asOf")
            if not as_of:
                raise ValueError("到期重检任务缺少 asOf 上下文。")
            report = spatial.expiry_recheck_report(
                worker_store.read(), as_of, worker_name="durable-worker"
            )
            report.update({
                "requestId": job["idempotencyKey"],
                "jobId": job["jobId"],
                "generatedAt": spatial.now(),
                "actor": "后台 Worker",
            })
            worker_store.finish_job(job["jobId"], status="succeeded", result=report)
        else:
            worker_store.finish_job(job["jobId"], status="failed", error=f"不支持的任务类型: {job['kind']}")
    except Exception as error:  # the domain runner records its own failures
        current = worker_store.job(job["jobId"])
        if current and current["status"] in {"queued", "running"}:
            worker_store.finish_job(job["jobId"], status="failed", error=f"{type(error).__name__}: {str(error)[:500]}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="AegisLab durable spatial job worker")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="claim and run at most one job")
    group.add_argument("--loop", action="store_true", help="keep polling for queued jobs")
    parser.add_argument("--poll-seconds", type=float, default=1.0, help="poll interval in loop mode")
    args = parser.parse_args()
    if args.loop:
        while True:
            if not run_once():
                time.sleep(max(0.1, args.poll_seconds))
    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
