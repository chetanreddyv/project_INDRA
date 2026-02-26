from typeguard import check_type
from core.cron_types import CronSchedule, CronPayload

logger = logging.getLogger("mcp.cron_tools")

def cron_add(name: str, schedule_type: str, schedule_value: str, target: str, command: str, delivery_mode: str = "silent") -> str:
    """
    Add a new scheduled cron job.
    
    Args:
        name: A human readable name for the job
        schedule_type: "at" (ISO 8601), "every" (milliseconds as string), or "cron" (e.g. "* * * * *")
        schedule_value: The value for the schedule_type specified
        target: "main" (system_event) or "isolated" (agent_turn)
        command: The instruction for the agent to execute
        delivery_mode: "silent" (no output), "announce" (output to main channels)
    
    Returns:
        The ID of the created job, or an error message.
    """
    try:
        if schedule_type == "at":
            from datetime import datetime
            dt = datetime.fromisoformat(schedule_value.replace("Z", "+00:00"))
            schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
        elif schedule_type == "every":
            schedule = CronSchedule(kind="every", every_ms=int(schedule_value))
        elif schedule_type == "cron":
            schedule = CronSchedule(kind="cron", expr=schedule_value)
        else:
            return f"Invalid schedule_type: {schedule_type}"
            
        job = cron_manager.add_job(
            name=name,
            schedule=schedule,
            message=command,
            deliver=(delivery_mode == "announce"),
            kind="system_event" if target == "main" else "agent_turn"
        )
        return f"Created job '{job.name}' with ID {job.id}"
    except Exception as e:
        logger.error(f"Error adding cron job: {e}")
        return f"Failed to create job: {e}"

def cron_list() -> str:
    """
    List all registered cron jobs.
    """
    jobs = cron_manager.list_jobs()
    if not jobs:
        return "No jobs registered."
    
    out = "Registered Jobs:\n"
    for j in jobs:
        status = j.get("last_status", "pending")
        next_run = j.get("next_run")
        if next_run:
            from datetime import datetime
            next_run_str = datetime.fromtimestamp(next_run / 1000.0).isoformat()
        else:
            next_run_str = "None"
        out += f"- ID: {j['id']} | Name: {j['name']} | Enabled: {j['enabled']} | Schedule: {j['schedule']} | Next: {next_run_str}\n"
    return out

def cron_remove(job_id: str) -> str:
    """
    Remove an existing cron job by ID.
    
    Args:
        job_id: The ID of the job to remove.
    """
    success = cron_manager.remove_job(job_id)
    if success:
        return f"Job {job_id} removed."
    return f"Job {job_id} not found."

TOOL_REGISTRY = {
    "cron_add": cron_add,
    "cron_list": cron_list,
    "cron_remove": cron_remove
}
