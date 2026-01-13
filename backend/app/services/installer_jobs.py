import time
from typing import Dict, List, TypedDict, Optional

class Job(TypedDict):
    id: str
    created_at: float
    lines: List[str]
    done: bool

_jobs: Dict[str, Job] = {}

def create_job(job_id: str) -> Job:
    job: Job = {"id": job_id, "created_at": time.time(), "lines": [], "done": False}
    _jobs[job_id] = job
    return job

def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)

def append(job_id: str, line: str) -> None:
    job = _jobs.get(job_id)
    if not job:
        job = create_job(job_id)
    job["lines"].append(line)

def mark_done(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job:
        job["done"] = True
