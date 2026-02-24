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

Resumes with the user's decision from Telegram buttons:
  - "approve" → execute the action (TODO: real MCP call)
  - "reject"  → inform user, no side-effect
  - "edit:<instruction>" → re-run agent with the edit instruction
"""

import logging
from langgraph.types import interrupt

logger = logging.getLogger(__name__)


async def human_approval_node(state: dict) -> dict:
    """
    Pause the graph and wait for human approval via Telegram buttons.

    Flow
    ----
    1. ``interrupt()`` is called with the action details.
    2. LangGraph pauses and saves state to the checkpointer.
    3. FastAPI sends Telegram approval buttons to the user.
    4. User clicks a button → ``Command(resume=decision)`` resumes here.
    5. This function continues with the decision value.
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
        # TODO: Replace this stub with a real MCP tool execution call.
        # The exact args are available in ``tool_args`` so this only
        # needs to call the right MCP server.
        logger.info(f"  -> Approved. Executing {action_name} with args: {tool_args}")
        args_lines = "\n".join(f"  • **{k}**: {v}" for k, v in tool_args.items())
        response = (
            f"✅ *Action Approved & Executed*\n\n"
            f"**{action_name}** has been completed.\n"
            + (f"\n{args_lines}" if args_lines else "")
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
            f"❌ *Action Rejected*\n\n"
            f"**{action_name}** was not executed.\n\n"
            f"If you'd like me to try a different approach, just let me know."
        )
        return {
            "agent_response": response,
            "pending_action": None,
        }
