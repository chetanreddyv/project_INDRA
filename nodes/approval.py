"""
nodes/approval.py — Human-in-the-Loop approval node.

Uses LangGraph's interrupt() to pause the graph when a write action
is intercepted by the Python approval gate in nodes/agent.py.

Security model
--------------
By the time this node runs, the write action has already been
*blocked* by Python (``WriteActionRequiresApproval`` was raised).
The ``pending_action`` dict contains:

    {
        "action":    str           # tool name, e.g. "send_email"
        "skill":     str           # owning skill, e.g. "google_workspace"
        "tool_args": dict          # exact args the LLM supplied
        "details":   str           # human-readable summary
    }

On approval, the tool is executed programmatically by importing the
real function from the MCP server module and calling it directly.

Resumes with the user's decision from Telegram buttons:
  - "approve" → execute the action via direct function call
  - "reject"  → inform user, no side-effect
  - "edit:<instruction>" → re-run agent with the edit instruction
"""

import logging
from langgraph.types import interrupt

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Tool Dispatcher — programmatic execution of approved actions
# ══════════════════════════════════════════════════════════════

def _get_tool_registry() -> dict:
    """
    Lazily load the global tool registry from the mcp_servers plugin manager.
    Maps tool names to their implementing functions.
    """
    try:
        from mcp_servers import GLOBAL_TOOL_REGISTRY
        return GLOBAL_TOOL_REGISTRY
    except ImportError as e:
        logger.warning(f"Could not load GLOBAL_TOOL_REGISTRY: {e}")
        return {}


def _execute_tool(action_name: str, tool_args: dict) -> str:
    """
    Execute a tool by name with the given arguments.
    Returns the tool's string result or an error message.
    """
    registry = _get_tool_registry()
    func = registry.get(action_name)
    if not func:
        return f"Error: Tool '{action_name}' not found in registry."

    try:
        logger.info(f"  -> Executing {action_name}({tool_args})")
        result = func(**tool_args)
        logger.info(f"  -> {action_name} completed successfully")
        return result
    except Exception as e:
        logger.error(f"  -> {action_name} failed: {e}")
        return f"Error executing {action_name}: {e}"


# ══════════════════════════════════════════════════════════════
# Approval Node
# ══════════════════════════════════════════════════════════════

async def human_approval_node(state: dict) -> dict:
    """
    Pause the graph and wait for human approval via Telegram buttons.

    Flow
    ----
    1. ``interrupt()`` is called with the action details.
    2. LangGraph pauses and saves state to the checkpointer.
    3. FastAPI sends Telegram approval buttons to the user.
    4. User clicks a button → ``Command(resume=decision)`` resumes here.
    5. On approve → call the real tool function programmatically.
    """
    logger.info("--- [Node: Human Approval] ---")
    pending = state.get("pending_action", {})

    if not pending:
        logger.warning("  -> No pending action, skipping approval")
        return {"pending_action": None}

    action_name = pending.get("action", "unknown")
    skill_name = pending.get("skill", "unknown")
    tool_args = pending.get("tool_args", {})

    # Build the interrupt payload — this is what app.py reads to
    # construct the Telegram approval message.
    interrupt_payload = {
        "action": action_name,
        "skill": skill_name,
        "tool_args": tool_args,
        "details": pending.get("details", f"Call **{action_name}**"),
    }

    # ── PAUSE ── LangGraph saves state; resumes when user responds ──
    decision = interrupt(interrupt_payload)
    logger.info(f"  -> Human decision received: {decision}")

    if decision == "approve":
        # ── Execute the real tool programmatically ──────────────────
        result = _execute_tool(action_name, tool_args)
        args_lines = "\n".join(f"  • {k}: {v}" for k, v in tool_args.items())
        response = (
            f"✅ Action Approved & Executed\n\n"
            f"{action_name} completed.\n"
            + (f"\n{args_lines}\n" if args_lines else "")
            + f"\nResult: {result}"
        )
        return {
            "agent_response": response,
            "pending_action": None,
        }

    elif isinstance(decision, str) and decision.startswith("edit:"):
        edit_instruction = decision[5:].strip()
        logger.info(f"  -> User requested edit: {edit_instruction}")
        return {
            "agent_response": None,
            "pending_action": None,
            "user_input": f"Please modify the previous action: {edit_instruction}",
            "_needs_rerun": True,
        }

    else:
        # Rejected (or unknown decision — always safe-fail to reject)
        logger.info(f"  -> Action rejected (decision={decision!r})")
        response = (
            f"❌ Action Rejected\n\n"
            f"{action_name} was not executed.\n\n"
            f"If you'd like me to try a different approach, just let me know."
        )
        return {
            "agent_response": response,
            "pending_action": None,
        }
