# ============================================================
# KLEOS — Background Job Queue (in-memory, async)
# Converted from: src/lib/ai/queue.ts
# ============================================================

import asyncio
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Literal

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


@dataclass
class Job:
    id: str
    agent_id: str
    action: str
    input: dict
    status: JobStatus
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None


class JobQueue:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._listeners: list[Callable[[Job], None]] = []
        self._processing: set[str] = set()

    def submit(self, agent_id: str, action: str, input: dict) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            action=action,
            input=input,
            status="pending",
        )
        self._jobs[job.id] = job
        self._notify_listeners(job)
        # Fire and forget — process async
        asyncio.create_task(self._process_next(job.id))
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def get_jobs_by_agent(self, agent_id: str) -> list[Job]:
        return sorted(
            [j for j in self._jobs.values() if j.agent_id == agent_id],
            key=lambda j: j.created_at,
            reverse=True,
        )

    def get_all_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get_active_jobs(self) -> list[Job]:
        return [j for j in self.get_all_jobs() if j.status in ("pending", "running")]

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.status in ("pending", "running"):
            job.status = "cancelled"
            self._notify_listeners(job)
            return True
        return False

    def on_job_update(self, listener: Callable[[Job], None]) -> Callable:
        self._listeners.append(listener)
        def unsubscribe():
            self._listeners.remove(listener)
        return unsubscribe

    def _notify_listeners(self, job: Job):
        import copy
        for listener in self._listeners:
            listener(copy.copy(job))

    async def _process_next(self, job_id: str):
        job = self._jobs.get(job_id)
        if not job or job_id in self._processing:
            return

        self._processing.add(job_id)
        job.status = "running"
        job.started_at = time.time()
        self._notify_listeners(job)

        try:
            from backend.ai.agents import execute_agent, AgentRequest
            response = await execute_agent(AgentRequest(
                agent_id=job.agent_id,
                action=job.action,
                input=job.input,
            ))
            if response.success:
                job.status = "completed"
                job.result = response.output
            else:
                job.status = "failed"
                job.error = response.error
        except Exception as error:
            job.status = "failed"
            job.error = str(error)
        finally:
            job.completed_at = time.time()
            job.duration_ms = (job.completed_at - (job.started_at or job.created_at)) * 1000
            self._processing.discard(job_id)
            self._notify_listeners(job)


# Singleton
job_queue = JobQueue()
