import logging
from core.cron_manager import cron_manager

logger = logging.getLogger("mcp.cron_tools")

def cron_add(schedule_type: str, schedule_value: str, target: str, command: str, delivery_mode: str = "silent") -> str:
    """
    Add a new scheduled cron job.
    
    Args:
        schedule_type: "at" (ISO 8601), "every" (milliseconds), or "cron" (e.g. "* * * * *")
        schedule_value: The value for the schedule_type specified
        target: "main" (shares context with main conversation) or "isolated" (fresh context)
        command: The instruction for the agent to execute
        delivery_mode: "silent" (no output), "announce" (output to main channels), or "webhook"
    
    Returns:
        The ID of the created job, or an error message.
    """
    job_data = {
        "schedule_type": schedule_type,
        "schedule_value": schedule_value,
        "target": target,
        "command": command,
        "delivery_mode": delivery_mode
    }
    job_id = cron_manager.add_job(job_data)
    return f"Created job {job_id}"

def cron_list() -> str:
    """
    List all registered cron jobs.
    """
    jobs = cron_manager.list_jobs()
    if not jobs:
        return "No jobs registered."
    
    out = "Registered Jobs:\n"
    for j in jobs:
        out += f"- ID: {j['id']} | Type: {j['schedule_type']} | Value: {j['schedule_value']} | Status: {j['status']}\n"
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
