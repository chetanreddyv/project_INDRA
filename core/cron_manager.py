import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Literal
import uuid

"""Cron types."""

from pydantic import BaseModel as _BaseModel, Field, ConfigDict

try:
    from croniter import croniter
except ImportError:
    croniter = None

logger = logging.getLogger("core.cron_manager")

CRON_DATA_DIR = Path("data/cron")
JOBS_FILE = CRON_DATA_DIR / "jobs.json"
RUNS_DIR = CRON_DATA_DIR / "runs"


class BaseModel(_BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CronSchedule(BaseModel):
    """Schedule definition for a cron job."""
    kind: Literal["at", "every", "cron"]
    # For "at": timestamp in ms
    at_ms: Optional[int] = Field(None, alias="atMs")
    # For "every": interval in ms
    every_ms: Optional[int] = Field(None, alias="everyMs")
    # For "cron": cron expression (e.g. "0 9 * * *")
    expr: Optional[str] = None
    # Timezone for cron expressions
    tz: Optional[str] = None


class CronPayload(BaseModel):
    """What to do when the job runs."""
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    # Deliver response to channel
    deliver: bool = False
    channel: Optional[str] = None  # e.g. "telegram"
    to: Optional[str] = None  # e.g. chat_id


class CronJobState(BaseModel):
    """Runtime state of a job."""
    next_run_at_ms: Optional[int] = Field(None, alias="nextRunAtMs")
    last_run_at_ms: Optional[int] = Field(None, alias="lastRunAtMs")
    last_status: Optional[Literal["ok", "error", "skipped"]] = Field(None, alias="lastStatus")
    last_error: Optional[str] = Field(None, alias="lastError")


class CronJob(BaseModel):
    """A scheduled job."""
    id: str
    name: str
    enabled: bool = True
    schedule: CronSchedule = Field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = Field(default_factory=CronPayload)
    state: CronJobState = Field(default_factory=CronJobState)
    created_at_ms: int = Field(0, alias="createdAtMs")
    updated_at_ms: int = Field(0, alias="updatedAtMs")
    delete_after_run: bool = Field(False, alias="deleteAfterRun")


class CronStore(BaseModel):
    """Persistent store for cron jobs."""
    version: int = 1
    jobs: list[CronJob] = Field(default_factory=list)

def _now_ms() -> int:
    return int(time.time() * 1000)

def _compute_next_run(schedule: CronSchedule, now_ms: int) -> Optional[int]:
    """Compute the next expected run time in ms."""
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None
        
    elif schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        return now_ms + schedule.every_ms
            
    elif schedule.kind == "cron" and schedule.expr:
        if croniter is None:
            logger.error("croniter is not installed, cannot schedule cron job.")
            return None
            
        try:
            base_time = now_ms / 1000.0
            
            if schedule.tz:
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(schedule.tz)
                except Exception:
                    # Fallback to local time if invalid ZoneInfo
                    tz = datetime.now().astimezone().tzinfo
            else:
                tz = datetime.now().astimezone().tzinfo

            base_dt = datetime.fromtimestamp(base_time, tz=tz)
            cron = croniter(schedule.expr, base_dt)
            next_dt = cron.get_next(datetime)
            return int(next_dt.timestamp() * 1000)
        except Exception as e:
            logger.error(f"Invalid cron expression: {e}")
            return None
    return None

def _apply_backoff(job: CronJob) -> None:
    """Apply exponential backoff on failure."""
    # Assuming failure count can be deduced or stored if needed, 
    # but the structure given doesn't have an explicit failure_count field.
    # We will use a standard 30s backoff for simplicity.
    backoff_ms = 30000 
    job.state.next_run_at_ms = _now_ms() + backoff_ms
    logger.warning(f"Job {job.id} failed. Applying backoff. Next run: {job.state.next_run_at_ms}")

def _complete_run(job: CronJob, success: bool, start_ms: int) -> None:
    job.state.last_run_at_ms = start_ms
    job.updated_at_ms = _now_ms()
    
    if success:
        job.state.last_status = "ok"
        job.state.last_error = None
        if job.schedule.kind == "at":
            if job.delete_after_run:
                job.enabled = False # Manager will handle deletion
            else:
                job.enabled = False
                job.state.next_run_at_ms = None
        else:
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())
    else:
        job.state.last_status = "error"
        if job.schedule.kind == "at":
            # If one-shot fails, disable it or leave it as error
            job.enabled = False
        else:
            _apply_backoff(job)


