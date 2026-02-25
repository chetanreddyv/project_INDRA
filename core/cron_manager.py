import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from croniter import croniter
except ImportError:
    croniter = None

logger = logging.getLogger("core.cron_manager")

CRON_DATA_DIR = Path("data/cron")
JOBS_FILE = CRON_DATA_DIR / "jobs.json"
RUNS_DIR = CRON_DATA_DIR / "runs"


class CronJob:
    """Represents a scheduled job."""
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id", f"job_{int(time.time())}")
        self.schedule_type = data.get("schedule_type", "cron") # 'at', 'every', 'cron'
        self.schedule_value = data.get("schedule_value", "* * * * *")
        self.target = data.get("target", "isolated") # 'main' or 'isolated'
        self.command = data.get("command", "")
        self.delivery_mode = data.get("delivery_mode", "silent") # 'silent', 'announce', 'webhook'
        
        self.status = data.get("status", "active") # 'active', 'paused', 'error', 'completed'
        self.failure_count = data.get("failure_count", 0)
        self.last_run_time = data.get("last_run_time", 0.0)
        self.next_run_time = data.get("next_run_time", 0.0)
        
        # Determine initial next_run_time if active
        if self.status == "active" and self.next_run_time == 0.0:
            self._compute_next_run()

    def _compute_next_run(self):
        """Compute the next expected run time."""
        now = time.time()
        
        if self.schedule_type == "at":
            try:
                dt = datetime.fromisoformat(self.schedule_value.replace("Z", "+00:00"))
                self.next_run_time = dt.timestamp()
            except ValueError:
                logger.error(f"Invalid isoformat for job {self.id}: {self.schedule_value}")
                self.status = "error"
                
        elif self.schedule_type == "every":
            # schedule_value is in milliseconds
            try:
                interval_ms = int(self.schedule_value)
                # If it's a new job, schedule it interval_ms from now
                # Or from last_run_time if available
                base_time = self.last_run_time if self.last_run_time > 0 else now
                self.next_run_time = base_time + (interval_ms / 1000.0)
                if self.next_run_time < now:
                    self.next_run_time = now + (interval_ms / 1000.0) # Catch up
            except ValueError:
                self.status = "error"
                
        elif self.schedule_type == "cron":
            if croniter is None:
                logger.error("croniter is not installed, cannot schedule cron job.")
                self.status = "error"
                return
                
            try:
                base_time = datetime.fromtimestamp(now, tz=timezone.utc)
                cron = croniter(self.schedule_value, base_time)
                self.next_run_time = cron.get_next(float)
            except Exception as e:
                logger.error(f"Invalid cron expression for {self.id}: {e}")
                self.status = "error"

    def apply_backoff(self):
        """Apply exponential backoff on failure."""
        self.failure_count += 1
        backoff_intervals = [30, 60, 300, 900, 3600] # 30s, 1m, 5m, 15m, 60m
        backoff = backoff_intervals[min(self.failure_count - 1, len(backoff_intervals) - 1)]
        self.next_run_time = time.time() + backoff
        logger.warning(f"Job {self.id} failed. Applying backoff of {backoff}s. Next run: {self.next_run_time}")

    def complete_run(self, success: bool):
        if success:
            self.failure_count = 0
            self.last_run_time = time.time()
            if self.schedule_type == "at":
                self.status = "completed"
            else:
                self._compute_next_run()
        else:
            if self.schedule_type == "at":
                self.status = "error"
                self.failure_count += 1
            else:
                self.apply_backoff()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "schedule_type": self.schedule_type,
            "schedule_value": self.schedule_value,
            "target": self.target,
            "command": self.command,
            "delivery_mode": self.delivery_mode,
            "status": self.status,
            "failure_count": self.failure_count,
            "last_run_time": self.last_run_time,
            "next_run_time": self.next_run_time
        }


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
        self._loop_task: Optional[asyncio.Task] = None
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
                jobs_data = json.load(f)
                self.jobs = {
                    j_id: CronJob(j_data) 
                    for j_id, j_data in jobs_data.items()
                }
            logger.info(f"Loaded {len(self.jobs)} cron jobs.")
        except Exception as e:
            logger.error(f"Failed to load jobs: {e}")

    def save_jobs(self):
        """Save jobs to local JSON file."""
        try:
            jobs_data = {j_id: job.to_dict() for j_id, job in self.jobs.items()}
            with open(JOBS_FILE, "w") as f:
                json.dump(jobs_data, f, indent=2)
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

    def add_job(self, job_data: dict) -> str:
        job = CronJob(job_data)
        self.jobs[job.id] = job
        self.save_jobs()
        logger.info(f"Added job {job.id}")
        return job.id

    def update_job(self, job_id: str, updates: dict) -> bool:
        if job_id not in self.jobs:
            return False
            
        job_data = self.jobs[job_id].to_dict()
        job_data.update(updates)
        self.jobs[job_id] = CronJob(job_data)
        self.save_jobs()
        return True

    def remove_job(self, job_id: str) -> bool:
        if job_id in self.jobs:
            del self.jobs[job_id]
            self.save_jobs()
            return True
        return False

    def list_jobs(self) -> list:
        return [job.to_dict() for job in self.jobs.values()]

    async def start(self):
        """Start the background checking loop."""
        if self.running:
            return
        self.running = True
        self._loop_task = asyncio.create_task(self._cron_loop())
        logger.info("Cron manager loop started.")

    async def stop(self):
        """Stop the background checking loop."""
        self.running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        logger.info("Cron manager loop stopped.")

    async def _cron_loop(self):
        """The main loop evaluating job schedules."""
        from core.lane_manager import lane_manager
        from config.settings import settings
        
        while self.running:
            try:
                now = time.time()
                for job in list(self.jobs.values()):
                    if job.status == "active" and now >= job.next_run_time:
                        logger.info(f"Triggering cron job {job.id}")
                        self.log_run(job.id, {"status": "started"})
                        
                        # We trigger it via asyncio.create_task to not block the cron loop
                        asyncio.create_task(self._execute_job(job))
                        
                await asyncio.sleep(10) # check every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cron loop error: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _execute_job(self, job: CronJob):
        from app import _run_graph, graph, checkpointer, telegram_client
        from core.lane_manager import lane_manager
        from config.settings import settings
        
        try:
            chat_id = None
            if settings.allowed_chat_id_list:
                chat_id = settings.allowed_chat_id_list[0]
                
            if not chat_id:
                logger.error("No allowed_chat_id configured, cannot run cron.")
                job.complete_run(False)
                self.save_jobs()
                return

            if job.target == "main":
                # Run in main context: mimic a system event
                msg = f"[SYSTEM] HEARTBEAT / CRON:\n{job.command}"
                logger.info(f"Running job {job.id} in MAIN session for {chat_id}")
                await lane_manager.submit(str(chat_id), _run_graph, chat_id, msg)
                final_response = "Sent to main lane"
                
            else: # isolated
                # Run isolated graph
                logger.info(f"Running job {job.id} in ISOLATED session")
                cron_thread_id = f"cron:{job.id}"
                
                # Setup execution in Graph
                config = {"configurable": {"thread_id": cron_thread_id}}
                final_response = "Done!"
                
                # Stream through graph directly, bypassing lane_manager to avoid main lane
                async for event in graph.astream(
                    {
                        "chat_id": cron_thread_id,
                        "user_input": f"[SYSTEM] CRON ISOLATED TASK:\n{job.command}",
                        "tool_failure_count": 0,
                    },
                    config=config,
                    stream_mode="updates"
                ):
                    pass
                
                state = await graph.aget_state(config)
                if state.next:
                    # Job paused for human approval. We cannot ask for approval in a background task
                    # without notifying the user, or maybe it notifies them via usual flow?
                    # The isolated graph will just sit paused. 
                    # If we wanted to, we could simulate an interrupt message.
                    logger.warning(f"Isolated job {job.id} paused for human approval.")
                    final_response = "Paused for approval."
                else:
                    final_response = state.values.get("agent_response", final_response)
                    if final_response is None:
                        final_response = "Done! (No response)"
                
                # Delivery
                if job.delivery_mode == "announce":
                    await telegram_client.send_message(
                        chat_id=chat_id, 
                        text=f"🔔 *Cron Job Completed* (`{job.id}`):\n\n{final_response}"
                    )
                elif job.delivery_mode == "webhook":
                    logger.info(f"Cron webhook delivery not fully implemented yet for {job.id}")
                    # In a real implementation we'd do a POST request
            
            job.complete_run(True)
            self.log_run(job.id, {"status": "completed", "response_preview": final_response[:100]})
            self.save_jobs()
            
        except Exception as e:
            logger.error(f"Error executing job {job.id}: {e}", exc_info=True)
            job.complete_run(False)
            self.log_run(job.id, {"status": "error", "error": str(e)})
            self.save_jobs()

cron_manager = CronManager()