class CronManager:
    """Manages scheduling and persistence of cron jobs."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CronManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.jobs: Dict[str, CronJob] = {}
        self.running = False
        self._timer_task: Optional[asyncio.Task] = None
        self._ensure_dirs()
        self.load_jobs()

    def _ensure_dirs(self):
        CRON_DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)

    def load_jobs(self):
        """Load jobs from local JSON file."""
        if not JOBS_FILE.exists():
            return
        
        try:
            with open(JOBS_FILE, "r") as f:
                json_data = f.read()
                store = CronStore.model_validate_json(json_data)
                self.jobs = {job.id: job for job in store.jobs}
            logger.info(f"Loaded {len(self.jobs)} cron jobs.")
        except Exception as e:
            logger.error(f"Failed to load jobs: {e}")

    def save_jobs(self):
        """Save jobs to local JSON file."""
        try:
            store = CronStore(version=1, jobs=list(self.jobs.values()))
            with open(JOBS_FILE, "w") as f:
                f.write(store.model_dump_json(by_alias=True, indent=2))
        except Exception as e:
            logger.error(f"Failed to save jobs: {e}")

    def log_run(self, job_id: str, payload: dict):
        """Log a job execution."""
        log_file = RUNS_DIR / f"{job_id}.jsonl"
        payload["timestamp"] = time.time()
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.error(f"Failed to log run for job {job_id}: {e}")

    def add_job(
        self,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool = False,
        kind: str = "agent_turn",
        delete_after_run: bool = False
    ) -> CronJob:
        now = _now_ms()
        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=name,
            enabled=True,
            schedule=schedule,
            payload=CronPayload(
                kind=kind,
                message=message,
                deliver=deliver
            ),
            state=CronJobState(next_run_at_ms=_compute_next_run(schedule, now)),
            created_at_ms=now,
            updated_at_ms=now,
            delete_after_run=delete_after_run,
        )
        self.jobs[job.id] = job
        self.save_jobs()
        self._arm_timer()
        logger.info(f"Added job {job.name} ({job.id})")
        return job

    def update_job(self, job_id: str, enabled: bool) -> bool:
        if job_id not in self.jobs:
            return False
            
        job = self.jobs[job_id]
        job.enabled = enabled
        job.updated_at_ms = _now_ms()
        if enabled:
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())
        else:
            job.state.next_run_at_ms = None
            
        self.save_jobs()
        self._arm_timer()
        return True

    def remove_job(self, job_id: str) -> bool:
        if job_id in self.jobs:
            del self.jobs[job_id]
            self.save_jobs()
            self._arm_timer()
            return True
        return False

    def list_jobs(self) -> list:
        # Returns a simple dictionary representation for the MCP tool
        res = []
        for j in self.jobs.values():
            schedule_str = f"expr: {j.schedule.expr}" if j.schedule.kind == "cron" else f"every: {j.schedule.every_ms}ms" if j.schedule.kind == "every" else f"at: {j.schedule.at_ms}ms"
            res.append({
                "id": j.id,
                "name": j.name,
                "enabled": j.enabled,
                "schedule": schedule_str,
                "target": j.payload.kind,
                "command": j.payload.message[:50],
                "last_status": j.state.last_status,
                "next_run": j.state.next_run_at_ms
            })
        return res

    async def start(self):
        """Start the cron service."""
        if self.running:
            return
        self.running = True
        # Recompute next runs to ensure we haven't missed anything while closed
        now = _now_ms()
        for job in self.jobs.values():
            if job.enabled:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
        
        self.save_jobs()
        self._arm_timer()
        logger.info(f"Cron manager started with {len(self.jobs)} jobs.")

    async def stop(self):
        """Stop the cron service."""
        self.running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
        logger.info("Cron manager stopped.")

    def _get_next_wake_time(self) -> Optional[float]:
        """Get the earliest next run time across all active jobs."""
        times = [
            j.state.next_run_at_ms for j in self.jobs.values() 
            if j.enabled and j.state.next_run_at_ms
        ]
        return min(times) / 1000.0 if times else None

    def _arm_timer(self):
        """Schedule the next timer tick, Nanobot-style."""
        if self._timer_task:
            self._timer_task.cancel()
        
        if not self.running:
            return

        next_wake = self._get_next_wake_time()
        if not next_wake:
            logger.debug("No active jobs to arm timer for.")
            return
        
        delay = max(0.1, next_wake - time.time())
        
        async def tick():
            try:
                await asyncio.sleep(delay)
                if self.running:
                    await self._on_timer()
            except asyncio.CancelledError:
                pass
        
        self._timer_task = asyncio.create_task(tick())
        logger.debug(f"Cron timer armed: waking in {delay:.2f}s")

    async def _on_timer(self):
        """Handle timer tick - run due jobs."""
        now = _now_ms()
        due_jobs = [
            j for j in self.jobs.values()
            if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms
        ]
        
        for job in due_jobs:
            logger.info(f"Triggering due cron job {job.id}")
            self.log_run(job.id, {"status": "started"})
            # Run in task to avoid blocking other due jobs
            asyncio.create_task(self._execute_job(job))
        
        # We save and re-arm after triggering all due jobs.
        # Note: _execute_job calls save_jobs and _arm_timer too, 
        # but triggered jobs might take time.
        self.save_jobs()
        self._arm_timer()

    async def _execute_job(self, job: CronJob):
        start_ms = _now_ms()
        import core.worker as worker
        from core.lane_manager import lane_manager
        from config.settings import settings
        from core.messaging import SystemEvent
        from nodes.graph import build_graph, checkpointer_context
        
        try:
            chat_id = None
            if settings.allowed_chat_id_list:
                chat_id = settings.allowed_chat_id_list[0]
                
            if not chat_id:
                logger.error("No allowed_chat_id configured, cannot run cron.")
                _complete_run(job, False, start_ms)
                self.save_jobs()
                return

            cron_thread_id = str(chat_id) if job.payload.kind == "system_event" else f"cron:{job.id}"
            user_msg = f"[SYSTEM] CRON EVENT:\n{job.payload.message}"
            
            # Use Future to wait for isolated jobs if we need to log their responses
            msg = SystemEvent(
                platform=f"cron_{job.payload.kind}",
                user_id=cron_thread_id,
                text=user_msg,
                deliver=job.payload.deliver
            )
            
            logger.info(f"Running job {job.id} ({job.payload.kind})")
            
            # We must fetch the global graph instance to run it.
            # In a real deployed worker architecture, we might not need to import graph from app
            from app import graph
            
            if not graph:
                 raise Exception("Graph is not initialized. Cannot run cron job.")

            future = await lane_manager.submit(cron_thread_id, worker.system_daemon, graph, msg)
            
            # Wait for the worker to finish the job
            result = await future
            
            if result and "error" in result:
                raise Exception(result["error"])
                
            _complete_run(job, True, start_ms)
            
            # Remove job if it was a one-shot configured to delete
            if job.schedule.kind == "at" and job.delete_after_run:
                self.jobs.pop(job.id, None)

            self.log_run(job.id, {"status": "completed", "response_preview": final_response[:100]})
            self.save_jobs()
            self._arm_timer() # Re-arm for the next occurrence
            
        except Exception as e:
            logger.error(f"Error executing job {job.id}: {e}", exc_info=True)
            job.state.last_error = str(e)
            _complete_run(job, False, start_ms)
            self.log_run(job.id, {"status": "error", "error": str(e)})
            self.save_jobs()
            self._arm_timer() # Re-arm with backoff if it's a recurring job

cron_manager = CronManager()
